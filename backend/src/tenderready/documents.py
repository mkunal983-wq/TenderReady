"""PDF ingestion and atomic, retryable analysis of immutable document versions."""
import asyncio
import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import uuid
from urllib.parse import unquote

from fastapi import HTTPException, Request
from sqlalchemy import select, update
from starlette.concurrency import run_in_threadpool

from .models import (AnalysisRequirement, DocumentAnalysis, DocumentPage, DocumentVersion,
                     ModelRun, ModelRunContext, RequirementVersion, SourceSpan, Workspace, EvidenceLibraryEntry)
from .nebius import IntegrationError, NemotronClient, SourceInput
from .pdf_parse import PDFError, parse_isolated


def storage_path(settings, key: str) -> Path:
    root = settings.storage_dir.resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root) or path == root:
        raise HTTPException(404, "Source document not found.")
    return path


def document_response(db, document):
    analysis = db.scalar(select(DocumentAnalysis).where(DocumentAnalysis.document_version_id == document.id))
    page_numbers = db.scalars(select(DocumentPage.page).where(DocumentPage.document_version_id == document.id)).all()
    return {
        "id": document.id, "workspace_id": document.workspace_id, "filename": document.filename,
        "kind": document.kind, "version": document.version, "document_key": document.document_key,
        "supersedes_id": document.supersedes_id,
        "page_count": len(page_numbers),
        "source_url": f"/workspaces/{document.workspace_id}/documents/{document.id}/file",
        "analysis": None if analysis is None else {
            "id": analysis.id, "status": analysis.status, "warnings": analysis.warnings,
            "error_code": analysis.error_code, "error_message": analysis.error_message,
            "pages_completed": analysis.pages_completed, "model": analysis.model,
            "attempts": analysis.attempts,
        },
    }


def require_document(db, workspace_id, document_id):
    document = db.scalar(select(DocumentVersion).where(
        DocumentVersion.workspace_id == str(workspace_id), DocumentVersion.id == str(document_id)))
    if document is None:
        raise HTTPException(404, "Document not found in this workspace.")
    return document


async def upload_document(request: Request, workspace_id: str, db, settings, evidence_type=None, document_kind="tender", replaces_id=None):
    if db.get(Workspace, workspace_id) is None:
        raise HTTPException(404, "Workspace not found.")
    filename = Path(unquote(request.headers.get("x-filename", "" )).replace("\\", "/")).name
    if (not filename.lower().endswith(".pdf") or len(filename) > 200
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in filename)):
        raise HTTPException(415, "Provide a PDF filename in X-Filename.")
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/pdf":
        raise HTTPException(415, "Upload the file body as application/pdf.")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.upload_max_bytes:
                raise HTTPException(413, "PDF exceeds the upload size limit.")
        except ValueError:
            raise HTTPException(400, "Invalid Content-Length.") from None
    settings.storage_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = f"{uuid.uuid4()}.pdf"
    path = storage_path(settings, key)
    size, checksum, committed = 0, hashlib.sha256(), False
    try:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as file:
            async for chunk in request.stream():
                size += len(chunk)
                if size > settings.upload_max_bytes:
                    raise HTTPException(413, "PDF exceeds the upload size limit.")
                checksum.update(chunk)
                file.write(chunk)
        with path.open("rb") as file:
            if file.read(5) != b"%PDF-":
                raise HTTPException(415, "The uploaded file is not a PDF.")
        try:
            parsed = await run_in_threadpool(parse_isolated, path, settings)
        except PDFError as error:
            raise HTTPException(422, str(error)) from None
        # End the read transaction before acquiring the workspace write lock.
        db.rollback()
        workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
        if workspace is None:
            raise HTTPException(404, "Workspace not found.")
        previous = db.scalar(select(DocumentVersion).where(
            DocumentVersion.workspace_id == workspace_id, DocumentVersion.kind == document_kind
        ).order_by(DocumentVersion.created_at.desc(), DocumentVersion.version.desc()).limit(1)) if evidence_type is None else None
        if replaces_id:
            previous = require_document(db, workspace_id, replaces_id)
            entry = db.scalar(select(EvidenceLibraryEntry).where(EvidenceLibraryEntry.workspace_id == workspace_id,
                EvidenceLibraryEntry.document_version_id == previous.id))
            if previous.kind != 'evidence' or not entry or entry.evidence_type != evidence_type:
                raise HTTPException(422, 'Replacement must have the same evidence type as the original.')
            successor = db.scalar(select(DocumentVersion.id).where(DocumentVersion.workspace_id == workspace_id,
                DocumentVersion.supersedes_id == previous.id))
            if successor:
                raise HTTPException(409, 'This evidence version has already been replaced. Select its current version.')
        document = DocumentVersion(
            workspace_id=workspace_id, document_key=previous.document_key if previous else str(uuid.uuid4()),
            version=previous.version + 1 if previous else 1, kind="evidence" if evidence_type else document_kind, filename=filename,
            storage_key=key, sha256=checksum.hexdigest(), supersedes_id=previous.id if previous else None,
        )
        db.add(document); db.flush()
        for page in parsed["pages"]:
            db.add(DocumentPage(workspace_id=workspace_id, document_version_id=document.id, **page))
            text = page["text"]
            # Preserve exact offsets. Long pages are processed fully in bounded chunks.
            start = 0
            while start < len(text):
                end = min(start + 10000, len(text))
                if end < len(text):
                    boundary = text.rfind("\n", start + 5000, end)
                    if boundary > start:
                        end = boundary + 1
                if text[start:end].strip():
                    db.add(SourceSpan(workspace_id=workspace_id, document_version_id=document.id,
                        page=page["page"], start_offset=start, end_offset=end, text=text[start:end]))
                start = end
        if evidence_type:
            db.add(EvidenceLibraryEntry(workspace_id=workspace_id, document_version_id=document.id,
                                       evidence_type=evidence_type))
        else:
            db.add(DocumentAnalysis(workspace_id=workspace_id, document_version_id=document.id,
                                    warnings=parsed["warnings"]))
        workspace.revision += 1
        db.commit(); committed = True
        return document_response(db, document)
    finally:
        if not committed:
            db.rollback()
            path.unlink(missing_ok=True)


async def analyze_document(analysis_id: str, sessions, settings, client_factory=NemotronClient):
    """Single-process MVP runner; API startup marks interrupted runs retryable.

    Results are committed only after every page/chunk validates successfully.
    No mocks or fallback-generated requirements exist in this production path.
    """
    client = None
    try:
        with sessions() as db:
            analysis = db.get(DocumentAnalysis, analysis_id)
            if analysis is None or analysis.status != "running":
                return
            workspace_id, document_id = analysis.workspace_id, analysis.document_version_id
            spans = db.scalars(select(SourceSpan).where(SourceSpan.document_version_id == document_id,
                SourceSpan.workspace_id == workspace_id).order_by(SourceSpan.page, SourceSpan.start_offset)).all()
            base_warnings = [f"Page {p.page} has no extractable text; manual review or OCR is required."
                for p in db.scalars(select(DocumentPage).where(DocumentPage.document_version_id == document_id))
                if not p.text.strip()]
        client = client_factory(settings)
        client.require_model()
        if settings.nebius_model not in await client.list_models():
            raise IntegrationError("Configured Nemotron model is not available to this account.", "model_unavailable")
        results, warnings, completed_pages = [], list(base_warnings), set()
        async with asyncio.timeout(settings.analysis_timeout_seconds):
            for index, span in enumerate(spans):
                started_at = datetime.now(timezone.utc)
                start = time.monotonic()
                try:
                    result = await client.extract_requirements([SourceInput(source_id=span.id, text=span.text)])
                except (Exception, asyncio.CancelledError) as error:
                    completed_at = datetime.now(timezone.utc)
                    code = error.code if isinstance(error, IntegrationError) else 'interrupted' if isinstance(error, asyncio.CancelledError) else 'analysis_failed'
                    with sessions.begin() as db:
                        run = ModelRun(workspace_id=workspace_id, model=settings.nebius_model,
                            operation='tender_requirement_extraction', duration_ms=round((time.monotonic()-start)*1000), outcome='failed')
                        db.add(run); db.flush()
                        db.add(ModelRunContext(workspace_id=workspace_id, model_run_id=run.id,
                            analysis_id=analysis_id, source_span_id=span.id, started_at=started_at,
                            completed_at=completed_at, attempts=None, error_code=code))
                    raise
                completed_at = datetime.now(timezone.utc)
                # A successful provider call is recorded even if a later page fails;
                # requirement publication remains all-or-nothing.
                with sessions.begin() as db:
                    run = ModelRun(workspace_id=workspace_id, model=result.usage.model,
                        operation='tender_requirement_extraction', input_tokens=result.usage.input_tokens,
                        output_tokens=result.usage.output_tokens, duration_ms=result.usage.duration_ms, outcome='succeeded')
                    db.add(run); db.flush()
                    db.add(ModelRunContext(workspace_id=workspace_id, model_run_id=run.id,
                        analysis_id=analysis_id, source_span_id=span.id, started_at=started_at,
                        completed_at=completed_at, attempts=result.usage.attempts))
                results.append((span, result))
                warnings.extend(result.batch.warnings)
                if index == len(spans) - 1 or spans[index + 1].page != span.page:
                    completed_pages.add(span.page)
                with sessions.begin() as db:
                    db.execute(update(DocumentAnalysis).where(DocumentAnalysis.id == analysis_id,
                        DocumentAnalysis.status == "running").values(pages_completed=len(completed_pages)))
        with sessions.begin() as db:
            current = db.get(DocumentAnalysis, analysis_id)
            if current.status != "running":
                return
            seen = set()
            for span, result in results:
                for extracted in result.batch.requirements:
                    if (span.id, extracted.statement) in seen:
                        continue
                    seen.add((span.id, extracted.statement))
                    condition = {
                        "numeric_conditions": [c.model_dump() for c in extracted.numeric_conditions],
                        "date_conditions": [c.model_dump() for c in extracted.date_conditions],
                        "excerpt": extracted.citations[0].quote,
                        "provenance": "nemotron_extraction", "confidence": extracted.confidence, "review_status": "awaiting_review",
                        "review_reasons": extracted.review_reasons,
                        "obligation_quote": extracted.obligation_quote,
                    }
                    requirement = RequirementVersion(workspace_id=workspace_id, requirement_key=str(uuid.uuid4()),
                        version=1, source_span_id=span.id, statement=extracted.statement,
                        category=extracted.category, obligation=extracted.obligation, condition=condition)
                    db.add(requirement); db.flush()
                    db.add(AnalysisRequirement(workspace_id=workspace_id, analysis_id=analysis_id,
                                               requirement_version_id=requirement.id))
            if not seen:
                warnings.append("No requirements were extracted. Review the complete document manually.")
            current.status = "succeeded"
            current.model = settings.nebius_model
            current.warnings = list(dict.fromkeys(warnings))
            current.error_code = None; current.error_message = None
    except (IntegrationError, TimeoutError) as error:
        with sessions.begin() as db:
            record = db.get(DocumentAnalysis, analysis_id)
            record.status = "failed"
            record.error_code = error.code if isinstance(error, IntegrationError) else "analysis_timeout"
            record.error_message = str(error) if isinstance(error, IntegrationError) else "Analysis timed out. Retry with a smaller PDF."
    except Exception:
        # Never expose provider response bodies, document text, SQL or secrets.
        with sessions.begin() as db:
            record = db.get(DocumentAnalysis, analysis_id)
            record.status = "failed"; record.error_code = "analysis_failed"
            record.error_message = "Analysis failed safely; no partial requirements were published. Retry the analysis."
    finally:
        if client is not None:
            await client.close()


def requirements_response(db, workspace_id: str, document_id: str):
    from .models import TenderSnapshot, SnapshotRequirement
    snapshot = db.scalar(select(TenderSnapshot).where(TenderSnapshot.workspace_id == workspace_id,
        TenderSnapshot.document_version_id == document_id))
    if snapshot:
        rows = db.execute(select(RequirementVersion, SourceSpan, SnapshotRequirement).join(SnapshotRequirement,
            SnapshotRequirement.requirement_version_id == RequirementVersion.id).join(SourceSpan,
            SourceSpan.id == SnapshotRequirement.source_span_id).where(SnapshotRequirement.snapshot_id == snapshot.id)).all()
    else:
        rows = [(req,span,None) for req,span in db.execute(select(RequirementVersion, SourceSpan).join(SourceSpan,
            RequirementVersion.source_span_id == SourceSpan.id).where(RequirementVersion.workspace_id == workspace_id,
            SourceSpan.document_version_id == document_id).order_by(SourceSpan.page, SourceSpan.start_offset, RequirementVersion.created_at))
            if not req.condition.get('canonicalized_from')]
    def grounded_conditions(req, span, key):
        source_url = f"/workspaces/{workspace_id}/documents/{span.document_version_id}/file#page={span.page}"
        return [{**condition, "source_document_id": span.document_version_id, "page": span.page,
                 "source_url": source_url} if condition.get('quote') and condition['quote'] in span.text else
                {**condition, "source_document_id": None, "page": None, "source_url": None}
                for condition in req.condition.get(key, [])]
    return [{"id": req.id, "requirement_id": req.requirement_key,
             "text": req.statement, "category": req.category, "obligation": req.obligation,
             **req.condition, "numeric_conditions": grounded_conditions(req, span, 'numeric_conditions'),
             "date_conditions": grounded_conditions(req, span, 'date_conditions'),
             "excerpt": membership.source_excerpt if membership else req.condition.get('excerpt',req.statement),
             "source_document_id": span.document_version_id, "source_filename": db.get(DocumentVersion,span.document_version_id).filename,
             "page": span.page, "source_url": f"/workspaces/{workspace_id}/documents/{span.document_version_id}/file#page={span.page}"
             } for req, span, membership in rows]
