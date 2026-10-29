from fastapi.testclient import TestClient
from sqlalchemy import text
from tenderready.api import create_app
from tenderready.config import Settings


def test_integrity_error_is_sanitized_and_next_request_succeeds(database):
    engine, _ = database
    # A real temporary DB constraint exercises failure and rollback without
    # replacing API responses or database calls with mocks.
    with engine.begin() as db:
        db.execute(text("CREATE UNIQUE INDEX test_unique_title ON workspaces(title)"))
    config = Settings(_env_file=None, app_api_token="", app_env="development")
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config, engine), client=("127.0.0.1", 50001)) as client:
        body = {"title": "Private title", "supplier_name": "Private supplier"}
        assert client.post("/workspaces", json=body).status_code == 201
        failed = client.post("/workspaces", json=body)
        assert failed.status_code == 409
        assert failed.json()["error"]["code"] == "conflict"
        assert "Private" not in failed.text and "UNIQUE" not in failed.text
        assert client.post("/workspaces", json={**body, "title": "Second title"}).status_code == 201
        assert len(client.get("/workspaces").json()) == 2


def test_untrusted_browser_origin_denied_even_on_loopback(database):
    engine, _ = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(Settings(_env_file=None), engine), client=("127.0.0.1", 50001)) as client:
        response = client.post("/workspaces", headers={"Origin": "https://untrusted.example"},
                               json={"title": "T", "supplier_name": "S"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
        assert client.get("/workspaces").json() == []


def test_response_metadata_and_no_cache(database):
    engine, _ = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(Settings(_env_file=None), engine), client=("127.0.0.1", 50001)) as client:
        response = client.post("/workspaces", json={"title": "T", "supplier_name": "S"})
        assert response.headers["Location"] == f"/workspaces/{response.json()['id']}"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["created_at"].endswith("Z")
