"""add problem_tags/problem_snippets fields

Revision ID: 017_problem_tags_snippets
Revises: 016_tenant_debug
Create Date: 2025-12-16

为 Critic 输出结构补齐更直观字段：
- critic_score_record: problem_tags(JSON), problem_snippets(JSON)
- expert_eval_result: problem_tags(JSON), problem_snippets(JSON)
- expert_batch_score_result: problem_tags(JSON), problem_snippets(JSON)

注意：MySQL DDL 非事务，迁移做成可重复执行（存在则跳过）。
"""

# pylint: disable=no-member

from alembic import op
import sqlalchemy as sa


revision = "017_problem_tags_snippets"
down_revision = "016_tenant_debug"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(col.get("name") == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def ensure_problem_fields(table: str) -> None:
        if table not in inspector.get_table_names():
            return

        if not _has_column(inspector, table, "problem_tags"):
            op.add_column(
                table,
                sa.Column("problem_tags", sa.JSON(), nullable=True, comment="问题标签（从模型输出解析）"),
            )
        if not _has_column(inspector, table, "problem_snippets"):
            op.add_column(
                table,
                sa.Column("problem_snippets", sa.JSON(), nullable=True, comment="问题片段列表（用于高亮展示）"),
            )

    ensure_problem_fields("critic_score_record")
    ensure_problem_fields("expert_eval_result")
    ensure_problem_fields("expert_batch_score_result")


def downgrade() -> None:
    # 为避免误删线上数据与索引，downgrade 仅做最小处理：不自动回滚列。
    # 如确需回滚，请手工评估并执行 ALTER TABLE。
    pass

