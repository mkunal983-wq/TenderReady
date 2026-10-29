"""Source-grounded automatic checks through real PDFs, API and temporary SQLite."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tenderready.models import Assessment, ModelRun, RequirementVersion, ReviewDecision, SourceSpan
from test_batch_verification import client_for
from test_documents import workspace
from test_verification import pdf, send_pdf


def scoped_requirement(client, sessions, wid, *, statement='RAM: at least 32 GB',
                       condition=None, context_changes=None):
    """Seed a synthetic interpretation of an uploaded PDF, never simulate AI."""
    document = send_pdf(client, wid, pdf('SYNTHETIC TENDER', 'Configuration A\n' + statement))
    with sessions.begin() as db:
        source = db.scalar(select(SourceSpan).where(
            SourceSpan.document_version_id == document['id'], SourceSpan.page == 2))
        start = source.start_offset + source.text.index('Configuration A')
        context = {'kind': 'product_scope', 'text': 'Configuration A', 'page': 2,
                   'source_document_id': document['id'], 'start_offset': start,
                   'end_offset': start + len('Configuration A'), **(context_changes or {})}
        requirement = RequirementVersion(workspace_id=wid, requirement_key=str(uuid4()), version=1,
            source_span_id=source.id, statement=statement, category='numeric_threshold', obligation='mandatory',
            condition={'provenance': 'synthetic_test_interpretation', 'confidence': 'high',
                       'excerpt': statement, 'source_context': [context], **(condition or {})})
        db.add(requirement)
        db.flush()
        rid = requirement.id
    return document, rid


def check_all(client, wid):
    client.app.state.nemotron_factory = lambda _: (_ for _ in ()).throw(AssertionError('No provider call allowed'))
    response = client.post(f'/workspaces/{wid}/verify-all', json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['failed'] == 0 and result['provider_calls'] == 0
    return result


def history(client, wid, rid):
    response = client.get(f'/workspaces/{wid}/requirements/{rid}/verification')
    assert response.status_code == 200, response.text
    return response.json()['assessments']


@pytest.mark.parametrize('single_document', [False, True])
def test_config_a_16gb_cannot_borrow_config_b_64gb(database, tmp_path, single_document):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client)
        tender, rid = scoped_requirement(client, sessions, wid)
        a_text = 'Configuration A\nModel: Atlas A14\nRAM: 16 GB'
        b_text = 'Configuration B\nModel: Atlas B14\nRAM: 64 GB'
        a = send_pdf(client, wid, pdf(a_text + '\n' + b_text if single_document else a_text), 'datasheet')
        if not single_document:
            send_pdf(client, wid, pdf(b_text), 'datasheet')
        run = check_all(client, wid)
        assert (run['checked'], run['skipped']) == (1, 0)
        assessment = history(client, wid, rid)[0]
        assert assessment['status'] == 'conflicting' and assessment['review_state'] == 'awaiting_review'
        numeric = [item for item in assessment['checks'] if item.get('field') == 'ram_gb']
        assert len(numeric) == 1 and numeric[0]['outcome'] == 'conflict'
        assert '32' in numeric[0]['rationale'] and '16 GB' in numeric[0]['rationale']
        assert {(ref['raw_value'], ref['document_version_id'], ref['page']) for ref in numeric[0]['sources']} == {('16 GB', a['id'], 1)}
        context = assessment['checks'][0]
        assert context['check_plan']['sources'][0]['source_document_id'] == tender['id']
        assert context['check_plan']['sources'][0]['page'] == 2
        assert context['check_plan']['scope']['label'] == 'Configuration A'
        assert context['coverage_confirmed'] is False and assessment['officially_verified'] is False
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ReviewDecision)) == 0
            assert db.scalar(select(func.count()).select_from(ModelRun)) == 0


def test_grounded_32gb_is_supported_without_silently_approving_and_repeat_skips(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client)
        _, rid = scoped_requirement(client, sessions, wid)
        evidence = send_pdf(client, wid, pdf('Configuration A\nModel: Atlas A14\nRAM: 32 GB'), 'datasheet')
        first = check_all(client, wid)
        assessment = history(client, wid, rid)[0]
        assert assessment['status'] == 'supported' and assessment['review_state'] == 'awaiting_review'
        assert assessment['checks'][0]['automatic_coverage'] is True
        assert assessment['checks'][0]['coverage_confirmed'] is False
        ram = next(item for item in assessment['checks'] if item.get('field') == 'ram_gb')
        assert ram['outcome'] == 'pass' and ram['sources'][0]['document_version_id'] == evidence['id']
        assert ram['sources'][0]['product_scope'] == 'configuration:a'
        assert ram['sources'][0]['scope_sources'][0]['quote'] == 'Configuration A'
        repeated = check_all(client, wid)
        assert (repeated['checked'], repeated['skipped']) == (0, 1)
        assert repeated['results'][0]['assessment_id'] == first['results'][0]['assessment_id']
        assert len(history(client, wid, rid)) == 1
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ReviewDecision)) == 0
            assert db.scalar(select(func.count()).select_from(Assessment)) == 1


@pytest.mark.parametrize('condition,context_changes,evidence_text', [
    ({'confidence': 'low'}, {}, 'Configuration A\nModel: Atlas A14\nRAM: 32 GB'),
    ({'ambiguous': True}, {}, 'Configuration A\nModel: Atlas A14\nRAM: 32 GB'),
    ({'requires_human_review': True}, {}, 'Configuration A\nModel: Atlas A14\nRAM: 32 GB'),
    ({}, {'page': 99}, 'Configuration A\nModel: Atlas A14\nRAM: 32 GB'),
    ({}, {'text': 'Configuration B'}, 'Configuration A\nModel: Atlas A14\nRAM: 32 GB'),
    ({}, {}, 'Model: Atlas A14\nRAM: 32 GB'),
])
def test_passing_capacity_is_not_supported_when_source_or_scope_uncertain(
        database, tmp_path, condition, context_changes, evidence_text):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client)
        _, rid = scoped_requirement(client, sessions, wid, condition=condition, context_changes=context_changes)
        send_pdf(client, wid, pdf(evidence_text), 'datasheet')
        check_all(client, wid)
        assessment = history(client, wid, rid)[0]
        assert assessment['status'] == 'inconclusive'
        assert any(check.get('outcome') == 'review' for check in assessment['checks'])
        assert assessment['review_state'] == 'awaiting_review'


@pytest.mark.parametrize('storage_line', ['Storage: 256 GB', 'Storage: 256 GB SSD'])
def test_flash_requirement_cannot_pass_capacity_only_or_different_medium(database, tmp_path, storage_line):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client)
        _, rid = scoped_requirement(client, sessions, wid, statement='Storage: 128 GB Flash or above')
        send_pdf(client, wid, pdf('Configuration A\nModel: Atlas A14\n' + storage_line), 'datasheet')
        check_all(client, wid)
        assessment = history(client, wid, rid)[0]
        assert assessment['status'] in {'inconclusive', 'conflicting'}
        numeric = next(c for c in assessment['checks'] if c.get('field') == 'storage_gb')
        assert numeric['outcome'] == 'pass'
        qualifier = next(c for c in assessment['checks'] if c.get('field') == 'storage_type')
        assert qualifier['outcome'] in {'review', 'conflict'}
        assert any(c['expected'] == 'Flash' for c in assessment['checks'][0]['criteria'])


@pytest.mark.parametrize('action', ['approved', 'rejected'])
def test_bulk_does_not_upgrade_or_overwrite_reviewed_old_findings(database, tmp_path, action):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client)
        _, rid = scoped_requirement(client, sessions, wid)
        evidence = send_pdf(client, wid, pdf('Configuration A\nModel: Atlas A14\nRAM: 32 GB'), 'datasheet')
        # Real persisted legacy finding: the newer automatic planner could cover
        # this clause, but an existing human decision must not be replaced.
        with sessions.begin() as db:
            previous = Assessment(workspace_id=wid, requirement_version_id=rid, workspace_revision=1,
                status='inconclusive', explanation='Legacy check awaiting manual scope review.', checks=[{
                    'method': 'verification_context', 'rules_version': 'legacy_checks_v1',
                    'criteria': [], 'coverage_confirmed': False, 'reviewer': '',
                    'library_document_ids': [evidence['id']], 'officially_verified': False,
                    'display_status': 'inconclusive'}])
            db.add(previous)
            db.flush()
            previous_id = previous.id
        reviewed = client.post(f'/workspaces/{wid}/assessments/{previous_id}/reviews', json={
            'action': action, 'reviewer': 'Scope reviewer', 'comment': 'Preserve this earlier review and its scope decision.'})
        assert reviewed.status_code == 201, reviewed.text
        before = history(client, wid, rid)
        result = check_all(client, wid)
        assert (result['checked'], result['skipped']) == (0, 1)
        assert result['results'][0]['assessment_id'] == previous_id
        after = history(client, wid, rid)
        assert after == before and len(after) == 1
        assert after[0]['review_state'] == action
        assert after[0]['reviews'][0]['comment'] == 'Preserve this earlier review and its scope decision.'
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ReviewDecision)) == 1
            assert db.scalar(select(func.count()).select_from(Assessment)) == 1
