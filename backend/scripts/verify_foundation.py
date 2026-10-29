"""Exercise real HTTP, migrations and restart persistence using disposable data.

Run with the project Python environment: python scripts/verify_foundation.py
No API responses, database calls, or subprocesses are mocked. The script opens
an ephemeral loopback port, so it needs permission to bind local sockets.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx


BACKEND = Path(__file__).resolve().parents[1]


def expect(response, status):
    if response.status_code != status:
        raise RuntimeError(f"Expected HTTP {status}, received {response.status_code}")
    return response.json()


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def start(environment, port, log):
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tenderready.api:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--no-proxy-headers"],
        cwd=BACKEND, env=environment, stdout=log, stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 15
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("The API subprocess exited before readiness")
            try:
                if client.get("/health").status_code == 200:
                    return process
            except httpx.TransportError:
                pass
            time.sleep(0.1)
    stop(process)
    raise RuntimeError("API startup timed out")


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix="tenderready-foundation-") as directory:
        root = Path(directory)
        database = root / "foundation.db"
        token = secrets.token_urlsafe(36)
        environment = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{database}",
            "APP_ENV": "production",
            "APP_API_TOKEN": token,
            "NEBIUS_API_KEY": "",
            "NEBIUS_MODEL": "",
            "PYTHONPATH": str(BACKEND / "src"),
        }
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"],
            cwd=BACKEND, env=environment, check=True, capture_output=True, text=True,
        )
        checks.append("fresh_migrations_applied")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with (root / "api.log").open("w") as log:
            process = start(environment, port, log)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False) as client:
                    expect(client.get("/workspaces"), 401)
                    checks.append("unauthenticated_access_denied")
                    client.headers["Authorization"] = f"Bearer {token}"
                    expect(client.get("/ready"), 200)
                    created = expect(client.post("/workspaces", json={
                        "title": "Restart persistence smoke tender", "supplier_name": "Synthetic Test Supplier"
                    }), 201)
                    assert created["id"]
                    assert expect(client.get(f"/workspaces/{created['id']}"), 200)["id"] == created["id"]
                    assert expect(client.get("/workspaces"), 200)[0]["id"] == created["id"]
                    checks.append("http_create_list_retrieve")
                    expect(client.get("/workspaces/not-a-uuid"), 422)
                    expect(client.get(f"/workspaces/{uuid4()}"), 404)
                    expect(client.post("/workspaces", json={"title": " ", "supplier_name": "S"}), 422)
                    checks.append("validation_and_not_found")
            finally:
                stop(process)

            process = start(environment, port, log)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False,
                                  headers={"Authorization": f"Bearer {token}"}) as client:
                    persisted = expect(client.get(f"/workspaces/{created['id']}"), 200)
                    assert persisted == created
                checks.append("http_persistence_after_process_restart")
                with sqlite3.connect(database) as connection:
                    row = connection.execute("SELECT title, supplier_name FROM workspaces WHERE id = ?", (created["id"],)).fetchone()
                    assert row == ("Restart persistence smoke tender", "Synthetic Test Supplier")
                    assert connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
                checks.append("independent_sqlite_readback")
            finally:
                stop(process)
    print(json.dumps({"status": "passed", "database": "temporary file-backed SQLite",
                      "transport": "real loopback HTTP", "checks": checks,
                      "provider_calls": 0, "temporary_resources_cleaned": True}, indent=2))


if __name__ == "__main__":
    main()
