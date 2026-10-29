"""Supplier projections and exports. Readiness is derived, never a stored claim."""
import csv
import io
import json
from datetime import date, timezone
from typing import Literal
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from . import amendments
from .check_planning import build_check_plan
from .clause_actions import interpretation_uncertain
from .models import (Workspace, DocumentVersion, Assessment, CorrectiveTask,
                     SourceSpan, TaskEvent, ReviewDecision, RequirementChange, ReassessmentImpact, TenderSnapshot)
from .verification import assessment_view, require_requirement, list_evidence, LABELS

NOTICE = 'Evidence review only. This is not a guarantee of legal eligibility, bid acceptance, document authenticity, or contract award.'
READINESS_LABELS = {'not_checked': 'Not checked', 'action_required': 'Task to complete', 'reference_only': 'Reference information', **LABELS}


def timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def require_workspace(db, wid):
    row = db.get(Workspace, wid)
    if row is None:
        raise HTTPException(404, 'Workspace not found.')
    return row


def effective_status(assessment, obligation):
    reasons = []
    if assessment is None:
        return 'not_checked', ['No evidence assessment has been recorded.']
    status = assessment['status']
    context = next((c for c in assessment.get('checks', []) if c.get('method') == 'verification_context'), {})
    if status == 'missing' and context.get('check_plan', {}).get('coverage') == 'partial':
        status = 'inconclusive'
        reasons.append('Evidence is missing for a prepared check, and other parts of this clause still need interpretation. Missing evidence does not resolve those parts.')
    if assessment.get('dependency_changed'):
        reasons.append('A linked component assessment, source version or reviewer decision changed. Reassess this combined clause; its previous history remains intact.')
    if assessment['stale']:
        reasons.append('Evidence, dates, or tender assumptions changed; rerun verification.')
    if assessment['review_state'] != 'approved':
        reasons.append('The current finding requires human approval; review state: ' + assessment['review_state'] + '.')
    if obligation == 'unclear':
        reasons.append('Mandatory or optional status is unclear; review the tender interpretation.')
    automatic_coverage = any(c.get('method') == 'verification_context' and c.get('automatic_coverage')
        for c in assessment.get('checks', []))
    only_approval_pending = (automatic_coverage and assessment['review_state'] == 'awaiting_review'
        and not assessment['stale'] and obligation != 'unclear')
    if status == 'supported' and reasons and not only_approval_pending:
        status = 'inconclusive'
    findings = [c['rationale'] for c in assessment.get('checks', []) if c.get('outcome') not in {None, 'pass', 'not_applicable'} and c.get('rationale')]
    return status, [assessment['explanation'], *dict.fromkeys(findings), *reasons]


def requirement_row(db, req, member=None):
    source = amendments.source_view(db, req, member.source_span_id if member else None,
                                   member.source_excerpt if member else None)
    latest = db.scalar(select(Assessment).where(Assessment.workspace_id == req.workspace_id,
        Assessment.requirement_version_id == req.id).order_by(Assessment.created_at.desc(), Assessment.id.desc()).limit(1))
    assessment = assessment_view(db, latest) if latest else None
    status, reasons = effective_status(assessment, req.obligation)
    reasons = list(dict.fromkeys([*reasons, *req.condition.get('review_reasons', [])]))
    plan = build_check_plan(req, db.get(SourceSpan, req.source_span_id))
    uncertain = interpretation_uncertain(req.condition)
    literal_next_action = (plan.get('action', {}).get('rule') == 'literal_source_action'
        and not req.condition.get('quantity_conflict')
        and not req.condition.get('unresolved_interpretations')
        and not plan['unhandled'])
    if (assessment and plan['kind'] == 'procedure' and (not uncertain or literal_next_action) and status in {'inconclusive', 'not_checked'}
            and (not assessment or (not assessment['stale'] and assessment['review_state'] not in {'rejected','reopened'}))):
        status = 'action_required'
        reasons.insert(0, 'This is a procedural action. Complete the linked task and retain its completion record. Task completion alone does not approve the bid.')

    # A complete automatic evidence match is distinct from final approval.
    # Pending approval must still block readiness and remain visible in exports.
    unresolved = status != 'supported' or not assessment or assessment['review_state'] != 'approved' or assessment['stale']
    if (plan['kind'] == 'reference' and not uncertain
            and (not assessment or (not assessment['stale'] and assessment['review_state'] not in {'rejected', 'reopened'}))):
        status = 'reference_only'
        unresolved = False
        reasons = ['Tender reference information; no supplier evidence assertion is made.']
    return {**source, 'category': req.category, 'obligation': req.obligation,
            'status': status, 'label': READINESS_LABELS[status], 'assessment': assessment,
            'reasons': reasons, 'unresolved': unresolved,
            'blocking': status != 'reference_only' and ((req.obligation != 'optional' and unresolved) or req.obligation == 'unclear')}


def dashboard(db, wid):
    workspace = require_workspace(db, wid)
    snapshot = amendments.latest_snapshot(db, wid)
    documents = db.scalars(select(DocumentVersion).where(DocumentVersion.workspace_id == wid,
        DocumentVersion.kind.in_(['tender', 'amendment'])).order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc())).all()
    if snapshot:
        rows = [requirement_row(db, req, member) for member, req in amendments.members(db, snapshot)]
    else:
        rows = [requirement_row(db, req) for req in amendments.candidates(db, wid, documents[0].id)] if documents else []
    rows.sort(key=lambda r: (r['filename'], r['page'], r['clause_id'] or r['stable_id']))
    applied = set(db.scalars(select(TenderSnapshot.document_version_id).where(TenderSnapshot.workspace_id == wid)))
    # Any unreviewed upload is a blocker, even if it predates the current snapshot.
    pending = [d.filename for d in documents if d.id not in applied]
    blockers = []
    if not snapshot:
        blockers.append('Publish a reviewed tender baseline before completing evidence review.')
    if not rows:
        blockers.append('No active requirements have been established.')
    if pending:
        blockers.append('Unapplied tender documents require review: ' + ', '.join(pending))
    mandatory_open = sum(r['blocking'] for r in rows)
    if mandatory_open:
        blockers.append(f'{mandatory_open} mandatory or unclassified requirements remain unresolved.')
    if any(r['status'] != 'reference_only' and r['obligation'] == 'optional' and (r['status'] == 'inconclusive' or not r['assessment'] or r['assessment']['review_state'] != 'approved' or r['assessment']['stale']) for r in rows):
        blockers.append('Optional requirements still need human review; record how they will be handled.')
    current_ids = {r['assessment']['id'] for r in rows if r['assessment']}
    blocking_ids = {r['assessment']['id'] for r in rows if r['assessment'] and r['obligation'] != 'optional' and r['status'] != 'reference_only'}
    tasks = [task_view(db, t, current_ids) for t in db.scalars(select(CorrectiveTask).where(
        CorrectiveTask.workspace_id == wid).order_by(CorrectiveTask.created_at.desc(), CorrectiveTask.id.desc()))]
    if any(t['status'] == 'open' and t['assessment_id'] in blocking_ids for t in tasks):
        blockers.append('Open corrective tasks remain on current mandatory or unclassified requirements.')
    return {'workspace_id': wid, 'title': workspace.title, 'supplier_name': workspace.supplier_name,
            'snapshot_sequence': snapshot.sequence if snapshot else None, 'notice': NOTICE,
            'review_complete': not blockers, 'blockers': blockers,
            'counts': {status: sum(r['status'] == status for r in rows) for status in READINESS_LABELS},
            'requirements': rows, 'tasks': tasks, 'pending_documents': pending}


def detail(db, wid, rid):
    req = require_requirement(db, wid, rid)
    snap = amendments.latest_snapshot(db, wid)
    member = next((m for m, r in amendments.members(db, snap) if r.id == rid), None) if snap else None
    return {**requirement_row(db, req, member), 'active': member is not None,
            'history': [assessment_view(db, a) for a in db.scalars(select(Assessment).where(
                Assessment.workspace_id == wid, Assessment.requirement_version_id == rid)
                .order_by(Assessment.created_at.desc(), Assessment.id.desc()))]}


class TaskFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=250)
    explanation: str = Field(min_length=1, max_length=4000)
    priority: Literal['low', 'medium', 'high'] = 'medium'
    due_date: date | None = None
    reviewer: str = Field(min_length=1, max_length=200)
    comment: str = Field(min_length=1, max_length=4000)


class TaskCreate(TaskFields):
    assessment_id: UUID


class TaskUpdate(TaskFields):
    status: Literal['open', 'resolved', 'dismissed']
    expected_revision: int = Field(ge=1)


def task_view(db, task, current_ids=None):
    assessment = db.get(Assessment, task.assessment_id)
    return {'id': task.id, 'assessment_id': task.assessment_id, 'requirement_id': assessment.requirement_version_id,
            'title': task.title, 'explanation': task.explanation, 'priority': task.priority,
            'due_date': task.due_date, 'status': task.status, 'revision': task.revision,
            'created_at': timestamp(task.created_at), 'historical': current_ids is not None and task.assessment_id not in current_ids,
            'history': [{'id': e.id, 'reviewer': e.reviewer, 'comment': e.comment,
                         'changes': e.changes, 'created_at': timestamp(e.created_at)}
                        for e in db.scalars(select(TaskEvent).where(TaskEvent.workspace_id == task.workspace_id,
                            TaskEvent.task_id == task.id).order_by(TaskEvent.created_at, TaskEvent.id))]}


def save_task(db, wid, payload, tid=None):
    require_workspace(db, wid)
    values = payload.model_dump(mode='json', include={'title', 'explanation', 'priority', 'due_date', 'status'})
    if tid:
        task = db.scalar(select(CorrectiveTask).where(CorrectiveTask.workspace_id == wid, CorrectiveTask.id == tid))
        if task is None:
            raise HTTPException(404, 'Task not found in this workspace.')
        before = {key: getattr(task, key) for key in values}
        changed = db.execute(update(CorrectiveTask).where(CorrectiveTask.id == tid,
            CorrectiveTask.workspace_id == wid, CorrectiveTask.revision == payload.expected_revision)
            .values(**values, revision=CorrectiveTask.revision + 1)).rowcount
        if not changed:
            raise HTTPException(409, 'This task changed. Refresh and review the latest version before saving.')
    else:
        assessment = db.scalar(select(Assessment).where(Assessment.workspace_id == wid, Assessment.id == str(payload.assessment_id)))
        if assessment is None:
            raise HTTPException(404, 'Assessment not found in this workspace.')
        task = CorrectiveTask(workspace_id=wid, assessment_id=assessment.id, **values)
        db.add(task)
        db.flush()
        before = None
    db.add(TaskEvent(workspace_id=wid, task_id=task.id, reviewer=payload.reviewer,
        comment=payload.comment, changes={'before': before, 'after': values}))
    db.commit()
    db.refresh(task)
    return task_view(db, task)


def timeline(db, wid, offset=0, limit=50):
    require_workspace(db, wid)
    events = []
    def add(row, kind, title, description, **refs):
        events.append({'id': row.id, 'kind': kind, 'created_at': timestamp(row.created_at),
                       'title': title, 'description': description, **refs})
    def records(model):
        return db.scalars(select(model).where(model.workspace_id == wid))
    for row in records(DocumentVersion):
        add(row, 'document', f'{row.kind.title()} uploaded · v{row.version}', row.filename, document_id=row.id)
    for row in records(TenderSnapshot):
        add(row, 'snapshot', f'Tender snapshot {row.sequence} · {row.mode}', f'Published by {row.reviewer}', document_id=row.document_version_id)
    for row in records(RequirementChange):
        before, after = row.details.get('before'), row.details.get('after')
        description = '\n'.join(f"{label}: {source.get('text', '')} ({source.get('filename', 'document')}, page {source.get('page') or 'not applicable'})"
            for label, source in [('Previous', before), ('Current', after)] if source)
        add(row, 'change', row.classification + ' requirement', description,
            requirement_id=row.new_requirement_id or row.old_requirement_id)
    for row in records(ReassessmentImpact):
        prior = db.get(Assessment, row.old_assessment_id)
        add(row, 'reassessment', 'Assessment reopened', row.reason, assessment_id=row.old_assessment_id, requirement_id=prior.requirement_version_id)
    for row in records(ReviewDecision):
        assessment = db.get(Assessment, row.assessment_id)
        add(row, 'review', f'{row.action.title()} by {row.reviewer}', row.comment,
            assessment_id=row.assessment_id, requirement_id=assessment.requirement_version_id)
    for row in records(Assessment):
        add(row, 'assessment', 'Evidence assessed: ' + LABELS[row.checks[0].get('display_status', row.status) if row.checks else row.status],
            row.explanation, assessment_id=row.id, requirement_id=row.requirement_version_id)
    for row in records(CorrectiveTask):
        first = db.scalar(select(TaskEvent).where(TaskEvent.task_id == row.id).order_by(TaskEvent.created_at, TaskEvent.id).limit(1))
        original = ((first.changes.get('before') or first.changes.get('after') or {}).get('title', row.title)) if first else row.title
        add(row, 'task', 'Corrective task created', original, task_id=row.id)
    for row in records(TaskEvent):
        add(row, 'task_update', f'Task updated by {row.reviewer}', row.comment, task_id=row.task_id, changes=row.changes)
    events.sort(key=lambda e: (e['created_at'], e['id']), reverse=True)
    return {'items': events[offset:offset + limit], 'total': len(events)}


def csv_cell(value):
    value = '' if value is None else str(value)
    # Prevent spreadsheet formula execution, including whitespace-prefixed formulas.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value


def export_csv(db, wid, kind):
    data = dashboard(db, wid)
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    def write(values):
        writer.writerow([csv_cell(v) for v in values])
    if kind == 'compliance-matrix':
        write(['record_type', 'requirement_id', 'version', 'category', 'obligation', 'status', 'unresolved',
               'review', 'tender_document', 'page', 'exact_clause', 'reason', 'evidence_references', 'validation_checks', 'open_tasks', 'review_history'])
        write(['workspace_summary', data['title'], data['snapshot_sequence'], '', '',
               'Evidence review complete' if data['review_complete'] else 'Action required', not data['review_complete'],
               '', '', '', NOTICE, ' | '.join(data['blockers']), '', '', '', ''])
        for r in data['requirements']:
            a = r['assessment'] or {}
            refs = [f"{s.get('filename', s['document_version_id'])} p{s['page']}: {s['quote']}" for c in a.get('checks', []) for s in c.get('sources', [])]
            write(['requirement', r['stable_id'], r['version'], r['category'], r['obligation'], r['label'], r['unresolved'],
                   a.get('review_state', 'not_assessed'), r['filename'], r['page'], r['text'], ' | '.join(r['reasons']),
                   ' | '.join(dict.fromkeys(refs)), json.dumps(a.get('checks', []), ensure_ascii=False),
                   json.dumps([{key: t[key] for key in ('title', 'explanation', 'priority', 'due_date', 'status')} for t in data['tasks'] if t['assessment_id'] == a.get('id') and t['status'] == 'open'], ensure_ascii=False),
                   json.dumps(a.get('reviews', []), ensure_ascii=False)])
    else:
        write(['record_type', 'document_id', 'filename', 'evidence_type', 'sha256', 'requirement_id', 'page', 'exact_excerpt',
               'requirement_status', 'unresolved', 'source_path', 'notice'])
        write(['workspace_summary', '', data['title'], '', '', '', '', '',
               'Evidence review complete' if data['review_complete'] else 'Action required', not data['review_complete'], '', NOTICE + ' ' + ' | '.join(data['blockers'])])
        for doc, entry in list_evidence(db, wid):
            refs = {}
            for r in data['requirements']:
                for check in (r['assessment'] or {}).get('checks', []):
                    for source in check.get('sources', []):
                        if source['document_version_id'] == doc.id:
                            refs[(r['stable_id'], source['fact_id'])] = (r, source)
            if not refs:
                write(['evidence', doc.id, doc.filename, entry.evidence_type, doc.sha256, '', '', '', 'Unlinked evidence', True,
                       f'/workspaces/{wid}/documents/{doc.id}/file', 'Not independently verified; upload alone is not proof.'])
            for r, s in refs.values():
                write(['evidence', doc.id, doc.filename, entry.evidence_type, doc.sha256, r['stable_id'], s['page'], s['quote'],
                       r['label'], r['unresolved'], f'/workspaces/{wid}/documents/{doc.id}/file#page={s["page"]}', 'Not independently verified.'])
    return out.getvalue()
