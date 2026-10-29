"""Repeatable synthetic E2E check over real API/database. No provider simulation.

Creates one NEW labelled sample workspace; never edits existing user workspaces.
Also callable with TestClient to test the same workflow on an isolated database.
"""
import json
from pathlib import Path
import httpx
from tenderready.config import Settings

SAMPLES = Path(__file__).resolve().parents[2] / 'frontend/public/samples/offline'
REVIEWER = 'SYNTHETIC DEMO — scripted acceptance review'
AUTH = {'reviewer': REVIEWER, 'coverage_confirmed': True}


def run(client):
    def call(method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.status_code == expected, (path, response.status_code, response.text[:300])
        return response.json()

    workspace = call('POST', '/workspaces', 201, json={
        'title': 'SAMPLE — full offline acceptance', 'supplier_name': 'Synthetic TenderReady Demo Supplier'})
    base = '/workspaces/' + workspace['id']

    def upload(name, path):
        return call('POST', base + path, 201, content=(SAMPLES / name).read_bytes(),
                    headers={'Content-Type': 'application/pdf', 'X-Filename': name})

    def verify(rid):
        return call('POST', f'{base}/requirements/{rid}/verify', 201, json=AUTH)

    def approve(assessment):
        return call('POST', f'{base}/assessments/{assessment["id"]}/reviews', 201, json={
            'action': 'approved', 'reviewer': REVIEWER,
            'comment': 'SYNTHETIC scripted review for testing only. Checked exact labelled model and thresholds; not an actual supplier approval.'})

    original = upload('original-tender.pdf', '/documents')
    docbase = f'{base}/documents/{original["id"]}'
    call('POST', docbase + '/extract-labelled')
    rows = call('GET', docbase + '/requirements')
    assert len(rows) == 2 and {r['page'] for r in rows} == {1, 2}
    pages = {p['page']: p['text'] for p in call('GET', docbase + '/pages')}
    assert all(r['excerpt'] in pages[r['page']] and r['obligation'] == 'mandatory' for r in rows)
    missing = verify(rows[0]['id'])
    assert missing['status'] == 'missing'
    wrong = upload('wrong-model.pdf', '/evidence?evidence_type=datasheet')
    wrong_assessment = verify(rows[0]['id'])
    assert wrong_assessment['status'] == 'conflicting'
    assert any(c.get('field') == 'model' and c.get('outcome') == 'conflict' for c in wrong_assessment['checks'])
    initial = upload('datasheet-16gb.pdf', '/evidence?evidence_type=datasheet&replaces_id=' + wrong['id'])
    approvals = {}
    for row in rows:
        assessment = verify(row['id'])
        assert assessment['status'] == 'supported'
        approvals['ram' if 'RAM-01' in row['text'] else 'ssd'] = approve(assessment)
    call('POST', docbase + '/baseline', 201, json=AUTH)
    assert call('GET', base + '/dashboard')['review_complete']
    amendment = upload('ram-amendment.pdf', '/documents?kind=amendment')
    amendbase = f'{base}/documents/{amendment["id"]}'
    call('POST', amendbase + '/extract-labelled')
    payload = {**AUTH, 'mode': 'delta'}
    preview = call('POST', amendbase + '/compare', json=payload)
    snapshot = call('POST', amendbase + '/apply-amendment', json={**payload, 'fingerprint': preview['fingerprint']})
    modified = next(c for c in snapshot['changes'] if c['classification'] == 'Modified')
    impact = next(i for i in modified['impacts'] if i['old_assessment']['id'] == approvals['ram']['id'])
    assert impact['old_assessment']['id'] == approvals['ram']['id']
    assert impact['old_assessment']['review_state'] == 'reopened'
    assert approvals['ram']['reviews'][0]['id'] in {r['id'] for r in impact['old_assessment']['reviews']}
    conflict = impact['new_assessment']
    assert conflict['status'] == 'conflicting'
    check = next(c for c in conflict['checks'] if c.get('field') == 'ram_gb')
    assert '32' in check['rationale'] and '16 GB' in check['rationale']
    assert check['sources'][0]['page'] == 1
    ssd = next(r for r in snapshot['requirements'] if r['clause_id'] == 'ssd-01')
    assert ssd['assessment']['id'] == approvals['ssd']['id'] and not ssd['assessment']['stale']
    assert ssd['assessment']['review_state'] == 'approved'
    assert not call('GET', base + '/dashboard')['review_complete']
    replacement = upload('replacement-32gb.pdf', '/evidence?evidence_type=datasheet&replaces_id=' + initial['id'])
    for row in snapshot['requirements']:
        assessment = verify(row['requirement_id'])
        assert assessment['status'] == 'supported'
        approve(assessment)
    evidence = call('GET', base + '/evidence')
    assert [e['id'] for e in evidence if e['is_current']] == [replacement['id']]
    for task in call('GET', base + '/dashboard')['tasks']:
        call('POST', base + '/tasks/' + task['id'], json={
            'title': task['title'], 'explanation': task['explanation'], 'priority': task['priority'],
            'status': 'resolved', 'expected_revision': task['revision'], 'reviewer': REVIEWER,
            'comment': 'SYNTHETIC test: replacement evidence checked and approved. Historical findings retained.'})
    final = call('GET', base + '/dashboard')
    assert final['review_complete'] and final['counts']['supported'] == 2
    timeline = call('GET', base + '/timeline?limit=100')
    assert {'review', 'reassessment', 'change', 'task'} <= {e['kind'] for e in timeline['items']}
    for kind in ['compliance-matrix', 'evidence-index']:
        response = client.get(base + '/exports/' + kind)
        assert response.status_code == 200 and 'no-store' in response.headers['cache-control']
        assert 'workspace_summary' in response.text
    return {'workspace_id': workspace['id'], 'mode': 'synthetic deterministic sample; NO AI inference',
            'source_pages': [1, 2], 'missing_evidence_detected': True, 'wrong_model_detected': True,
            'ram_conflict': check['rationale'], 'old_approval_preserved': True,
            'unrelated_storage_approval_preserved_after_amendment': True,
            'replacement_resolved': True, 'final_counts': final['counts'], 'review_complete': final['review_complete'],
            'exports': ['compliance-matrix: 200', 'evidence-index: 200']}


def main():
    settings = Settings()
    token = settings.app_api_token.get_secret_value()
    # Local only; do not follow redirects or send application credentials through proxies.
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=60,
                      headers={'Authorization': f'Bearer {token}'} if token else {}) as client:
        report = run(client)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
