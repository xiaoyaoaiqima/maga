"""add expert_type field to critic_score_record

Revision ID: 018_expert_type
Revises: 017_problem_tags_snippets
Create Date: 2025-12-17

为 critic_score_record 添加 expert_type 字段，用于区分 BAN（合规封禁）和 CRITIC（质量评分）类型。
同时更新现有数据：根据 expert_func 设置 expert_type。

BAN 类型的 expert_func:
- CriticIllegal（不合法）
- CriticKeywordFilter（违禁词）
- CriticUnreasonable（不合理）
- CriticCounterproductive（不合目的）

其他均为 CRITIC 类型。
"""
# pylint: disable=no-member

from alembic import op
import sqlalchemy as sa


revision = "018_expert_type"
down_revision = "017_problem_tags_snippets"
branch_labels = None
depends_on = None


# BAN 类型的 expert_func 列表
BAN_EXPERT_FUNCS = (
    "CriticIllegal",
    "CriticKeywordFilter",
    "CriticUnreasonable",
    "CriticCounterproductive",
)


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(col.get("name") == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    record_table = "critic_score_record"
    if record_table not in inspector.get_table_names():
        return

    # 1. 添加 expert_type 字段
    if not _has_column(inspector, record_table, "expert_type"):
        op.add_column(
            record_table,
            sa.Column(
                "expert_type",
                sa.String(32),
                nullable=False,
                server_default="CRITIC",
                comment="专家类型：BAN（合规封禁）/ CRITIC（质量评分）",
            ),
        )
        op.create_index("idx_critic_expert_type", record_table, ["expert_type"])

    # 2. 根据 expert_func 更新现有数据的 expert_type
    # BAN 类型
    ban_funcs_str = ", ".join(f"'{f}'" for f in BAN_EXPERT_FUNCS)
    op.execute(
        f"""
        UPDATE {record_table}
        SET expert_type = 'BAN'
        WHERE expert_func IN ({ban_funcs_str})
          AND expert_type = 'CRITIC'
        """
    )


def downgrade() -> None:
    # 为避免误删线上数据与索引，downgrade 仅做最小处理
    pass

