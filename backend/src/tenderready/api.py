import secrets
from datetime import datetime, timezone
from typing import Literal
from contextlib import asynccontextmanager
from ipaddress import ip_address
from uuid import UUID, uuid4
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError
from .config import BACKEND_ROOT, Settings, get_settings
from .db import build_engine, build_session_factory
from .errors import install_error_handlers
from .models import Workspace, DocumentVersion, DocumentAnalysis
from .schemas import WorkspaceCreate, WorkspaceView, WorkspaceRename, WorkspaceDelete
from .documents import (upload_document, document_response, require_document, storage_path,
                        analyze_document, requirements_response)
from .nebius import NemotronClient
from .models import SourceSpan, RequirementVersion, Assessment
from .verification import (EvidenceType, VerifyInput, ReviewInput, ManualRequirement,
    verify, review, assessment_view, require_requirement, verification_preview, list_evidence)
from .batch_verification import BulkVerifyInput, verify_all


def create_app(settings: Settings | None = None, engine=None):
    settings = settings or get_settings()
    engine = engine or build_engine(settings.database_url)
    sessions = build_session_factory(engine)
    expected_heads = set(ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini"))).get_heads())

    @asynccontextmanager
    async def lifespan(_):
        # Single-process runner: a previous process may have stopped mid-analysis.
        # Only recover after migrations are current; never hide a broken schema.
        with sessions() as db:
            try:
                if set(db.scalars(text("SELECT version_num FROM alembic_version"))) == expected_heads:
                    db.execute(update(DocumentAnalysis).where(DocumentAnalysis.status == "running").values(
                        status="failed", error_code="interrupted", error_message="Analysis was interrupted by a server restart. Retry it."))
                    db.commit()
            except SQLAlchemyError:
                db.rollback()
        yield
        engine.dispose()

    app = FastAPI(title="TenderReady", version="0.1.0", lifespan=lifespan)
    app.state.nemotron_factory = NemotronClient
    install_error_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "X-Filename"])

    def require_active_route(request):
        wid = request.path_params.get("workspace_id")
        if not wid:
            return
        try:
            wid = str(UUID(str(wid)))
        except ValueError:
            return  # Let FastAPI return its normal validated UUID error.
        with sessions() as db:
            row = db.get(Workspace, wid)
            if row is not None and row.deleted_at is not None:
                raise HTTPException(404, "Workspace not found.")

    def authorize(request: Request, authorization: str | None = Header(default=None)):
        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            raise HTTPException(403, "Request origin is not allowed.")
        token = settings.app_api_token.get_secret_value()
        if token:
            if not secrets.compare_digest((authorization or "").encode("utf-8"), f"Bearer {token}".encode("utf-8")):
                raise HTTPException(401, "Invalid application token", headers={"WWW-Authenticate": "Bearer"})
            require_active_route(request)
            return
        # A single-operator local mode, not multi-user authentication. Never trust
        # X-Forwarded-For here; production requires a configured token.
        try:
            # A loopback socket alone does not prevent DNS rebinding. Require
            # the browser's destination host to be loopback as well.
            local = (request.client is not None and ip_address(request.client.host).is_loopback
                     and request.url.hostname in {"localhost", "127.0.0.1", "::1"})
        except ValueError:
            local = False
        if settings.app_env != "development" or not local:
            raise HTTPException(403, "Unauthenticated development access is restricted to loopback.")
        require_active_route(request)

    def session():
        with sessions() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "tenderready", "phase": "foundation"}

    @app.get("/ready", dependencies=[Depends(authorize)])
    def ready(db=Depends(session)):
        try:
            actual_heads = set(db.scalars(text("SELECT version_num FROM alembic_version")))
            if actual_heads != expected_heads:
                raise HTTPException(503, "Database migrations are not current. Run alembic upgrade head.")
            db.execute(select(Workspace.id).limit(1))
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable or migrations not applied") from None
        return {"database": "ready", "inference": "configured_unverified" if settings.nebius_api_key.get_secret_value() and settings.nebius_model else "not_configured"}

    @app.post("/workspaces", response_model=WorkspaceView, status_code=201, dependencies=[Depends(authorize)])
    def create_workspace(payload: WorkspaceCreate, response: Response, db=Depends(session)):
        workspace = Workspace(**payload.model_dump())
        db.add(workspace)
        db.commit()
        response.headers["Location"] = f"/workspaces/{workspace.id}"
        return workspace

    @app.get("/workspaces", response_model=list[WorkspaceView], dependencies=[Depends(authorize)])
    def list_workspaces(limit: int = Query(default=100, ge=1, le=100),
                        offset: int = Query(default=0, ge=0, le=10000), db=Depends(session)):
        return db.scalars(select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.created_at.desc(), Workspace.id.desc())
                          .offset(offset).limit(limit)).all()

    @app.get("/workspaces/{workspace_id}", response_model=WorkspaceView, dependencies=[Depends(authorize)])
    def get_workspace(workspace_id: UUID, db=Depends(session)):
        workspace = db.get(Workspace, str(workspace_id))
        if workspace is None:
            raise HTTPException(404, "Workspace not found.")
        return workspace

    @app.post("/workspaces/{workspace_id}/rename", response_model=WorkspaceView, dependencies=[Depends(authorize)])
    def rename_workspace(workspace_id: UUID, payload: WorkspaceRename, db=Depends(session)):
        wid = str(workspace_id)
        row = db.get(Workspace, wid)
        if row is None or row.deleted_at is not None:
            raise HTTPException(404, "Workspace not found.")
        changed = db.execute(update(Workspace).where(Workspace.id == wid,
            Workspace.deleted_at.is_(None), Workspace.title == payload.expected_title).values(title=payload.title)).rowcount
        if not changed:
            raise HTTPException(409, "Workspace changed. Refresh the list before renaming.")
        db.commit()
        db.expire_all()
        return db.get(Workspace, wid)

    @app.post("/workspaces/{workspace_id}/delete", dependencies=[Depends(authorize)])
    def delete_workspace(workspace_id: UUID, payload: WorkspaceDelete, db=Depends(session)):
        wid = str(workspace_id)
        row = db.get(Workspace, wid)
        if row is None or row.deleted_at is not None:
            raise HTTPException(404, "Workspace not found.")
        changed = db.execute(update(Workspace).where(Workspace.id == wid,
            Workspace.deleted_at.is_(None), Workspace.title == payload.expected_title).values(
                deleted_at=datetime.now(timezone.utc))).rowcount
        if not changed:
            raise HTTPException(409, "Workspace changed. Refresh the list before deleting.")
        db.commit()
        return {"deleted": True, "id": wid}

    @app.post("/workspaces/{workspace_id}/documents", status_code=201, dependencies=[Depends(authorize)])
    async def upload(workspace_id: UUID, request: Request, kind: Literal["tender", "amendment"] = "tender", db=Depends(session)):
        return await upload_document(request, str(workspace_id), db, settings, document_kind=kind)

    @app.get("/workspaces/{workspace_id}/documents", dependencies=[Depends(authorize)])
    def list_documents(workspace_id: UUID, db=Depends(session)):
        if db.get(Workspace, str(workspace_id)) is None:
            raise HTTPException(404, "Workspace not found.")
        documents = db.scalars(select(DocumentVersion).where(DocumentVersion.workspace_id == str(workspace_id),
            DocumentVersion.kind.in_(["tender", "amendment"])).order_by(DocumentVersion.created_at.desc(), DocumentVersion.version.desc())).all()
        return [document_response(db, doc) for doc in documents]

    @app.get("/workspaces/{workspace_id}/documents/{document_id}/file", dependencies=[Depends(authorize)])
    def source_file(workspace_id: UUID, document_id: UUID, db=Depends(session)):
        document = require_document(db, workspace_id, document_id)
        path = storage_path(settings, document.storage_key)
        if not path.is_file():
            raise HTTPException(404, "Source file unavailable.")
        return FileResponse(path, media_type="application/pdf", filename=document.filename,
                            content_disposition_type="inline", headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/workspaces/{workspace_id}/documents/{document_id}/requirements", dependencies=[Depends(authorize)])
    def requirements(workspace_id: UUID, document_id: UUID, db=Depends(session)):
        require_document(db, workspace_id, document_id)
        return requirements_response(db, str(workspace_id), str(document_id))

    @app.post("/workspaces/{workspace_id}/documents/{document_id}/reconcile", dependencies=[Depends(authorize)])
    def reconcile_extraction(workspace_id: UUID, document_id: UUID, db=Depends(session)):
        from .reconciliation import reconcile_document
        document = require_document(db, workspace_id, document_id)
        reconcile_document(db, str(workspace_id), str(document_id))
        return document_response(db, document)

    @app.get("/workspaces/{workspace_id}/documents/{document_id}/reconciliations", dependencies=[Depends(authorize)])
    def reconciliation_history(workspace_id: UUID, document_id: UUID, db=Depends(session)):
        from .models import ExtractionReconciliation
        from .reconciliation import audit_view
        require_document(db, workspace_id, document_id)
        return [audit_view(r) for r in db.scalars(select(ExtractionReconciliation).where(
            ExtractionReconciliation.workspace_id == str(workspace_id),
            ExtractionReconciliation.document_version_id == str(document_id)).order_by(ExtractionReconciliation.revision))]

    @app.post("/workspaces/{workspace_id}/documents/{document_id}/analyze", status_code=202, dependencies=[Depends(authorize)])
    def analyze(workspace_id: UUID, document_id: UUID, background: BackgroundTasks, db=Depends(session)):
        document = require_document(db, workspace_id, document_id)
        if document.kind not in {"tender", "amendment"}:
            raise HTTPException(422, "Use evidence verification for supplier documents.")
        if db.scalar(select(TenderSnapshot.id).where(TenderSnapshot.document_version_id == document.id)):
            raise HTTPException(409, "This document is published; upload a new version to reinterpret it.")
        record = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_version_id == document.id))
        if record is None:
            raise HTTPException(409, "This legacy document has no parsed pages; upload a PDF to analyze it.")
        changed = db.execute(update(DocumentAnalysis).where(DocumentAnalysis.id == record.id,
            DocumentAnalysis.status.in_(["ready", "failed"])).values(
                status="running", error_code=None, error_message=None, pages_completed=0,
                attempts=DocumentAnalysis.attempts + 1, model=settings.nebius_model)).rowcount
        db.commit()
        if changed:
            background.add_task(analyze_document, record.id, sessions, settings, app.state.nemotron_factory)
        db.expire_all()
        return document_response(db, document)

    @app.post("/workspaces/{workspace_id}/evidence", status_code=201, dependencies=[Depends(authorize)])
    async def upload_evidence(workspace_id: UUID, request: Request, evidence_type: EvidenceType, replaces_id: UUID | None = None, db=Depends(session)):
        return await upload_document(request, str(workspace_id), db, settings, evidence_type=evidence_type,
                                     replaces_id=str(replaces_id) if replaces_id else None)

    @app.get("/workspaces/{workspace_id}/evidence", dependencies=[Depends(authorize)])
    def evidence(workspace_id: UUID, db=Depends(session)):
        get_workspace(workspace_id, db)
        rows = list_evidence(db, str(workspace_id), include_superseded=True)
        replaced = {doc.supersedes_id for doc, _ in rows if doc.supersedes_id}
        return [{**document_response(db, doc), "evidence_type": entry.evidence_type,
                 "is_current": doc.id not in replaced} for doc, entry in rows]

    @app.get("/workspaces/{workspace_id}/documents/{document_id}/pages", dependencies=[Depends(authorize)])
    def pages(workspace_id: UUID, document_id: UUID, db=Depends(session)):
        from .models import DocumentPage
        require_document(db, workspace_id, document_id)
        return [{"page": p.page, "text": p.text} for p in db.scalars(select(DocumentPage).where(
            DocumentPage.workspace_id == str(workspace_id), DocumentPage.document_version_id == str(document_id)).order_by(DocumentPage.page))]

    @app.post("/workspaces/{workspace_id}/documents/{document_id}/manual-requirements", status_code=201, dependencies=[Depends(authorize)])
    def transcribe(workspace_id: UUID, document_id: UUID, payload: ManualRequirement, db=Depends(session)):
        document = require_document(db, workspace_id, document_id)
        if document.kind not in {"tender", "amendment"}:
            raise HTTPException(422, "Requirements must cite tender documents.")
        if db.scalar(select(TenderSnapshot.id).where(TenderSnapshot.document_version_id == document.id)):
            raise HTTPException(409, "Published interpretations are immutable; upload a new version.")
        span = next((s for s in db.scalars(select(SourceSpan).where(SourceSpan.workspace_id == str(workspace_id),
            SourceSpan.document_version_id == str(document_id), SourceSpan.page == payload.page)) if payload.excerpt in s.text), None)
        if span is None:
            raise HTTPException(422, "Excerpt must occur exactly on the selected source page.")
        workspace = db.scalar(select(Workspace).where(Workspace.id == str(workspace_id)).with_for_update())
        req = RequirementVersion(workspace_id=str(workspace_id), requirement_key=str(uuid4()), version=1,
            source_span_id=span.id, statement=payload.excerpt, category="manual_review", obligation="unclear",
            condition={"excerpt": payload.excerpt, "confidence": "human_transcription", "review_status": "awaiting_review",
                "review_reasons": ["Manually transcribed; no model extraction claimed."], "numeric_conditions": [],
                "date_conditions": [], "provenance": "human_transcription", "reviewer": payload.reviewer})
        db.add(req); workspace.revision += 1; db.commit()
        return next(r for r in requirements_response(db, str(workspace_id), str(document_id)) if r["id"] == req.id)

    @app.get("/workspaces/{workspace_id}/requirements/{requirement_id}/verification", dependencies=[Depends(authorize)])
    def verification(workspace_id: UUID, requirement_id: UUID, db=Depends(session)):
        req = require_requirement(db, str(workspace_id), str(requirement_id))
        assessments = db.scalars(select(Assessment).where(Assessment.workspace_id == str(workspace_id),
            Assessment.requirement_version_id == req.id).order_by(Assessment.created_at.desc(), Assessment.id.desc())).all()
        plan = verification_preview(db, req)
        return {"suggested_criteria": plan['criteria'], "check_plan": plan,
                "assessments": [assessment_view(db, a) for a in assessments]}

    @app.post("/workspaces/{workspace_id}/requirements/{requirement_id}/verify", status_code=201, dependencies=[Depends(authorize)])
    def verify_requirement(workspace_id: UUID, requirement_id: UUID, payload: VerifyInput, db=Depends(session)):
        return verify(db, str(workspace_id), str(requirement_id), payload)

    @app.post("/workspaces/{workspace_id}/verify-all", dependencies=[Depends(authorize)])
    def verify_workspace(workspace_id: UUID, payload: BulkVerifyInput | None = None, db=Depends(session)):
        return verify_all(db, str(workspace_id))

    @app.post("/workspaces/{workspace_id}/assessments/{assessment_id}/reviews", status_code=201, dependencies=[Depends(authorize)])
    def review_assessment(workspace_id: UUID, assessment_id: UUID, payload: ReviewInput, db=Depends(session)):
        return review(db, str(workspace_id), str(assessment_id), payload)

    from . import amendments
    from .models import TenderSnapshot

    @app.post("/workspaces/{workspace_id}/documents/{document_id}/extract-labelled", dependencies=[Depends(authorize)])
    def extract_labelled(workspace_id: UUID, document_id: UUID, db=Depends(session)):
        return amendments.extract_labelled(db, str(workspace_id), str(document_id))

    @app.post("/workspaces/{workspace_id}/documents/{document_id}/baseline", status_code=201, dependencies=[Depends(authorize)])
    def publish_baseline(workspace_id: UUID, document_id: UUID, payload: amendments.SnapshotInput, db=Depends(session)):
        return amendments.baseline(db, str(workspace_id), str(document_id), payload)

    @app.post("/workspaces/{workspace_id}/documents/{document_id}/compare", dependencies=[Depends(authorize)])
    def compare_amendment(workspace_id: UUID, document_id: UUID, payload: amendments.CompareInput, db=Depends(session)):
        return amendments.compare(db, str(workspace_id), str(document_id), payload)

    @app.post("/workspaces/{workspace_id}/documents/{document_id}/apply-amendment", dependencies=[Depends(authorize)])
    def apply_amendment(workspace_id: UUID, document_id: UUID, payload: amendments.CompareInput, db=Depends(session)):
        return amendments.apply(db, str(workspace_id), str(document_id), payload)

    @app.get("/workspaces/{workspace_id}/snapshots", dependencies=[Depends(authorize)])
    def snapshots(workspace_id: UUID, db=Depends(session)):
        get_workspace(workspace_id, db)
        return [amendments.snapshot_view(db,s) for s in db.scalars(select(TenderSnapshot).where(
            TenderSnapshot.workspace_id==str(workspace_id)).order_by(TenderSnapshot.sequence.desc()))]

    from . import supplier

    @app.get("/workspaces/{workspace_id}/dashboard", dependencies=[Depends(authorize)])
    def supplier_dashboard(workspace_id: UUID, db=Depends(session)):
        return supplier.dashboard(db, str(workspace_id))

    @app.get("/workspaces/{workspace_id}/requirements/{requirement_id}/detail", dependencies=[Depends(authorize)])
    def requirement_detail(workspace_id: UUID, requirement_id: UUID, db=Depends(session)):
        return supplier.detail(db, str(workspace_id), str(requirement_id))

    @app.post("/workspaces/{workspace_id}/tasks", status_code=201, dependencies=[Depends(authorize)])
    def create_task(workspace_id: UUID, payload: supplier.TaskCreate, db=Depends(session)):
        return supplier.save_task(db, str(workspace_id), payload)

    @app.post("/workspaces/{workspace_id}/tasks/{task_id}", dependencies=[Depends(authorize)])
    def update_task(workspace_id: UUID, task_id: UUID, payload: supplier.TaskUpdate, db=Depends(session)):
        return supplier.save_task(db, str(workspace_id), payload, str(task_id))

    @app.get("/workspaces/{workspace_id}/timeline", dependencies=[Depends(authorize)])
    def version_timeline(workspace_id: UUID, offset: int = Query(0, ge=0, le=100000),
                         limit: int = Query(50, ge=1, le=100), db=Depends(session)):
        return supplier.timeline(db, str(workspace_id), offset, limit)

    @app.get("/workspaces/{workspace_id}/exports/{kind}", dependencies=[Depends(authorize)])
    def export(workspace_id: UUID, kind: Literal["compliance-matrix", "evidence-index"], db=Depends(session)):
        content = supplier.export_csv(db, str(workspace_id), kind)
        return Response(content="\ufeff" + content, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{kind}.csv"',
                                 "X-Content-Type-Options": "nosniff"})

    return app
