"""API-to-database acceptance test; provider transport is deliberately simulated."""
import json
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from tenderready.api import create_app
from tenderready.amendments import safe_grammar
from tenderready.verification import condition_criterion
from tenderready.config import Settings
from tenderready.models import ModelRun
from tenderready.nebius import NemotronClient
from test_documents import config, workspace
from test_verification import pdf, send_pdf


def fixture_provider(settings):
    settings = settings.model_copy(update={'nebius_api_key': Settings(_env_file=None, nebius_api_key='fixture-only').nebius_api_key})

    def respond(request):
        if request.url.path.endswith('/models'):
            return httpx.Response(200, json={'object':'list', 'data':[{'id':settings.nebius_model, 'object':'model', 'created':1, 'owned_by':'nvidia'}]})
        source = json.loads(json.loads(request.content)['messages'][1]['content'])['sources'][0]
        statement = 'The product must have at least 32 GB RAM.'
        rows = []
        if statement in source['text']:
            rows = [{'statement':statement, 'category':'numeric_threshold', 'obligation':'mandatory',
                     'citations':[{'source_id':source['source_id'], 'quote':statement}], 'obligation_quote':statement,
                     'numeric_conditions':[{'operator':'>=', 'value_text':'32', 'unit_text':'GB', 'quote':statement}],
                     'date_conditions':[], 'confidence':'high', 'review_reasons':[]}]
        payload = {'requirements':rows, 'warnings':[]}
        return httpx.Response(200, json={'id':'fixture', 'object':'chat.completion', 'created':1, 'model':settings.nebius_model,
            'choices':[{'index':0, 'finish_reason':'stop', 'message':{'role':'assistant', 'content':json.dumps(payload)}}],
            'usage':{'prompt_tokens':20, 'completion_tokens':10, 'total_tokens':30}})

    return NemotronClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(respond)))


def test_source_linked_ai_condition_flows_to_deterministic_assessment(database, tmp_path):
    engine, sessions = database
    app = create_app(config(tmp_path), engine)
    app.state.nemotron_factory = fixture_provider
    with TestClient(base_url='http://127.0.0.1:8000', app=app, client=('127.0.0.1', 1)) as client:
        wid = workspace(client)
        tender = send_pdf(client, wid, pdf('Synthetic tender cover', 'The product must have at least 32 GB RAM.'))
        endpoint = f'/workspaces/{wid}/documents/{tender["id"]}'
        assert client.post(endpoint + '/analyze').status_code == 202
        rows = client.get(endpoint + '/requirements').json()
        assert len(rows) == 1
        req = rows[0]
        assert req['source_document_id'] == tender['id'] and req['page'] == 2
        assert req['excerpt'] == 'The product must have at least 32 GB RAM.'
        assert req['review_status'] == 'awaiting_review'
        condition = req['numeric_conditions'][0]
        assert (condition['operator'], condition['value_text'], condition['unit_text'], condition['quote']) == ('>=', '32', 'GB', req['excerpt'])
        assert condition['source_document_id'] == tender['id'] and condition['page'] == 2
        assert condition['source_url'].endswith('#page=2')
        send_pdf(client, wid, pdf('Model: Atlas A14\nRAM: 16 GB'), 'datasheet')
        result = client.post(f'/workspaces/{wid}/requirements/{req["id"]}/verify', json={'coverage_confirmed':True, 'reviewer':'Test reviewer'})
        assert result.status_code == 201, result.text
        assessment = result.json()
        assert assessment['status'] == 'conflicting'
        check = next(c for c in assessment['checks'] if c.get('field') == 'ram_gb' and c.get('outcome') == 'conflict')
        assert '32' in check['rationale'] and '16 GB' in check['rationale']
        assert check['method'] == 'deterministic' and check['sources'][0]['page'] == 1
        with sessions() as db:
            runs = db.scalars(select(ModelRun).where(ModelRun.workspace_id == wid)).all()
            assert runs and all(run.outcome == 'succeeded' and run.model == config(tmp_path).nebius_model for run in runs)
            assert sum(run.input_tokens for run in runs) == 40


def test_ai_prose_is_not_treated_as_complete_amendment_transfer_grammar():
    statement = 'The product must have at least 32 GB RAM.'
    req = SimpleNamespace(statement=statement, condition={'numeric_conditions':[{'operator':'>=', 'value_text':'32', 'unit_text':'GB', 'quote':statement}]})
    assert not safe_grammar(req)


def test_positive_fragment_does_not_hide_a_negated_requirement():
    statement = 'The product must not have at least 32 GB RAM.'
    condition = {'operator':'>=', 'value_text':'32', 'unit_text':'GB', 'quote':'at least 32 GB RAM'}
    req = SimpleNamespace(statement=statement, condition={'numeric_conditions':[condition]})
    assert condition_criterion(req, condition, 'numeric') is None
