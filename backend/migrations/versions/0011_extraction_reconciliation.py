"""Append-only audit of cached extraction reconciliation; retain existing rows."""
from alembic import op
import sqlalchemy as sa

revision = '0011_extraction_reconciliation'
down_revision = '0010_extraction_batch_cache'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('extraction_reconciliations',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id'),nullable=False),
        sa.Column('analysis_id',sa.String(36),nullable=False),
        sa.Column('document_version_id',sa.String(36),nullable=False),
        sa.Column('revision',sa.Integer,nullable=False),
        sa.Column('rules_version',sa.String(100),nullable=False),
        sa.Column('input_fingerprint',sa.String(64),nullable=False),
        sa.Column('output_fingerprint',sa.String(64),nullable=False),
        sa.Column('summary',sa.JSON(),nullable=False),sa.Column('changes',sa.JSON(),nullable=False),
        sa.ForeignKeyConstraint(['workspace_id','analysis_id'],['document_analyses.workspace_id','document_analyses.id']),
        sa.ForeignKeyConstraint(['workspace_id','document_version_id'],['document_versions.workspace_id','document_versions.id']),
        sa.UniqueConstraint('workspace_id','document_version_id','revision'),
        sa.CheckConstraint('revision >= 1'),
        sa.CheckConstraint('length(input_fingerprint) = 64 AND length(output_fingerprint) = 64'))
    op.create_index('ix_extraction_reconciliations_workspace_id','extraction_reconciliations',['workspace_id'])
    dialect=op.get_context().dialect.name
    if dialect == 'postgresql':
        op.execute('CREATE TRIGGER immutable_extraction_reconciliations BEFORE UPDATE OR DELETE ON extraction_reconciliations FOR EACH ROW EXECUTE FUNCTION tenderready_reject_mutation()')
    elif dialect == 'sqlite':
        for action in ('UPDATE','DELETE'):
            op.execute(f"CREATE TRIGGER immutable_extraction_reconciliations_{action.lower()} BEFORE {action} ON extraction_reconciliations BEGIN SELECT RAISE(ABORT, 'Evidence history is append-only'); END")
    else:
        raise RuntimeError('Supported databases: PostgreSQL and SQLite')


def downgrade():
    if op.get_context().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER immutable_extraction_reconciliations ON extraction_reconciliations')
    else:
        for action in ('update','delete'):
            op.execute(f'DROP TRIGGER immutable_extraction_reconciliations_{action}')
    op.drop_index('ix_extraction_reconciliations_workspace_id',table_name='extraction_reconciliations')
    op.drop_table('extraction_reconciliations')
