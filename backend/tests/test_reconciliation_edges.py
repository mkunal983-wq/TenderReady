"""Regression checks for source reconciliation boundaries and existing rows."""
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from tenderready.documents import requirements_response
from tenderready.models import (Workspace, DocumentVersion, DocumentPage, SourceSpan,
    DocumentAnalysis, RequirementVersion, AnalysisRequirement)
from tenderready.quantity_rules import quantity_candidates
from tenderready.reconciliation import reconcile_document
from tenderready.requirement_selection import current_rows


def seed(db, text, statements, split_at=None):
    workspace = Workspace(title='Source boundary test', supplier_name='Synthetic supplier')
    db.add(workspace); db.flush()
    document = DocumentVersion(workspace_id=workspace.id, document_key=str(uuid4()), version=1,
        kind='tender', filename='synthetic.pdf', storage_key='unused.pdf', sha256='0' * 64)
    db.add(document); db.flush()
    db.add(DocumentPage(workspace_id=workspace.id, document_version_id=document.id, page=1, text=text))
    bounds = [0, split_at, len(text)] if split_at is not None else [0, len(text)]
    spans = []
    for start, end in zip(bounds, bounds[1:]):
        span = SourceSpan(workspace_id=workspace.id, document_version_id=document.id, page=1,
            start_offset=start, end_offset=end, text=text[start:end])
        db.add(span); db.flush(); spans.append(span)
    analysis = DocumentAnalysis(workspace_id=workspace.id, document_version_id=document.id,
        status='succeeded', model=None, pages_completed=1)
    db.add(analysis); db.flush()
    rows = []
    for statement in statements:
        span = next(s for s in spans if statement in s.text)
        req = RequirementVersion(workspace_id=workspace.id, requirement_key=str(uuid4()), version=1,
            source_span_id=span.id, statement=statement, category='required_information',
            obligation='unclear', condition={'provenance':'nemotron_extraction',
                'excerpt':statement, 'numeric_conditions':[], 'date_conditions':[],
                'source_context':[], 'review_reasons':['Original model interpretation.']})
        db.add(req); db.flush(); rows.append(req)
        db.add(AnalysisRequirement(workspace_id=workspace.id, analysis_id=analysis.id,
            requirement_version_id=req.id))
    db.commit()
    return workspace.id, document.id, rows, spans


@pytest.mark.parametrize('complete_first', [True, False])
def test_existing_complete_clause_and_fragment_have_one_current_supplier_requirement(database, complete_first):
    _, sessions = database
    first = '5) Bidders are required to download the BOQ and fill white cells (such as'
    rest = 'name of bidder). Do not change other cells or the filename.'
    full = first + '\n' + rest
    page = full + '\n6) Follow the server time.'
    statements = [full, first] if complete_first else [first, full]
    with sessions() as db:
        wid, did, old, _ = seed(db, page, statements)
        original_full = next(r for r in old if r.statement == full)
        original_fragment = next(r for r in old if r.statement == first)
        audit = reconcile_document(db, wid, did)
        rows = current_rows(db, wid, did)
        assert [r.id for r, _ in rows] == [original_full.id]
        archived = [r for r, _ in current_rows(db, wid, did, include_reference=True)
                    if r.condition.get('disposition') == 'duplicate']
        assert len(archived) == 1
        assert archived[0].supersedes_id == original_fragment.id
        assert archived[0].condition['merged_into_requirement_key'] == original_full.requirement_key
        assert archived[0].statement == full
        assert db.get(RequirementVersion, original_fragment.id).statement == first
        assert audit.summary['provider_calls'] == 0
        assert len(requirements_response(db, wid, did)) == 1
        assert reconcile_document(db, wid, did).id == audit.id


def test_same_page_procedure_crossing_storage_span_gets_exact_new_span(database):
    _, sessions = database
    prefix = 'Page introduction.\n' + ('Unrelated text. ' * 660) + '\n'
    first = '5) Bidders are required to download the BOQ and fill white cells (such as'
    rest = 'name of bidder). The filename shall remain unchanged.'
    full = first + '\n' + rest
    page = prefix + full + '\n6) Follow the server time.'
    split = len(prefix) + len(first)
    with sessions() as db:
        wid, did, old, spans = seed(db, page, [first], split_at=split)
        audit = reconcile_document(db, wid, did)
        rows = current_rows(db, wid, did)
        assert len(rows) == 1
        corrected, bound = rows[0]
        assert corrected.statement == full and corrected.supersedes_id == old[0].id
        assert bound.id not in {s.id for s in spans}
        assert bound.page == 1 and page[bound.start_offset:bound.end_offset] == full
        assert bound.start_offset == len(prefix)
        assert db.get(RequirementVersion, old[0].id).source_span_id == spans[0].id
        assert db.get(DocumentAnalysis, audit.analysis_id).status == 'succeeded'
        response = requirements_response(db, wid, did)[0]
        assert response['page'] == 1 and response['source_document_id'] == did
        assert response['source_url'].endswith('#page=1')
        assert response['requires_human_review']
        assert db.scalar(select(func.count()).select_from(SourceSpan)) == 3
        assert reconcile_document(db, wid, did).id == audit.id


def test_already_extracted_quantity_row_is_upgraded_without_second_requirement_key(database):
    _, sessions = database
    page = 'PRICE SCHEDULE\nItem Description Quantity Unit Cost\n1.00 Tablets 7 Nos. 0.0000\nTotal in Figures\n'
    candidate = quantity_candidates([{'page':1, 'text':page}])[0]
    with sessions() as db:
        wid, did, old, _ = seed(db, page, [candidate['text']])
        audit = reconcile_document(db, wid, did)
        rows = current_rows(db, wid, did)
        assert len(rows) == 1
        corrected, _ = rows[0]
        assert corrected.requirement_key == old[0].requirement_key
        assert corrected.version == 2 and corrected.supersedes_id == old[0].id
        assert corrected.statement == old[0].statement
        quantity = corrected.condition['quantity_conditions'][0]
        assert quantity['count'] == 7 and quantity['kind'] == 'schedule'
        assert quantity['operator'] == 'unspecified'
        assert page[quantity['value_start_offset']:quantity['value_end_offset']] == '7'
        assert corrected.condition['requires_human_review']
        assert corrected.condition['previous_model_review_reasons'] == ['Original model interpretation.']
        assert 'quantity_conditions' not in db.get(RequirementVersion, old[0].id).condition
        assert audit.summary['modified'] == 1 and audit.summary['added'] == 0
        assert reconcile_document(db, wid, did).id == audit.id
        assert db.scalar(select(func.count()).select_from(RequirementVersion)) == 2
