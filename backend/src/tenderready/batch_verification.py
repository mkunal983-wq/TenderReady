"""Run existing source-grounded checks without granting human approval.

This is a bounded synchronous operation on the current tender only. Fresh
assessments are reused, and every new assessment is appended by verification.py.
There are no provider calls or inferred coverage confirmations in this path.
"""
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update

from . import amendments
from .procedural_tasks import prepare_task
from .models import Assessment, DocumentVersion, Workspace
from .verification import Strict, VerifyInput, assessment_view, verify, planning_update_needed


class BulkVerifyInput(Strict):
    """No client-selected requirements, check results, or approval fields."""


def verify_all(db, wid):
    # An UPDATE with unchanged values takes a write lock on SQLite as well as
    # PostgreSQL. Serializing before reading results makes repeated/concurrent
    # submissions reuse the same assessments, without changing workspace data.
    locked = db.execute(update(Workspace).where(
        Workspace.id == wid, Workspace.deleted_at.is_(None)
    ).values(revision=Workspace.revision)).rowcount
    if not locked:
        raise HTTPException(404, 'Workspace not found.')

    snapshot = amendments.latest_snapshot(db, wid)
    if snapshot:
        requirements = [req for _, req in amendments.members(db, snapshot)]
    else:
        document = db.scalar(select(DocumentVersion).where(
            DocumentVersion.workspace_id == wid,
            DocumentVersion.kind.in_(['tender', 'amendment'])
        ).order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc()).limit(1))
        requirements = amendments.candidates(db, wid, document.id) if document else []

    results = []
    # Components are strictly shorter than their combined clauses.
    for requirement in sorted(requirements, key=lambda req: (len(req.statement), req.id)):
        previous = db.scalar(select(Assessment).where(
            Assessment.workspace_id == wid,
            Assessment.requirement_version_id == requirement.id
        ).order_by(Assessment.created_at.desc(), Assessment.id.desc()).limit(1))
        previous_view = assessment_view(db, previous) if previous else None
        upgrade_plan = previous is not None and planning_update_needed(db, requirement, previous)
        if previous_view and not previous_view['stale'] and not upgrade_plan:
            prepare_task(db, requirement, previous.id)
            results.append({'requirement_id': requirement.id, 'assessment_id': previous.id,
                'outcome': 'skipped', 'status': previous_view['status'],
                'reason': 'The latest check is still current. Its result and reviews were kept.'})
            continue

        try:
            # Keep user-defined checks on a stale result. Coverage and final
            # approval must be reviewed again against the replacement evidence.
            context = next((check for check in previous.checks
                if check.get('method') == 'verification_context'), {}) if previous else {}
            payload = VerifyInput(criteria=[] if upgrade_plan else context.get('criteria', []))
            with db.begin_nested():
                current = verify(db, wid, requirement.id, payload, commit=False)
            prepare_task(db, requirement, current['id'])
            results.append({'requirement_id': requirement.id, 'assessment_id': current['id'],
                'outcome': 'checked', 'status': current['status'],
                'reason': 'Document checks saved. Review unclear details and approve results separately.'})
        except (HTTPException, ValidationError) as exc:
            # A bad/source-incompatible suggested rule must not stop unrelated
            # requirements. Never echo validator input or database/provider data.
            reason = str(exc.detail) if isinstance(exc, HTTPException) else 'The suggested checks need a manual review before they can run.'
            results.append({'requirement_id': requirement.id,
                'assessment_id': previous.id if previous else None,
                'outcome': 'failed', 'status': previous_view['status'] if previous_view else 'not_checked',
                'reason': reason})

    # Database/system failures roll back the whole operation through the API
    # session handler. Known row validation failures are isolated by savepoints.
    db.commit()
    return {'total': len(requirements),
            **{key: sum(row['outcome'] == key for row in results) for key in ('checked', 'skipped', 'failed')},
            'provider_calls': 0, 'results': results}
