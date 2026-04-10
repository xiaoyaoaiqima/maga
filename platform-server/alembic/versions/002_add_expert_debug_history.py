"""add expert_debug_history table

Revision ID: 002
Revises: 001
Create Date: 2025-12-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001_add_auth_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 expert_debug_history 表"""
    op.create_table(
        'expert_debug_history',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='技术主键'),
        sa.Column('expert_config_code', sa.String(64), nullable=False, comment='调试的 expert_config_code'),
        sa.Column('expert_config_name', sa.String(255), nullable=True, comment='调试时的 expert_config 名称'),
        sa.Column('success', sa.Boolean(), nullable=False, default=False, comment='执行是否成功'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('model_code', sa.String(255), nullable=True, comment='使用的模型编码'),
        sa.Column('model_config_used', sa.JSON(), nullable=True, comment='实际使用的模型配置'),
        sa.Column('prompt_template', sa.Text(), nullable=True, comment='原始 prompt 模板'),
        sa.Column('plugin_config_snapshot', sa.JSON(), nullable=True, comment='使用的 plugin_config_snapshot'),
        sa.Column('rendered_prompt', sa.Text(), nullable=True, comment='渲染后的 prompt'),
        sa.Column('prompt_override', sa.Text(), nullable=True, comment='用户手动覆盖的 prompt'),
        sa.Column('input_content', sa.Text(), nullable=True, comment='输入的测试内容'),
        sa.Column('output_content', sa.Text(), nullable=True, comment='AI 输出的内容'),
        sa.Column('execution_time_ms', sa.Integer(), nullable=False, default=0, comment='执行时间（毫秒）'),
        sa.Column('token_usage', sa.JSON(), nullable=True, comment='Token 使用情况'),
        sa.Column('trace_id', sa.String(64), nullable=True, comment='调用追踪 ID'),
        sa.Column('is_starred', sa.Boolean(), nullable=False, default=False, comment='是否收藏'),
        sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        sa.Column('created_by', sa.String(255), nullable=True, comment='创建人'),
        sa.Column('is_deleted', sa.BigInteger(), nullable=True, default=0, comment='是否删除'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('idx_debug_history_expert_code', 'expert_debug_history', ['expert_config_code'])
    op.create_index('idx_debug_history_create_time', 'expert_debug_history', ['create_time'])
    op.create_index('idx_debug_history_starred', 'expert_debug_history', ['is_starred'])


def downgrade() -> None:
    """删除 expert_debug_history 表"""
    op.drop_index('idx_debug_history_starred', table_name='expert_debug_history')
    op.drop_index('idx_debug_history_create_time', table_name='expert_debug_history')
    op.drop_index('idx_debug_history_expert_code', table_name='expert_debug_history')
    op.drop_table('expert_debug_history')

