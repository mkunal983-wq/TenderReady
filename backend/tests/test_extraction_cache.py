"""Real migrated DB checks; provider transports here are explicitly test-only."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import httpx
from reportlab.pdfgen import canvas
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from tenderready.api import create_app
from tenderready.config import Settings, get_settings
from tenderready.db import build_engine
from tenderready.extraction_batches import BatchContext, ExtractionBatch, plan_batches
from tenderready.extraction_cache import batch_fingerprint, extract_checkpoint
from tenderready.models import ExtractionBatchCache, ModelRun, SourceSpan
from tenderready.nebius import IntegrationError, NemotronClient
from test_documents import config, provider_factory, upload, workspace


def test_retry_reuses_only_completed_validated_batch(database, tmp_path):
    engine, sessions = database
    app = create_app(config(tmp_path), engine)
    first_calls = []
    app.state.nemotron_factory = provider_factory('second_page_failure', first_calls)
    with TestClient(base_url='http://127.0.0.1:8000', app=app, client=('127.0.0.1', 1)) as client:
        wid = workspace(client)
        doc = upload(client, wid).json()
        endpoint = f"/workspaces/{wid}/documents/{doc['id']}"
        client.post(endpoint + '/analyze')
        assert client.get(endpoint + '/requirements').json() == []
        assert len(first_calls) == 2
        with sessions() as db:
            caches = db.scalars(select(ExtractionBatchCache)).all()
            assert len(caches) == 1
            cached_run = caches[0].model_run_id
            assert db.get(ModelRun, cached_run).outcome == 'succeeded'
            assert db.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.outcome == 'failed')) == 1
        retry_calls = []
        app.state.nemotron_factory = provider_factory('success', retry_calls)
        client.post(endpoint + '/analyze')
        rows = client.get(endpoint + '/requirements').json()
        assert len(rows) == 2
        assert len(retry_calls) == 1
        assert '30 November' in retry_calls[0]['text']
        assert next(row for row in rows if row['page'] == 1)['model_run_id'] == cached_run
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ExtractionBatchCache)) == 2
            assert db.scalar(select(func.count()).select_from(ModelRun)) == 3
        # Repeated success is idempotent and does not spend another provider call.
        client.post(endpoint + '/analyze')
        assert len(retry_calls) == 1


def test_batch_fingerprint_tracks_source_configuration_and_context():
    span = SimpleNamespace(id='span', text='Configuration A\nMemory: 8 GB or above;\n')
    context = BatchContext('product_scope', 0, 15, 'Configuration A')
    batch = ExtractionBatch(16, len(span.text), (context,))
    settings = Settings(_env_file=None)
    original = batch_fingerprint(span, batch, settings)
    assert len(original) == 64
    for update in [
        {'nebius_model': 'nvidia/another-nemotron'},
        {'nebius_base_url': 'https://provider.example/v1'},
        {'nebius_enable_thinking': False},
        {'nebius_extraction_format': 'line_refs'},
        {'nebius_json_mode': not settings.nebius_json_mode},
        {'nebius_max_output_tokens': settings.nebius_max_output_tokens + 1},
    ]:
        assert batch_fingerprint(span, batch, settings.model_copy(update=update)) != original
    for changed in [
        replace(batch, start=batch.start + 1),
        replace(batch, contexts=()),
        replace(batch, contexts=(replace(context, text='Configuration B'),)),
        replace(batch, contexts=(replace(context, start=1, end=16),)),
        replace(batch, contexts=(replace(context, kind='table_header'),)),
    ]:
        assert batch_fingerprint(span, changed, settings) != original
    altered_source = SimpleNamespace(id=span.id, text=span.text.replace('8 GB', '4 GB'))
    assert batch_fingerprint(altered_source, batch, settings) != original
    # Authentication changes are not interpretation changes and must not enter stored keys.
    credentials_only = settings.model_copy(update={'nebius_api_key': Settings(_env_file=None, nebius_api_key='test-secret').nebius_api_key})
    assert batch_fingerprint(span, batch, credentials_only) == original


def _scoped_pdf():
    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    lines = [
        'Item Minimum required specification Anticipated', 'Requirement',
        'Configuration A', 'Memory: 8 GB or above;', '10',
        'Configuration B', 'Memory: 8 GB or above;', '10',
        '2. Eligibility Criteria for Bidders:-', 'The bidder must be registered.',
    ]
    for index, line in enumerate(lines):
        pdf.drawString(45, 800 - index * 20, line)
    pdf.save()
    return stream.getvalue()


def _scoped_provider(settings):
    configured = settings.model_copy(update={'nebius_api_key': Settings(_env_file=None, nebius_api_key='test-only').nebius_api_key})
    def transport(request):
        if request.url.path.endswith('/models'):
            return httpx.Response(200, json={'object': 'list', 'data': [{'id': configured.nebius_model, 'created': 1, 'object': 'model', 'owned_by': 'nvidia'}]})
        body = json.loads(request.content)
        source = json.loads(body['messages'][1]['content'])['sources'][0]
        quote = 'Memory: 8 GB or above;'
        rows = []
        if quote in source['text']:
            assert 'Configuration ' in source['context']
            rows = [{'statement': quote, 'category': 'numeric_threshold', 'obligation': 'unclear',
                     'obligation_quote': None, 'citations': [{'source_id': source['source_id'], 'quote': quote}],
                     'numeric_conditions': [{'operator': '>=', 'value_text': '8', 'unit_text': 'GB', 'quote': quote}],
                     'date_conditions': [], 'confidence': 'high', 'review_reasons': []}]
        return httpx.Response(200, json={'id': 'test-only', 'created': 1, 'object': 'chat.completion', 'model': configured.nebius_model,
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps({'requirements': rows, 'warnings': []})}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}})
    return NemotronClient(configured, httpx.AsyncClient(transport=httpx.MockTransport(transport)))


def test_scoped_conditions_keep_source_offsets_and_distinct_product_requirements(database, tmp_path):
    engine, sessions = database
    app = create_app(config(tmp_path), engine)
    app.state.nemotron_factory = _scoped_provider
    with TestClient(base_url='http://127.0.0.1:8000', app=app, client=('127.0.0.1', 1)) as client:
        wid = workspace(client)
        doc = upload(client, wid, _scoped_pdf()).json()
        endpoint = f"/workspaces/{wid}/documents/{doc['id']}"
        client.post(endpoint + '/analyze')
        analysis = client.get(f'/workspaces/{wid}/documents').json()[0]['analysis']
        assert analysis['status'] == 'succeeded', analysis
        rows = client.get(endpoint + '/requirements').json()
        quantities = [r for r in rows if r.get('quantity_conditions')]
        assert len(quantities) == 2
        assert all(r['quantity_conditions'][0]['count'] == 10 for r in quantities)
        assert all(r['numeric_conditions'][0]['operator'] == 'unspecified' for r in quantities)
        rows = [r for r in rows if not r.get('quantity_conditions')]
        # Identical technical text applies to two products, so it must not collapse.
        assert len(rows) == 2 and rows[0]['text'] == rows[1]['text']
        assert len({row['id'] for row in rows}) == 2
        pages = {p['page']: p['text'] for p in client.get(endpoint + '/pages').json()}
        scopes = set()
        for row in rows:
            assert row['page'] == 1
            assert row['requires_human_review'] is True
            assert row['review_status'] == 'awaiting_review'
            assert row['review_reasons']
            for context in row['source_context']:
                assert context['source_document_id'] == doc['id']
                assert context['page'] == 1
                assert context['source_url'].endswith('/file#page=1')
                assert pages[1][context['start_offset']:context['end_offset']] == context['text']
                if context['kind'] == 'product_scope':
                    scopes.add(context['text'])
            condition = row['numeric_conditions'][0]
            assert condition['value_text'] == '8' and condition['operator'] == '>='
            assert condition['page'] == 1 and condition['source_document_id'] == doc['id']
            assert condition['quote'] in pages[1]
        assert scopes == {'Configuration A', 'Configuration B'}
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ExtractionBatchCache)) == 4


def test_cache_is_append_only_and_cannot_cross_workspaces(database, tmp_path):
    engine, sessions = database
    app = create_app(config(tmp_path), engine)
    app.state.nemotron_factory = provider_factory('success', [])
    with TestClient(base_url='http://127.0.0.1:8000', app=app, client=('127.0.0.1', 1)) as client:
        wid = workspace(client)
        other = workspace(client)
        doc = upload(client, wid).json()
        client.post(f"/workspaces/{wid}/documents/{doc['id']}/analyze")
    with sessions() as db:
        cached = db.scalar(select(ExtractionBatchCache))
        cache_id = cached.id
        fields = {name: getattr(cached, name) for name in ('analysis_id', 'source_span_id', 'model_run_id', 'fingerprint', 'result')}
        cached.result = {'changed': True}
        with pytest.raises(ValueError, match='append-only'):
            db.commit()
        db.rollback()
    with sessions() as db:
        db.add(ExtractionBatchCache(workspace_id=other, **fields))
        with pytest.raises(IntegrityError, match='FOREIGN KEY'):
            db.commit()
        db.rollback()
    for statement in ('UPDATE extraction_batch_cache SET result = :value WHERE id = :id',
                      'DELETE FROM extraction_batch_cache WHERE id = :id'):
        with engine.connect() as connection:
            with pytest.raises(IntegrityError, match='append-only'):
                connection.execute(text(statement), {'id': cache_id, 'value': '{}'})
            connection.rollback()


@pytest.mark.asyncio
async def test_cached_output_is_revalidated_before_reuse(database, tmp_path):
    engine, sessions = database
    settings = config(tmp_path)
    app = create_app(settings, engine)
    app.state.nemotron_factory = provider_factory('success', [])
    with TestClient(base_url='http://127.0.0.1:8000', app=app, client=('127.0.0.1', 1)) as client:
        wid = workspace(client)
        doc = upload(client, wid).json()
        client.post(f"/workspaces/{wid}/documents/{doc['id']}/analyze")
    changed = settings.model_copy(update={'nebius_max_output_tokens': settings.nebius_max_output_tokens + 1})
    with sessions.begin() as db:
        cached = db.scalar(select(ExtractionBatchCache))
        span = db.get(SourceSpan, cached.source_span_id)
        batch = plan_batches(span.text)[0]
        malformed = deepcopy(cached.result)
        malformed['extraction']['batch']['requirements'][0]['statement'] = 'Fabricated condition absent from source.'
        db.add(ExtractionBatchCache(workspace_id=wid, analysis_id=cached.analysis_id,
            source_span_id=span.id, model_run_id=cached.model_run_id,
            fingerprint=batch_fingerprint(span, batch, changed), result=malformed))
        analysis_id = cached.analysis_id
    class NeverCalled:
        async def extract_requirements(self, _):
            raise AssertionError('Invalid checkpoint must fail safely, not silently consume another provider call')
    with pytest.raises(IntegrationError) as raised:
        await extract_checkpoint(analysis_id, span, batch, sessions, changed, NeverCalled())
    assert raised.value.code == 'invalid_checkpoint'


def test_cache_migration_preserves_legacy_model_runs(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    monkeypatch.setenv('DATABASE_URL', url)
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(cfg, '0009_model_run_context')
    engine = build_engine(url)
    with engine.begin() as connection:
        now = datetime.now(timezone.utc)
        connection.execute(text("INSERT INTO workspaces (id, title, supplier_name, revision, created_at) VALUES ('w', 'Tender', 'Supplier', 1, :now)"), {'now': now})
        connection.execute(text("INSERT INTO model_runs (id, workspace_id, model, operation, duration_ms, outcome, created_at) VALUES ('old', 'w', 'legacy', 'extraction', 10, 'succeeded', :now)"), {'now': now})
    engine.dispose()
    command.upgrade(cfg, 'head')
    engine = build_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT model, outcome FROM model_runs WHERE id='old'")).one() == ('legacy', 'succeeded')
        assert connection.execute(text('SELECT count(*) FROM extraction_batch_cache')).scalar_one() == 0
    engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize('unsupported_kind', ['numeric', 'date'])
def test_unresolved_line_condition_persists_literal_clause_for_review_only(database, tmp_path, unsupported_kind):
    """A failed interpretation cannot become a verified fact or amendment key."""
    from tenderready.models import RequirementVersion, ReviewDecision
    from tenderready.verification import threshold_sentence
    from test_verification import pdf, send_pdf

    engine, sessions = database
    settings = config(tmp_path, nebius_extraction_format='line_refs')
    app = create_app(settings, engine)
    statement = 'The Atlas A14 product must have at least 32 GB RAM.'
    calls = []

    def factory(current):
        configured = current.model_copy(update={'nebius_api_key': Settings(_env_file=None, nebius_api_key='test-only').nebius_api_key})
        def respond(request):
            if request.url.path.endswith('/models'):
                return httpx.Response(200, json={'object': 'list', 'data': [
                    {'id': configured.nebius_model, 'created': 1, 'object': 'model', 'owned_by': 'nvidia'}]})
            body = json.loads(request.content)
            source = json.loads(body['messages'][1]['content'])
            line = next(item['line'] for item in source['lines'] if item['text'].strip() == statement)
            calls.append(len(body['messages']))
            numeric = [{'operator': '>=', 'value_text': '32', 'unit_text': 'GB'}]
            dates = []
            if unsupported_kind == 'numeric':
                numeric.append({'operator': '>=', 'value_text': '999', 'unit_text': 'GB'})
            else:
                dates.append({'relation': 'on_or_before', 'boundary_text': '2099-12-31'})
            # The model repeats the invalid condition even in the bounded repair.
            payload = {'requirements': [{'start_line': line, 'end_line': line,
                'category': 'numeric_threshold', 'obligation': 'mandatory',
                'numeric_conditions': numeric, 'date_conditions': dates,
                'confidence': 'high', 'review_reasons': []}], 'warnings': []}
            return httpx.Response(200, json={'id': 'test-only', 'created': 1, 'object': 'chat.completion', 'model': configured.nebius_model,
                'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(payload)}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}})
        return NemotronClient(configured, httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    app.state.nemotron_factory = factory
    with TestClient(base_url='http://127.0.0.1:8000', app=app, client=('127.0.0.1', 1)) as client:
        wid = workspace(client)
        doc = send_pdf(client, wid, pdf(statement))
        endpoint = f"/workspaces/{wid}/documents/{doc['id']}"
        client.post(endpoint + '/analyze')
        state = client.get(f'/workspaces/{wid}/documents').json()[0]['analysis']
        assert state['status'] == 'succeeded', state
        assert calls == [2, 4]  # Initial response then exactly one repair, no bypass on first response.
        rows = client.get(endpoint + '/requirements').json()
        assert len(rows) == 1
        row = rows[0]
        assert row['text'] == row['excerpt'] == statement
        assert row['source_document_id'] == doc['id'] and row['page'] == 1
        assert row['source_url'].endswith('/file#page=1')
        assert row['source_context'] == []
        assert row['confidence'] == 'low'
        assert row['requires_human_review'] is True
        assert row['review_status'] == 'awaiting_review'
        assert any(reason.startswith(f'Unresolved model interpretation: {unsupported_kind} condition') for reason in row['review_reasons'])
        assert row['date_conditions'] == []
        assert len(row['numeric_conditions']) == 1
        assert row['numeric_conditions'][0]['value_text'] == '32'
        assert row['numeric_conditions'][0]['quote'] == statement
        assert row['numeric_conditions'][0]['page'] == 1
        # Random UUIDs can contain 999; inspect semantic values, not identifiers.
        interpretation = json.dumps([row['text'], row['excerpt'], row['review_reasons'],
            [{k: c[k] for k in ('operator', 'value_text', 'unit_text', 'quote')} for c in row['numeric_conditions']],
            row['date_conditions']])
        assert '999' not in interpretation and '2099-12-31' not in interpretation
        with sessions() as db:
            req = db.get(RequirementVersion, row['id'])
            # This complete sentence would otherwise be eligible for automatic
            # threshold matching, but unresolved interpretation disables it.
            assert threshold_sentence(req) is None
            assert db.scalar(select(func.count()).select_from(ReviewDecision)) == 0
        send_pdf(client, wid, pdf('Model: Atlas A14\nRAM: 32 GB'), 'datasheet')
        result = client.post(f"/workspaces/{wid}/requirements/{row['id']}/verify",
                             json={'coverage_confirmed': True, 'reviewer': 'Test reviewer'})
        assert result.status_code == 201, result.text
        assessment = result.json()
        assert assessment['status'] == 'inconclusive'
        assert assessment['review_state'] == 'awaiting_review'
        assert assessment['officially_verified'] is False
        assert any(check.get('field') == 'interpretation' and check.get('outcome') == 'review'
                   for check in assessment['checks'])
