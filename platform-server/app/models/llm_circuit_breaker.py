"""
LLM Circuit Breaker model - 熔断状态表

说明：
- 生产环境建议使用 Redis 存储（多实例共享）
- 此表作为持久化备份和状态查询
- 熔断状态：closed（正常）-> open（熔断）-> half_open（半开探测）
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, BigInteger, DateTime, Integer, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LLMCircuitBreaker(Base):
    """熔断状态表"""

    __tablename__ = "llm_circuit_breaker"

    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键"
    )

    # 端点标识
    provider_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="端点编码"
    )

    # 熔断状态
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="closed",
        comment="状态：closed/open/half_open"
    )

    # 计数
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="连续失败次数"
    )

    success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="半开状态下成功次数"
    )

    # 失败信息
    last_failure_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="最后失败时间"
    )

    last_failure_reason: Mapped[Optional[str]] = mapped_column(
        String(256),
        nullable=True,
        comment="最后失败原因"
    )

    # 熔断截止
    open_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="熔断截止时间"
    )

    # 更新时间
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间"
    )

    # 索引
    __table_args__ = (
        Index("idx_breaker_provider", "provider_code"),
        Index("idx_breaker_state", "state"),
    )

    def __repr__(self) -> str:
        return (
            f"<LLMCircuitBreaker(provider_code={self.provider_code}, "
            f"state={self.state}, failure_count={self.failure_count})>"
        )

    @property
    def is_open(self) -> bool:
        """是否熔断中"""
        if self.state == "open":
            if self.open_until and datetime.now() > self.open_until:
                return False  # 已过熔断期，应进入 half_open
            return True
        return False

    @property
    def is_closed(self) -> bool:
        """是否正常"""
        return self.state == "closed"

    @property
    def is_half_open(self) -> bool:
        """是否半开状态"""
        return self.state == "half_open"

