"""Immutable tender snapshots, deterministic diff and selective check propagation.

Parsing/interpretation and publication are separate. Partial corrigenda carry
omitted requirements forward. Complete replacement omissions require an explicit
coverage attestation. Neither similarity nor an LLM chooses approval invalidation.
"""
import hashlib
import json
import re
import uuid
from copy import deepcopy
from typing import Literal
from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select
from .models import (Workspace, DocumentVersion, SourceSpan, RequirementVersion, DocumentAnalysis,
    AnalysisRequirement, TenderSnapshot, SnapshotRequirement, RequirementChange, Assessment,
    ReviewDecision, ReassessmentImpact, CorrectiveTask)
from .documents import require_document
from .verification import (Strict, Criterion, VerifyInput, propose, normalize, typed, verify,
    assessment_view, record_dependencies)


class SnapshotInput(Strict):
    reviewer: str = Field(min_length=1, max_length=200)
    coverage_confirmed: bool = False


class Mapping(Strict):
    candidate_id: str = Field(min_length=36, max_length=36)
    previous_requirement_id: str = Field(min_length=36, max_length=36)


class Removal(Strict):
    requirement_id: str = Field(min_length=36, max_length=36)
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=5000)


class CompareInput(SnapshotInput):
    mode: Literal['full','delta'] = 'delta'
    mappings: list[Mapping] = Field(default_factory=list, max_length=500)
    removals: list[Removal] = Field(default_factory=list, max_length=500)
    fingerprint: str | None = Field(default=None, min_length=64, max_length=64)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def latest_snapshot(db, wid):
    return db.scalar(select(TenderSnapshot).where(TenderSnapshot.workspace_id == wid).order_by(TenderSnapshot.sequence.desc()).limit(1))


def candidates(db, wid, did):
    return [r for r in db.scalars(select(RequirementVersion).join(SourceSpan,
        RequirementVersion.source_span_id == SourceSpan.id).where(RequirementVersion.workspace_id == wid,
        SourceSpan.document_version_id == did).order_by(RequirementVersion.created_at, RequirementVersion.id))
        if not r.condition.get('canonicalized_from')]


def members(db, snapshot):
    return db.execute(select(SnapshotRequirement, RequirementVersion).join(RequirementVersion,
        SnapshotRequirement.requirement_version_id == RequirementVersion.id).where(SnapshotRequirement.snapshot_id == snapshot.id)).all()


def clause_id_text(text):
    match = re.search(r'^Requirement ID:\s*([A-Za-z0-9_.-]+)\s*$', text, re.M)
    return match[1].casefold() if match else None


def clause_id(req):
    return clause_id_text(req.statement)

def attributes(req):
    criteria = propose(req)
    normalized = []
    try:
        for c in criteria:
            c = Criterion(**c)
            normalized.append((c.field, c.operator, format(typed(c.field, c.expected).normalize(), 'f') if c.field in {'ram_gb','storage_gb','project_value_inr'} else str(typed(c.field, c.expected)), c.evidence_type))
    except ValueError:
        return None
    return sorted(normalized)


def safe_grammar(req):
    """Only these complete line grammars permit automatic check-spec transfer."""
    criteria = propose(req)
    covered = {normalize(c['quote']) for c in criteria}
    lines = [line.strip() for line in req.statement.splitlines() if line.strip()]
    return bool(criteria) and attributes(req) is not None and all(
        re.fullmatch(r'Requirement ID:\s*[A-Za-z0-9_.-]+', line) or
        re.fullmatch(r'Obligation: (?:mandatory|optional)', line) or
        (re.match(r'^(?:Model|Bidder|RAM|Storage|Valid until|Project value|Certificate number):\s*', line, re.I)
         and normalize(line) in covered) for line in lines)


def equivalent(old, new):
    if old.category != new.category or old.obligation != new.obligation:
        return False
    if normalize(old.statement) == normalize(new.statement):
        return True
    return safe_grammar(old) and safe_grammar(new) and attributes(old) == attributes(new)


def source_view(db, req, span_id=None, excerpt=None):
    if req is None: return None
    span = db.get(SourceSpan, span_id or req.source_span_id)
    document = db.get(DocumentVersion, span.document_version_id)
    return {'requirement_id': req.id, 'stable_id': req.requirement_key, 'clause_id': clause_id_text(excerpt or req.statement),
        'version': req.version, 'text': excerpt or req.statement, 'attributes': attributes(req),
        'document_id': document.id, 'filename': document.filename, 'page': span.page,
        'source_url': f'/workspaces/{req.workspace_id}/documents/{document.id}/file#page={span.page}'}


def extract_labelled(db, wid, did):
    db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    doc = require_document(db, wid, did)
    if doc.kind not in {'tender','amendment'}: raise HTTPException(422, 'Tender or amendment document required.')
    if db.scalar(select(TenderSnapshot.id).where(TenderSnapshot.document_version_id == did)):
        raise HTTPException(409, 'This document is already published in an immutable snapshot.')
    analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_version_id == did))
    if analysis is None or analysis.status == 'running': raise HTTPException(409, 'Document is unavailable or being analyzed.')
    existing = candidates(db, wid, did)
    if existing:
        if all(r.condition.get('provenance') == 'deterministic_labelled_extraction' for r in existing):
            return {'count': len(existing), 'method': 'deterministic_labelled_extraction'}
        raise HTTPException(409, 'Requirements already exist; use their reviewed interpretation.')
    rows = []
    ids = set()
    for span in db.scalars(select(SourceSpan).where(SourceSpan.workspace_id == wid, SourceSpan.document_version_id == did)):
        for block in re.finditer(r'^Requirement ID: ([A-Za-z0-9_.-]+)\n((?:(?!Requirement ID:|End requirement\b)[^\n]+\n?)+)', span.text, re.M):
            statement = block[0].rstrip()
            obligations = re.findall(r'^Obligation: (mandatory|optional)$', statement, re.M)
            if len(obligations) > 1:
                raise HTTPException(422, 'Multiple obligation labels require human resolution.')
            req = RequirementVersion(workspace_id=wid, requirement_key=str(uuid.uuid4()), version=1,
                source_span_id=span.id, statement=statement, category='manual_review',
                obligation=obligations[0] if obligations else 'unclear',
                condition={'excerpt': statement, 'confidence': 'deterministic', 'provenance': 'deterministic_labelled_extraction',
                'review_status': 'awaiting_review', 'review_reasons': ['Limited labelled grammar; completeness requires reviewer confirmation.'],
                'numeric_conditions': [], 'date_conditions': []})
            if not safe_grammar(req):
                raise HTTPException(422, 'A labelled block contains unsupported text. Use Nemotron interpretation or exact human transcription.')
            if block[1].casefold() in ids: raise HTTPException(422, 'Duplicate clause IDs require human resolution.')
            ids.add(block[1].casefold()); rows.append(req)
    if not rows: raise HTTPException(422, 'No supported Requirement ID blocks found. Use Nemotron extraction or human transcription.')
    for req in rows:
        db.add(req); db.flush()
        db.add(AnalysisRequirement(workspace_id=wid, analysis_id=analysis.id, requirement_version_id=req.id))
    analysis.status = 'succeeded'; analysis.model = None
    analysis.error_code = None; analysis.error_message = None
    analysis.warnings = ['Deterministic labelled extraction, not Nemotron. Confirm complete coverage before publishing.']
    db.commit()
    return {'count': len(rows), 'method': 'deterministic_labelled_extraction'}


def baseline(db, wid, did, payload):
    workspace = db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    doc = require_document(db, wid, did)
    if latest_snapshot(db, wid): raise HTTPException(409, 'A baseline already exists. Compare this document as a revision.')
    if not payload.coverage_confirmed: raise HTTPException(422, 'Confirm that the extracted requirements cover the complete baseline.')
    rows = candidates(db, wid, did)
    if not rows or doc.kind != 'tender': raise HTTPException(422, 'A tender with extracted requirements is required.')
    ensure_ready(db, did)
    ensure_unique_clause_ids(rows)
    snapshot = TenderSnapshot(workspace_id=wid, document_version_id=did, sequence=1, mode='baseline',
        reviewer=payload.reviewer, fingerprint=digest([r.id for r in rows]))
    db.add(snapshot); db.flush()
    for req in rows:
        db.add(SnapshotRequirement(workspace_id=wid, snapshot_id=snapshot.id, requirement_version_id=req.id,
            source_span_id=req.source_span_id, source_excerpt=req.statement))
        for assessment in db.scalars(select(Assessment).where(Assessment.requirement_version_id == req.id)):
            record_dependencies(db, assessment)
    workspace.revision += 1
    db.commit()
    return snapshot_view(db, snapshot)


def ensure_ready(db, did):
    analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_version_id == did))
    if analysis and analysis.status == 'running': raise HTTPException(409, 'Wait for extraction to finish.')
    # Manual, source-backed transcription is explicitly permitted; the reviewer
    # attests completeness. A failed model job never publishes partial rows.


def ensure_unique_clause_ids(rows):
    ids = [clause_id(r) for r in rows if clause_id(r)]
    if len(ids) != len(set(ids)): raise HTTPException(422, 'Duplicate clause IDs require human resolution.')


def compare(db, wid, did, payload):
    document = require_document(db, wid, did)
    active = latest_snapshot(db, wid)
    if not active: raise HTTPException(409, 'Publish the original tender as a baseline first.')
    if db.scalar(select(TenderSnapshot.id).where(TenderSnapshot.document_version_id == did)):
        raise HTTPException(409, 'This document has already been published.')
    if document.kind not in {'tender','amendment'}: raise HTTPException(422, 'Tender or amendment required.')
    ensure_ready(db, did)
    old_members = members(db, active)
    old = {r.id: r for _, r in old_members}; refs = {r.id: item for item,r in old_members}
    new = {r.id: r for r in candidates(db, wid, did)}
    if not new and not payload.removals: raise HTTPException(422, 'Extract requirements or specify explicit removal evidence first.')
    ensure_unique_clause_ids(list(new.values()))
    used = set(); matched = {}; methods = {}
    for mapping in payload.mappings:
        if mapping.candidate_id not in new or mapping.previous_requirement_id not in old:
            raise HTTPException(422, 'Mapping must reference this document and the active baseline.')
        if mapping.candidate_id in matched or mapping.previous_requirement_id in used:
            raise HTTPException(422, 'Requirement mappings must be one-to-one.')
        matched[mapping.candidate_id] = mapping.previous_requirement_id; used.add(mapping.previous_requirement_id)
        methods[mapping.candidate_id] = 'reviewer_mapping'
    for nid,nreq in new.items():
        if nid in matched: continue
        choices = [oid for oid,oreq in old.items() if oid not in used and clause_id(nreq) and clause_id(nreq) == clause_id_text(refs[oid].source_excerpt)]
        method = 'explicit_clause_id'
        if not choices:
            choices = [oid for oid,oreq in old.items() if oid not in used and not (clause_id(nreq) and clause_id_text(refs[oid].source_excerpt)) and normalize(nreq.statement) == normalize(oreq.statement)]
            method = 'exact_normalized_text'
        if len(choices)>1: raise HTTPException(422, 'Ambiguous match; supply an explicit one-to-one reviewer mapping.')
        if choices:
            matched[nid]=choices[0]; used.add(choices[0]); methods[nid]=method
    explicit_removals = {}
    for removal in payload.removals:
        if removal.requirement_id not in old or removal.requirement_id in used or removal.requirement_id in explicit_removals:
            raise HTTPException(422, 'Removal must reference an unmatched active requirement once.')
        spans = db.scalars(select(SourceSpan).where(SourceSpan.workspace_id == wid, SourceSpan.document_version_id == did, SourceSpan.page == removal.page))
        span = next((s for s in spans if removal.quote in s.text), None)
        if span is None: raise HTTPException(422, 'Removal quotation must occur exactly on the amendment page.')
        known_clause = clause_id_text(refs[removal.requirement_id].source_excerpt)
        if not re.search(r'\b(remove[ds]?|delete[ds]?|withdrawn?|cancelled|omitted)\b', removal.quote, re.I) or (known_clause and known_clause not in removal.quote.casefold()):
            raise HTTPException(422, 'Quote the explicit deletion instruction naming this clause; omissions belong to full replacement mode.')
        explicit_removals[removal.requirement_id] = {'document_id':did, 'filename':document.filename,
            'page':span.page, 'text':removal.quote, 'source_url':f'/workspaces/{wid}/documents/{did}/file#page={span.page}'}
    changes = []
    def entry(classification, before, after, method, removal_ref=None):
        prior_ref = refs[before.id] if before else None
        return {'classification':classification, 'old_id':before.id if before else None,
            'candidate_id':after.id if after else None, 'match_method':method,
            'before':source_view(db,before,prior_ref.source_span_id,prior_ref.source_excerpt) if before else None,
            'after':source_view(db,after) if after else removal_ref,
            'reason': {'Added':'New requirement has no mapped predecessor.', 'Modified':'Requirement attributes or wording changed.',
                'Removed':'Requirement explicitly removed or omitted from a confirmed complete replacement.',
                'Unchanged':'Requirement is unchanged; evidence assessments and approvals are retained.'}[classification]}
    for nid,nreq in new.items():
        before = old.get(matched.get(nid))
        classification = 'Added' if before is None else 'Unchanged' if equivalent(before,nreq) else 'Modified'
        changes.append(entry(classification,before,nreq,methods.get(nid,'unmatched')))
    for oid,oreq in old.items():
        if oid in used: continue
        removed = oid in explicit_removals or payload.mode == 'full'
        change = entry('Removed' if removed else 'Unchanged',oreq,None,'explicit_removal' if oid in explicit_removals else 'full_document_omission' if removed else 'carried_forward',
            explicit_removals.get(oid) or ({'document_id':did,'filename':document.filename,'page':None,'text':'Absent from the complete revised tender; no page is fabricated.','source_url':f'/workspaces/{wid}/documents/{did}/file'} if removed else None))
        if not removed: change['after']=change['before']
        changes.append(change)
    workspace = db.get(Workspace,wid)
    review_ids = list(db.scalars(select(ReviewDecision.id).where(ReviewDecision.workspace_id==wid).order_by(ReviewDecision.id)))
    assessment_ids = list(db.scalars(select(Assessment.id).where(Assessment.workspace_id==wid).order_by(Assessment.id)))
    fingerprint=digest({'snapshot':active.id,'revision':workspace.revision,'changes':changes,'mode':payload.mode,
        'reviews':review_ids,'assessments':assessment_ids})
    return {'base_snapshot_id':active.id,'document_id':did,'mode':payload.mode,'fingerprint':fingerprint,
        'changes':changes,'warnings':['Unmatched clauses are never fuzzily paired. Review all Added/Removed rows; supply a mapping for renamed or renumbered clauses.',
        'Full replacement treats omissions as removals only after explicit coverage confirmation. Delta mode preserves omitted requirements.']}


def transfer_spec(old, new, prior):
    """Transfer only a complete, recognized grammar with identical check shape."""
    if prior is None or old.category != new.category or old.obligation != new.obligation or not safe_grammar(old) or not safe_grammar(new): return None,None
    context = next((c for c in prior.checks if c.get('method')=='verification_context'), {})
    if prior.checks[0].get('method')=='human_correction' or not context.get('coverage_confirmed'): return None,None
    old_spec = context.get('criteria',[]); proposed = propose(new)
    if len(old_spec)!=len(proposed) or len({c['field'] for c in old_spec})!=len(old_spec): return None,None
    lookup={c['field']:c for c in old_spec}
    old_proposed={c['field']:c for c in propose(old)}
    if set(lookup)!=set(old_proposed) or set(lookup)!={c['field'] for c in proposed}: return None,None
    updated=[]; changed=set()
    for c in proposed:
        prior_c=lookup[c['field']]; original=old_proposed[c['field']]
        # Do not override a reviewer's different interpretation of an operator.
        if prior_c['operator']!=original['operator'] or typed(c['field'],prior_c['expected'])!=typed(c['field'],original['expected']): return None,None
        updated.append({**c,'evidence_type':prior_c['evidence_type']})
        if c['operator']!=prior_c['operator'] or typed(c['field'],c['expected'])!=typed(c['field'],prior_c['expected']): changed.add(c['field'])
    if 'model' in changed: changed.update(c['field'] for c in updated); changed.add('product_scope')
    if 'bidder' in changed: changed.add('bidder_identity')
    if changed & {'valid_from','valid_until'}: changed.add('validity')
    return updated,changed


def apply(db, wid, did, payload):
    workspace=db.scalar(select(Workspace).where(Workspace.id==wid).with_for_update())
    existing=db.scalar(select(TenderSnapshot).where(TenderSnapshot.workspace_id==wid,TenderSnapshot.document_version_id==did))
    if existing:
        if payload.fingerprint==existing.fingerprint: return snapshot_view(db,existing)
        raise HTTPException(409,'Document is already published.')
    plan=compare(db,wid,did,payload)
    if not payload.coverage_confirmed: raise HTTPException(422,'Review the complete interpretation, mappings, and omissions before applying.')
    if payload.fingerprint!=plan['fingerprint']: raise HTTPException(409,'Preview is stale. Compare again before applying.')
    base=db.get(TenderSnapshot,plan['base_snapshot_id']); old_refs={r.id:item for item,r in members(db,base)}
    snapshot=TenderSnapshot(workspace_id=wid,document_version_id=did,previous_snapshot_id=base.id,
        sequence=base.sequence+1,mode=payload.mode,reviewer=payload.reviewer,fingerprint=plan['fingerprint'])
    db.add(snapshot); db.flush(); workspace.revision+=1
    for item in plan['changes']:
        old=db.get(RequirementVersion,item['old_id']) if item['old_id'] else None
        candidate=db.get(RequirementVersion,item['candidate_id']) if item['candidate_id'] else None
        classification=item['classification']; current=None
        if classification=='Modified':
            current=RequirementVersion(workspace_id=wid, requirement_key=old.requirement_key,version=old.version+1,
                supersedes_id=old.id,source_span_id=candidate.source_span_id,statement=candidate.statement,
                category=candidate.category,obligation=candidate.obligation,
                condition={**candidate.condition,'canonicalized_from':candidate.id})
            db.add(current); db.flush()
        elif classification=='Added': current=candidate
        elif classification=='Unchanged': current=old
        if current:
            source_id=candidate.source_span_id if candidate else old_refs[old.id].source_span_id
            excerpt=candidate.statement if candidate else old_refs[old.id].source_excerpt
            db.add(SnapshotRequirement(workspace_id=wid,snapshot_id=snapshot.id,requirement_version_id=current.id,
                source_span_id=source_id,source_excerpt=excerpt))
        details=deepcopy(item)
        if current:
            details['current_requirement_id']=current.id; details['stable_id']=current.requirement_key
            if details.get('after'):
                details['after']={**details['after'],'requirement_id':current.id,'stable_id':current.requirement_key,'version':current.version}
        change=RequirementChange(workspace_id=wid,snapshot_id=snapshot.id,old_requirement_id=old.id if old else None,
            new_requirement_id=current.id if current else None,classification=classification,details=details)
        db.add(change); db.flush()
        if classification == 'Added':
            verify(db,wid,current.id,VerifyInput(reviewer=payload.reviewer), commit=False,
                infer_criteria=safe_grammar(current))
        if classification not in {'Modified','Removed'}: continue
        lineage=list(db.scalars(select(RequirementVersion.id).where(RequirementVersion.workspace_id==wid,
            RequirementVersion.requirement_key==old.requirement_key)))
        affected=list(db.scalars(select(Assessment).where(Assessment.workspace_id==wid,
            Assessment.requirement_version_id.in_(lineage)).order_by(Assessment.created_at.desc())))
        prior=next((a for a in affected if a.requirement_version_id==old.id),None)
        result=None
        if classification=='Modified':
            spec,fields=transfer_spec(old,current,prior)
            reuse=prior if spec is not None and not assessment_view(db,prior)['stale'] else None
            if reuse is None: fields=None
            # Unknown prose always receives an inconclusive full recheck; it
            # never inherits a completeness attestation from an earlier clause.
            result=verify(db,wid,current.id,VerifyInput(criteria=[Criterion(**c) for c in spec] if spec is not None else [],
                coverage_confirmed=spec is not None, reviewer=f'Amendment propagation ({payload.reviewer})'),
                commit=False,reuse=reuse,affected_fields=fields,infer_criteria=spec is not None)
        reason=f'{classification}: {old.statement}'+(f' -> {current.statement}' if current else '')+f'. Snapshot {snapshot.sequence}; supporting requirement assumptions changed.'
        for assessment in affected:
            approvals=list(db.scalars(select(ReviewDecision).where(ReviewDecision.assessment_id==assessment.id,
                ReviewDecision.action=='approved').order_by(ReviewDecision.created_at)))
            latest=db.scalar(select(ReviewDecision).where(ReviewDecision.assessment_id==assessment.id).order_by(ReviewDecision.created_at.desc(),ReviewDecision.id.desc()).limit(1))
            if latest and latest.action=='approved':
                db.add(ReviewDecision(workspace_id=wid,assessment_id=assessment.id,action='reopened',reviewer='TenderReady amendment propagation',
                    comment=reason,workspace_revision=workspace.revision))
            db.add(ReassessmentImpact(workspace_id=wid,change_id=change.id,old_assessment_id=assessment.id,
                new_assessment_id=result['id'] if result else None,reason=reason,approval_ids=[a.id for a in approvals]))
        if classification=='Removed' and prior:
            db.add(CorrectiveTask(workspace_id=wid,assessment_id=prior.id,title='Review removed tender requirement',explanation=reason))
    db.commit()
    return snapshot_view(db,snapshot)


def snapshot_view(db,snapshot):
    changes=[]
    for change in db.scalars(select(RequirementChange).where(RequirementChange.snapshot_id==snapshot.id).order_by(RequirementChange.created_at)):
        impacts=[]
        for impact in db.scalars(select(ReassessmentImpact).where(ReassessmentImpact.change_id==change.id)):
            old=db.get(Assessment,impact.old_assessment_id)
            new=db.get(Assessment,impact.new_assessment_id) if impact.new_assessment_id else None
            impacts.append({'old_assessment':assessment_view(db,old),'new_assessment':assessment_view(db,new) if new else None,
                'approval_ids':impact.approval_ids,'reason':impact.reason})
        details=deepcopy(change.details)
        # Canonical foreign keys are authoritative; candidate UUIDs belong only
        # to the draft preview and must not masquerade as stable applied IDs.
        if change.new_requirement_id and details.get('after'):
            canonical=db.get(RequirementVersion,change.new_requirement_id)
            details['after'].update(requirement_id=canonical.id,stable_id=canonical.requirement_key,version=canonical.version)
        changes.append({**details,'id':change.id,'impacts':impacts})
    active=[]
    for item,req in members(db,snapshot):
        latest=db.scalar(select(Assessment).where(Assessment.requirement_version_id==req.id).order_by(Assessment.created_at.desc()).limit(1))
        active.append({**source_view(db,req,item.source_span_id,item.source_excerpt),
            'assessment':assessment_view(db,latest) if latest else None})
    return {'id':snapshot.id,'sequence':snapshot.sequence,'mode':snapshot.mode,'document_id':snapshot.document_version_id,
        'previous_snapshot_id':snapshot.previous_snapshot_id,'reviewer':snapshot.reviewer,
        'requirements':active,'changes':changes}
