"""Offline correction of cached extraction using real PDF/API/SQLite storage.

Seeded model rows are explicit test fixtures, not evidence of live inference.
Any attempt to construct a provider client fails these tests.
"""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from tenderready.api import create_app
from tenderready.models import (
    AnalysisRequirement, DocumentAnalysis, DocumentPage, ExtractionBatchCache,
    ExtractionReconciliation, ModelRun, RequirementVersion, ReviewDecision,
    SourceSpan, Workspace,
)
from tenderready.requirement_selection import current_rows
from test_documents import config, workspace
from test_quantity_rules import ANTICIPATED, SCHEDULE
from test_verification import evaluate, pdf, send_pdf


GUARANTEE = '1. The supplier shall provide a bank guarantee at the time of delivery of goods.'
RAM = 'Model: Atlas A14\nThe laptop must have at least 32 GB RAM.'
PORTAL = 'The documents would be encrypted on the server before being available to bid openers.'


def offline_app(tmp_path, engine):
    app = create_app(config(tmp_path), engine)

    def forbidden_provider(*args, **kwargs):
        pytest.fail('Cached reconciliation must never construct a provider client.')

    app.state.nemotron_factory = forbidden_provider
    return app


def seed_completed(client, sessions, *, pages=None, provenance='nemotron_extraction', clear_ram_review_notes=False):
    """Persist an intentionally flawed previous model interpretation for repair."""
    wid = workspace(client)
    doc = send_pdf(client, wid, pdf(*(pages or [GUARANTEE + '\n\n' + RAM + '\n\n' + PORTAL])))
    ids = {}
    with sessions.begin() as db:
        analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_version_id == doc['id']))
        analysis.status = 'succeeded'
        analysis.pages_completed = len(pages or [None])
        analysis.model = 'fixture-cached-model'
        span = db.scalar(select(SourceSpan).where(SourceSpan.document_version_id == doc['id']).order_by(SourceSpan.page))
        model = ModelRun(workspace_id=wid, model='fixture-cached-model', operation='extract_requirements',
            input_tokens=123, output_tokens=45, duration_ms=10, outcome='succeeded')
        db.add(model)
        db.flush()
        db.add(ExtractionBatchCache(workspace_id=wid, analysis_id=analysis.id, source_span_id=span.id,
            model_run_id=model.id, fingerprint='a' * 64, result={'requirements': [], 'warnings': []}))
        for key, statement, category, numeric, dates in [
            ('guarantee', GUARANTEE, 'validity_date', [], [{'relation': 'on_or_after',
                'boundary_text': 'delivery of goods', 'quote': GUARANTEE}]),
            ('ram', RAM, 'numeric_threshold', [{'operator': '>=', 'value_text': '32',
                'unit_text': 'GB', 'quote': 'The laptop must have at least 32 GB RAM.'}], []),
            ('portal', PORTAL, 'required_information', [], []),
        ]:
            if statement not in span.text:
                continue
            condition = {'provenance': provenance, 'excerpt': statement,
                'numeric_conditions': numeric, 'date_conditions': dates,
                'review_status': 'awaiting_review',
                'review_reasons': [] if key == 'ram' and clear_ram_review_notes else ['Cached model fixture needs review.']}
            requirement = RequirementVersion(workspace_id=wid, requirement_key=str(uuid4()), version=1,
                source_span_id=span.id, statement=statement, category=category,
                obligation='mandatory', condition=condition)
            db.add(requirement)
            db.flush()
            db.add(AnalysisRequirement(workspace_id=wid, analysis_id=analysis.id,
                requirement_version_id=requirement.id))
            ids[key] = requirement.id
    return wid, doc, ids


def test_reconcile_versions_cached_rows_without_provider_and_is_idempotent(database, tmp_path):
    engine, sessions = database
    with TestClient(base_url='http://127.0.0.1:8000', app=offline_app(tmp_path, engine), client=('127.0.0.1', 1)) as client:
        wid, doc, old = seed_completed(client, sessions)
        endpoint = f'/workspaces/{wid}/documents/{doc["id"]}'
        with sessions() as db:
            original = deepcopy(db.get(RequirementVersion, old['guarantee']).condition)
            revision = db.get(Workspace, wid).revision
        result = client.post(endpoint + '/reconcile')
        assert result.status_code == 200, result.text
        summary = result.json()['analysis']['reconciliation']
        assert {k: summary[k] for k in ('revision', 'added', 'modified', 'reference', 'unchanged', 'provider_calls', 'cached_batches')} == {
            'revision': 1, 'added': 0, 'modified': 1, 'reference': 1, 'unchanged': 1, 'provider_calls': 0, 'cached_batches': 1}
        assert summary['created_at']
        rows = client.get(endpoint + '/requirements').json()
        assert len(rows) == 2
        guarantee = next(r for r in rows if r['text'] == GUARANTEE)
        assert guarantee['supersedes_id'] == old['guarantee'] and guarantee['version'] == 2
        assert guarantee['date_conditions'][0]['relation'] == 'relative'
        assert guarantee['temporal_conditions'][0]['relation'] == 'at_event'
        for condition in guarantee['date_conditions'] + guarantee['temporal_conditions']:
            assert condition['source_document_id'] == doc['id'] and condition['page'] == 1
            assert condition['quote'] == GUARANTEE
            assert condition['source_url'].endswith('/file#page=1')
        assert guarantee['requires_human_review'] and guarantee['review_status'] == 'awaiting_review'
        assert next(r for r in rows if r['text'] == RAM)['id'] == old['ram']
        history = client.get(endpoint + '/reconciliations').json()
        assert len(history) == 1
        assert {c['action'] for c in history[0]['changes']} == {'modified', 'reference'}
        assert {c['previous_requirement_id'] for c in history[0]['changes']} == {old['guarantee'], old['portal']}
        repeated = client.post(endpoint + '/reconcile')
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()['analysis']['reconciliation'] == summary
        assert client.get(endpoint + '/reconciliations').json() == history
    with sessions() as db:
        assert db.get(RequirementVersion, old['guarantee']).condition == original
        assert db.get(Workspace, wid).revision == revision
        assert db.scalar(select(func.count()).select_from(RequirementVersion)) == 5
        assert db.scalar(select(func.count()).select_from(ExtractionReconciliation)) == 1
        assert db.scalar(select(func.count()).select_from(ModelRun)) == 1
        assert db.scalar(select(func.count()).select_from(ExtractionBatchCache)) == 1
        reference = next(r for r, _ in current_rows(db, wid, doc['id'], include_reference=True)
                         if r.condition.get('disposition') == 'reference')
        assert reference.supersedes_id == old['portal'] and reference.obligation == 'unclear'
        assert len(current_rows(db, wid, doc['id'])) == 2
        with pytest.raises(IntegrityError):
            db.execute(text('UPDATE extraction_reconciliations SET revision = 2'))
            db.commit()


def test_quantity_recovery_persists_exact_sources_and_never_minimums(database, tmp_path):
    engine, sessions = database
    with TestClient(base_url='http://127.0.0.1:8000', app=offline_app(tmp_path, engine), client=('127.0.0.1', 1)) as client:
        wid, doc, _ = seed_completed(client, sessions, pages=[ANTICIPATED, SCHEDULE])
        endpoint = f'/workspaces/{wid}/documents/{doc["id"]}'
        response = client.post(endpoint + '/reconcile')
        assert response.status_code == 200, response.text
        assert response.json()['analysis']['reconciliation']['added'] == 6
        rows = client.get(endpoint + '/requirements').json()
        assert len(rows) == 6
        with sessions() as db:
            source = {p.page: p.text for p in db.scalars(select(DocumentPage).where(DocumentPage.document_version_id == doc['id']))}
        for row in rows:
            assert row['text'] == row['excerpt'] and row['text'] in source[row['page']]
            assert row['obligation'] == 'unclear' and row['requires_human_review']
            assert row['numeric_conditions'][0]['operator'] == 'unspecified'
            quantity = row['quantity_conditions'][0]
            assert quantity['source_document_id'] == doc['id'] and quantity['page'] == row['page']
            assert quantity['operator'] == 'unspecified' and quantity['count'] in {7, 9, 3}
            assert source[row['page']][quantity['value_start_offset']:quantity['value_end_offset']] == quantity['value_text']
            assert len(row['quantity_references']) == 1
            for ref in row['source_context'] + row['quantity_references']:
                assert source[ref['page']][ref['start_offset']:ref['end_offset']] == ref['text']
                assert ref['source_document_id'] == doc['id']
                assert ref['source_url'].endswith(f'/file#page={ref["page"]}')
        assert client.post(endpoint + '/reconcile').json()['analysis']['reconciliation']['revision'] == 1


@pytest.mark.parametrize('status', ['ready', 'running', 'failed'])
def test_incomplete_analysis_cannot_reconcile(database, tmp_path, status):
    engine, sessions = database
    with TestClient(base_url='http://127.0.0.1:8000', app=offline_app(tmp_path, engine), client=('127.0.0.1', 1)) as client:
        wid, doc, _ = seed_completed(client, sessions)
        with sessions.begin() as db:
            analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_version_id == doc['id']))
            analysis.status = status
        response = client.post(f'/workspaces/{wid}/documents/{doc["id"]}/reconcile')
        assert response.status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ExtractionReconciliation)) == 0
        assert db.scalar(select(func.count()).select_from(RequirementVersion)) == 3


def test_published_snapshot_is_not_reinterpreted(database, tmp_path):
    engine, sessions = database
    with TestClient(base_url='http://127.0.0.1:8000', app=offline_app(tmp_path, engine), client=('127.0.0.1', 1)) as client:
        wid, doc, old = seed_completed(client, sessions)
        endpoint = f'/workspaces/{wid}/documents/{doc["id"]}'
        baseline = client.post(endpoint + '/baseline', json={'reviewer': 'Test reviewer', 'coverage_confirmed': True})
        assert baseline.status_code == 201, baseline.text
        before = client.get(endpoint + '/requirements').json()
        assert {r['id'] for r in before} == set(old.values())
        response = client.post(endpoint + '/reconcile')
        assert response.status_code == 409
        assert client.get(endpoint + '/requirements').json() == before
        assert client.get(endpoint + '/reconciliations').json() == []


def test_reconcile_is_workspace_scoped_and_authorized(database, tmp_path):
    engine, sessions = database
    app = offline_app(tmp_path, engine)
    with TestClient(base_url='http://127.0.0.1:8000', app=app, client=('127.0.0.1', 1)) as client:
        wid, doc, _ = seed_completed(client, sessions)
        other = workspace(client)
        wrong = f'/workspaces/{other}/documents/{doc["id"]}'
        assert client.post(wrong + '/reconcile').status_code == 404
        assert client.get(wrong + '/reconciliations').status_code == 404
    with TestClient(base_url='http://127.0.0.1:8000', app=app, client=('203.0.113.1', 1)) as remote:
        endpoint = f'/workspaces/{wid}/documents/{doc["id"]}'
        assert remote.post(endpoint + '/reconcile').status_code == 403
        assert remote.get(endpoint + '/reconciliations').status_code == 403
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ExtractionReconciliation)) == 0


def test_reconciliation_stales_only_affected_assessment_preserving_reviews(database, tmp_path):
    engine, sessions = database
    with TestClient(base_url='http://127.0.0.1:8000', app=offline_app(tmp_path, engine), client=('127.0.0.1', 1)) as client:
        # RAM is the unrelated, source-grounded control. Only flawed clauses
        # carry unresolved review notes; no production uncertainty is bypassed.
        wid, doc, ids = seed_completed(client, sessions, clear_ram_review_notes=True)
        send_pdf(client, wid, pdf('Model: Atlas A14\nRAM: 32 GB'), 'datasheet')
        affected = evaluate(client, wid, ids['guarantee'])
        unchanged = evaluate(client, wid, ids['ram'])
        assert unchanged['status'] == 'supported', unchanged
        for assessment, action in [(affected, 'rejected'), (unchanged, 'approved')]:
            result = client.post(f'/workspaces/{wid}/assessments/{assessment["id"]}/reviews', json={
                'action': action, 'reviewer': 'Test reviewer', 'comment': 'Original review is preserved.'})
            assert result.status_code == 201, result.text
        with sessions() as db:
            before = [(r.id, r.action, r.comment, r.created_at) for r in db.scalars(select(ReviewDecision).order_by(ReviewDecision.id))]
        result = client.post(f'/workspaces/{wid}/documents/{doc["id"]}/reconcile')
        assert result.status_code == 200, result.text
        affected_view = client.get(f'/workspaces/{wid}/requirements/{ids["guarantee"]}/verification').json()['assessments'][0]
        unchanged_view = client.get(f'/workspaces/{wid}/requirements/{ids["ram"]}/verification').json()['assessments'][0]
        assert affected_view['stale'] and affected_view['requires_reassessment']
        assert affected_view['review_state'] == 'rejected'
        assert unchanged_view['id'] == unchanged['id'] and unchanged_view['review_state'] == 'approved'
        assert not unchanged_view['stale'] and not unchanged_view['requires_reassessment']
        assert client.post(f'/workspaces/{wid}/assessments/{affected["id"]}/reviews', json={
            'action': 'approved', 'reviewer': 'Test reviewer', 'comment': 'Cannot approve superseded criteria.'}).status_code == 409
        with sessions() as db:
            after = [(r.id, r.action, r.comment, r.created_at) for r in db.scalars(select(ReviewDecision).order_by(ReviewDecision.id))]
            assert after == before


def test_human_transcription_is_not_silently_reinterpreted(database, tmp_path):
    engine, sessions = database
    with TestClient(base_url='http://127.0.0.1:8000', app=offline_app(tmp_path, engine), client=('127.0.0.1', 1)) as client:
        wid, doc, ids = seed_completed(client, sessions, provenance='human_transcription')
        endpoint = f'/workspaces/{wid}/documents/{doc["id"]}'
        response = client.post(endpoint + '/reconcile')
        assert response.status_code == 200, response.text
        summary = response.json()['analysis']['reconciliation']
        assert summary['modified'] == summary['reference'] == summary['added'] == 0
        assert summary['unchanged'] == 3
        assert {r['id'] for r in client.get(endpoint + '/requirements').json()} == set(ids.values())
