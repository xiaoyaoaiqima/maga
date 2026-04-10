"""
ExpertTask model
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExpertTask(Base):
    """ExpertTask model"""

    __tablename__ = "expert_task"

    # 主键ID
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )

    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="对应 job.job_id"
    )

    expert_config_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="对应 expert_config.expert_config_code"
    )

    cron_expression: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="cron 表达式"
    )

    misfire_policy: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="计划执行错误策略：1立即执行 2执行一次 3放弃执行"
    )

    concurrent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="是否并发执行：0允许 1禁止"
    )

    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="0待执行 1执行中 2暂停 3完成（一次性任务）"
    )

    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="Create Time"
    )

    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="Update Time"
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Created By"
    )

    updated_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Updated By"
    )

    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）"
    )

    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )

    def __repr__(self) -> str:
        return f"<ExpertTask(id={self.id}, job_id={self.job_id}, expert_config_code={self.expert_config_code})>"

