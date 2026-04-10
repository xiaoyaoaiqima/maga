"""
Job Business Context model - Job 业务上下文关联表

说明：
- 关联 Job 与业务维度（平台、品牌、活动）
- 用于成本统计时的维度聚合
- 与 expert_call_trace 通过 job_id 关联
"""
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import String, BigInteger, JSON, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JobBusinessContext(Base):
    """Job 业务上下文关联表"""

    __tablename__ = "job_business_context"

    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键"
    )

    # Job 关联
    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="关联 job.job_id"
    )

    # 业务维度
    platform_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="平台编码"
    )

    brand_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="品牌 ID"
    )

    campaign_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="活动 ID"
    )

    # 扩展上下文
    extra_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="扩展业务上下文"
    )

    # 时间戳
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
    )

    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间"
    )

    # 索引
    __table_args__ = (
        Index("idx_context_job_id", "job_id"),
        Index("idx_context_platform", "platform_code"),
        Index("idx_context_brand", "brand_id"),
        Index("idx_context_campaign", "campaign_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<JobBusinessContext(job_id={self.job_id}, "
            f"platform={self.platform_code}, brand={self.brand_id})>"
        )

