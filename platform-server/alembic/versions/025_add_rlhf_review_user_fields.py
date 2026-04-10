"""add rlhf review user fields

Revision ID: 025_add_rlhf_review_user_fields
Revises: 024_inspection_data
Create Date: 2024-12-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '025_add_rlhf_review_user_fields'
down_revision: Union[str, None] = '024_inspection_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in columns


def _index_exists(table_name: str, index_name: str) -> bool:
    """检查索引是否存在"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    indexes = [i['name'] for i in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    """添加审核人信息字段"""
    
    # 添加 review_user_id 字段
    if not _column_exists('rlhf_feedback', 'review_user_id'):
        op.add_column(
            'rlhf_feedback',
            sa.Column('review_user_id', sa.String(64), nullable=True, comment='审核人ID')
        )
    
    # 添加 review_user_name 字段
    if not _column_exists('rlhf_feedback', 'review_user_name'):
        op.add_column(
            'rlhf_feedback',
            sa.Column('review_user_name', sa.String(64), nullable=True, comment='审核人姓名')
        )
    
    # 添加 review_time 字段
    if not _column_exists('rlhf_feedback', 'review_time'):
        op.add_column(
            'rlhf_feedback',
            sa.Column('review_time', sa.DateTime(timezone=True), nullable=True, comment='审核时间')
        )
    
    # 添加索引以支持按审核人查询
    if not _index_exists('rlhf_feedback', 'ix_rlhf_feedback_review_user_id'):
        op.create_index('ix_rlhf_feedback_review_user_id', 'rlhf_feedback', ['review_user_id'])


def downgrade() -> None:
    """移除审核人信息字段"""
    op.drop_index('ix_rlhf_feedback_review_user_id', table_name='rlhf_feedback')
    op.drop_column('rlhf_feedback', 'review_time')
    op.drop_column('rlhf_feedback', 'review_user_name')
    op.drop_column('rlhf_feedback', 'review_user_id')
