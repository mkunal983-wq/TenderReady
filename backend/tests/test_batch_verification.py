"""Real PDF, migrated database and API coverage for workspace document checks."""
import csv
import io
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from tenderready.api import create_app
from tenderready.models import Assessment, CorrectiveTask, ModelRun, RequirementVersion, ReviewDecision, SourceSpan
from test_amendments import AUTH, RAM32, setup, upload_revision
from test_documents import config, workspace
from test_verification import evaluate, pdf, send_pdf


def client_for(engine, tmp_path, **kwargs):
    return TestClient(app=create_app(config(tmp_path), engine), base_url='http://127.0.0.1:8000',
                      client=('127.0.0.1', 1), **kwargs)


def store_requirements(client, sessions, wid, statements):
    """Trusted synthetic interpretations linked to real PDF pages; no fake AI."""
    document = send_pdf(client, wid, pdf('SYNTHETIC TENDER', '\n\n'.join(text for text, _ in statements)))
    ids = []
    with sessions.begin() as db:
        span = db.scalar(select(SourceSpan).where(SourceSpan.document_version_id == document['id'], SourceSpan.page == 2))
        for statement, condition in statements:
            row = RequirementVersion(workspace_id=wid, requirement_key=str(uuid4()), version=1,
                source_span_id=span.id, statement=statement, obligation='mandatory', category='numeric_threshold',
                condition={'excerpt': statement, **condition})
            db.add(row); db.flush(); ids.append(row.id)
    return document, ids


def test_not_checked_is_distinct_and_bulk_checks_preserve_uncertainty(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        # The provider must never be constructed by this deterministic workflow.
        client.app.state.nemotron_factory = lambda _: (_ for _ in ()).throw(AssertionError('No AI call expected'))
        wid = workspace(client); prefix = f'/workspaces/{wid}'
        statement = 'The product must have at least 32 GB RAM.'
        _, ids = store_requirements(client, sessions, wid, [
            (statement, {'confidence': 'high', 'numeric_conditions': [
                {'operator': '>=', 'value_text': '32', 'unit_text': 'GB', 'quote': statement}]}),
            ('Certificate number: CERT-1', {}),
            ('Submit the guarantee at the time of delivery.', {'requires_human_review': True}),
        ])
        send_pdf(client, wid, pdf('SYNTHETIC DATASHEET', 'Model: Atlas A14\nRAM: 16 GB'), 'datasheet')
        before = client.get(prefix + '/dashboard').json()
        assert before['counts']['not_checked'] == 3 and before['counts']['inconclusive'] == 0
        assert not before['review_complete'] and all(row['blocking'] for row in before['requirements'])
        detail = client.get(prefix + f'/requirements/{ids[0]}/detail').json()
        assert detail['status'] == 'not_checked' and detail['label'] == 'Not checked' and detail['page'] == 2
        csv_rows = list(csv.DictReader(io.StringIO(client.get(prefix + '/exports/compliance-matrix').text.lstrip('\ufeff'))))
        assert [row['status'] for row in csv_rows[1:]] == ['Not checked'] * 3

        response = client.post(prefix + '/verify-all', json={})
        assert response.status_code == 200, response.text
        result = response.json()
        assert (result['total'], result['checked'], result['skipped'], result['failed'], result['provider_calls']) == (3, 3, 0, 0, 0)
        assert {row['status'] for row in result['results']} == {'conflicting', 'missing', 'inconclusive'}
        after = client.get(prefix + '/dashboard').json()
        assert after['counts']['not_checked'] == 0 and after['counts']['inconclusive'] == 1
        assert not after['review_complete']
        ram = client.get(prefix + f'/requirements/{ids[0]}/verification').json()['assessments'][0]
        check = next(item for item in ram['checks'] if item.get('field') == 'ram_gb' and item.get('outcome') == 'conflict')
        assert '32' in check['rationale'] and '16 GB' in check['rationale']
        assert check['sources'][0]['page'] == 2 and check['sources'][0]['quote'] == 'RAM: 16 GB'
        assert ram['review_state'] == 'awaiting_review' and not ram['officially_verified']
        assert ram['checks'][0]['coverage_confirmed'] is False
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ModelRun)) == 0
            assert db.scalar(select(func.count()).select_from(ReviewDecision)) == 0
            assert db.scalar(select(func.count()).select_from(Assessment)) == 3

        repeated = client.post(prefix + '/verify-all').json()
        assert (repeated['checked'], repeated['skipped'], repeated['failed']) == (0, 3, 0)
        assert {row['assessment_id'] for row in result['results']} == {row['assessment_id'] for row in repeated['results']}
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Assessment)) == 3
            assert db.scalar(select(func.count()).select_from(CorrectiveTask)) == 4  # Three findings plus the procedural action.


def test_bulk_preserves_current_approvals_and_ignores_unapplied_and_other_workspaces(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid, _, _, _, assessments, _ = setup(client)
        # The pending amendment must not silently become the current tender.
        upload_revision(client, wid, RAM32)
        other = workspace(client)
        _, other_ids = store_requirements(client, sessions, other, [('RAM: at least 64 GB', {})])
        result = client.post(f'/workspaces/{wid}/verify-all', json={}).json()
        assert (result['total'], result['checked'], result['skipped']) == (2, 0, 2)
        assert {row['assessment_id'] for row in result['results']} == {a['id'] for a in assessments}
        rows = client.get(f'/workspaces/{wid}/dashboard').json()['requirements']
        assert all(row['assessment']['review_state'] == 'approved' for row in rows)
        assert all(row['assessment']['reviews'][0]['comment'] == 'Confirmed original requirement.' for row in rows)
        assert client.get(f'/workspaces/{other}/requirements/{other_ids[0]}/detail').json()['status'] == 'not_checked'


def test_bulk_rechecks_replacement_without_overwriting_old_review_or_unrelated_approval(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client); prefix = f'/workspaces/{wid}'
        doc, ids = store_requirements(client, sessions, wid, [
            ('Model: Atlas A14\nRAM: at least 32 GB', {}), ('Certificate number: CERT-1', {})])
        old_document = send_pdf(client, wid, pdf('Model: Atlas A14\nRAM: 16 GB'), 'datasheet')
        send_pdf(client, wid, pdf('Bidder: Sample Supplier\nCertificate number: CERT-1'), 'certificate')
        old_results = [evaluate(client, wid, rid) for rid in ids]
        for old in old_results:
            assert client.post(prefix + f'/assessments/{old["id"]}/reviews', json={
                'action': 'approved', 'reviewer': 'Test reviewer', 'comment': 'Reviewed the original result.'}).status_code == 201
        assert client.post(prefix + f'/documents/{doc["id"]}/baseline', json=AUTH).status_code == 201
        replacement = client.post(prefix + f'/evidence?evidence_type=datasheet&replaces_id={old_document["id"]}',
            content=pdf('Model: Atlas A14\nRAM: 32 GB'), headers={'Content-Type': 'application/pdf', 'X-Filename': 'replacement.pdf'})
        assert replacement.status_code == 201
        result = client.post(prefix + '/verify-all', json={}).json()
        assert (result['checked'], result['skipped'], result['failed']) == (1, 1, 0)
        history = client.get(prefix + f'/requirements/{ids[0]}/verification').json()['assessments']
        assert len(history) == 2 and history[1]['id'] == old_results[0]['id']
        assert history[1]['review_state'] == 'approved' and history[1]['reviews'][0]['comment'] == 'Reviewed the original result.'
        assert history[0]['review_state'] == 'awaiting_review' and history[0]['status'] == 'supported'
        assert history[0]['checks'][0]['automatic_coverage'] is True
        assert history[0]['checks'][0]['coverage_confirmed'] is False
        assert history[0]['reviews'] == []
        assert any(c.get('field') == 'ram_gb' and c.get('outcome') == 'pass' for c in history[0]['checks'])
        assert {source['document_version_id'] for check in history[0]['checks'] for source in check.get('sources', [])} == {replacement.json()['id']}
        unrelated = client.get(prefix + f'/requirements/{ids[1]}/verification').json()['assessments']
        assert len(unrelated) == 1 and unrelated[0]['id'] == old_results[1]['id'] and unrelated[0]['review_state'] == 'approved'


def test_unsupported_automatic_date_wording_becomes_a_saved_review_finding(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client)
        _, ids = store_requirements(client, sessions, wid, [
            ('Valid until: sometime after delivery', {}), ('RAM: at least 32 GB', {})])
        result = client.post(f'/workspaces/{wid}/verify-all', json={}).json()
        assert (result['checked'], result['failed']) == (2, 0)
        bad = next(row for row in result['results'] if row['requirement_id'] == ids[0])
        assert bad['outcome'] == 'checked' and bad['status'] == 'inconclusive' and bad['assessment_id']
        history = client.get(f'/workspaces/{wid}/requirements/{ids[0]}/verification').json()
        assert history['suggested_criteria'] == []
        assert any('cannot be safely turned into an automatic check' in c.get('rationale', '') for c in history['assessments'][0]['checks'])
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Assessment)) == 2


def test_mea_storage_and_mixed_rows_keep_unsupported_details_for_human_review(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client); prefix = f'/workspaces/{wid}'
        statements = ['Storage: 128 GB Flash or above', 'Storage: 16 GB or Higher;',
            'Model: Atlas A14\nStorage: 128 GB Flash or above\nMemory: 4 GB or above',
            'Tablet Screen Size: 8.9 inch or above;\nStorage: 16 GB or Higher;\nMemory: 2GB or higher;']
        _, ids = store_requirements(client, sessions, wid, [(text, {}) for text in statements])
        send_pdf(client, wid, pdf('Model: Atlas A14\nStorage: 256 GB\nRAM: 16 GB'), 'datasheet')
        result = client.post(prefix + '/verify-all', json={}).json()
        assert (result['checked'], result['failed']) == (4, 0)
        assert {item['status'] for item in result['results']} == {'inconclusive'}
        for index, rid in enumerate(ids):
            view = client.get(prefix + f'/requirements/{rid}/verification').json()
            storage = next(c for c in view['suggested_criteria'] if c['field'] == 'storage_gb')
            assert storage['operator'] == 'gte' and storage['expected'] == ('128' if index in {0, 2} else '16')
            assert storage['quote'] in statements[index]
            check = view['assessments'][0]
            assert check['review_state'] == 'awaiting_review' and check['officially_verified'] is False
            if index in {0, 2}:
                assert any(c['field'] == 'storage_type' and c['expected'] == 'Flash' for c in view['suggested_criteria'])
                assert any(c.get('field') == 'storage_type' and c.get('outcome') == 'review' for c in check['checks'])
            if index == 3:
                assert any(c.get('field') == 'screen_inches' and c.get('outcome') == 'review' for c in check['checks'])
                assert any(c['field'] == 'screen_inches' and c['expected'] == '8.9' for c in view['suggested_criteria'])
            assert client.get(prefix + f'/requirements/{rid}/detail').json()['page'] == 2

        # Explicit custom inputs must never be silently discarded by the filter.
        invalid = {'field': 'storage_gb', 'operator': 'eq', 'expected': '128 GB Flash or above',
            'quote': statements[0], 'evidence_type': 'datasheet'}
        response = client.post(prefix + f'/requirements/{ids[0]}/verify', json={'criteria': [invalid]})
        assert response.status_code == 422
        assert 'Unsupported expected value' in response.json()['error']['message']
        assert len(client.get(prefix + f'/requirements/{ids[0]}/verification').json()['assessments']) == 1


def test_stale_human_correction_keeps_custom_checks_and_review_history(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client); prefix = f'/workspaces/{wid}'
        _, ids = store_requirements(client, sessions, wid, [('Model: Atlas A14\nRAM: at least 32 GB', {})])
        old_document = send_pdf(client, wid, pdf('Model: Atlas A14\nRAM: 32 GB'), 'datasheet')
        criteria = [
            {'field': 'model', 'operator': 'eq', 'expected': 'Atlas A14', 'quote': 'Model: Atlas A14', 'evidence_type': 'datasheet'},
            {'field': 'ram_gb', 'operator': 'eq', 'expected': '32 GB', 'quote': 'RAM: at least 32 GB', 'evidence_type': 'datasheet'},
        ]
        original = evaluate(client, wid, ids[0], criteria=criteria)
        correction = client.post(prefix + f'/assessments/{original["id"]}/reviews', json={
            'action': 'corrected', 'reviewer': 'Test reviewer', 'comment': 'Supplier configuration still needs clarification.',
            'corrected_status': 'inconclusive'})
        assert correction.status_code == 201
        old_history = client.get(prefix + f'/requirements/{ids[0]}/verification').json()['assessments']
        assert len(old_history) == 2 and old_history[0]['checks'][0]['method'] == 'human_correction'
        assert client.post(prefix + f'/evidence?evidence_type=datasheet&replaces_id={old_document["id"]}',
            content=pdf('Model: Atlas A14\nRAM: 64 GB'), headers={'Content-Type': 'application/pdf', 'X-Filename': 'replacement.pdf'}).status_code == 201
        result = client.post(prefix + '/verify-all', json={}).json()
        assert (result['checked'], result['failed']) == (1, 0)
        history = client.get(prefix + f'/requirements/{ids[0]}/verification').json()['assessments']
        assert len(history) == 3 and history[1]['id'] == old_history[0]['id']
        assert history[1]['reviews'][0]['comment'] == 'Supplier configuration still needs clarification.'
        assert history[0]['checks'][0]['criteria'] == criteria
        assert history[0]['checks'][0]['coverage_confirmed'] is False
        assert history[0]['status'] == 'conflicting' and history[0]['review_state'] == 'awaiting_review'


def test_posting_filtered_suggestions_cannot_hide_unsupported_part_of_clause(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client); prefix = f'/workspaces/{wid}'
        statement = 'Model: Atlas A14\nStorage: 128 GB Flash or above\nWarranty: onsite support'
        _, ids = store_requirements(client, sessions, wid, [(statement, {})])
        send_pdf(client, wid, pdf('Model: Atlas A14\nStorage: 256 GB'), 'datasheet')
        endpoint = prefix + f'/requirements/{ids[0]}'
        suggested = client.get(endpoint + '/verification').json()['suggested_criteria']
        assert {c['field'] for c in suggested} == {'model', 'storage_gb', 'storage_type'}
        assert next(c for c in suggested if c['field'] == 'storage_type')['expected'] == 'Flash'
        # This is the actual UI request shape after accepting suggested checks.
        result = client.post(endpoint + '/verify', json={'criteria': suggested,
            'coverage_confirmed': True, 'reviewer': 'Test reviewer'})
        assert result.status_code == 201
        first = result.json()
        assert first['status'] == 'inconclusive'
        assert any(c.get('field') == 'interpretation' and c.get('outcome') == 'review' for c in first['checks'])
        assert any('Warranty:' in item['text'] for item in first['checks'][0]['check_plan']['unhandled'])
        assert any(c.get('field') == 'storage_type' and c.get('outcome') == 'review' for c in first['checks'])
        # Adding a valid capacity check still does not prove the "Flash" detail.
        custom = [*suggested, {'field': 'storage_gb', 'operator': 'gte', 'expected': '128 GB',
            'quote': 'Storage: 128 GB Flash or above', 'evidence_type': 'datasheet'}]
        changed = client.post(endpoint + '/verify', json={'criteria': custom,
            'coverage_confirmed': True, 'reviewer': 'Test reviewer'}).json()
        assert changed['status'] == 'inconclusive' and changed['checks'][0]['criteria'] == custom
        assert any(c.get('field') == 'storage_gb' and c.get('outcome') == 'pass' for c in changed['checks'])
        # An explicit human decision is still available and remains identified
        # as such, preserving both deterministic results and source warnings.
        correction = client.post(prefix + f'/assessments/{changed["id"]}/reviews', json={
            'action': 'corrected', 'corrected_status': 'supported', 'reviewer': 'Test reviewer',
            'comment': 'Reviewer separately checked the Flash storage specification and onsite warranty.'})
        assert correction.status_code == 201
        history = client.get(endpoint + '/verification').json()['assessments']
        assert len(history) == 3 and history[0]['checks'][0]['method'] == 'human_correction'
        assert history[0]['status'] == 'supported' and history[1]['status'] == history[2]['status'] == 'inconclusive'


def test_manual_coverage_cannot_drop_flash_or_reverse_capacity_but_complete_checks_work(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client); prefix = f'/workspaces/{wid}'
        text = 'Model: Atlas A14\nStorage: 128 GB Flash or above'
        _, ids = store_requirements(client, sessions, wid, [(text, {})])
        old = send_pdf(client, wid, pdf('Model: Atlas A14\nStorage: 128 GB'), 'datasheet')
        endpoint = prefix + f'/requirements/{ids[0]}'
        suggested = client.get(endpoint + '/verification').json()['suggested_criteria']
        assert {c['field'] for c in suggested} == {'model', 'storage_gb', 'storage_type'}
        omitted = [c for c in suggested if c['field'] != 'storage_type']
        first = client.post(endpoint + '/verify', json={
            'criteria': omitted, 'coverage_confirmed': True, 'reviewer': 'Test reviewer'})
        assert first.status_code == 201, first.text
        assert first.json()['status'] == 'inconclusive'
        assert any(c.get('field') == 'coverage' and c.get('outcome') == 'review' for c in first.json()['checks'])
        replacement = client.post(prefix + f'/evidence?evidence_type=datasheet&replaces_id={old["id"]}',
            content=pdf('Model: Atlas A14\nStorage: 128 GB Flash'),
            headers={'Content-Type': 'application/pdf', 'X-Filename': 'replacement.pdf'})
        assert replacement.status_code == 201
        reversed_rule = [{**c, 'operator': 'lte'} if c['field'] == 'storage_gb' else c for c in suggested]
        second = client.post(endpoint + '/verify', json={
            'criteria': reversed_rule, 'coverage_confirmed': True, 'reviewer': 'Test reviewer'})
        assert second.status_code == 201, second.text
        assert second.json()['status'] == 'inconclusive'
        assert any(c.get('field') == 'coverage' and c.get('outcome') == 'review' for c in second.json()['checks'])
        third = client.post(endpoint + '/verify', json={'criteria': suggested})
        assert third.status_code == 201, third.text
        final = third.json()
        assert final['status'] == 'supported' and final['review_state'] == 'awaiting_review'
        assert final['reviews'] == [] and final['officially_verified'] is False
        flash = next(c for c in final['checks'] if c.get('field') == 'storage_type')
        assert flash['outcome'] == 'pass'
        assert flash['sources'][0]['quote'] == 'Storage: 128 GB Flash'
        assert flash['sources'][0]['document_version_id'] == replacement.json()['id']
        history = client.get(endpoint + '/verification').json()['assessments']
        assert [item['id'] for item in history] == [final['id'], second.json()['id'], first.json()['id']]
        assert [item['status'] for item in history] == ['supported', 'inconclusive', 'inconclusive']


def test_bulk_authentication_origin_validation_and_empty_workspaces(database, tmp_path):
    engine, _ = database
    settings = config(tmp_path).model_copy(update={'app_api_token': SecretStr('a' * 40)})
    with TestClient(app=create_app(settings, engine), base_url='http://127.0.0.1:8000', client=('127.0.0.1', 1)) as client:
        headers = {'Authorization': 'Bearer ' + 'a' * 40}
        wid = client.post('/workspaces', json={'title': 'Empty', 'supplier_name': 'Supplier'}, headers=headers).json()['id']
        endpoint = f'/workspaces/{wid}/verify-all'
        assert client.post(endpoint, json={}).status_code == 401
        assert client.post(endpoint, json={}, headers={**headers, 'Origin': 'https://untrusted.example'}).status_code == 403
        assert client.post(endpoint, json={'coverage_confirmed': True}, headers=headers).status_code == 422
        assert client.post(endpoint, json={'requirement_ids': [str(uuid4())]}, headers=headers).status_code == 422
        assert client.post(f'/workspaces/{uuid4()}/verify-all', json={}, headers=headers).status_code == 404
        result = client.post(endpoint, json={}, headers=headers).json()
        assert result == {'total': 0, 'checked': 0, 'skipped': 0, 'failed': 0, 'provider_calls': 0, 'results': []}


def test_concurrent_bulk_clicks_do_not_duplicate_assessments(database, tmp_path):
    engine, sessions = database
    with client_for(engine, tmp_path) as client:
        wid = workspace(client)
        store_requirements(client, sessions, wid, [('RAM: at least 32 GB', {}), ('Please supply a signed declaration.', {})])
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post(f'/workspaces/{wid}/verify-all', json={}), range(2)))
        assert all(response.status_code == 200 for response in responses)
        assert sorted(response.json()['checked'] for response in responses) == [0, 2]
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Assessment)) == 2


def test_system_failure_rolls_back_the_whole_batch(database, tmp_path, monkeypatch):
    from tenderready import batch_verification
    engine, sessions = database
    with client_for(engine, tmp_path, raise_server_exceptions=False) as client:
        wid = workspace(client)
        store_requirements(client, sessions, wid, [('RAM: at least 32 GB', {}), ('Please supply a signed declaration.', {})])
        real_verify = batch_verification.verify
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('Internal detail must not be returned')
            return real_verify(*args, **kwargs)
        monkeypatch.setattr(batch_verification, 'verify', fail_second)
        response = client.post(f'/workspaces/{wid}/verify-all', json={})
        assert response.status_code == 500 and 'Internal detail' not in response.text
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Assessment)) == 0
            assert db.scalar(select(func.count()).select_from(CorrectiveTask)) == 0
