"""extend critic score fields for visualization

Revision ID: 015_extend_critic_score_fields
Revises: 014_expert_batch_score_result
Create Date: 2025-12-16

为“线上打分 + 批量评测”统一可视化补齐字段：
- critic_score_record: source_type/dataset_code/run_id/test_case_id/highlights
- critic_score_daily_stats: source_type/dataset_code，并更新唯一约束维度

注意：MySQL DDL 非事务，迁移做成可重复执行（存在则跳过）。
"""
# pylint: disable=no-member

from alembic import op
import sqlalchemy as sa


revision = "015_extend_critic_score_fields"
down_revision = "014_expert_batch_score_result"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(col.get("name") == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ---------------- critic_score_record ----------------
    record_table = "critic_score_record"
    if record_table in inspector.get_table_names():
        if not _has_column(inspector, record_table, "source_type"):
            op.add_column(
                record_table,
                sa.Column("source_type", sa.String(32), nullable=False, server_default="job", comment="来源类型：job/eval_run/debug"),
            )
            op.create_index("idx_critic_source_type", record_table, ["source_type"])

        if not _has_column(inspector, record_table, "dataset_code"):
            op.add_column(
                record_table,
                sa.Column("dataset_code", sa.String(64), nullable=True, comment="数据集标识（eval_run/test_case 场景）"),
            )
            op.create_index("idx_critic_dataset_code", record_table, ["dataset_code"])

        if not _has_column(inspector, record_table, "run_id"):
            op.add_column(
                record_table,
                sa.Column("run_id", sa.BigInteger(), nullable=True, comment="eval_run id（批量测试场景）"),
            )
            op.create_index("idx_critic_run_id", record_table, ["run_id"])

        if not _has_column(inspector, record_table, "test_case_id"):
            op.add_column(
                record_table,
                sa.Column("test_case_id", sa.BigInteger(), nullable=True, comment="test_case id（批量测试场景）"),
            )
            op.create_index("idx_critic_test_case_id", record_table, ["test_case_id"])

        if not _has_column(inspector, record_table, "highlights"):
            op.add_column(
                record_table,
                sa.Column("highlights", sa.Text(), nullable=True, comment="精彩原文摘录"),
            )

    # ---------------- critic_score_daily_stats ----------------
    stats_table = "critic_score_daily_stats"
    if stats_table in inspector.get_table_names():
        if not _has_column(inspector, stats_table, "source_type"):
            op.add_column(
                stats_table,
                sa.Column("source_type", sa.String(32), nullable=False, server_default="job", comment="来源类型：job/eval_run/debug"),
            )
            op.create_index("idx_critic_stats_source_type", stats_table, ["source_type"])

        if not _has_column(inspector, stats_table, "dataset_code"):
            op.add_column(
                stats_table,
                sa.Column("dataset_code", sa.String(64), nullable=True, comment="数据集标识（eval_run/test_case 场景）"),
            )
            op.create_index("idx_critic_stats_dataset_code", stats_table, ["dataset_code"])

        # 更新唯一约束：uq_critic_daily_stats
        existing_uq = {uc.get("name") for uc in inspector.get_unique_constraints(stats_table)}
        if "uq_critic_daily_stats" in existing_uq:
            # 旧约束字段较少，需要 drop 再建
            op.drop_constraint("uq_critic_daily_stats", stats_table, type_="unique")

        op.create_unique_constraint(
            "uq_critic_daily_stats",
            stats_table,
            ["stat_date", "source_type", "dataset_code", "expert_config_code", "expert_func", "model_code"],
        )


def downgrade() -> None:
    # 为避免误删线上数据与索引，downgrade 仅做最小处理：不自动回滚列/索引。
    # 如确需回滚，请手工评估并执行 ALTER TABLE。
    pass

