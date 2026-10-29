"""Offline, append-only reconciliation of a completed draft extraction.

This module has no provider dependency. Source interpretations stay unapproved;
published snapshots and their decisions are never rewritten by these rules.
"""
from copy import deepcopy
from datetime import timezone
import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, func

from .clause_rules import reconcile_clause, procedural_candidates
from .quantity_rules import quantity_candidates
from .requirement_selection import current_rows
from .models import (Workspace, DocumentVersion, DocumentPage, DocumentAnalysis,
    SourceSpan, RequirementVersion, AnalysisRequirement, TenderSnapshot,
    ExtractionReconciliation, ExtractionBatchCache)

RULES_VERSION = 'source-reconciliation-v1'
CONDITION_KEYS = ('numeric_conditions', 'date_conditions', 'quantity_conditions',
                  'temporal_conditions', 'advisory_conditions')
META_KEYS = ('excerpt', 'confidence', 'obligation_quote', 'source_context',
             'quantity_references', 'quantity_conflict', 'disposition',
             'previous_model_review_reasons', 'review_reasons', 'reconciliation',
             'unresolved_interpretations', 'merged_into_requirement_key')


def fingerprint(rows, pages):
    payload = {'rules': RULES_VERSION, 'pages': pages,
        'requirements': sorted([(r.id, r.statement, r.condition) for r, _ in rows], key=lambda x: x[0])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def flat(req, span):
    return {**deepcopy(req.condition), 'id': req.id, 'text': req.statement,
        'page': span.page, 'category': req.category, 'obligation': req.obligation,
        'excerpt': req.condition.get('excerpt', req.statement)}


def grounded_conditions(req, span, key):
    return [{**c, 'source_document_id': span.document_version_id, 'page': span.page,
        'source_url': f'/workspaces/{req.workspace_id}/documents/{span.document_version_id}/file#page={span.page}'}
        for c in req.condition.get(key, []) if c.get('quote') and c['quote'] in span.text]


def audit_view(record, changes=True):
    if record is None:
        return None
    created = record.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {**record.summary, 'revision': record.revision, 'created_at': created.isoformat(),
            **({'changes': record.changes} if changes else {})}


def latest_reconciliation(db, wid, did):
    return db.scalar(select(ExtractionReconciliation).where(
        ExtractionReconciliation.workspace_id == wid, ExtractionReconciliation.document_version_id == did)
        .order_by(ExtractionReconciliation.revision.desc()).limit(1))


def validate_proposal(proposal, pages, spans, wid, did):
    """Bind only exact quotations and recorded page offsets to source URLs."""
    p = deepcopy(proposal)
    page = pages.get(p.get('page'), '')
    excerpt = p.get('excerpt', p['text'])
    span = next((s for s in spans if s.page == p['page'] and excerpt in s.text), None)
    if not excerpt or p['text'] not in excerpt or excerpt not in page:
        raise HTTPException(422, 'Correction could not be grounded in its source page; review manually.')
    if span is None:
        start = page.find(excerpt)
        if page.find(excerpt, start + 1) >= 0:
            raise HTTPException(422, 'Repeated source passage has ambiguous offsets; review manually.')
        span = SourceSpan(workspace_id=wid, document_version_id=did, page=p['page'],
            start_offset=start, end_offset=start + len(excerpt), text=excerpt)
    for key in CONDITION_KEYS:
        for c in p.get(key, []):
            quote = c.get('quote', '')
            if not quote or quote not in excerpt:
                raise HTTPException(422, 'A corrected condition is not supported by its source excerpt.')
            for field in ('value_text', 'unit_text', 'boundary_text', 'event_text', 'period_text', 'frequency_text'):
                if c.get(field) and c[field] not in quote:
                    raise HTTPException(422, 'A corrected value is not literal source text; review manually.')
            if c.get('value_start_offset') is not None and page[c['value_start_offset']:c['value_end_offset']] != c.get('value_text'):
                raise HTTPException(422, 'Quantity cell offsets do not match the source.')
    for key in ('source_context', 'quantity_references'):
        for ref in p.get(key, []):
            text = pages.get(ref.get('page'), '')
            if not ref.get('text') or text[ref.get('start_offset', 0):ref.get('end_offset', 0)] != ref['text']:
                raise HTTPException(422, 'Source context offsets do not match the document.')
            ref.update(source_document_id=did,
                source_url=f'/workspaces/{wid}/documents/{did}/file#page={ref["page"]}')
    for ref in p.get('reconciliation', {}).get('evidence', []):
        if pages.get(ref.get('page'), '')[ref.get('start_offset', 0):ref.get('end_offset', 0)] != ref.get('text'):
            raise HTTPException(422, 'Correction audit reference does not match the document.')
    return p, span


def reconcile_document(db, wid, did, *, commit=True):
    wid, did = str(wid), str(did)
    workspace = db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    document = db.scalar(select(DocumentVersion).where(DocumentVersion.workspace_id == wid, DocumentVersion.id == did))
    if workspace is None or workspace.deleted_at is not None or document is None:
        raise HTTPException(404, 'Document not found in this workspace.')
    if document.kind not in {'tender', 'amendment'}:
        raise HTTPException(422, 'Reconciliation applies only to tender requirements.')
    if db.scalar(select(TenderSnapshot.id).where(TenderSnapshot.workspace_id == wid, TenderSnapshot.document_version_id == did)):
        raise HTTPException(409, 'Published tender history is immutable. Upload a revised tender for new interpretation.')
    analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.workspace_id == wid, DocumentAnalysis.document_version_id == did))
    if analysis is None or analysis.status != 'succeeded':
        raise HTTPException(409, 'Complete extraction before reconciling cached results.')
    page_list = [{'page': p.page, 'text': p.text} for p in db.scalars(select(DocumentPage).where(
        DocumentPage.workspace_id == wid, DocumentPage.document_version_id == did).order_by(DocumentPage.page))]
    pages = {p['page']: p['text'] for p in page_list}
    spans = list(db.scalars(select(SourceSpan).where(SourceSpan.workspace_id == wid, SourceSpan.document_version_id == did)))
    rows = current_rows(db, wid, did, include_reference=True)
    before = fingerprint(rows, page_list)
    previous = latest_reconciliation(db, wid, did)
    if previous and previous.output_fingerprint == before:
        return previous
    proposals = []
    canonical = {}
    for r, s in rows:
        if r.condition.get('disposition') not in {'reference', 'duplicate'}:
            scope = tuple(c['text'] for c in r.condition.get('source_context', []) if c['kind'] == 'product_scope')
            canonical.setdefault((s.page, r.statement, scope), r.requirement_key)
    for req, span in rows:
        if req.condition.get('disposition') in {'reference', 'duplicate'}:
            continue
        if req.condition.get('provenance') not in {'nemotron_extraction', 'deterministic_source_reconciliation'}:
            continue  # Explicit human transcriptions are not silently reinterpreted.
        proposal = reconcile_clause(flat(req, span), pages)
        if proposal is None:
            continue
        scope = tuple(c['text'] for c in proposal.get('source_context', []) if c['kind'] == 'product_scope')
        identity = (proposal['page'], proposal['text'], scope)
        if identity in canonical and canonical[identity] != req.requirement_key:
            proposal['disposition'] = 'duplicate'
            proposal['merged_into_requirement_key'] = canonical[identity]
            proposal['review_reasons'].append('Overlapping fragments were consolidated into the same complete source clause; original versions remain in history.')
        else:
            canonical[identity] = req.requirement_key
        proposals.append((req, proposal))
    existing = {(s.page, r.statement): (r, s) for r, s in rows
                if r.condition.get('disposition') not in {'reference', 'duplicate'}}
    for candidate in [*quantity_candidates(page_list), *procedural_candidates(pages)]:
        match = existing.get((candidate['page'], candidate['text']))
        if match and 'quantity_conditions' in candidate:
            old, span = match
            if (old.condition.get('provenance') in {'nemotron_extraction', 'deterministic_source_reconciliation'}
                    and any(old.condition.get(k) != candidate.get(k) for k in
                            ('quantity_conditions', 'quantity_conflict'))):
                proposal = {**flat(old, span), **candidate,
                    'previous_model_review_reasons': old.condition.get('previous_model_review_reasons', old.condition.get('review_reasons', []))}
                proposals = [(r, p) for r, p in proposals if r is None or r.id != old.id]
                proposals.append((old, proposal))
        elif match is None:
            proposals.append((None, candidate))
    summary = {'added': 0, 'modified': 0, 'reference': 0, 'unchanged': len(rows), 'provider_calls': 0,
        'cached_batches': db.scalar(select(func.count()).select_from(ExtractionBatchCache).where(
            ExtractionBatchCache.workspace_id == wid, ExtractionBatchCache.analysis_id == analysis.id))}
    changes = []
    for old, proposal in proposals:
        p, span = validate_proposal(proposal, pages, spans, wid, did)
        if span.id is None:
            db.add(span); db.flush(); spans.append(span)
        condition = deepcopy(old.condition) if old else {}
        for key in (*CONDITION_KEYS, *META_KEYS):
            if key in p:
                condition[key] = p[key]
        condition.update(provenance='deterministic_source_reconciliation',
            review_status='awaiting_review', requires_human_review=True, reconciliation_version=RULES_VERSION)
        condition.setdefault('excerpt', p['text'])
        condition.setdefault('reconciliation', {'method': RULES_VERSION, 'rules': ['explicit_quantity_table'],
            'evidence': [{'page': span.page, 'text': p['text'], 'start_offset': pages[span.page].index(p['text']),
                          'end_offset': pages[span.page].index(p['text']) + len(p['text'])}]})
        new = RequirementVersion(workspace_id=wid, requirement_key=old.requirement_key if old else str(uuid4()),
            version=old.version + 1 if old else 1, supersedes_id=old.id if old else None,
            source_span_id=span.id, statement=p['text'], category=p['category'], obligation=p['obligation'], condition=condition)
        db.add(new); db.flush()
        db.add(AnalysisRequirement(workspace_id=wid, analysis_id=analysis.id, requirement_version_id=new.id))
        action = 'reference' if condition.get('disposition') in {'reference', 'duplicate'} else 'modified' if old else 'added'
        summary[action] += 1
        summary['unchanged'] -= int(old is not None)
        changes.append({'previous_requirement_id': old.id if old else None, 'requirement_id': new.id,
            'action': action, 'page': span.page, 'text': new.statement,
            'previous_text': old.statement if old else None,
            'reason': ' '.join(condition.get('review_reasons', [])),
            'source_url': f'/workspaces/{wid}/documents/{did}/file#page={span.page}'})
    db.flush()
    record = ExtractionReconciliation(workspace_id=wid, analysis_id=analysis.id, document_version_id=did,
        revision=previous.revision + 1 if previous else 1, rules_version=RULES_VERSION,
        input_fingerprint=before, output_fingerprint=fingerprint(current_rows(db, wid, did, include_reference=True), page_list),
        summary=summary, changes=changes)
    db.add(record); db.flush()
    if commit:
        db.commit()
    return record
