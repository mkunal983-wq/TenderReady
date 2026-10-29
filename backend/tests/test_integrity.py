"""Real database persistence and constraint tests; no mocked storage or APIs."""
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select, Table, MetaData
from sqlalchemy.exc import IntegrityError

from tenderready.config import get_settings
from tenderready.db import build_engine, build_session_factory
from tenderready.models import (
    AmendmentChange, Assessment, AssessmentEvidence, CorrectiveTask,
    DocumentVersion, EvidenceFact, RequirementVersion, ReviewDecision,
    SourceSpan, Workspace,
)


def persist(db, row):
    db.add(row)
    db.flush()
    return row


def make_document(db, workspace, kind, **overrides):
    values = dict(workspace_id=workspace.id, document_key=str(uuid.uuid4()),
                  version=1, kind=kind, filename=f"{kind}.pdf", storage_key=str(uuid.uuid4()),
                  sha256="a" * 64)
    values.update(overrides)
    return persist(db, DocumentVersion(**values))


def make_span(db, document):
    return persist(db, SourceSpan(workspace_id=document.workspace_id,
        document_version_id=document.id, page=1, start_offset=0, end_offset=4, text="test"))


def legacy_workspace(db, title, supplier):
    from datetime import datetime, timezone
    table = Table('workspaces', MetaData(), autoload_with=db.connection())
    row = SimpleNamespace(id=str(uuid.uuid4()))
    db.execute(table.insert().values(id=row.id, title=title, supplier_name=supplier,
        revision=1, created_at=datetime.now(timezone.utc)))
    return row


def make_graph(db, legacy=False):
    workspace = legacy_workspace(db, "Synthetic tender", "Synthetic Supplier") if legacy else persist(db, Workspace(title="Synthetic tender", supplier_name="Synthetic Supplier"))
    tender = make_document(db, workspace, "tender")
    evidence = make_document(db, workspace, "evidence")
    amendment = make_document(db, workspace, "amendment")
    tender_span, evidence_span, amendment_span = (make_span(db, d) for d in (tender, evidence, amendment))
    requirement = persist(db, RequirementVersion(workspace_id=workspace.id,
        requirement_key=str(uuid.uuid4()), version=1, source_span_id=tender_span.id,
        statement="Provide manufacturer authorization", category="required_information",
        obligation="mandatory"))
    fact = persist(db, EvidenceFact(workspace_id=workspace.id, source_span_id=evidence_span.id,
        field="authorization", raw_value="present"))
    assessment = persist(db, Assessment(workspace_id=workspace.id, requirement_version_id=requirement.id,
        workspace_revision=1, status="supported", explanation="Document contains authorization"))
    link = persist(db, AssessmentEvidence(workspace_id=workspace.id, assessment_id=assessment.id,
        evidence_fact_id=fact.id))
    if legacy:
        # Seed the historical schema with its own columns, not today's ORM model.
        from datetime import datetime, timezone
        table = Table('corrective_tasks', MetaData(), autoload_with=db.connection())
        task = SimpleNamespace(id=str(uuid.uuid4()))
        db.execute(table.insert().values(id=task.id, workspace_id=workspace.id,
            assessment_id=assessment.id, title="Review authorization", explanation="Human review required",
            status="open", created_at=datetime.now(timezone.utc)))
    else:
        task = persist(db, CorrectiveTask(workspace_id=workspace.id, assessment_id=assessment.id,
            title="Review authorization", explanation="Human review required"))
    review = persist(db, ReviewDecision(workspace_id=workspace.id, assessment_id=assessment.id,
        action="approved", reviewer="Synthetic Reviewer", workspace_revision=1))
    db.commit()
    return SimpleNamespace(**locals())


def test_complete_graph_persists_across_sessions(database):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        ids = {name: getattr(graph, name).id for name in ("workspace", "tender", "evidence", "requirement", "fact", "assessment", "review", "task")}
    with factory() as db:
        requirement = db.get(RequirementVersion, ids["requirement"])
        tender_span = db.get(SourceSpan, requirement.source_span_id)
        assert tender_span.document_version_id == ids["tender"]
        fact = db.get(EvidenceFact, ids["fact"])
        evidence_span = db.get(SourceSpan, fact.source_span_id)
        assert evidence_span.document_version_id == ids["evidence"]
        assert db.get(ReviewDecision, ids["review"]).assessment_id == ids["assessment"]
        assert db.get(CorrectiveTask, ids["task"]).assessment_id == ids["assessment"]
        link = db.scalar(select(AssessmentEvidence).where(AssessmentEvidence.assessment_id == ids["assessment"]))
        assert link.evidence_fact_id == ids["fact"]
        assert all(db.get(model, ids[name]).workspace_id == ids["workspace"] for model, name in (
            (DocumentVersion, "tender"), (DocumentVersion, "evidence"),
            (RequirementVersion, "requirement"), (EvidenceFact, "fact"),
            (Assessment, "assessment"), (ReviewDecision, "review"), (CorrectiveTask, "task")))


@pytest.mark.parametrize("target", ["assessment", "evidence_link", "task", "review"])
def test_cross_workspace_graph_links_are_rejected(database, target):
    _, factory = database
    with factory() as db:
        a, b = make_graph(db), make_graph(db)
        unreviewed = persist(db, Assessment(workspace_id=b.workspace.id,
            requirement_version_id=b.requirement.id, workspace_revision=1,
            status="inconclusive", explanation="Not yet reviewed"))
        constructors = {
            "assessment": lambda: Assessment(workspace_id=b.workspace.id,
                requirement_version_id=a.requirement.id, workspace_revision=1, status="missing", explanation="test"),
            "evidence_link": lambda: AssessmentEvidence(workspace_id=b.workspace.id,
                assessment_id=unreviewed.id, evidence_fact_id=a.fact.id),
            "task": lambda: CorrectiveTask(workspace_id=b.workspace.id, assessment_id=a.assessment.id,
                title="test", explanation="test"),
            "review": lambda: ReviewDecision(workspace_id=b.workspace.id, assessment_id=a.assessment.id,
                action="approved", reviewer="test", workspace_revision=1),
        }
        db.add(constructors[target]())
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize("invalid", ["key", "kind", "gap", "missing_parent", "first_with_parent"])
def test_document_lineage_guard(database, invalid):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        values = dict(document_key=graph.tender.document_key, version=2, supersedes_id=graph.tender.id)
        kind = "tender"
        if invalid == "key": values["document_key"] = "another-key"
        if invalid == "kind": kind = "evidence"
        if invalid == "gap": values["version"] = 3
        if invalid == "missing_parent": values["supersedes_id"] = None
        if invalid == "first_with_parent": values.update(version=1, document_key="another-key")
        with pytest.raises(IntegrityError, match="lineage"):
            make_document(db, graph.workspace, kind, **values)


@pytest.mark.parametrize("invalid", ["key", "gap", "missing_parent", "first_with_parent", "evidence_source"])
def test_requirement_lineage_and_source_guard(database, invalid):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        values = dict(workspace_id=graph.workspace.id, requirement_key=graph.requirement.requirement_key,
            version=2, supersedes_id=graph.requirement.id, source_span_id=graph.amendment_span.id,
            statement="Amended requirement", category="required_information", obligation="mandatory")
        if invalid == "key": values["requirement_key"] = "another-key"
        if invalid == "gap": values["version"] = 3
        if invalid == "missing_parent": values["supersedes_id"] = None
        if invalid == "first_with_parent": values.update(version=1, requirement_key="another-key")
        if invalid == "evidence_source": values["source_span_id"] = graph.evidence_span.id
        with pytest.raises(IntegrityError, match="lineage|source"):
            persist(db, RequirementVersion(**values))


def test_valid_successor_preserves_original_history(database):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        second = make_document(db, graph.workspace, "evidence", document_key=graph.evidence.document_key,
            version=2, supersedes_id=graph.evidence.id)
        req2 = persist(db, RequirementVersion(workspace_id=graph.workspace.id,
            requirement_key=graph.requirement.requirement_key, version=2,
            supersedes_id=graph.requirement.id, source_span_id=graph.amendment_span.id,
            statement="Amended requirement", category="required_information", obligation="mandatory"))
        change = persist(db, AmendmentChange(workspace_id=graph.workspace.id,
            source_span_id=graph.amendment_span.id, old_requirement_id=graph.requirement.id,
            new_requirement_id=req2.id, change_type="replacement", explanation="Threshold changed"))
        db.commit()
        assert second.version == 2 and req2.version == 2
        assert db.get(ReviewDecision, graph.review.id).assessment_id == graph.assessment.id
        assert change.old_requirement_id == graph.requirement.id


def test_evidence_fact_rejects_tender_source(database):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        with pytest.raises(IntegrityError, match="evidence document"):
            persist(db, EvidenceFact(workspace_id=graph.workspace.id,
                source_span_id=graph.tender_span.id, field="test", raw_value="test"))


def test_amendment_rejects_non_amendment_source(database):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        with pytest.raises(IntegrityError, match="amendment document"):
            persist(db, AmendmentChange(workspace_id=graph.workspace.id,
                source_span_id=graph.tender_span.id, change_type="ambiguous", explanation="test"))


def test_review_history_cannot_be_deleted_with_raw_sql(database):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        with pytest.raises(IntegrityError, match="append-only"):
            db.execute(delete(ReviewDecision).where(ReviewDecision.id == graph.review.id))


def test_evidence_set_is_frozen_after_review(database):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        fact = persist(db, EvidenceFact(workspace_id=graph.workspace.id,
            source_span_id=graph.evidence_span.id, field="replacement_fact", raw_value="different"))
        with pytest.raises(IntegrityError, match="frozen"):
            persist(db, AssessmentEvidence(workspace_id=graph.workspace.id,
                assessment_id=graph.assessment.id, evidence_fact_id=fact.id))


def test_amendment_source_cannot_be_changed_to_tender(database):
    _, factory = database
    with factory() as db:
        graph = make_graph(db)
        change = persist(db, AmendmentChange(workspace_id=graph.workspace.id,
            source_span_id=graph.amendment_span.id, change_type="ambiguous", explanation="test"))
        db.commit()
        change.source_span_id = graph.tender_span.id
        with pytest.raises(IntegrityError, match="amendment document"):
            db.commit()


def test_upgrade_rejects_invalid_existing_history(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "0002_immutable_records")
    engine = build_engine(url)
    with build_session_factory(engine)() as db:
        workspace = legacy_workspace(db, "Legacy", "Legacy")
        make_document(db, workspace, "tender", version=4)
        db.commit()
    with pytest.raises(IntegrityError, match="tenderready_existing_lineage_invalid"):
        command.upgrade(cfg, "head")
    with engine.connect() as connection:
        assert connection.scalar(select(DocumentVersion.version)) == 4
    engine.dispose()
    get_settings.cache_clear()


def test_upgrade_preserves_valid_reviewed_history(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'valid-old.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "0002_immutable_records")
    engine = build_engine(url)
    factory = build_session_factory(engine)
    with factory() as db:
        graph = make_graph(db, legacy=True)
        review_id, link_id, requirement_id = graph.review.id, graph.link.id, graph.requirement.id
    command.upgrade(cfg, "head")
    with factory() as db:
        assert db.get(ReviewDecision, review_id).action == "approved"
        assert db.get(AssessmentEvidence, link_id).evidence_fact_id == graph.fact.id
        assert db.get(RequirementVersion, requirement_id).version == 1
        assert db.get(CorrectiveTask, graph.task.id).priority == "medium"
        assert db.get(CorrectiveTask, graph.task.id).revision == 1
    engine.dispose()
    get_settings.cache_clear()
