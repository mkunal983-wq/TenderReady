"""Supplier task metadata and immutable task audit."""
from alembic import op
import sqlalchemy as sa

revision = '0007_supplier_workflow'
down_revision = '0f15d90dbcdd'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('corrective_tasks', sa.Column('priority', sa.String(20), nullable=False, server_default='medium'))
    op.add_column('corrective_tasks', sa.Column('due_date', sa.String(10), nullable=True))
    op.add_column('corrective_tasks', sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))
    op.create_index('uq_tasks_workspace_id', 'corrective_tasks', ['workspace_id', 'id'], unique=True)
    op.create_table('task_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('task_id', sa.String(36), nullable=False),
        sa.Column('reviewer', sa.String(200), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id', 'task_id'], ['corrective_tasks.workspace_id', 'corrective_tasks.id']))
    op.create_index('ix_task_events_workspace_id', 'task_events', ['workspace_id'])
    if op.get_context().dialect.name == 'postgresql':
        op.execute('CREATE TRIGGER immutable_task_events BEFORE UPDATE OR DELETE ON task_events FOR EACH ROW EXECUTE FUNCTION tenderready_reject_mutation()')
    else:
        for action in ('UPDATE', 'DELETE'):
            op.execute(f"CREATE TRIGGER immutable_task_events_{action.lower()} BEFORE {action} ON task_events BEGIN SELECT RAISE(ABORT, 'Task history is append-only'); END")


def downgrade():
    op.drop_table('task_events')
    op.drop_index('uq_tasks_workspace_id', table_name='corrective_tasks')
    for column in ('revision', 'due_date', 'priority'):
        op.drop_column('corrective_tasks', column)
