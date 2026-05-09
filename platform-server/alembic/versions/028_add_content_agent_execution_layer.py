"""add content agent execution layer tables

Revision ID: 028_add_content_agent_execution_layer
Revises: 027_add_prompt_optimizer_tables
Create Date: 2026-05-08

"""
from alembic import op
import sqlalchemy as sa


revision = "028_add_content_agent_execution_layer"
down_revision = "027_add_prompt_optimizer_tables"
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
    if not _table_exists("executor_registry"):
        op.create_table(
            "executor_registry",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("executor_code", sa.String(64), nullable=False, comment="执行器编码"),
            sa.Column("executor_type", sa.String(64), nullable=False, comment="执行器类型"),
            sa.Column("profile_name", sa.String(128), nullable=True, comment="Hermes profile 名称"),
            sa.Column("display_name", sa.String(255), nullable=True, comment="展示名称"),
            sa.Column("capabilities", sa.JSON(), nullable=True, comment="能力列表"),
            sa.Column("trigger_mode", sa.String(32), nullable=False, server_default="polling", comment="触发模式"),
            sa.Column("endpoint", sa.String(512), nullable=True, comment="HTTP worker 地址"),
            sa.Column("config_json", sa.JSON(), nullable=True, comment="非敏感配置"),
            sa.Column("enabled", sa.Integer(), nullable=False, server_default="1", comment="是否启用"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.Column("update_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("executor_code", name="uq_executor_registry_executor_code"),
        )
    _create_index_if_missing("idx_executor_registry_executor_code", "executor_registry", ["executor_code"])
    _create_index_if_missing("idx_executor_registry_enabled", "executor_registry", ["enabled"])

    if not _table_exists("content_agent_task"):
        op.create_table(
            "content_agent_task",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("task_code", sa.String(64), nullable=True, comment="任务编码"),
            sa.Column("task_type", sa.String(64), nullable=False, comment="任务类型"),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending", comment="任务状态"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0", comment="优先级"),
            sa.Column("executor_code", sa.String(64), nullable=True, comment="执行器编码"),
            sa.Column("brand_id", sa.BigInteger(), nullable=True, comment="品牌ID"),
            sa.Column("product_id", sa.BigInteger(), nullable=True, comment="产品ID"),
            sa.Column("campaign_id", sa.BigInteger(), nullable=True, comment="活动ID"),
            sa.Column("brief_id", sa.BigInteger(), nullable=True, comment="Brief ID"),
            sa.Column("input_snapshot", sa.JSON(), nullable=True, comment="执行输入快照"),
            sa.Column("asset_refs", sa.JSON(), nullable=True, comment="资产引用快照"),
            sa.Column("output_summary", sa.JSON(), nullable=True, comment="输出摘要"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0", comment="重试次数"),
            sa.Column("created_by", sa.String(100), nullable=True, comment="创建人"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.Column("update_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_code", name="uq_content_agent_task_task_code"),
        )
    for index_name, columns in (
        ("idx_content_agent_task_task_code", ["task_code"]),
        ("idx_content_agent_task_task_type", ["task_type"]),
        ("idx_content_agent_task_status", ["status"]),
        ("idx_content_agent_task_priority", ["priority"]),
        ("idx_content_agent_task_executor_code", ["executor_code"]),
        ("idx_content_agent_task_brand_id", ["brand_id"]),
        ("idx_content_agent_task_product_id", ["product_id"]),
        ("idx_content_agent_task_campaign_id", ["campaign_id"]),
        ("idx_content_agent_task_brief_id", ["brief_id"]),
    ):
        _create_index_if_missing(index_name, "content_agent_task", columns)

    if not _table_exists("content_agent_run"):
        op.create_table(
            "content_agent_run",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("task_id", sa.BigInteger(), nullable=False, comment="任务ID"),
            sa.Column("run_code", sa.String(64), nullable=True, comment="Run 编码"),
            sa.Column("executor_code", sa.String(64), nullable=False, comment="执行器编码"),
            sa.Column("executor_type", sa.String(64), nullable=True, comment="执行器类型快照"),
            sa.Column("external_run_id", sa.String(128), nullable=True, comment="外部执行器 Run ID"),
            sa.Column("status", sa.String(32), nullable=False, server_default="running", comment="Run 状态"),
            sa.Column("model_summary", sa.JSON(), nullable=True, comment="模型摘要"),
            sa.Column("config_snapshot", sa.JSON(), nullable=True, comment="执行配置快照"),
            sa.Column("started_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="开始时间"),
            sa.Column("finished_at", sa.DateTime(), nullable=True, comment="结束时间"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.Column("update_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_code", name="uq_content_agent_run_run_code"),
        )
    for index_name, columns in (
        ("idx_content_agent_run_task_id", ["task_id"]),
        ("idx_content_agent_run_run_code", ["run_code"]),
        ("idx_content_agent_run_executor_code", ["executor_code"]),
        ("idx_content_agent_run_external_run_id", ["external_run_id"]),
        ("idx_content_agent_run_status", ["status"]),
    ):
        _create_index_if_missing(index_name, "content_agent_run", columns)

    if not _table_exists("content_agent_event"):
        op.create_table(
            "content_agent_event",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("run_id", sa.BigInteger(), nullable=False, comment="Run ID"),
            sa.Column("step", sa.String(64), nullable=False, comment="执行步骤"),
            sa.Column("event_type", sa.String(64), nullable=False, comment="事件类型"),
            sa.Column("expert_code", sa.String(128), nullable=True, comment="Expert 编码"),
            sa.Column("model_code", sa.String(128), nullable=True, comment="模型编码"),
            sa.Column("input_snapshot", sa.JSON(), nullable=True, comment="输入快照"),
            sa.Column("output_snapshot", sa.JSON(), nullable=True, comment="输出快照"),
            sa.Column("message", sa.Text(), nullable=True, comment="简要说明"),
            sa.Column("latency_ms", sa.Integer(), nullable=True, comment="耗时毫秒"),
            sa.Column("token_usage", sa.JSON(), nullable=True, comment="Token 使用"),
            sa.Column("metadata_json", sa.JSON(), nullable=True, comment="扩展数据"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.PrimaryKeyConstraint("id"),
        )
    for index_name, columns in (
        ("idx_content_agent_event_run_id", ["run_id"]),
        ("idx_content_agent_event_step", ["step"]),
        ("idx_content_agent_event_event_type", ["event_type"]),
        ("idx_content_agent_event_expert_code", ["expert_code"]),
    ):
        _create_index_if_missing(index_name, "content_agent_event", columns)

    if not _table_exists("content_agent_artifact"):
        op.create_table(
            "content_agent_artifact",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("run_id", sa.BigInteger(), nullable=False, comment="Run ID"),
            sa.Column("artifact_type", sa.String(64), nullable=False, comment="产物类型"),
            sa.Column("name", sa.String(255), nullable=True, comment="产物名称"),
            sa.Column("content_text", sa.Text(), nullable=True, comment="文本内容"),
            sa.Column("content_json", sa.JSON(), nullable=True, comment="JSON 内容"),
            sa.Column("file_url", sa.String(1024), nullable=True, comment="文件 URL"),
            sa.Column("version_no", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
            sa.Column("metadata_json", sa.JSON(), nullable=True, comment="扩展数据"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("idx_content_agent_artifact_run_id", "content_agent_artifact", ["run_id"])
    _create_index_if_missing("idx_content_agent_artifact_artifact_type", "content_agent_artifact", ["artifact_type"])


def downgrade() -> None:
    for index_name, table_name in (
        ("idx_content_agent_artifact_artifact_type", "content_agent_artifact"),
        ("idx_content_agent_artifact_run_id", "content_agent_artifact"),
        ("idx_content_agent_event_expert_code", "content_agent_event"),
        ("idx_content_agent_event_event_type", "content_agent_event"),
        ("idx_content_agent_event_step", "content_agent_event"),
        ("idx_content_agent_event_run_id", "content_agent_event"),
        ("idx_content_agent_run_status", "content_agent_run"),
        ("idx_content_agent_run_external_run_id", "content_agent_run"),
        ("idx_content_agent_run_executor_code", "content_agent_run"),
        ("idx_content_agent_run_run_code", "content_agent_run"),
        ("idx_content_agent_run_task_id", "content_agent_run"),
        ("idx_content_agent_task_brief_id", "content_agent_task"),
        ("idx_content_agent_task_campaign_id", "content_agent_task"),
        ("idx_content_agent_task_product_id", "content_agent_task"),
        ("idx_content_agent_task_brand_id", "content_agent_task"),
        ("idx_content_agent_task_executor_code", "content_agent_task"),
        ("idx_content_agent_task_priority", "content_agent_task"),
        ("idx_content_agent_task_status", "content_agent_task"),
        ("idx_content_agent_task_task_type", "content_agent_task"),
        ("idx_content_agent_task_task_code", "content_agent_task"),
        ("idx_executor_registry_enabled", "executor_registry"),
        ("idx_executor_registry_executor_code", "executor_registry"),
    ):
        if _table_exists(table_name) and _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in (
        "content_agent_artifact",
        "content_agent_event",
        "content_agent_run",
        "content_agent_task",
        "executor_registry",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
