"""Real PDF/storage/database tests; provider transport is stubbed ONLY in tests."""
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select, func

from tenderready.api import create_app
from tenderready.config import Settings
from tenderready.models import DocumentPage, DocumentVersion, RequirementVersion, SourceSpan, DocumentAnalysis, ModelRun, ModelRunContext
from tenderready.nebius import NemotronClient
from tenderready.pdf_parse import PDFError, parse_pdf

SAMPLE = Path(__file__).parents[2] / "samples" / "sample-tender.pdf"


def config(tmp_path, **kwargs):
    return Settings(_env_file=None, storage_dir=tmp_path / "storage", app_api_token="",
                    nebius_api_key="", **kwargs)


def workspace(client):
    return client.post("/workspaces", json={"title": "Sample tender", "supplier_name": "Sample Supplier"}).json()["id"]


def upload(client, wid, data=None, name="tender.pdf"):
    return client.post(f"/workspaces/{wid}/documents", content=SAMPLE.read_bytes() if data is None else data,
                       headers={"Content-Type": "application/pdf", "X-Filename": name})


def test_pdf_parser_preserves_pages_and_text():
    parsed = parse_pdf(SAMPLE, 40, 160000)
    assert [p["page"] for p in parsed["pages"]] == [1, 2]
    assert "at least INR\n1,500,000" in parsed["pages"][0]["text"]
    assert "30 November 2026" in parsed["pages"][1]["text"]
    assert parsed["warnings"] == []


def test_pdf_parser_rejects_encryption_scan_and_malformed(tmp_path):
    encrypted = tmp_path / "encrypted.pdf"
    writer = PdfWriter(); writer.append(SAMPLE); writer.encrypt("password"); writer.write(encrypted)
    with pytest.raises(PDFError, match="Encrypted"):
        parse_pdf(encrypted, 40, 160000)
    blank = tmp_path / "blank.pdf"
    writer = PdfWriter(); writer.add_blank_page(width=600, height=800); writer.write(blank)
    with pytest.raises(PDFError, match="No extractable"):
        parse_pdf(blank, 40, 160000)
    bad = tmp_path / "bad.pdf"; bad.write_bytes(b"%PDF-not-real")
    with pytest.raises(PDFError, match="malformed"):
        parse_pdf(bad, 40, 160000)
    with pytest.raises(PDFError, match="pages"):
        parse_pdf(SAMPLE, 1, 160000)


def test_mixed_blank_page_warns_with_actual_page_number(tmp_path):
    path = tmp_path / "mixed.pdf"
    writer = PdfWriter(); writer.append(SAMPLE); writer.add_blank_page(width=600, height=800); writer.write(path)
    result = parse_pdf(path, 40, 160000)
    assert len(result["pages"]) == 3
    assert "Page 3" in result["warnings"][0]


def test_upload_persists_versions_pages_spans_and_original_file(database, tmp_path):
    engine, sessions = database
    settings = config(tmp_path)
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings, engine), client=("127.0.0.1", 1)) as client:
        wid = workspace(client)
        first = upload(client, wid, name="..%2F..%2Ftender.pdf")
        assert first.status_code == 201, first.text
        doc = first.json()
        assert doc["filename"] == "tender.pdf" and doc["version"] == 1 and doc["page_count"] == 2
        second = upload(client, wid).json()
        assert second["version"] == 2 and second["document_key"] == doc["document_key"]
        source = client.get(f"/workspaces/{wid}/documents/{doc['id']}/file")
        assert source.content == SAMPLE.read_bytes()
        assert client.get(f"/workspaces/{wid}/documents/{doc['id']}/requirements").json() == []
        assert len(client.get(f"/workspaces/{wid}/documents").json()) == 2
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentPage)) == 4
        spans = db.scalars(select(SourceSpan)).all()
        assert {s.page for s in spans} == {1, 2}
        assert all(s.workspace_id == wid for s in spans)
        stored = db.get(DocumentVersion, doc["id"])
        assert settings.storage_dir.joinpath(stored.storage_key).read_bytes() == SAMPLE.read_bytes()
        assert settings.storage_dir.joinpath(stored.storage_key).stat().st_mode & 0o777 == 0o600


def test_upload_validation_and_failed_files_cleaned(database, tmp_path):
    engine, sessions = database
    settings = config(tmp_path, upload_max_bytes=1024)
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings, engine), client=("127.0.0.1", 1)) as client:
        wid = workspace(client)
        assert upload(client, wid).status_code == 413
        assert upload(client, wid, b"hello").status_code == 415
        assert upload(client, wid, b"%PDF-broken").status_code == 422
        assert upload(client, wid, b"test", name="a.txt").status_code == 415
        assert upload(client, str(uuid4()), b"test").status_code == 404
    assert list(settings.storage_dir.glob("*")) == []
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 0


def test_cross_workspace_and_access_control(database, tmp_path):
    engine, _ = database
    app = create_app(config(tmp_path), engine)
    with TestClient(base_url="http://127.0.0.1:8000", app=app, client=("127.0.0.1", 1)) as client:
        a, b = workspace(client), workspace(client)
        doc = upload(client, a).json()
        for suffix in ("file", "requirements"):
            assert client.get(f"/workspaces/{b}/documents/{doc['id']}/{suffix}").status_code == 404
        assert client.post(f"/workspaces/{b}/documents/{doc['id']}/analyze").status_code == 404
    with TestClient(base_url="http://127.0.0.1:8000", app=app, client=("203.0.113.1", 1)) as remote:
        assert remote.get(f"/workspaces/{a}/documents").status_code == 403
        assert upload(remote, a).status_code == 403


def provider_factory(responses, calls):
    def factory(settings):
        configured = settings.model_copy(update={"nebius_api_key": Settings(_env_file=None, nebius_api_key="test-only").nebius_api_key})
        def transport(request):
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"object": "list", "data": [{"id": configured.nebius_model, "created": 1, "object": "model", "owned_by": "nvidia"}]})
            body = json.loads(request.content)
            source = json.loads(body["messages"][1]["content"])["sources"][0]
            calls.append(source)
            if responses == "rate_limit":
                return httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"message": "PRIVATE"}})
            if responses == "second_page_failure" and "30 November" in source["text"]:
                return httpx.Response(401, json={"error": {"message": "PRIVATE"}})
            statement = next(line for line in source["text"].splitlines() if "must" in line)
            payload = {"requirements": [{"statement": statement, "category": "required_information",
                "obligation": "mandatory", "obligation_quote": statement,
                "citations": [{"source_id": source["source_id"], "quote": statement}],
                "numeric_conditions": [], "date_conditions": [], "confidence": "medium", "review_reasons": []}], "warnings": []}
            return httpx.Response(200, json={"id": "fixture", "created": 1, "object": "chat.completion", "model": configured.nebius_model,
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(payload)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}})
        return NemotronClient(configured, httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    return factory


def test_analysis_full_persistence_with_explicit_provider_fixture(database, tmp_path):
    engine, sessions = database
    app = create_app(config(tmp_path), engine)
    calls = []; app.state.nemotron_factory = provider_factory("success", calls)
    with TestClient(base_url="http://127.0.0.1:8000", app=app, client=("127.0.0.1", 1)) as client:
        wid = workspace(client); doc = upload(client, wid).json()
        endpoint = f"/workspaces/{wid}/documents/{doc['id']}"
        assert client.post(endpoint + "/analyze").status_code == 202
        status = client.get(f"/workspaces/{wid}/documents").json()[0]["analysis"]
        assert status["status"] == "succeeded", status
        rows = client.get(endpoint + "/requirements").json()
        assert len(rows) == 2 and {r["page"] for r in rows} == {1, 2}
        assert all(r["review_status"] == "awaiting_review" and r["review_reasons"] for r in rows)
        assert all(r["text"] == r["excerpt"] for r in rows)
        client.post(endpoint + "/analyze")
        assert len(calls) == 2  # Success is idempotent: no repeated inference or rows.
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(RequirementVersion)) == 2
        runs = db.scalars(select(ModelRun).order_by(ModelRun.created_at)).all()
        contexts = db.scalars(select(ModelRunContext).order_by(ModelRunContext.created_at)).all()
        assert len(runs) == len(contexts) == 2
        assert all(r.outcome == 'succeeded' and r.input_tokens == 100 and r.output_tokens == 100 for r in runs)
        assert all(c.attempts == 1 and c.error_code is None and c.completed_at >= c.started_at for c in contexts)
        assert {c.model_run_id for c in contexts} == {r.id for r in runs}
        assert all(db.get(SourceSpan, c.source_span_id).document_version_id == doc['id'] for c in contexts)
        for req in db.scalars(select(RequirementVersion)):
            span = db.get(SourceSpan, req.source_span_id)
            assert req.statement in span.text and span.document_version_id == doc["id"]


@pytest.mark.parametrize("failure,code", [("rate_limit", "rate_limited"), ("second_page_failure", "provider_auth")])
def test_analysis_failure_does_not_publish_partial_requirements(database, tmp_path, failure, code):
    engine, sessions = database
    app = create_app(config(tmp_path), engine)
    calls = []; app.state.nemotron_factory = provider_factory(failure, calls)
    with TestClient(base_url="http://127.0.0.1:8000", app=app, client=("127.0.0.1", 1)) as client:
        wid = workspace(client); doc = upload(client, wid).json()
        endpoint = f"/workspaces/{wid}/documents/{doc['id']}"
        client.post(endpoint + "/analyze")
        state = client.get(f"/workspaces/{wid}/documents").json()[0]["analysis"]
        assert state["status"] == "failed" and state["error_code"] == code
        assert "PRIVATE" not in state["error_message"]
        assert client.get(endpoint + "/requirements").json() == []
        with sessions() as db:
            runs = db.scalars(select(ModelRun).order_by(ModelRun.created_at)).all()
            contexts = db.scalars(select(ModelRunContext).order_by(ModelRunContext.created_at)).all()
            assert len(runs) == len(contexts) == (2 if failure == 'second_page_failure' else 1)
            assert runs[-1].outcome == 'failed' and contexts[-1].error_code == code
            assert contexts[-1].attempts is None
            if failure == 'second_page_failure':
                assert runs[0].outcome == 'succeeded'
        app.state.nemotron_factory = provider_factory("success", [])
        client.post(endpoint + "/analyze")
        assert len(client.get(endpoint + "/requirements").json()) == 2


def test_missing_key_retains_uploaded_document(database, tmp_path):
    engine, sessions = database
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(config(tmp_path), engine), client=("127.0.0.1", 1)) as client:
        wid = workspace(client); doc = upload(client, wid).json()
        client.post(f"/workspaces/{wid}/documents/{doc['id']}/analyze")
        state = client.get(f"/workspaces/{wid}/documents").json()[0]["analysis"]
        assert state["status"] == "failed" and state["error_code"] == "not_configured"
        assert client.get(f"/workspaces/{wid}/documents/{doc['id']}/file").content == SAMPLE.read_bytes()
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ModelRun)) == 0


def test_streaming_upload_size_limit_without_content_length(database, tmp_path):
    engine, _ = database
    settings = config(tmp_path, upload_max_bytes=1024)
    with TestClient(base_url="http://127.0.0.1:8000", app=create_app(settings, engine), client=("127.0.0.1", 1)) as client:
        wid = workspace(client)
        def chunks():
            yield b"%PDF-" + b"x" * 800
            yield b"y" * 800
        response = client.post(f"/workspaces/{wid}/documents", content=chunks(), headers={"Content-Type": "application/pdf", "X-Filename": "test.pdf"})
        assert response.status_code == 413
        assert client.get(f"/workspaces/{wid}/documents").json() == []
    assert list(settings.storage_dir.glob("*")) == []


def test_parser_timeout_is_handled_without_raw_errors(tmp_path, monkeypatch):
    import subprocess
    import tenderready.pdf_parse as parser
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("parser", 1)
    monkeypatch.setattr(parser.subprocess, "run", timeout)
    with pytest.raises(PDFError, match="timed out"):
        parser.parse_isolated(SAMPLE, config(tmp_path))


def test_restart_marks_interrupted_analysis_retryable(database, tmp_path):
    engine, sessions = database
    app = create_app(config(tmp_path), engine)
    with TestClient(base_url="http://127.0.0.1:8000", app=app, client=("127.0.0.1", 1)) as client:
        wid = workspace(client); doc = upload(client, wid).json()
    with sessions.begin() as db:
        analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_version_id == doc["id"]))
        analysis.status = "running"
    with TestClient(base_url="http://127.0.0.1:8000", app=app, client=("127.0.0.1", 1)) as client:
        state = client.get(f"/workspaces/{wid}/documents").json()[0]["analysis"]
        assert state["status"] == "failed" and state["error_code"] == "interrupted"
