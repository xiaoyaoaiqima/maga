"""Add expert_total_output column to expert_debug_history

Revision ID: 008_expert_total_output
Revises: 007_tenant_activity_agent
Create Date: 2025-12-11

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008_expert_total_output'
down_revision = '007_tenant_activity_agent'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('expert_debug_history', sa.Column('expert_total_output', sa.JSON(), nullable=True, comment='Expert 返回的完整结果'))

def downgrade() -> None:
    op.drop_column('expert_debug_history', 'expert_total_output')
