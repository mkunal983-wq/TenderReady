"""Record per-call provenance and timing without changing existing model runs."""
from alembic import op
import sqlalchemy as sa

revision = "0009_model_run_context"
down_revision = "0008_workspace_management"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("uq_model_runs_workspace_id_id", "model_runs", ["workspace_id", "id"], unique=True)
    op.create_table(
        "model_run_contexts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("model_run_id", sa.String(36), nullable=False, unique=True),
        sa.Column("analysis_id", sa.String(36), nullable=False),
        sa.Column("source_span_id", sa.String(36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer),
        sa.Column("error_code", sa.String(50)),
        sa.ForeignKeyConstraint(["workspace_id", "model_run_id"], ["model_runs.workspace_id", "model_runs.id"]),
        sa.ForeignKeyConstraint(["workspace_id", "analysis_id"], ["document_analyses.workspace_id", "document_analyses.id"]),
        sa.ForeignKeyConstraint(["workspace_id", "source_span_id"], ["source_spans.workspace_id", "source_spans.id"]),
        sa.CheckConstraint("attempts IS NULL OR attempts >= 1"),
    )
    op.create_index("ix_model_run_contexts_workspace_id", "model_run_contexts", ["workspace_id"])
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        op.execute("CREATE TRIGGER immutable_model_run_contexts BEFORE UPDATE OR DELETE ON model_run_contexts FOR EACH ROW EXECUTE FUNCTION tenderready_reject_mutation()")
    elif dialect == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER immutable_model_run_contexts_{action.lower()} BEFORE {action} ON model_run_contexts BEGIN SELECT RAISE(ABORT, 'Evidence history is append-only'); END")
    else:
        raise RuntimeError("Supported databases: PostgreSQL and SQLite")


def downgrade():
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER immutable_model_run_contexts ON model_run_contexts")
    else:
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER immutable_model_run_contexts_{action}")
    op.drop_index("ix_model_run_contexts_workspace_id", table_name="model_run_contexts")
    op.drop_table("model_run_contexts")
    op.drop_index("uq_model_runs_workspace_id_id", table_name="model_runs")
