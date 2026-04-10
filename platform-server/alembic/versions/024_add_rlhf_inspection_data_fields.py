"""Add rlhf inspection data fields

Revision ID: 024_inspection_data
Revises: 023_rlhf_annotations
Create Date: 2025-12-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '024_inspection_data'
down_revision = '023_rlhf_annotations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get current columns
    conn = op.get_bind()
    columns = [c['name'] for c in sa.inspect(conn).get_columns('rlhf_feedback')]
    
    if 'inspection_status' not in columns:
        op.add_column('rlhf_feedback', sa.Column('inspection_status', sa.String(32), nullable=True, server_default='PENDING', comment='抽检状态: PENDING/IN_PROGRESS/PASSED/FAILED'))
        op.create_index('idx_rlhf_inspection_status', 'rlhf_feedback', ['inspection_status'])
    
    if 'inspection_result' not in columns:
        op.add_column('rlhf_feedback', sa.Column('inspection_result', sa.String(32), nullable=True, comment='抽检结果: PASSED/FAILED'))
    
    if 'inspection_comment' not in columns:
        op.add_column('rlhf_feedback', sa.Column('inspection_comment', sa.Text(), nullable=True, comment='抽检意见'))
    
    if 'inspection_user_id' not in columns:
        op.add_column('rlhf_feedback', sa.Column('inspection_user_id', sa.String(64), nullable=True, comment='抽检人ID'))
    
    if 'inspection_user_name' not in columns:
        op.add_column('rlhf_feedback', sa.Column('inspection_user_name', sa.String(64), nullable=True, comment='抽检人姓名'))
    
    if 'inspection_time' not in columns:
        op.add_column('rlhf_feedback', sa.Column('inspection_time', sa.DateTime(timezone=True), nullable=True, comment='抽检时间'))


def downgrade() -> None:
    op.drop_index('idx_rlhf_inspection_status', 'rlhf_feedback')
    op.drop_column('rlhf_feedback', 'inspection_time')
    op.drop_column('rlhf_feedback', 'inspection_user_name')
    op.drop_column('rlhf_feedback', 'inspection_user_id')
    op.drop_column('rlhf_feedback', 'inspection_comment')
    op.drop_column('rlhf_feedback', 'inspection_result')
    op.drop_column('rlhf_feedback', 'inspection_status')

