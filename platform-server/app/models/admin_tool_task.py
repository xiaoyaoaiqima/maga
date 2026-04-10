"""
AdminToolTask model - 管理工具异步任务

用于「系统设置 -> 管理工具」中触发的异步回刷/盘点/校验等任务。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, JSON, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminToolTask(Base):
    __tablename__ = "admin_tool_task"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="主键"
    )

    task_type: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="任务类型（pricing_audit/cost_backfill/...）"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="状态：pending/running/success/failed/cancelled",
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="进度 0~100",
    )

    message: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, comment="进度/状态提示"
    )

    params: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="任务参数（表单提交内容）"
    )

    result: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="任务结果（统计/清单/对账报告等）"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="失败原因/堆栈摘要"
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="创建人 user_id"
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="开始时间"
    )

    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="结束时间"
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), nullable=True, comment="创建时间"
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_admin_tool_task_type", "task_type"),
        Index("idx_admin_tool_task_status", "status", "created_at"),
        Index("idx_admin_tool_task_created_by", "created_by", "created_at"),
    )


