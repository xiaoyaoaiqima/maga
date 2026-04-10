"""
CalibrationTask model - 校准任务表
"""
# pylint: disable=not-callable
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CalibrationTask(Base):
    """校准任务表"""

    __tablename__ = "calibration_task"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )

    task_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="任务编码",
    )

    task_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="任务名称",
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="PENDING",
        comment="状态：PENDING/IN_PROGRESS/DONE/CANCELLED",
    )

    assignee_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="指派人ID",
    )

    assignee_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="指派人姓名",
    )

    start_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="开始时间",
    )

    finish_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="完成时间",
    )

    due_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="截止时间",
    )

    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注",
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人ID",
    )

    created_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人姓名",
    )

    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间",
    )

    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_calibration_task_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<CalibrationTask(id={self.id}, task_name={self.task_name})>"
