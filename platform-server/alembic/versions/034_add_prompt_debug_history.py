"""add prompt debug history

Revision ID: 034_add_prompt_debug_history
Revises: 033_add_comment_delivery_ledger
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "034_add_prompt_debug_history"
down_revision = "033_add_comment_delivery_ledger"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("content_prompt_debug_history"):
        return
    op.create_table(
        "content_prompt_debug_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("run_group_id", sa.String(64), nullable=False, comment="工作台执行组ID"),
        sa.Column("workbench_mode", sa.String(16), nullable=False, server_default="single", comment="single/compare"),
        sa.Column("panel_key", sa.String(16), nullable=False, server_default="left", comment="left/right"),
        sa.Column("item_index", sa.Integer(), nullable=False, server_default="0", comment="组内篇序号，从0开始"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1", comment="面板并发篇数"),
        sa.Column("prompt", mysql.LONGTEXT(), nullable=False, comment="用户 Prompt"),
        sa.Column("system_prompt", mysql.LONGTEXT(), nullable=True, comment="System Prompt"),
        sa.Column("requested_model_code", sa.String(128), nullable=False, comment="请求模型编码"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.9", comment="temperature"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="1500", comment="max_tokens"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否成功"),
        sa.Column("content", mysql.LONGTEXT(), nullable=True, comment="模型原始输出"),
        sa.Column("model_code", sa.String(128), nullable=True, comment="实际模型编码"),
        sa.Column("provider_code", sa.String(64), nullable=True, comment="Provider 编码"),
        sa.Column("provider_model", sa.String(128), nullable=True, comment="Provider 模型"),
        sa.Column("token_usage", sa.JSON(), nullable=True, comment="Token 使用"),
        sa.Column("latency_ms", sa.Integer(), nullable=True, comment="调用耗时毫秒"),
        sa.Column("error_message", mysql.LONGTEXT(), nullable=True, comment="失败信息"),
        sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_prompt_debug_history_run_group", "content_prompt_debug_history", ["run_group_id"])
    op.create_index("idx_prompt_debug_history_success", "content_prompt_debug_history", ["success"])
    op.create_index("idx_prompt_debug_history_create_time", "content_prompt_debug_history", ["create_time"])


def downgrade() -> None:
    if _table_exists("content_prompt_debug_history"):
        op.drop_table("content_prompt_debug_history")
