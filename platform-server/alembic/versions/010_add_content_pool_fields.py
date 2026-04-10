"""add_content_pool_fields

Revision ID: 010
Revises: 009
Create Date: 2025-12-14 02:56:08.940000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column('content', sa.Column('tenant_id', sa.Integer(), nullable=True, comment='租户ID'))
    op.add_column('content', sa.Column('activity_id', sa.Integer(), nullable=True, comment='活动ID'))
    op.add_column('content', sa.Column('agent_code', sa.String(length=64), nullable=True, comment='Agent编码'))
    op.add_column('content', sa.Column('distribution_status', sa.String(length=32), nullable=False, server_default="PENDING", comment='分发状态：PENDING(待入库)/AVAILABLE(上架)/LOCKED(锁定)/CONSUMED(已消费)'))
    op.add_column('content', sa.Column('lock_until', sa.DateTime(), nullable=True, comment='锁定截止时间'))
    op.add_column('content', sa.Column('external_order_id', sa.String(length=64), nullable=True, comment='外部订单ID（幂等）'))
    op.add_column('content', sa.Column('quality_score', sa.Integer(), nullable=False, server_default="0", comment='质量分（0-100）'))
    op.add_column('content', sa.Column('tags', sa.JSON(), nullable=True, comment='标签列表'))
    
    # Create indexes
    op.create_index(op.f('ix_content_activity_id'), 'content', ['activity_id'], unique=False)
    op.create_index(op.f('ix_content_agent_code'), 'content', ['agent_code'], unique=False)
    op.create_index(op.f('ix_content_distribution_status'), 'content', ['distribution_status'], unique=False)
    op.create_index(op.f('ix_content_external_order_id'), 'content', ['external_order_id'], unique=False)
    op.create_index(op.f('ix_content_quality_score'), 'content', ['quality_score'], unique=False)
    op.create_index(op.f('ix_content_tenant_id'), 'content', ['tenant_id'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_content_tenant_id'), table_name='content')
    op.drop_index(op.f('ix_content_quality_score'), table_name='content')
    op.drop_index(op.f('ix_content_external_order_id'), table_name='content')
    op.drop_index(op.f('ix_content_distribution_status'), table_name='content')
    op.drop_index(op.f('ix_content_agent_code'), table_name='content')
    op.drop_index(op.f('ix_content_activity_id'), table_name='content')
    
    # Drop columns
    op.drop_column('content', 'tags')
    op.drop_column('content', 'quality_score')
    op.drop_column('content', 'external_order_id')
    op.drop_column('content', 'lock_until')
    op.drop_column('content', 'distribution_status')
    op.drop_column('content', 'agent_code')
    op.drop_column('content', 'activity_id')
    op.drop_column('content', 'tenant_id')
