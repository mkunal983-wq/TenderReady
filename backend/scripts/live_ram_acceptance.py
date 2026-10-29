"""Real Nemotron acceptance test. Missing key is BLOCKED, never a fixture fallback.

Uses only synthetic PDFs, leaves a fresh workspace for inspection, and verifies
model-run records against the same configured database as the local API.
"""
import asyncio
import json
import time
from pathlib import Path
import httpx
from sqlalchemy import select
from tenderready.config import Settings
from tenderready.db import build_engine, build_session_factory
from tenderready.models import ModelRun, ModelRunContext
from tenderready.nebius import NemotronClient, IntegrationError

ROOT = Path(__file__).resolve().parents[2]


async def discover(settings):
    client = NemotronClient(settings)
    try:
        client.require_model()
        available = await client.list_models()
        if settings.nebius_model not in available:
            raise IntegrationError('Configured model is unavailable for this account. Run tenderready models and select an exact returned NVIDIA Nemotron ID.', 'model_unavailable')
    finally:
        await client.close()


def main():
    settings = Settings()
    if not settings.nebius_api_key.get_secret_value():
        print(json.dumps({'live_inference': 'BLOCKED', 'code': 'not_configured',
                          'message': 'Save NEBIUS_API_KEY privately on the server and restart the backend. No provider call or sample substitution was performed.'}))
        return 2
    try:
        asyncio.run(discover(settings))
    except IntegrationError as error:
        print(json.dumps({'live_inference': 'BLOCKED', 'code': error.code, 'message': str(error)}))
        return 2
    token = settings.app_api_token.get_secret_value()
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=60, trust_env=False,
                      headers={'Authorization': f'Bearer {token}'} if token else {}) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                raise RuntimeError(f'Local API returned HTTP {response.status_code}; inspect the workspace UI.')
            return response.json()
        readiness = call('GET', '/ready')
        if readiness['inference'] == 'not_configured':
            raise RuntimeError('Backend has not loaded the key. Restart it before running this test.')
        workspace = call('POST', '/workspaces', json={'title': 'LIVE Nemotron test — 32 GB vs 16 GB', 'supplier_name': 'Synthetic Phase 1A Supplier'})
        base = '/workspaces/' + workspace['id']
        print(json.dumps({'workspace_id': workspace['id'], 'ui': 'http://127.0.0.1:5173/#' + base + '/requirements'}), flush=True)
        def upload(filename, path):
            return call('POST', base + path, content=(ROOT / 'samples/phase1a-live' / filename).read_bytes(),
                        headers={'Content-Type': 'application/pdf', 'X-Filename': filename})
        document = upload('tender-32gb.pdf', '/documents')
        docbase = base + '/documents/' + document['id']
        call('POST', docbase + '/analyze')
        deadline = time.monotonic() + settings.analysis_timeout_seconds + 60
        while True:
            documents = call('GET', base + '/documents')
            analysis = next(d['analysis'] for d in documents if d['id'] == document['id'])
            if analysis['status'] in {'succeeded', 'failed'}:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Analysis still pending; inspect the saved workspace.')
            time.sleep(2)
        if analysis['status'] != 'succeeded':
            print(json.dumps({'live_inference': 'FAILED', 'code': analysis['error_code'], 'message': analysis['error_message']}))
            return 2
        requirements = call('GET', docbase + '/requirements')
        pages = {p['page']: p['text'] for p in call('GET', docbase + '/pages')}
        candidates = [r for r in requirements if any(c['operator'] == '>=' and c['value_text'] == '32' and c['unit_text'] in {'GB', 'GB RAM'} for c in r['numeric_conditions'])]
        if not candidates:
            raise RuntimeError('Provider responded, but no valid >=32 GB condition was extracted. Human review required.')
        row = candidates[0]
        assert row['page'] == 2 and row['source_document_id'] == document['id']
        assert row['excerpt'] in pages[2]
        assert all(c['page'] == 2 and c['source_document_id'] == document['id'] for c in row['numeric_conditions'])
        upload('datasheet-16gb.pdf', '/evidence?evidence_type=datasheet')
        assessment = call('POST', base + '/requirements/' + row['id'] + '/verify',
                          json={'coverage_confirmed': False, 'reviewer': 'Synthetic live acceptance check'})
        assert assessment['status'] == 'conflicting'
        check = next(c for c in assessment['checks'] if c.get('field') == 'ram_gb' and c.get('outcome') == 'conflict')
        assert '32' in check['rationale'] and '16 GB' in check['rationale']
    engine = build_engine(settings.database_url)
    try:
        with build_session_factory(engine)() as db:
            runs = db.execute(select(ModelRun, ModelRunContext).join(ModelRunContext, ModelRunContext.model_run_id == ModelRun.id)
                .where(ModelRun.workspace_id == workspace['id'], ModelRun.outcome == 'succeeded')).all()
            assert runs, 'No persisted successful model-run context found.'
            assert all(r.model == settings.nebius_model for r, _ in runs), 'Backend used a different model; restart it.'
            metadata = [{'id': r.id, 'model': r.model, 'input_tokens': r.input_tokens, 'output_tokens': r.output_tokens,
                         'duration_ms': r.duration_ms, 'outcome': r.outcome, 'created_at': r.created_at.isoformat()} for r, _ in runs]
    finally:
        engine.dispose()
    print(json.dumps({'live_inference': 'SUCCEEDED', 'requirements': requirements,
                      'assessment_status': assessment['status'], 'ram_check': check, 'model_runs': metadata}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, AssertionError, httpx.HTTPError) as exc:
        # No provider payloads, auth headers or connection URLs are printed.
        print(json.dumps({'live_inference': 'NOT_VERIFIED', 'error_type': type(exc).__name__,
                          'message': str(exc) if isinstance(exc, RuntimeError) else 'Acceptance check failed; inspect the retained workspace and server configuration.'}))
        raise SystemExit(2) from None
