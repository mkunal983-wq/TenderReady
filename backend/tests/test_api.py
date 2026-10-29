from fastapi.testclient import TestClient
from tenderready.api import create_app
from tenderready.config import Settings


def test_workspace_roundtrip_and_health(database):
    engine, _ = database
    app = create_app(Settings(_env_file=None, nebius_api_key="", nebius_model="", app_api_token=""), engine)
    with TestClient(base_url="http://127.0.0.1:8000", app=app, client=("127.0.0.1", 50000)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").json()["inference"] == "not_configured"
        response = client.post("/workspaces", json={"title": "Laptop procurement", "supplier_name": "Example Supplier"})
        assert response.status_code == 201
        assert response.json()["revision"] == 1
        assert client.get("/workspaces").json()[0]["id"] == response.json()["id"]
        assert client.post("/workspaces", json={"title": "  ", "supplier_name": "A"}).status_code == 422


def test_token_guard(database):
    engine, _ = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(Settings(_env_file=None, app_api_token="private-test-token"), engine)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/workspaces").status_code == 401
        assert client.get("/workspaces", headers={"Authorization": "Bearer private-test-token"}).status_code == 200
