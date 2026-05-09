"""add prompt optimizer tables

Revision ID: 027_add_prompt_optimizer_tables
Revises: 026_add_test_set_table, 20260125_add_dashboard_cache
Create Date: 2026-05-07

"""
from alembic import op
import sqlalchemy as sa


revision = "027_add_prompt_optimizer_tables"
down_revision = ("026_add_test_set_table", "20260125_add_dashboard_cache")
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
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    if not _table_exists("prompt_asset"):
        op.create_table(
            "prompt_asset",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("tenant_code", sa.String(64), nullable=True, comment="租户编码"),
            sa.Column("name", sa.String(255), nullable=False, comment="提示词名称"),
            sa.Column("prompt_type", sa.String(32), nullable=False, server_default="generation", comment="提示词类型"),
            sa.Column("description", sa.Text(), nullable=True, comment="描述"),
            sa.Column("current_version_id", sa.BigInteger(), nullable=True, comment="当前版本ID"),
            sa.Column("tags", sa.JSON(), nullable=True, comment="标签"),
            sa.Column("is_deleted", sa.Integer(), nullable=False, server_default="0", comment="是否删除"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.Column("update_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("idx_prompt_asset_tenant_code", "prompt_asset", ["tenant_code"])

    if not _table_exists("prompt_version"):
        op.create_table(
            "prompt_version",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("prompt_id", sa.BigInteger(), nullable=False, comment="提示词资产ID"),
            sa.Column("version_no", sa.Integer(), nullable=False, comment="版本号"),
            sa.Column("content", sa.Text(), nullable=False, comment="提示词内容"),
            sa.Column("parent_version_id", sa.BigInteger(), nullable=True, comment="父版本ID"),
            sa.Column("source_run_id", sa.BigInteger(), nullable=True, comment="来源优化任务ID"),
            sa.Column("change_summary", sa.Text(), nullable=True, comment="变更摘要"),
            sa.Column("created_by", sa.String(64), nullable=True, comment="创建人"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("prompt_id", "version_no", name="uq_prompt_version_prompt_version_no"),
        )
    _create_index_if_missing("idx_prompt_version_prompt_id", "prompt_version", ["prompt_id"])
    _create_index_if_missing("idx_prompt_version_source_run_id", "prompt_version", ["source_run_id"])

    if not _table_exists("prompt_issue"):
        op.create_table(
            "prompt_issue",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("prompt_id", sa.BigInteger(), nullable=False, comment="提示词资产ID"),
            sa.Column("prompt_version_id", sa.BigInteger(), nullable=False, comment="提示词版本ID"),
            sa.Column("issue_type", sa.String(32), nullable=False, server_default="human_opinion", comment="问题类型"),
            sa.Column("problem_text", sa.Text(), nullable=False, comment="问题描述/人类意见"),
            sa.Column("generated_content", sa.Text(), nullable=True, comment="生成内容"),
            sa.Column("generated_title", sa.Text(), nullable=True, comment="生成标题"),
            sa.Column("issue_metadata", sa.JSON(), nullable=True, comment="扩展元数据"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("idx_prompt_issue_prompt_id", "prompt_issue", ["prompt_id"])
    _create_index_if_missing("idx_prompt_issue_prompt_version_id", "prompt_issue", ["prompt_version_id"])

    if not _table_exists("prompt_optimizer_run"):
        op.create_table(
            "prompt_optimizer_run",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("prompt_id", sa.BigInteger(), nullable=False, comment="提示词资产ID"),
            sa.Column("prompt_version_id", sa.BigInteger(), nullable=False, comment="提示词版本ID"),
            sa.Column("issue_id", sa.BigInteger(), nullable=True, comment="问题ID"),
            sa.Column("mode", sa.String(32), nullable=False, comment="优化模式"),
            sa.Column("model", sa.String(128), nullable=True, comment="模型"),
            sa.Column("base_url", sa.String(512), nullable=True, comment="模型 API 地址"),
            sa.Column("temperature", sa.String(32), nullable=True, comment="温度参数"),
            sa.Column("max_tokens", sa.Integer(), nullable=True, comment="最大输出 token"),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending", comment="状态"),
            sa.Column("input_snapshot", sa.JSON(), nullable=True, comment="输入快照"),
            sa.Column("raw_output", sa.Text(), nullable=True, comment="模型原始输出"),
            sa.Column("parsed_output", sa.JSON(), nullable=True, comment="解析后的输出"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.Column("update_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("idx_prompt_optimizer_run_prompt_id", "prompt_optimizer_run", ["prompt_id"])
    _create_index_if_missing("idx_prompt_optimizer_run_prompt_version_id", "prompt_optimizer_run", ["prompt_version_id"])
    _create_index_if_missing("idx_prompt_optimizer_run_issue_id", "prompt_optimizer_run", ["issue_id"])
    _create_index_if_missing("idx_prompt_optimizer_run_mode", "prompt_optimizer_run", ["mode"])
    _create_index_if_missing("idx_prompt_optimizer_run_status", "prompt_optimizer_run", ["status"])

    if not _table_exists("prompt_patch"):
        op.create_table(
            "prompt_patch",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("run_id", sa.BigInteger(), nullable=False, comment="优化任务ID"),
            sa.Column("patch_index", sa.Integer(), nullable=False, comment="patch 顺序"),
            sa.Column("operation", sa.String(32), nullable=False, comment="操作"),
            sa.Column("old_text", sa.Text(), nullable=False, comment="原文或定位锚点"),
            sa.Column("new_text", sa.Text(), nullable=True, comment="新文本"),
            sa.Column("reason", sa.Text(), nullable=True, comment="修改原因"),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending", comment="审阅状态"),
            sa.Column("edited_new_text", sa.Text(), nullable=True, comment="人工编辑后的新文本"),
            sa.Column("review_comment", sa.Text(), nullable=True, comment="人工审阅备注"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.Column("update_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "patch_index", name="uq_prompt_patch_run_index"),
        )
    _create_index_if_missing("idx_prompt_patch_run_id", "prompt_patch", ["run_id"])
    _create_index_if_missing("idx_prompt_patch_status", "prompt_patch", ["status"])

    if not _table_exists("prompt_evaluation"):
        op.create_table(
            "prompt_evaluation",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("prompt_id", sa.BigInteger(), nullable=False, comment="提示词资产ID"),
            sa.Column("base_version_id", sa.BigInteger(), nullable=False, comment="基准版本ID"),
            sa.Column("candidate_version_id", sa.BigInteger(), nullable=False, comment="候选版本ID"),
            sa.Column("test_set_id", sa.BigInteger(), nullable=True, comment="测试集ID"),
            sa.Column("result_snapshot", sa.JSON(), nullable=True, comment="验证结果快照"),
            sa.Column("human_score", sa.String(32), nullable=True, comment="人工评分"),
            sa.Column("critic_score", sa.String(32), nullable=True, comment="审核评分"),
            sa.Column("summary", sa.Text(), nullable=True, comment="验证摘要"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("idx_prompt_evaluation_prompt_id", "prompt_evaluation", ["prompt_id"])
    _create_index_if_missing("idx_prompt_evaluation_base_version_id", "prompt_evaluation", ["base_version_id"])
    _create_index_if_missing("idx_prompt_evaluation_candidate_version_id", "prompt_evaluation", ["candidate_version_id"])


def downgrade() -> None:
    for index_name, table_name in (
        ("idx_prompt_evaluation_candidate_version_id", "prompt_evaluation"),
        ("idx_prompt_evaluation_base_version_id", "prompt_evaluation"),
        ("idx_prompt_evaluation_prompt_id", "prompt_evaluation"),
        ("idx_prompt_patch_status", "prompt_patch"),
        ("idx_prompt_patch_run_id", "prompt_patch"),
        ("idx_prompt_optimizer_run_status", "prompt_optimizer_run"),
        ("idx_prompt_optimizer_run_mode", "prompt_optimizer_run"),
        ("idx_prompt_optimizer_run_issue_id", "prompt_optimizer_run"),
        ("idx_prompt_optimizer_run_prompt_version_id", "prompt_optimizer_run"),
        ("idx_prompt_optimizer_run_prompt_id", "prompt_optimizer_run"),
        ("idx_prompt_issue_prompt_version_id", "prompt_issue"),
        ("idx_prompt_issue_prompt_id", "prompt_issue"),
        ("idx_prompt_version_source_run_id", "prompt_version"),
        ("idx_prompt_version_prompt_id", "prompt_version"),
        ("idx_prompt_asset_tenant_code", "prompt_asset"),
    ):
        if _table_exists(table_name) and _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in (
        "prompt_evaluation",
        "prompt_patch",
        "prompt_optimizer_run",
        "prompt_issue",
        "prompt_version",
        "prompt_asset",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
