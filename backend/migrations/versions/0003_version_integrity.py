"""Validate document roles and linear version ancestry without rewriting history.

The preflight is deliberately executed before installing guards. Existing invalid
history stops the migration instead of silently rewriting immutable records.
"""
from alembic import op

revision = "0003_version_integrity"
down_revision = "0002_immutable_records"
branch_labels = None
depends_on = None


# Keep migration definitions independent of the evolving ORM model module.
GUARDS = {
    "document_versions": (
        "document lineage must start at version 1 and preserve its key and kind",
        """(NEW.version = 1 AND NEW.supersedes_id IS NOT NULL)
        OR (NEW.version > 1 AND NOT EXISTS (
            SELECT 1 FROM document_versions previous
            WHERE previous.id = NEW.supersedes_id
              AND previous.workspace_id = NEW.workspace_id
              AND previous.document_key = NEW.document_key
              AND previous.kind = NEW.kind
              AND previous.version = NEW.version - 1
        ))""",
    ),
    "requirement_versions": (
        "requirement lineage or source document kind is invalid",
        """(NEW.version = 1 AND NEW.supersedes_id IS NOT NULL)
        OR (NEW.version > 1 AND NOT EXISTS (
            SELECT 1 FROM requirement_versions previous
            WHERE previous.id = NEW.supersedes_id
              AND previous.workspace_id = NEW.workspace_id
              AND previous.requirement_key = NEW.requirement_key
              AND previous.version = NEW.version - 1
        ))
        OR NOT EXISTS (
            SELECT 1 FROM source_spans source
            JOIN document_versions document ON document.id = source.document_version_id
              AND document.workspace_id = source.workspace_id
            WHERE source.id = NEW.source_span_id
              AND source.workspace_id = NEW.workspace_id
              AND document.kind IN ('tender', 'amendment')
        )""",
    ),
    "evidence_facts": (
        "evidence facts must reference an evidence document version",
        """NOT EXISTS (
            SELECT 1 FROM source_spans source
            JOIN document_versions document ON document.id = source.document_version_id
              AND document.workspace_id = source.workspace_id
            WHERE source.id = NEW.source_span_id
              AND source.workspace_id = NEW.workspace_id
              AND document.kind = 'evidence'
        )""",
    ),
    "amendment_changes": (
        "amendment changes must reference an amendment document version",
        """NOT EXISTS (
            SELECT 1 FROM source_spans source
            JOIN document_versions document ON document.id = source.document_version_id
              AND document.workspace_id = source.workspace_id
            WHERE source.id = NEW.source_span_id
              AND source.workspace_id = NEW.workspace_id
              AND document.kind = 'amendment'
        )""",
    ),
    "assessment_evidence": (
        "reviewed assessment evidence is frozen; create a new assessment",
        """EXISTS (
            SELECT 1 FROM review_decisions review
            WHERE review.assessment_id = NEW.assessment_id
              AND review.workspace_id = NEW.workspace_id
        )""",
    ),
}


def upgrade():
    dialect = op.get_context().dialect.name
    if dialect not in ("sqlite", "postgresql"):
        raise RuntimeError("Supported databases: PostgreSQL and SQLite")

    # SQL-only preflight also works with `alembic upgrade --sql` exports.
    op.execute("""CREATE TEMPORARY TABLE _tenderready_integrity_preflight (
        valid INTEGER CONSTRAINT tenderready_existing_lineage_invalid CHECK (valid = 1)
    )""")
    for table, (_, condition) in GUARDS.items():
        # Reviewed existing links are valid. This guard applies only to later
        # additions; it cannot retrospectively infer when old rows were linked.
        if table == "assessment_evidence":
            continue
        existing_condition = condition.replace("NEW.", "candidate.")
        op.execute(f"""INSERT INTO _tenderready_integrity_preflight (valid)
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM {table} candidate WHERE {existing_condition}
            ) THEN 0 ELSE 1 END""")
    op.execute("DROP TABLE _tenderready_integrity_preflight")

    for table, (message, condition) in GUARDS.items():
        if dialect == "postgresql":
            op.execute(f"""CREATE FUNCTION tenderready_validate_{table}() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                IF {condition} THEN
                    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = '{message}';
                END IF;
                RETURN NEW;
                END; $$""")
            op.execute(f"""CREATE TRIGGER validate_{table}
                BEFORE INSERT OR UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION tenderready_validate_{table}()""")
        else:
            for action in ("INSERT", "UPDATE"):
                op.execute(f"""CREATE TRIGGER validate_{table}_{action.lower()}
                    BEFORE {action} ON {table} WHEN {condition}
                    BEGIN SELECT RAISE(ABORT, '{message}'); END""")


def downgrade():
    dialect = op.get_context().dialect.name
    for table in reversed(GUARDS):
        if dialect == "postgresql":
            op.execute(f"DROP TRIGGER validate_{table} ON {table}")
            op.execute(f"DROP FUNCTION tenderready_validate_{table}()")
        else:
            for action in ("insert", "update"):
                op.execute(f"DROP TRIGGER validate_{table}_{action}")
