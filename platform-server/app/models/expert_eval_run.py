"""
ExpertEvalRun model - 专家评测运行表
"""
# pylint: disable=not-callable

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import BigInteger, String, JSON, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExpertEvalRun(Base):
    """ExpertEvalRun model - 专家评测运行表"""

    __tablename__ = "expert_eval_run"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="主键",
    )

    run_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="运行编号",
    )

    expert_config_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="专家配置 code",
    )

    expert_config_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="本次运行使用的 expert_config 快照",
    )

    select_params: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="选样参数（dataset_code/ids/limit 等）",
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="running",
        comment="running/success/failed/cancelled",
    )

    total_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="总数",
    )

    success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="成功数",
    )

    failed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="失败数",
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="开始时间",
    )

    end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="结束时间",
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人",
    )

