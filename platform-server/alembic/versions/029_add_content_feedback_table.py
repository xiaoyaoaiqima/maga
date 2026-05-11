"""add content feedback table

Revision ID: 029_add_content_feedback_table
Revises: 028_add_content_agent_execution_layer
Create Date: 2026-05-11

"""
from alembic import op
import sqlalchemy as sa


revision = "029_add_content_feedback_table"
down_revision = "028_add_content_agent_execution_layer"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return index_name in [idx["name"] for idx in inspector.get_indexes(table_name)]


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    if not _table_exists("content_feedback"):
        op.create_table(
            "content_feedback",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("batch_id", sa.BigInteger(), nullable=True, comment="批次ID"),
            sa.Column("item_id", sa.BigInteger(), nullable=False, comment="批次文章ID"),
            sa.Column("version_id", sa.BigInteger(), nullable=True, comment="反馈版本ID"),
            sa.Column("task_id", sa.BigInteger(), nullable=True, comment="任务ID"),
            sa.Column("run_id", sa.BigInteger(), nullable=True, comment="Run ID"),
            sa.Column("artifact_id", sa.BigInteger(), nullable=True, comment="Artifact ID"),
            sa.Column("action", sa.String(32), nullable=False, comment="反馈动作"),
            sa.Column("review_status", sa.String(32), nullable=False, comment="评审状态"),
            sa.Column("quoted_text", sa.Text(), nullable=True, comment="引用片段"),
            sa.Column("comment", sa.Text(), nullable=True, comment="反馈内容"),
            sa.Column("submitter", sa.String(100), nullable=True, comment="提交人"),
            sa.Column("metadata_json", sa.JSON(), nullable=True, comment="扩展数据"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.PrimaryKeyConstraint("id"),
        )
    for index_name, columns in (
        ("idx_content_feedback_batch_id", ["batch_id"]),
        ("idx_content_feedback_item_id", ["item_id"]),
        ("idx_content_feedback_version_id", ["version_id"]),
        ("idx_content_feedback_task_id", ["task_id"]),
        ("idx_content_feedback_run_id", ["run_id"]),
        ("idx_content_feedback_artifact_id", ["artifact_id"]),
        ("idx_content_feedback_action", ["action"]),
        ("idx_content_feedback_review_status", ["review_status"]),
        ("idx_content_feedback_submitter", ["submitter"]),
    ):
        _create_index_if_missing(index_name, "content_feedback", columns)


def downgrade() -> None:
    for index_name in (
        "idx_content_feedback_submitter",
        "idx_content_feedback_review_status",
        "idx_content_feedback_action",
        "idx_content_feedback_artifact_id",
        "idx_content_feedback_run_id",
        "idx_content_feedback_task_id",
        "idx_content_feedback_version_id",
        "idx_content_feedback_item_id",
        "idx_content_feedback_batch_id",
    ):
        if _table_exists("content_feedback") and _index_exists("content_feedback", index_name):
            op.drop_index(index_name, table_name="content_feedback")
    if _table_exists("content_feedback"):
        op.drop_table("content_feedback")
