"""One-shot audit of the actual running API. No provider or storage mocks.

Uses the fresh workspace created in the UI; refuses to rerun a completed scenario.
Creates explicitly synthetic application data and writes an audit report.
"""
import json
import time
from pathlib import Path
from uuid import uuid4
import httpx
from sqlalchemy import select, func
from tenderready.config import Settings
from tenderready.db import build_engine, build_session_factory
from tenderready.models import Assessment, ReviewDecision, TaskEvent, DocumentVersion, SourceSpan

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / 'samples' / 'final-audit'


def main():
    settings = Settings()
    token = settings.app_api_token.get_secret_value()
    reviewer = 'Synthetic final audit reviewer'
    report = {'workflow': 'Real UI workspace/upload + live HTTP workflow + independent database reads', 'steps': {}}
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=60,
                      headers={'Authorization': f'Bearer {token}'} if token else {}) as client:
        def call(method, path, expected=200, **kwargs):
            response = client.request(method, path, **kwargs)
            assert response.status_code == expected, (path, response.status_code, response.text[:250])
            return response.json()
        workspace = next(w for w in call('GET', '/workspaces') if w['title'] == 'Final audit — replacement evidence and amendment')
        wid = workspace['id']; prefix = '/workspaces/' + wid
        report['workspace_id'] = wid
        assert not call('GET', prefix + '/snapshots'), 'Use a fresh audit workspace; this script is not a data-reset tool.'
        report['steps']['1_workspace'] = {'result': 'passed', 'created_through': 'UI', 'id': wid}
        documents = call('GET', prefix + '/documents')
        original = next(d for d in documents if d['filename'] == 'original-tender.pdf')
        report['steps']['2_upload'] = {'result': 'passed', 'uploaded_through': 'UI', 'pages': original['page_count']}
        source_file = client.get(prefix + f'/documents/{original["id"]}/file')
        assert source_file.content == (SAMPLES / 'original-tender.pdf').read_bytes()
        docpath = prefix + '/documents/' + original['id']
        if not settings.nebius_api_key.get_secret_value():
            call('POST', docpath + '/analyze', expected=202)
            for _ in range(40):
                analysis = next(d for d in call('GET', prefix + '/documents') if d['id'] == original['id'])['analysis']
                if analysis['status'] != 'running':
                    break
                time.sleep(0.1)
            assert analysis['status'] == 'failed' and analysis['error_code'] == 'not_configured'
            assert call('GET', docpath + '/requirements') == []
            report['nemotron'] = {'result': 'blocked', 'reason': analysis['error_message'],
                'endpoint': settings.nebius_base_url, 'model': settings.nebius_model,
                'no_partial_requirements': True, 'provider_calls': 0}
        else:
            raise RuntimeError('Credentials now present: run live inference audit rather than this labelled-fixture path.')
        call('POST', docpath + '/extract-labelled')
        reqs = call('GET', docpath + '/requirements')
        ram = next(r for r in reqs if 'RAM-01' in r['text'])
        ssd = next(r for r in reqs if 'SSD-01' in r['text'])
        assert ram['page'] == 1 and ssd['page'] == 2
        pages = {p['page']: p['text'] for p in call('GET', docpath + '/pages')}
        assert all(r['excerpt'] in pages[r['page']] for r in reqs)
        report['steps']['3_extraction'] = {'result': 'passed_deterministic_only', 'ram_page': 1, 'ssd_page': 2, 'exact_quotes': True}
        def upload(name, kind='evidence'):
            path = prefix + ('/evidence?evidence_type=datasheet' if kind == 'evidence' else '/documents?kind=amendment')
            return call('POST', path, expected=201, content=(SAMPLES / name).read_bytes(),
                headers={'Content-Type': 'application/pdf', 'X-Filename': name})
        initial = upload('initial-datasheet.pdf')
        report['steps']['4_evidence'] = {'result': 'passed', 'id': initial['id']}
        def verify(rid):
            return call('POST', prefix + '/requirements/' + rid + '/verify', expected=201,
                        json={'reviewer': reviewer, 'coverage_confirmed': True})
        def review(aid, action, comment, **extra):
            return call('POST', prefix + '/assessments/' + aid + '/reviews', expected=201,
                        json={'action': action, 'reviewer': reviewer, 'comment': comment, **extra})
        oldram, oldssd = verify(ram['id']), verify(ssd['id'])
        assert oldram['status'] == 'conflicting' and oldssd['status'] == 'supported'
        oldram = review(oldram['id'], 'approved', 'Audit confirms 8 GB fails the original 16 GB minimum; approval is of the conflict finding.')
        oldssd = review(oldssd['id'], 'approved', 'Audit confirms the original 512 GB storage evidence and full criterion coverage.')
        old_review_ids = [r['id'] for r in oldram['reviews']]
        report['steps']['5_mismatch'] = {'result': 'passed', 'required_ram': 16, 'observed_ram': 8, 'status': oldram['status']}
        call('POST', docpath + '/baseline', expected=201, json={'reviewer': reviewer, 'coverage_confirmed': True})
        amendment = upload('ram-amendment.pdf', 'amendment')
        amendpath = prefix + '/documents/' + amendment['id']
        call('POST', amendpath + '/extract-labelled')
        payload = {'mode': 'delta', 'reviewer': reviewer, 'coverage_confirmed': True}
        plan = call('POST', amendpath + '/compare', json=payload)
        current = call('POST', amendpath + '/apply-amendment', json={**payload, 'fingerprint': plan['fingerprint']})
        report['steps']['6_amendment'] = {'result': 'passed', 'snapshot': current['sequence']}
        changed = next(c for c in current['changes'] if c['classification'] == 'Modified')
        impact = changed['impacts'][0]
        assert impact['old_assessment']['review_state'] == 'reopened'
        assert set(old_review_ids) <= {r['id'] for r in impact['old_assessment']['reviews']}
        executed = [c['field'] for c in impact['new_assessment']['checks'] if c.get('execution') == 'executed']
        assert executed == ['ram_gb']
        report['steps']['7_reassessment'] = {'result': 'passed', 'executed_fields': executed, 'original_review_ids_preserved': old_review_ids}
        active_ssd = next(r for r in current['requirements'] if r['clause_id'] == 'ssd-01')
        assert active_ssd['assessment']['id'] == oldssd['id'] and active_ssd['assessment']['review_state'] == 'approved' and not active_ssd['assessment']['stale']
        report['steps']['8_unrelated'] = {'result': 'passed_after_amendment', 'assessment_id': oldssd['id'], 'reviews_preserved': True}
        replacement = upload('replacement-datasheet.pdf')
        active_ram = next(r for r in current['requirements'] if r['clause_id'] == 'ram-01')
        newram = verify(active_ram['requirement_id'])
        refs = [s for check in newram['checks'] for s in check.get('sources', [])]
        assert any(s['document_version_id'] == replacement['id'] and s['raw_value'] == '32 GB' for s in refs)
        assert newram['status'] == 'conflicting'  # Known blocker, not disguised as a successful correction.
        report['steps']['9_replacement'] = {'result': 'automatic_resolution_blocked', 'status': newram['status'],
            'reason': 'Old and replacement datasheets remain active; explicit supersession is not implemented.',
            'replacement_id': replacement['id'], 'assessment_id': newram['id'], 'replacement_quote_preserved': True}
        # Exercise the existing human-correction path explicitly; never relabel it as a deterministic success.
        corrected = review(newram['id'], 'corrected',
            'SYNTHETIC AUDIT human decision: replacement-datasheet.pdf page 1 explicitly replaces the initial 8 GB configuration and states Atlas A14, RAM 32 GB. I select this revised configuration for this finding. Original deterministic conflicts remain preserved; no official verification is claimed.',
            corrected_status='supported')
        assert corrected['checks'][0]['method'] == 'human_correction' and corrected['review_state'] == 'approved'
        report['steps']['9_replacement']['manual_resolution'] = 'Explicit human correction saved as a new assessment; deterministic conflicts preserved.'
        report['steps']['9_replacement']['corrected_assessment_id'] = corrected['id']
        # Replacement of same-category evidence conservatively stales other datasheet-based findings.
        after = call('GET', prefix + '/dashboard')
        ssd_after = next(r for r in after['requirements'] if r['clause_id'] == 'ssd-01')
        report['replacement_side_effect'] = {'ssd_stale_after_upload': ssd_after['assessment']['stale'],
            'explanation': 'Evidence invalidation is category-wide; unaffected storage must be rechecked after a new datasheet.'}
        rerun_ssd = verify(active_ssd['requirement_id'])
        assert rerun_ssd['status'] == 'supported'
        review(rerun_ssd['id'], 'approved', 'Rechecked storage after replacement evidence; both datasheets consistently state 512 GB.')
        exported = {}
        for kind in ('compliance-matrix', 'evidence-index'):
            response = client.get(prefix + '/exports/' + kind)
            assert response.status_code == 200 and 'no-store' in response.headers['cache-control']
            (ROOT / ('final-audit-' + kind + '.csv')).write_bytes(response.content)
            exported[kind] = response.status_code
        final = call('GET', prefix + '/dashboard')
        assert not final['review_complete']  # No invention of mandatory/optional obligations.
        report['steps']['10_approve_export'] = {'result': 'passed_with_explicit_human_correction', 'exports': exported,
            'review_complete': final['review_complete'], 'blockers': final['blockers']}
        # Actual server negative-path checks. No credentials are sent to other hosts.
        invalid = {'Content-Type': 'application/pdf', 'X-Filename': 'malformed.pdf'}
        before = len(call('GET', prefix + '/documents'))
        malformed = client.post(prefix + '/documents', content=b'%PDF-broken', headers=invalid)
        assert malformed.status_code == 422
        wrong_type = client.post(prefix + '/documents', content=b'hello', headers={**invalid, 'Content-Type': 'text/plain'})
        assert wrong_type.status_code == 415
        oversized = client.post(prefix + '/documents', content=b'%PDF-' + b'x' * settings.upload_max_bytes, headers=invalid)
        assert oversized.status_code == 413
        assert len(call('GET', prefix + '/documents')) == before
        wrong_workspace = client.get('/workspaces/' + str(uuid4()) + '/documents/' + original['id'] + '/file')
        assert wrong_workspace.status_code == 404
        origin = client.get(prefix + '/dashboard', headers={'Origin': 'https://untrusted.invalid'})
        assert origin.status_code == 403
        host = client.get('/ready', headers={'Host': 'untrusted.invalid'})
        report['security'] = {'malformed_pdf': malformed.status_code, 'wrong_type': wrong_type.status_code,
            'oversized_pdf': oversized.status_code, 'cross_workspace_file': wrong_workspace.status_code,
            'untrusted_origin': origin.status_code, 'untrusted_host': host.status_code, 'rejected_uploads_not_persisted': True}
    engine = build_engine(settings.database_url)
    with build_session_factory(engine)() as db:
        documents = list(db.scalars(select(DocumentVersion).where(DocumentVersion.workspace_id == wid)))
        assessments = list(db.scalars(select(Assessment).where(Assessment.workspace_id == wid)))
        reviews = list(db.scalars(select(ReviewDecision).where(ReviewDecision.workspace_id == wid)))
        assert len(documents) == 4 and len(assessments) == 6
        assert set(old_review_ids) <= {r.id for r in reviews}
        assert db.scalar(select(func.count()).select_from(SourceSpan).where(SourceSpan.workspace_id == wid)) == 5
        report['database'] = {'documents': len(documents), 'assessments': len(assessments), 'reviews': len(reviews),
            'source_spans': 5, 'old_history_preserved': True,
            'file_modes': sorted({oct((settings.storage_dir / d.storage_key).stat().st_mode & 0o777) for d in documents}),
            'task_event_count': db.scalar(select(func.count()).select_from(TaskEvent).where(TaskEvent.workspace_id == wid))}
    engine.dispose()
    report['result'] = 'PARTIAL — missing live inference and automatic evidence replacement; no ready-bid claim'
    (ROOT / 'final-audit-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
