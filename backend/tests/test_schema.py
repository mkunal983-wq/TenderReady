import pytest
from sqlalchemy import inspect, update
from sqlalchemy.exc import IntegrityError
from tenderready.models import DocumentVersion, SourceSpan, Workspace, RequirementVersion, Assessment, ReviewDecision


def document(db, workspace):
    row = DocumentVersion(workspace_id=workspace.id, document_key="doc-1", version=1,
        kind="tender", filename="sample.pdf", storage_key="private/sample.pdf", sha256="a" * 64)
    db.add(row)
    db.flush()
    return row


def test_migrations_create_tables(database):
    engine, _ = database
    assert {"workspaces", "document_versions", "assessments", "amendment_changes", "model_runs", "jobs"} <= set(inspect(engine).get_table_names())


def test_cross_workspace_source_rejected(database):
    _, factory = database
    with factory() as db:
        a, b = Workspace(title="A", supplier_name="A"), Workspace(title="B", supplier_name="B")
        db.add_all([a, b]); db.flush()
        doc = document(db, a)
        db.add(SourceSpan(workspace_id=b.id, document_version_id=doc.id, page=1, start_offset=0, end_offset=4, text="test"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_document_versions_unique(database):
    _, factory = database
    with factory() as db:
        w = Workspace(title="A", supplier_name="A"); db.add(w); db.flush()
        document(db, w)
        with pytest.raises(IntegrityError):
            document(db, w)


def test_raw_sql_cannot_mutate_history(database):
    _, factory = database
    with factory() as db:
        w = Workspace(title="A", supplier_name="A"); db.add(w); db.flush()
        doc = document(db, w); db.commit()
        with pytest.raises(IntegrityError, match="append-only"):
            db.execute(update(DocumentVersion).where(DocumentVersion.id == doc.id).values(filename="changed.pdf"))


def test_approval_is_bound_to_assessment_version(database):
    _, factory = database
    with factory() as db:
        w = Workspace(title="A", supplier_name="A"); db.add(w); db.flush()
        doc = document(db, w)
        span = SourceSpan(workspace_id=w.id, document_version_id=doc.id, page=1, start_offset=0, end_offset=4, text="test")
        db.add(span); db.flush()
        req = RequirementVersion(workspace_id=w.id, requirement_key="req-1", version=1,
            source_span_id=span.id, statement="Provide authorization", category="required_information", obligation="mandatory")
        db.add(req); db.flush()
        assessment = Assessment(workspace_id=w.id, requirement_version_id=req.id,
            workspace_revision=1, status="supported", explanation="Evidence matches")
        db.add(assessment); db.flush()
        decision = ReviewDecision(workspace_id=w.id, assessment_id=assessment.id,
            action="approved", reviewer="Reviewer", workspace_revision=1)
        db.add(decision); db.commit()
        assert decision.assessment_id == assessment.id
        decision.action = "reopened"
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
