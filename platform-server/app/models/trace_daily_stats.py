"""
TraceDailyStats model - 追踪每日统计表

用于存储每日聚合的追踪统计数据，支持报表和分析
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, BigInteger, DateTime, Integer, Float, Date, DECIMAL, func, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from app.models.base import Base


class TraceDailyStats(Base):
    """追踪每日统计表"""

    __tablename__ = "trace_daily_stats"

    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )

    # 统计维度
    stat_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="统计日期"
    )

    stage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="阶段"
    )

    expert_config_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Expert 编码"
    )

    experiment_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="实验ID"
    )

    experiment_group: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="实验分组"
    )

    # LLM Provider 维度
    provider_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="LLM Provider 编码"
    )

    # 调用计数
    total_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="总调用数"
    )

    success_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="成功数"
    )

    failed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="失败数"
    )

    timeout_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="超时数"
    )

    # 耗时统计
    avg_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="平均耗时"
    )

    p50_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="P50 耗时"
    )

    p95_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="P95 耗时"
    )

    p99_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="P99 耗时"
    )

    min_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="最小耗时"
    )

    max_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="最大耗时"
    )

    # Token 统计
    total_input_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
        comment="总输入 Token 数"
    )

    total_output_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
        comment="总输出 Token 数"
    )

    avg_input_tokens: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="平均输入 Token 数"
    )

    avg_output_tokens: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="平均输出 Token 数"
    )

    # 成本统计
    total_cost: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 4),
        nullable=True,
        comment="总成本（美元）"
    )

    avg_cost: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 4),
        nullable=True,
        comment="平均成本（美元）"
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USD",
        server_default="USD",
        comment="计价币种（USD/CNY）"
    )

    # 时间戳
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间"
    )

    # 唯一约束和索引
    __table_args__ = (
        UniqueConstraint(
            "stat_date", "stage", "expert_config_code",
            "experiment_id", "experiment_group", "provider_code", "currency",
            name="uk_date_stage_expert_exp_provider_currency"
        ),
        Index("idx_stat_date", "stat_date"),
        Index("idx_stage", "stage"),
        Index("idx_expert_code", "expert_config_code"),
        Index("idx_experiment", "experiment_id", "experiment_group"),
        Index("idx_provider", "provider_code"),
    )

    def __repr__(self) -> str:
        return (
            f"<TraceDailyStats(id={self.id}, date={self.stat_date}, "
            f"stage={self.stage}, total={self.total_count})>"
        )

    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.total_count == 0:
            return 0.0
        return round(self.success_count / self.total_count * 100, 2)

    @property
    def error_rate(self) -> float:
        """计算错误率"""
        if self.total_count == 0:
            return 0.0
        return round((self.failed_count + self.timeout_count) / self.total_count * 100, 2)

