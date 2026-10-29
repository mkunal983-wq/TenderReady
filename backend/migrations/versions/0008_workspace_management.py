"""Retain deleted workspace records and their immutable evidence history."""
from alembic import op
import sqlalchemy as sa

revision = '0008_workspace_management'
down_revision = '0007_supplier_workflow'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('workspaces', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('workspaces', 'deleted_at')
