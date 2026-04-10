"""add expert_batch_score_result table

Revision ID: 014_expert_batch_score_result
Revises: 013_critic_score
Create Date: 2025-12-15 23:59:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '014_expert_batch_score_result'
down_revision = '013_critic_score'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL DDL 非事务：如果上次迁移中断，可能出现“表已创建但版本未写入”的不一致状态
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'expert_batch_score_result'

    if table_name not in inspector.get_table_names():
        op.create_table(
            table_name,
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='技术主键'),
            sa.Column('expert_config_code', sa.String(length=64), nullable=False, comment='expert_config 配置 code'),
            sa.Column('content_id', sa.String(length=64), nullable=True, comment='测试用例 content_id（关联 content 表）'),
            sa.Column('title', sa.String(length=500), nullable=True, comment='文章标题'),
            sa.Column('content', sa.Text(), nullable=True, comment='文章正文'),
            sa.Column('score', sa.Integer(), nullable=True, comment='评分分数 (0-100)'),
            sa.Column('reason', sa.Text(), nullable=True, comment='评分理由'),
            sa.Column('highlights', sa.Text(), nullable=True, comment='精彩原文摘录'),
            sa.Column('model_code', sa.String(length=255), nullable=True, comment='使用的模型编码'),
            sa.Column('execution_time_ms', sa.Integer(), nullable=True, comment='执行耗时（毫秒）'),
            sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息（如果失败）'),
            sa.Column('success', sa.Boolean(), nullable=False, server_default='1', comment='是否成功'),
            sa.Column('create_time', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True, comment='创建时间'),
            sa.Column('created_by', sa.String(length=255), nullable=True, comment='创建人'),
            sa.PrimaryKeyConstraint('id'),
            comment='专家批量评分结果表'
        )

    # 确保索引存在（表可能已存在但索引未创建）
    existing_indexes = {ix.get("name") for ix in inspector.get_indexes(table_name)}
    if 'ix_expert_batch_score_result_expert_config_code' not in existing_indexes:
        op.create_index('ix_expert_batch_score_result_expert_config_code', table_name, ['expert_config_code'])
    if 'ix_expert_batch_score_result_content_id' not in existing_indexes:
        op.create_index('ix_expert_batch_score_result_content_id', table_name, ['content_id'])


def downgrade() -> None:
    op.drop_table('expert_batch_score_result')
