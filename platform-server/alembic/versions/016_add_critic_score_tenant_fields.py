"""add tenant/activity/debug_history fields to critic_score_record

Revision ID: 016_tenant_debug
Revises: 015_extend_critic_score_fields
Create Date: 2025-12-16

为统一三种写入场景（job/eval_run/debug）补充字段：
- critic_score_record: tenant_id, activity_id, debug_history_id

注意：MySQL DDL 非事务，迁移做成可重复执行（存在则跳过）。
"""
# pylint: disable=no-member

from alembic import op
import sqlalchemy as sa


revision = "016_tenant_debug"
down_revision = "015_extend_critic_score_fields"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(col.get("name") == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    record_table = "critic_score_record"
    if record_table not in inspector.get_table_names():
        return

    # tenant_id - job 场景
    if not _has_column(inspector, record_table, "tenant_id"):
        op.add_column(
            record_table,
            sa.Column("tenant_id", sa.BigInteger(), nullable=True, comment="租户ID（job场景）"),
        )
        op.create_index("idx_critic_tenant_id", record_table, ["tenant_id"])

    # activity_id - job 场景
    if not _has_column(inspector, record_table, "activity_id"):
        op.add_column(
            record_table,
            sa.Column("activity_id", sa.BigInteger(), nullable=True, comment="活动ID（job场景）"),
        )
        op.create_index("idx_critic_activity_id", record_table, ["activity_id"])

    # debug_history_id - debug 场景
    if not _has_column(inspector, record_table, "debug_history_id"):
        op.add_column(
            record_table,
            sa.Column("debug_history_id", sa.BigInteger(), nullable=True, comment="调试历史ID（debug场景）"),
        )
        op.create_index("idx_critic_debug_history_id", record_table, ["debug_history_id"])


def downgrade() -> None:
    # 为避免误删线上数据与索引，downgrade 仅做最小处理：不自动回滚列/索引。
    # 如确需回滚，请手工评估并执行 ALTER TABLE。
    pass
