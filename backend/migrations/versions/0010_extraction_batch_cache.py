"""Keep validated extraction checkpoints without changing published history."""
from alembic import op
import sqlalchemy as sa

revision = '0010_extraction_batch_cache'
down_revision = '0009_model_run_context'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('extraction_batch_cache',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('analysis_id', sa.String(36), nullable=False),
        sa.Column('source_span_id', sa.String(36), nullable=False),
        sa.Column('model_run_id', sa.String(36), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.UniqueConstraint('workspace_id', 'analysis_id', 'fingerprint'),
        sa.ForeignKeyConstraint(['workspace_id','analysis_id'], ['document_analyses.workspace_id','document_analyses.id']),
        sa.ForeignKeyConstraint(['workspace_id','source_span_id'], ['source_spans.workspace_id','source_spans.id']),
        sa.ForeignKeyConstraint(['workspace_id','model_run_id'], ['model_runs.workspace_id','model_runs.id']),
        sa.CheckConstraint('length(fingerprint) = 64'))
    op.create_index('ix_extraction_batch_cache_workspace_id','extraction_batch_cache',['workspace_id'])
    if op.get_context().dialect.name == 'postgresql':
        op.execute('CREATE TRIGGER immutable_extraction_batch_cache BEFORE UPDATE OR DELETE ON extraction_batch_cache FOR EACH ROW EXECUTE FUNCTION tenderready_reject_mutation()')
    else:
        for action in ('UPDATE','DELETE'):
            op.execute(f"CREATE TRIGGER immutable_extraction_batch_cache_{action.lower()} BEFORE {action} ON extraction_batch_cache BEGIN SELECT RAISE(ABORT, 'Evidence history is append-only'); END")


def downgrade():
    if op.get_context().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER immutable_extraction_batch_cache ON extraction_batch_cache')
    else:
        for action in ('update','delete'):
            op.execute(f'DROP TRIGGER immutable_extraction_batch_cache_{action}')
    op.drop_index('ix_extraction_batch_cache_workspace_id',table_name='extraction_batch_cache')
    op.drop_table('extraction_batch_cache')
