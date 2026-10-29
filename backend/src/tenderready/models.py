"""Portable schema. All evidence links are constrained to their workspace.

Document, requirement, assessment, and decision rows are append-only in the
application. SQLite supports local tests; PostgreSQL is the deployment target.
Migrations also enforce source document kinds and sequential same-key version
lineage at the database boundary. Apply migrations rather than create_all().
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Integer, String, Text, UniqueConstraint, Index, event,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Workspace(Record, Base):
    __tablename__ = "workspaces"
    title: Mapped[str] = mapped_column(String(200))
    supplier_name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("revision >= 1"),)


class Scoped(Record):
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)


def scoped_fk(column, table):
    return ForeignKeyConstraint(["workspace_id", column], [f"{table}.workspace_id", f"{table}.id"])


class DocumentVersion(Scoped, Base):
    """Shared version model: tender, amendment, and supplier evidence documents."""
    __tablename__ = "document_versions"
    document_key: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    supersedes_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "document_key", "version"),
        scoped_fk("supersedes_id", "document_versions"),
        CheckConstraint("version >= 1"),
        CheckConstraint("kind IN ('tender','amendment','evidence')"),
        CheckConstraint("length(sha256) = 64"),
    )


class SourceSpan(Scoped, Base):
    __tablename__ = "source_spans"
    document_version_id: Mapped[str] = mapped_column(String(36))
    page: Mapped[int] = mapped_column(Integer)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        scoped_fk("document_version_id", "document_versions"),
        CheckConstraint("page >= 1 AND start_offset >= 0 AND end_offset > start_offset"),
    )


class RequirementVersion(Scoped, Base):
    __tablename__ = "requirement_versions"
    requirement_key: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    source_span_id: Mapped[str] = mapped_column(String(36))
    statement: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))
    obligation: Mapped[str] = mapped_column(String(20))
    condition: Mapped[dict] = mapped_column(JSON, default=dict)
    supersedes_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "requirement_key", "version"),
        scoped_fk("source_span_id", "source_spans"),
        scoped_fk("supersedes_id", "requirement_versions"),
        CheckConstraint("version >= 1"),
        CheckConstraint("obligation IN ('mandatory','optional','unclear')"),
        CheckConstraint("category IN ('product_identity','bidder_identity','validity_date','numeric_threshold','required_information','manual_review')"),
    )


class EvidenceFact(Scoped, Base):
    __tablename__ = "evidence_facts"
    source_span_id: Mapped[str] = mapped_column(String(36))
    field: Mapped[str] = mapped_column(String(100))
    raw_value: Mapped[str] = mapped_column(Text)
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("workspace_id", "id"), scoped_fk("source_span_id", "source_spans"))


class Assessment(Scoped, Base):
    __tablename__ = "assessments"
    requirement_version_id: Mapped[str] = mapped_column(String(36))
    workspace_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text)
    checks: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"), scoped_fk("requirement_version_id", "requirement_versions"),
        CheckConstraint("workspace_revision >= 1"),
        CheckConstraint("status IN ('supported','missing','conflicting','inconclusive')"),
    )


class AssessmentEvidence(Scoped, Base):
    __tablename__ = "assessment_evidence"
    assessment_id: Mapped[str] = mapped_column(String(36))
    evidence_fact_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("assessment_id", "evidence_fact_id"),
        scoped_fk("assessment_id", "assessments"), scoped_fk("evidence_fact_id", "evidence_facts"),
    )


class ReviewDecision(Scoped, Base):
    __tablename__ = "review_decisions"
    assessment_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(20))
    reviewer: Mapped[str] = mapped_column(String(200))
    comment: Mapped[str] = mapped_column(Text, default="")
    workspace_revision: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        scoped_fk("assessment_id", "assessments"),
        CheckConstraint("action IN ('approved','rejected','reopened')"),
        CheckConstraint("workspace_revision >= 1"),
    )


class CorrectiveTask(Scoped, Base):
    __tablename__ = "corrective_tasks"
    assessment_id: Mapped[str] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(250))
    explanation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="medium", server_default="medium")
    due_date: Mapped[str | None] = mapped_column(String(10))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    __table_args__ = (Index("uq_tasks_workspace_id", "workspace_id", "id", unique=True),
        scoped_fk("assessment_id", "assessments"), CheckConstraint("status IN ('open','resolved','dismissed')"))


class TaskEvent(Scoped, Base):
    __tablename__ = "task_events"
    task_id: Mapped[str] = mapped_column(String(36))
    reviewer: Mapped[str] = mapped_column(String(200))
    comment: Mapped[str] = mapped_column(Text)
    changes: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (scoped_fk("task_id", "corrective_tasks"),)



class AmendmentChange(Scoped, Base):
    __tablename__ = "amendment_changes"
    source_span_id: Mapped[str] = mapped_column(String(36))
    old_requirement_id: Mapped[str | None] = mapped_column(String(36))
    new_requirement_id: Mapped[str | None] = mapped_column(String(36))
    change_type: Mapped[str] = mapped_column(String(20))
    review_state: Mapped[str] = mapped_column(String(20), default="awaiting_review")
    explanation: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        scoped_fk("source_span_id", "source_spans"),
        scoped_fk("old_requirement_id", "requirement_versions"),
        scoped_fk("new_requirement_id", "requirement_versions"),
        CheckConstraint("change_type IN ('addition','replacement','deletion','ambiguous')"),
        CheckConstraint("review_state IN ('awaiting_review','confirmed','rejected')"),
    )


class Job(Scoped, Base):
    __tablename__ = "jobs"
    kind: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    input_revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','stale')"),
        CheckConstraint("attempts >= 0 AND input_revision >= 1"),
    )


class ModelRun(Scoped, Base):
    __tablename__ = "model_runs"
    job_id: Mapped[str | None] = mapped_column(String(36))
    model: Mapped[str] = mapped_column(String(200))
    operation: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(30))
    __table_args__ = (Index("uq_model_runs_workspace_id_id", "workspace_id", "id", unique=True), scoped_fk("job_id", "jobs"))


class DocumentPage(Scoped, Base):
    __tablename__ = "document_pages"
    document_version_id: Mapped[str] = mapped_column(String(36))
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("document_version_id", "page"),
        scoped_fk("document_version_id", "document_versions"),
        CheckConstraint("page >= 1"),
    )


class DocumentAnalysis(Scoped, Base):
    __tablename__ = "document_analyses"
    document_version_id: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    pages_completed: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        scoped_fk("document_version_id", "document_versions"),
        CheckConstraint("status IN ('ready','running','succeeded','failed')"),
        CheckConstraint("pages_completed >= 0 AND attempts >= 0"),
    )


class ModelRunContext(Scoped, Base):
    """Provenance and timing for an individual provider call, including failures."""
    __tablename__ = "model_run_contexts"
    model_run_id: Mapped[str] = mapped_column(String(36), unique=True)
    analysis_id: Mapped[str] = mapped_column(String(36))
    source_span_id: Mapped[str] = mapped_column(String(36))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(50))
    __table_args__ = (scoped_fk("model_run_id", "model_runs"), scoped_fk("analysis_id", "document_analyses"),
                      scoped_fk("source_span_id", "source_spans"),
                      CheckConstraint("attempts IS NULL OR attempts >= 1"))


class AnalysisRequirement(Scoped, Base):
    __tablename__ = "analysis_requirements"
    analysis_id: Mapped[str] = mapped_column(String(36))
    requirement_version_id: Mapped[str] = mapped_column(String(36), unique=True)
    __table_args__ = (
        scoped_fk("analysis_id", "document_analyses"),
        scoped_fk("requirement_version_id", "requirement_versions"),
    )


class ExtractionBatchCache(Scoped, Base):
    """Validated provider output, reusable only for identical source/configuration.

    Checkpoints are not published requirements or approved findings. They avoid
    paying again for completed batches when a later batch fails.
    """
    __tablename__ = "extraction_batch_cache"
    analysis_id: Mapped[str] = mapped_column(String(36))
    source_span_id: Mapped[str] = mapped_column(String(36))
    model_run_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("workspace_id", "analysis_id", "fingerprint"),
        scoped_fk("analysis_id", "document_analyses"),
        scoped_fk("source_span_id", "source_spans"),
        scoped_fk("model_run_id", "model_runs"),
        CheckConstraint("length(fingerprint) = 64"),
    )


class ExtractionReconciliation(Scoped, Base):
    """Append-only audit of source-grounded corrections, never an approval."""
    __tablename__ = "extraction_reconciliations"
    analysis_id: Mapped[str] = mapped_column(String(36))
    document_version_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    rules_version: Mapped[str] = mapped_column(String(100))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    output_fingerprint: Mapped[str] = mapped_column(String(64))
    summary: Mapped[dict] = mapped_column(JSON)
    changes: Mapped[list] = mapped_column(JSON)
    __table_args__ = (
        scoped_fk("analysis_id", "document_analyses"),
        scoped_fk("document_version_id", "document_versions"),
        UniqueConstraint("workspace_id", "document_version_id", "revision"),
        CheckConstraint("revision >= 1"),
        CheckConstraint("length(input_fingerprint) = 64 AND length(output_fingerprint) = 64"),
    )


class EvidenceLibraryEntry(Scoped, Base):
    __tablename__ = "evidence_library_entries"
    document_version_id: Mapped[str] = mapped_column(String(36), unique=True)
    evidence_type: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        scoped_fk("document_version_id", "document_versions"),
        CheckConstraint("evidence_type IN ('datasheet','authorization','certificate','project_reference')"),
    )


class TenderSnapshot(Scoped, Base):
    __tablename__ = "tender_snapshots"
    document_version_id: Mapped[str] = mapped_column(String(36), unique=True)
    previous_snapshot_id: Mapped[str | None] = mapped_column(String(36))
    sequence: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(20))
    reviewer: Mapped[str] = mapped_column(String(200))
    fingerprint: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("workspace_id", "id"), UniqueConstraint("workspace_id", "sequence"),
        scoped_fk("document_version_id", "document_versions"), scoped_fk("previous_snapshot_id", "tender_snapshots"),
        CheckConstraint("sequence >= 1"), CheckConstraint("mode IN ('baseline','full','delta')"))


class SnapshotRequirement(Scoped, Base):
    __tablename__ = "snapshot_requirements"
    source_excerpt: Mapped[str] = mapped_column(Text)
    snapshot_id: Mapped[str] = mapped_column(String(36))
    requirement_version_id: Mapped[str] = mapped_column(String(36))
    source_span_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("snapshot_id", "requirement_version_id"), scoped_fk("snapshot_id", "tender_snapshots"),
        scoped_fk("requirement_version_id", "requirement_versions"), scoped_fk("source_span_id", "source_spans"))


class RequirementChange(Scoped, Base):
    __tablename__ = "requirement_changes"
    snapshot_id: Mapped[str] = mapped_column(String(36))
    old_requirement_id: Mapped[str | None] = mapped_column(String(36))
    new_requirement_id: Mapped[str | None] = mapped_column(String(36))
    classification: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("workspace_id", "id"), scoped_fk("snapshot_id", "tender_snapshots"),
        scoped_fk("old_requirement_id", "requirement_versions"), scoped_fk("new_requirement_id", "requirement_versions"),
        CheckConstraint("classification IN ('Added','Modified','Removed','Unchanged')"))


class AssessmentDependency(Scoped, Base):
    __tablename__ = "assessment_dependencies"
    assessment_id: Mapped[str] = mapped_column(String(36))
    requirement_version_id: Mapped[str] = mapped_column(String(36))
    evidence_fact_id: Mapped[str | None] = mapped_column(String(36))
    field: Mapped[str] = mapped_column(String(100))
    product_model: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (scoped_fk("assessment_id", "assessments"), scoped_fk("requirement_version_id", "requirement_versions"),
                     scoped_fk("evidence_fact_id", "evidence_facts"))


class ReassessmentImpact(Scoped, Base):
    __tablename__ = "reassessment_impacts"
    change_id: Mapped[str] = mapped_column(String(36))
    old_assessment_id: Mapped[str] = mapped_column(String(36))
    new_assessment_id: Mapped[str | None] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(Text)
    approval_ids: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("change_id", "old_assessment_id"), scoped_fk("change_id", "requirement_changes"),
        scoped_fk("old_assessment_id", "assessments"), scoped_fk("new_assessment_id", "assessments"))


def prevent_mutation(*_):
    raise ValueError("Versioned evidence and decisions are append-only; create a new version.")


for immutable in (DocumentVersion, SourceSpan, RequirementVersion, EvidenceFact,
                  Assessment, AssessmentEvidence, ReviewDecision, ModelRun, ModelRunContext,
                  DocumentPage, AnalysisRequirement, ExtractionBatchCache, ExtractionReconciliation, EvidenceLibraryEntry, TenderSnapshot, SnapshotRequirement,
                  RequirementChange, AssessmentDependency, ReassessmentImpact, TaskEvent):
    event.listen(immutable, "before_update", prevent_mutation)
    event.listen(immutable, "before_delete", prevent_mutation)
