"""Real migrated SQLite/API tests; no HTTP or database response mocks."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from tenderready.api import create_app
from tenderready.config import Settings
from tenderready.db import build_engine


LOCAL_CLIENT = ("127.0.0.1", 50000)
REMOTE_CLIENT = ("203.0.113.20", 50000)
TOKEN = "foundation-test-access-token-32-characters"


def settings(**overrides):
    return Settings(_env_file=None, app_env="development", app_api_token="",
                    nebius_api_key="", nebius_model="", **overrides)


def assert_error(response, status):
    assert response.status_code == status, response.text
    envelope = response.json()
    assert set(envelope) == {"error"}
    assert set(envelope["error"]) == {"code", "message", "details"}
    assert isinstance(envelope["error"]["code"], str)
    assert isinstance(envelope["error"]["message"], str)


def test_create_list_get_persist_after_restarting_application(database):
    engine, _ = database
    database_url = str(engine.url)
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), engine), client=LOCAL_CLIENT) as client:
        created = client.post("/workspaces", json={
            "title": "  School laptop procurement  ",
            "supplier_name": "  Example IT Hardware Ltd  ",
        })
        assert created.status_code == 201
        workspace = created.json()
        assert workspace["title"] == "School laptop procurement"
        assert workspace["supplier_name"] == "Example IT Hardware Ltd"
        assert workspace["revision"] == 1
        assert workspace["created_at"]
        assert client.get(f"/workspaces/{workspace['id']}").json() == workspace

    # A fresh engine/app cannot obtain this row from an in-memory fake.
    restarted_engine = build_engine(database_url)
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), restarted_engine), client=LOCAL_CLIENT) as restarted:
        assert restarted.get(f"/workspaces/{workspace['id']}").json() == workspace
        assert restarted.get("/workspaces").json() == [workspace]
    readback_engine = build_engine(database_url)
    try:
        with readback_engine.connect() as connection:
            row = connection.execute(text("SELECT title, supplier_name FROM workspaces WHERE id = :id"),
                                     {"id": workspace["id"]}).one()
            assert tuple(row) == ("School laptop procurement", "Example IT Hardware Ltd")
    finally:
        readback_engine.dispose()


@pytest.mark.parametrize("payload", [
    {"title": "  ", "supplier_name": "Supplier"},
    {"title": "Tender", "supplier_name": " "},
    {"title": "a" * 201, "supplier_name": "Supplier"},
    {"title": "Tender", "supplier_name": "a" * 201},
    {"title": 123, "supplier_name": "Supplier"},
    {"title": "Tender", "supplier_name": None},
    {"title": "Tender\nsecond line", "supplier_name": "Supplier"},
    {"title": "Tender", "supplier_name": "Supplier\u0085hidden"},
    {"title": "Tender", "supplier_name": "Supplier", "owner_id": "injected"},
    {"title": "Tender"},
])
def test_invalid_workspace_inputs_are_rejected_without_persistence(database, payload):
    engine, _ = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), engine), client=LOCAL_CLIENT) as client:
        response = client.post("/workspaces", json=payload)
        assert_error(response, 422)
        assert "injected" not in response.text
        assert client.get("/workspaces").json() == []


def test_unknown_and_malformed_workspace_ids(database):
    engine, _ = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), engine), client=LOCAL_CLIENT) as client:
        assert_error(client.get(f"/workspaces/{uuid4()}"), 404)
        assert_error(client.get("/workspaces/not-a-uuid"), 422)
        assert_error(client.get("/does-not-exist"), 404)


def test_paginated_listing_preserves_existing_array_contract(database):
    engine, _ = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), engine), client=LOCAL_CLIENT) as client:
        created = [client.post("/workspaces", json={"title": f"Tender {i}", "supplier_name": "Supplier"}).json()
                   for i in range(3)]
        page = client.get("/workspaces?limit=1&offset=1")
        assert page.status_code == 200
        assert isinstance(page.json(), list)
        assert page.json()[0]["id"] == created[1]["id"]
        for query in ("limit=0", "limit=101", "offset=-1", "offset=10001", "limit=invalid"):
            assert_error(client.get(f"/workspaces?{query}"), 422)


def test_configured_token_protects_all_workspace_operations(database):
    engine, _ = database
    configured = Settings(_env_file=None, app_env="development", app_api_token=TOKEN)
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(configured, engine), client=REMOTE_CLIENT) as client:
        assert client.get("/health").status_code == 200
        for path in ("/ready", "/workspaces", f"/workspaces/{uuid4()}"):
            assert_error(client.get(path), 401)
            assert_error(client.get(path, headers={"Authorization": "Bearer wrong"}), 401)
            assert_error(client.get(path, headers={b"Authorization": b"Bearer \xff"}), 401)
        assert_error(client.post("/workspaces", json={"title": "T", "supplier_name": "S"}), 401)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        created = client.post("/workspaces", headers=headers, json={"title": "T", "supplier_name": "S"})
        assert created.status_code == 201
        assert client.get("/workspaces", headers=headers).json()[0]["id"] == created.json()["id"]
        assert client.get(f"/workspaces/{created.json()['id']}", headers=headers).status_code == 200


def test_remote_development_access_cannot_spoof_loopback(database):
    engine, _ = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), engine), client=REMOTE_CLIENT) as client:
        headers = {"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1", "Host": "localhost"}
        assert_error(client.get("/workspaces", headers=headers), 403)
        assert_error(client.post("/workspaces", headers=headers, json={"title": "T", "supplier_name": "S"}), 403)


@pytest.mark.parametrize("token", ["", "short"])
def test_production_requires_nontrivial_access_token(token):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", app_api_token=token)


def test_production_accepts_configured_access_token():
    configured = Settings(_env_file=None, app_env="production", app_api_token=TOKEN)
    assert configured.app_env == "production"


def test_missing_schema_returns_consistent_sanitized_errors(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), engine), client=LOCAL_CLIENT, raise_server_exceptions=False) as client:
        for response in (
            client.get("/ready"),
            client.get("/workspaces"),
            client.post("/workspaces", json={"title": "Private tender title", "supplier_name": "Private supplier"}),
        ):
            assert_error(response, 503)
            assert "SELECT" not in response.text and "INSERT" not in response.text
            assert "no such table" not in response.text
            assert "Private tender title" not in response.text


def test_readiness_rejects_outdated_migration_revision(database):
    engine, _ = database
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '7f509ab5bc0d'"))
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), engine), client=LOCAL_CLIENT) as client:
        assert_error(client.get("/ready"), 503)


def test_readiness_accepts_fresh_migrations(database):
    engine, _ = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings(), engine), client=LOCAL_CLIENT) as client:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["database"] == "ready"
