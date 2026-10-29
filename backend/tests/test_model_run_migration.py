"""Provider audit migration preserves pre-existing immutable history."""
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tenderready.config import get_settings
from tenderready.db import build_engine


def test_model_run_context_migration_preserves_legacy_run(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    monkeypatch.setenv('DATABASE_URL', url)
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(cfg, '0008_workspace_management')
    engine = build_engine(url)
    with engine.begin() as connection:
        now = datetime.now(timezone.utc)
        connection.execute(text("INSERT INTO workspaces (id, title, supplier_name, revision, created_at) VALUES (:id, 'Tender', 'Supplier', 1, :now)"), {'id':'w', 'now':now})
        connection.execute(text("INSERT INTO model_runs (id, workspace_id, model, operation, duration_ms, outcome, created_at) VALUES ('old', 'w', 'legacy', 'extraction', 10, 'succeeded', :now)"), {'now':now})
    engine.dispose()
    command.upgrade(cfg, 'head')
    engine = build_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT model, outcome FROM model_runs WHERE id='old'")).one() == ('legacy', 'succeeded')
        assert connection.execute(text('SELECT count(*) FROM model_run_contexts')).scalar_one() == 0
    engine.dispose()
    get_settings.cache_clear()
