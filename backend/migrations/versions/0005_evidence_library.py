"""Workspace-scoped, immutable supplier document classification."""
from alembic import op
import sqlalchemy as sa
revision = '0005_evidence_library'
down_revision = 'b87e2ed89db4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('evidence_library_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('document_version_id', sa.String(36), nullable=False, unique=True),
        sa.Column('evidence_type', sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id', 'document_version_id'], ['document_versions.workspace_id','document_versions.id']),
        sa.CheckConstraint("evidence_type IN ('datasheet','authorization','certificate','project_reference')"))
    op.create_index('ix_evidence_library_entries_workspace_id', 'evidence_library_entries', ['workspace_id'])
    condition = "NOT EXISTS (SELECT 1 FROM document_versions WHERE id=NEW.document_version_id AND workspace_id=NEW.workspace_id AND kind='evidence')"
    if op.get_context().dialect.name == 'sqlite':
        for action in ('UPDATE','DELETE'):
            op.execute(f"CREATE TRIGGER immutable_evidence_library_{action.lower()} BEFORE {action} ON evidence_library_entries BEGIN SELECT RAISE(ABORT, 'Evidence history is append-only'); END")
        op.execute(f"CREATE TRIGGER evidence_library_kind BEFORE INSERT ON evidence_library_entries WHEN {condition} BEGIN SELECT RAISE(ABORT, 'Evidence document required'); END")
    else:
        op.execute('CREATE TRIGGER immutable_evidence_library BEFORE UPDATE OR DELETE ON evidence_library_entries FOR EACH ROW EXECUTE FUNCTION tenderready_reject_mutation()')
        op.execute(f"CREATE FUNCTION tenderready_library_kind() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF {condition} THEN RAISE EXCEPTION 'Evidence document required'; END IF; RETURN NEW; END; $$")
        op.execute('CREATE TRIGGER evidence_library_kind BEFORE INSERT ON evidence_library_entries FOR EACH ROW EXECUTE FUNCTION tenderready_library_kind()')


def downgrade():
    op.drop_table('evidence_library_entries')
    if op.get_context().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION tenderready_library_kind()')
