"""Full real persistence workflow, deliberately no provider calls."""
import importlib.util
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tenderready.api import create_app
from tenderready.models import ModelRun, ReviewDecision, DocumentVersion
from test_documents import config, workspace
from test_verification import pdf, send_pdf

spec = importlib.util.spec_from_file_location('offline_acceptance', Path(__file__).parents[1] / 'scripts/offline_acceptance.py')
scenario = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scenario)


def test_complete_offline_workflow_preserves_history_without_fabricating_ai(database, tmp_path):
    engine, sessions = database
    app = create_app(config(tmp_path), engine)
    def forbidden_provider(*args):
        pytest.fail('Offline samples must never invoke or substitute for the AI provider')
    app.state.nemotron_factory = forbidden_provider
    with TestClient(app, base_url='http://127.0.0.1:8000', client=('127.0.0.1', 1)) as client:
        result = scenario.run(client)
        assert result['replacement_resolved'] and result['review_complete']
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ModelRun)) == 0
        assert db.scalar(select(func.count()).select_from(ReviewDecision)) >= 5
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 5


@pytest.mark.parametrize('label,expected', [
    ('Obligation: mandatory', 'mandatory'), ('Obligation: optional', 'optional'), ('', 'unclear'),
    ('Obligation: probably mandatory', None), ('Obligation: mandatory\nObligation: optional', None),
])
def test_labelled_obligation_requires_explicit_single_source_label(database, tmp_path, label, expected):
    engine, _ = database
    with TestClient(create_app(config(tmp_path), engine), base_url='http://127.0.0.1:8000', client=('127.0.0.1', 1)) as client:
        wid = workspace(client)
        doc = send_pdf(client, wid, pdf('Requirement ID: RAM-01\n' + (label+'\n' if label else '') + 'Model: Atlas A14\nRAM: at least 32 GB\nEnd requirement'))
        base = f'/workspaces/{wid}/documents/{doc["id"]}'
        response = client.post(base + '/extract-labelled')
        if expected is None:
            assert response.status_code == 422
            assert client.get(base + '/requirements').json() == []
        else:
            assert response.status_code == 200
            row = client.get(base + '/requirements').json()[0]
            assert row['obligation'] == expected and row['confidence'] == 'deterministic'


def test_live_acceptance_without_key_reports_blocker_before_any_network(monkeypatch, capsys):
    live_spec = importlib.util.spec_from_file_location('live_ram_acceptance', Path(__file__).parents[1] / 'scripts/live_ram_acceptance.py')
    live = importlib.util.module_from_spec(live_spec)
    live_spec.loader.exec_module(live)
    from tenderready.config import Settings
    monkeypatch.setattr(live, 'Settings', lambda: Settings(_env_file=None, nebius_api_key=''))
    monkeypatch.setattr(live.httpx, 'Client', lambda **kwargs: pytest.fail('Missing credentials must fail before network access'))
    assert live.main() == 2
    assert 'BLOCKED' in capsys.readouterr().out
