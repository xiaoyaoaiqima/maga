"""Content-agent execution layer models.

These tables keep MAGA as the marketing content source of truth while external
executors such as the Hermes MAGA worker perform capability work through APIs.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class ContentBatchJob(Base):
    """Batch generation planning job owned by MAGA."""

    __tablename__ = "content_batch_job"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    batch_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True, comment="批次编码")
    asset_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="资产键")
    product_topic: Mapped[str] = mapped_column(String(255), nullable=False, comment="产品/主题")
    target_audience: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="目标人群")
    style: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="风格")
    count: Mapped[int] = mapped_column(Integer, nullable=False, comment="计划篇数")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True, comment="状态")
    strategy_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="策略")
    diversity_plan_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="多样性计划摘要")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="创建人")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class ContentBatchItem(Base):
    """One planned or generated item inside a batch generation job."""

    __tablename__ = "content_batch_item"
    __table_args__ = (
        UniqueConstraint("batch_id", "item_no", name="uq_content_batch_item_batch_no"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    batch_id: Mapped[int] = mapped_column(BIGINT_PK, nullable=False, index=True, comment="批次ID")
    item_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="批次内序号")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True, comment="状态")
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False, comment="单篇生成计划")
    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="关联任务ID")
    run_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="关联Run ID")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="标题")
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="正文")
    quality_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="质量评分")
    diversity_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="多样性评分")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class ContentBatchItemVersion(Base):
    """Operator review/version snapshot for a generated batch item."""

    __tablename__ = "content_batch_item_version"
    __table_args__ = (
        UniqueConstraint("item_id", "version_no", name="uq_content_batch_item_version_item_no"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    item_id: Mapped[int] = mapped_column(BIGINT_PK, nullable=False, index=True, comment="批次文章ID")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号")
    source_action: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="操作来源")
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="评审状态")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="标题快照")
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="正文快照")
    feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="运营反馈")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="创建人")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展数据")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class ContentFeedback(Base):
    """Run-outside operator feedback used by later training and prompt optimization."""

    __tablename__ = "content_feedback"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    batch_id: Mapped[Optional[int]] = mapped_column(BIGINT_PK, nullable=True, index=True, comment="批次ID")
    item_id: Mapped[int] = mapped_column(BIGINT_PK, nullable=False, index=True, comment="批次文章ID")
    version_id: Mapped[Optional[int]] = mapped_column(BIGINT_PK, nullable=True, index=True, comment="反馈版本ID")
    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="任务ID")
    run_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="Run ID")
    artifact_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="Artifact ID")
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="反馈动作")
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="评审状态")
    quoted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="引用片段")
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="反馈内容")
    submitter: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True, comment="提交人")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展数据")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class ExecutorRegistry(Base):
    """Registered execution worker, e.g. Hermes profile maga-worker."""

    __tablename__ = "executor_registry"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    executor_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="执行器编码")
    executor_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="执行器类型")
    profile_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="Hermes profile 名称")
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="展示名称")
    capabilities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="v0.0 能力列表")
    protocol_version: Mapped[str] = mapped_column(String(16), nullable=False, default="0.1", comment="协议版本")
    invoke_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="Executor invoke URL")
    supported_capabilities_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="协议能力清单")
    auth_token_secret_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Executor token secret ref")
    hmac_secret_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="HMAC secret ref")
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="最大并发")
    trigger_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="push", comment="触发模式")
    endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="v0.0 HTTP worker 地址")
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
    run_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True, comment="Run token")
    executor_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="执行器编码")
    executor_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="执行器类型快照")
    external_run_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="外部执行器 Run ID")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True, comment="Run 状态")
    status_substate: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment="Run 子状态")
    current_stage_call_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment="当前 Stage Call ID")
    rewrite_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="改写轮次")
    weighted_score_summary_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="MAGA 聚合分数摘要")
    model_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="模型摘要")
    config_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="执行配置快照")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True, comment="开始时间")
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="结束时间")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class ContentAgentStageCall(Base):
    """One protocol capability invocation within a run."""

    __tablename__ = "content_agent_stage_call"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_no", name="uq_content_agent_stage_call_run_sequence"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    stage_call_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="协议 Stage Call ID")
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="Run ID")
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="Run 内阶段序号")
    capability: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="Capability")
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1", comment="Capability schema version")
    invoke_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="sync", comment="sync/async")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True, comment="Stage 状态")
    input_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="入参 input 快照")
    output_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="出参 output 快照")
    stats_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="执行统计")
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="错误码")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")
    retryable: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="是否可重试")
    retry_of_stage_call_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment="重试上一跳")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="结束时间")
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True, comment="截止时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class ContentAgentEvent(Base):
    """Structured execution trace event."""

    __tablename__ = "content_agent_event"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_content_agent_event_run_idempotency"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="Run ID")
    stage_call_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment="Stage Call ID")
    step: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="执行步骤")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="事件类型")
    expert_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="Expert 编码")
    model_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="模型编码")
    input_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="输入快照")
    output_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="输出快照")
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="简要说明")
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="耗时毫秒")
    token_usage: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="Token 使用")
    otel_attributes_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="OTel GenAI 属性")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展数据")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="幂等键")
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="发生时间")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class ContentAgentArtifact(Base):
    """Execution artifact such as draft, final content, or score report."""

    __tablename__ = "content_agent_artifact"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_content_agent_artifact_run_idempotency"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="Run ID")
    stage_call_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment="Stage Call ID")
    artifact_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True, comment="协议 Artifact ID")
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="产物类型")
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="产物名称")
    content_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="文本内容")
    content_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="JSON 内容")
    file_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="文件 URL")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展数据")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="幂等键")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class ContentAgentHumanReview(Base):
    """Human review gate requested during protocol execution."""

    __tablename__ = "content_agent_human_review"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="Run ID")
    stage_call_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment="Stage Call ID")
    reason: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="评审原因")
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="评审载荷")
    response_schema_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="响应 schema")
    ui_hint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="UI hint")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True, comment="评审状态")
    responder_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="处理人")
    response_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="用户响应")
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
