"""Enforce evidence history immutability at the database boundary."""
from alembic import op

revision = "0002_immutable_records"
down_revision = "7f509ab5bc0d"
branch_labels = None
depends_on = None

TABLES = (
    "document_versions", "source_spans", "requirement_versions", "evidence_facts",
    "assessments", "assessment_evidence", "review_decisions", "model_runs",
)


def upgrade():
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        op.execute("""CREATE FUNCTION tenderready_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Evidence history is append-only; insert a new version';
        END; $$""")
        for table in TABLES:
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION tenderready_reject_mutation()")
    elif dialect == "sqlite":
        for table in TABLES:
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Evidence history is append-only'); END")
    else:
        raise RuntimeError("Supported databases: PostgreSQL and SQLite")


def downgrade():
    dialect = op.get_context().dialect.name
    for table in TABLES:
        if dialect == "postgresql":
            op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
        else:
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER immutable_{table}_{action}")
    if dialect == "postgresql":
        op.execute("DROP FUNCTION tenderready_reject_mutation()")
