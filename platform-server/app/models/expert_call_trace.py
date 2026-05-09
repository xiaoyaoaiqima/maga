"""
ExpertCallTrace model - 统一调用追踪表

三层标识体系：
- 第一层: job_id（任务级）
- 第二层: sub_job_id ≈ content_id（内容级，1:1 对等）
- 第三层: trace_id + span_id（调用级）
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, JSON, DateTime, Integer, DECIMAL, func, Index
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from app.models.base import Base


class ExpertCallTrace(Base):
    """统一调用追踪表"""

    __tablename__ = "expert_call_trace"

    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )

    # ========== 三层标识体系 ==========

    # 第一层：任务标识
    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Job ID（任务级，来自 Job 表）"
    )

    # 第二层：内容标识（sub_job_id 与 content_id 对等，1:1 关系）
    sub_job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Sub Job ID（执行侧视角，每次执行生成）"
    )

    content_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="内容ID（内容侧视角，与 sub_job_id 1:1 对等，GE 成功时生成）"
    )

    # 第三层：调用标识
    trace_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="请求追踪ID（单次请求，跨服务传递）"
    )

    span_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="调用ID（单次调用，如 Plugin 渲染）"
    )

    parent_span_id: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="父调用ID（形成调用链路）"
    )

    # ========== 调用信息 ==========

    stage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="阶段：plugin_render/prompt_render/ge_generation/ag_ban/ag_critic/debug"
    )

    expert_config_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="ExpertConfig 编码"
    )

    expert_type: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="Expert 类型：GENERATION/VALIDATION/SCORING"
    )

    service_app: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="目标服务 app-id"
    )

    service_method: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="调用方法"
    )

    # ========== 执行状态 ==========

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="pending/running/success/failed/timeout"
    )

    error_type: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="错误类型：timeout/validation/model_error/..."
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息"
    )

    # ========== 性能指标 ==========

    start_time: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        comment="开始时间（毫秒精度）"
    )

    end_time: Mapped[Optional[datetime]] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=True,
        comment="结束时间"
    )

    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="总耗时（毫秒）"
    )

    queue_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="排队时间"
    )

    model_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="模型调用时间"
    )

    render_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="渲染时间（Plugin/Prompt）"
    )

    # ========== Token 统计 ==========

    model_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="模型编码"
    )

    model_provider: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="模型提供商"
    )

    # LLM Provider 扩展字段
    provider_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="LLM Provider 编码（关联 llm_provider_config）"
    )

    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="输入 Token 数"
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="输出 Token 数"
    )

    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="总 Token 数"
    )

    # ========== 成本统计 ==========

    input_cost: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 6),
        nullable=True,
        comment="输入成本（美元）"
    )

    output_cost: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 6),
        nullable=True,
        comment="输出成本（美元）"
    )

    total_cost: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 6),
        nullable=True,
        comment="总成本（美元）"
    )

    currency: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="计价币种（USD/CNY）"
    )

    # ========== Failover ==========

    failover_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=0,
        comment="failover 次数（0 表示首选成功）"
    )

    # ========== A/B Test 支持 ==========

    experiment_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="实验ID"
    )

    experiment_group: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="实验分组：control/treatment/..."
    )

    experiment_variant: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="实验变体（如 prompt 版本）"
    )

    experiment_source: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="实验来源：api/job/system"
    )

    # ========== 业务结果 ==========

    result_summary: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="结果摘要"
    )

    plugin_config_snapshot: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="Plugin 配置快照，格式: [{plugin_code, variable_mapping}]"
    )

    rendered_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="渲染后的 Prompt"
    )

    # ========== 调用者信息 ==========

    caller_service: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="调用方服务"
    )

    caller_user_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="调用者用户ID"
    )

    client_ip: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="客户端IP"
    )

    # ========== 源数据引用 ==========

    source_log_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="源服务日志ID（用于跨服务关联）"
    )

    source_log_table: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="源日志表名"
    )

    # ========== RLHF 扩展字段（文章生产全链路）==========

    rlhf_feedback_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="关联 rlhf_feedback.id"
    )

    reviewer_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="审核人ID（RLHF 阶段）"
    )

    reviewer_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="审核人姓名"
    )

    # ========== 时间戳 ==========

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
    )

    # ========== 复合索引 ==========
    __table_args__ = (
        # 任务+子任务联合查询
        Index("idx_job_sub", "job_id", "sub_job_id"),
        # 内容+阶段查询
        Index("idx_content_stage", "content_id", "stage"),
        # Span 链路查询
        Index("idx_span_parent", "span_id", "parent_span_id"),
        # 阶段+状态统计
        Index("idx_stage_status", "stage", "status"),
        # 实验分析
        Index("idx_expert_call_trace_experiment", "experiment_id", "experiment_group"),
        # 模型统计
        Index("idx_model_created", "model_code", "created_at"),
        # Provider 统计
        Index("idx_expert_call_trace_provider", "provider_code", "created_at"),
        # 成本统计
        Index("idx_cost", "total_cost", "created_at"),
        # RLHF 审核人统计
        Index("idx_reviewer", "reviewer_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExpertCallTrace(id={self.id}, job_id={self.job_id}, "
            f"stage={self.stage}, status={self.status})>"
        )
