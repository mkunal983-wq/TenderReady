from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from tenderready.db import build_engine, build_session_factory


@pytest.fixture
def database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    from tenderready.config import get_settings
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    engine = build_engine(url)
    yield engine, build_session_factory(engine)
    engine.dispose()
    get_settings.cache_clear()
