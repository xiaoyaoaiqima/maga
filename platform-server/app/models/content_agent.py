"""Content-agent execution layer models.

These tables keep MAGA as the marketing content source of truth while external
executors such as Hermes xhs-writer perform generation work through APIs.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class ExecutorRegistry(Base):
    """Registered execution worker, e.g. Hermes profile xhs-writer."""

    __tablename__ = "executor_registry"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    executor_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="执行器编码")
    executor_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="执行器类型")
    profile_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="Hermes profile 名称")
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="展示名称")
    capabilities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="能力列表")
    trigger_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="polling", comment="触发模式")
    endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="HTTP worker 地址")
    config_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="非敏感配置")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True, comment="是否启用")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class ContentAgentTask(Base):
    """Marketing content generation task owned by MAGA."""

    __tablename__ = "content_agent_task"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    task_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True, comment="任务编码")
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="任务类型")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True, comment="任务状态")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True, comment="优先级")
    executor_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment="执行器编码")
    brand_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="品牌ID")
    product_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="产品ID")
    campaign_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="活动ID")
    brief_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="Brief ID")
    input_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="执行输入快照")
    asset_refs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="资产引用快照")
    output_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="输出摘要")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="失败原因")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="重试次数")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="创建人")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class ContentAgentRun(Base):
    """One execution attempt for a content-agent task."""

    __tablename__ = "content_agent_run"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="任务ID")
    run_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True, comment="Run 编码")
    executor_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="执行器编码")
    executor_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="执行器类型快照")
    external_run_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="外部执行器 Run ID")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True, comment="Run 状态")
    model_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="模型摘要")
    config_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="执行配置快照")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True, comment="开始时间")
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="结束时间")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class ContentAgentEvent(Base):
    """Structured execution trace event."""

    __tablename__ = "content_agent_event"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="Run ID")
    step: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="执行步骤")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="事件类型")
    expert_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="Expert 编码")
    model_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="模型编码")
    input_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="输入快照")
    output_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="输出快照")
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="简要说明")
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="耗时毫秒")
    token_usage: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="Token 使用")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展数据")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class ContentAgentArtifact(Base):
    """Execution artifact such as draft, final content, or score report."""

    __tablename__ = "content_agent_artifact"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="Run ID")
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="产物类型")
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="产物名称")
    content_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="文本内容")
    content_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="JSON 内容")
    file_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="文件 URL")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展数据")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
