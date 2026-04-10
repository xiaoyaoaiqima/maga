"""Add RLHF trace fields

Revision ID: 006_rlhf_trace
Revises: 005_rlhf
Create Date: 2025-12-09

扩展 expert_call_trace 表，支持 RLHF 阶段追踪：
- rlhf_feedback_id: 关联 rlhf_feedback.id
- reviewer_id: 审核人ID
- reviewer_name: 审核人姓名
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_rlhf_trace'
down_revision = '005_rlhf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加 RLHF 扩展字段
    op.add_column(
        'expert_call_trace',
        sa.Column('rlhf_feedback_id', sa.BigInteger(), nullable=True, comment='关联 rlhf_feedback.id')
    )
    op.add_column(
        'expert_call_trace',
        sa.Column('reviewer_id', sa.String(64), nullable=True, comment='审核人ID（RLHF 阶段）')
    )
    op.add_column(
        'expert_call_trace',
        sa.Column('reviewer_name', sa.String(64), nullable=True, comment='审核人姓名')
    )
    
    # 添加索引
    op.create_index('idx_rlhf_feedback', 'expert_call_trace', ['rlhf_feedback_id'])
    op.create_index('idx_reviewer', 'expert_call_trace', ['reviewer_id', 'created_at'])


def downgrade() -> None:
    # 删除索引
    op.drop_index('idx_reviewer', table_name='expert_call_trace')
    op.drop_index('idx_rlhf_feedback', table_name='expert_call_trace')
    
    # 删除字段
    op.drop_column('expert_call_trace', 'reviewer_name')
    op.drop_column('expert_call_trace', 'reviewer_id')
    op.drop_column('expert_call_trace', 'rlhf_feedback_id')

