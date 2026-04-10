"""add expert_debug_batch_task table

Revision ID: 20251217_add_expert_debug_batch_task
Revises: 
Create Date: 2025-12-17 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '20251217_debug_batch'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建批量调试任务表"""
    # 检查表是否存在
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'expert_debug_batch_task' not in tables:
        op.create_table('expert_debug_batch_task',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True, comment='主键'),
            sa.Column('task_id', sa.String(length=64), nullable=False, comment='任务唯一标识'),
            sa.Column('expert_config_code', sa.String(length=128), nullable=False, comment='Expert 配置编码'),
            sa.Column('expert_config_name', sa.String(length=256), nullable=True, comment='Expert 配置名称'),
            sa.Column('status', sa.String(length=32), nullable=False, comment='任务状态: pending/running/completed/failed'),
            sa.Column('total', sa.Integer(), nullable=False, default=0, comment='总任务数'),
            sa.Column('completed', sa.Integer(), nullable=False, default=0, comment='已完成数'),
            sa.Column('success_count', sa.Integer(), nullable=False, default=0, comment='成功数'),
            sa.Column('failed_count', sa.Integer(), nullable=False, default=0, comment='失败数'),
            sa.Column('request_params', mysql.JSON(), nullable=True, comment='请求参数'),
            sa.Column('results', mysql.JSON(), nullable=True, comment='结果列表'),
            sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
            sa.Column('start_time', sa.DateTime(), nullable=True, comment='开始时间'),
            sa.Column('end_time', sa.DateTime(), nullable=True, comment='结束时间'),
            sa.Column('create_time', sa.DateTime(), server_default=sa.func.now(), nullable=False, comment='创建时间'),
            sa.Column('update_time', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False, comment='更新时间'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('task_id', name='uk_task_id'),
            sa.Index('idx_expert_config_code', 'expert_config_code'),
            sa.Index('idx_status', 'status'),
            sa.Index('idx_create_time', 'create_time'),
            comment='Expert 批量调试任务表'
        )


def downgrade() -> None:
    """删除批量调试任务表"""
    op.drop_table('expert_debug_batch_task')

