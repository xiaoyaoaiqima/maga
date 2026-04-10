"""
CalibrationRecord model - 校准工作台人工评分记录表
"""
# pylint: disable=not-callable
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, Integer, Boolean, DateTime, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CalibrationRecord(Base):
    """校准工作台人工评分记录表"""

    __tablename__ = "calibration_record"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )

    calibration_task_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="校准任务ID",
    )

    content_row_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="content表主键ID",
    )

    content_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="内容ID（全局唯一）",
    )

    job_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Job ID",
    )

    sub_job_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Sub Job ID",
    )

    expert_config_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="专家配置编码",
    )

    expert_func: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="专家函数名",
    )

    expert_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="专家类型（CRITIC/BAN）",
    )

    human_score_value: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="人工评分（0-100）",
    )

    human_passed: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment="人工通过（1=通过/0=不通过）",
    )

    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注",
    )

    reviewer_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="评分人ID",
    )

    reviewer_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="评分人姓名",
    )

    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        index=True,
        comment="创建时间",
    )

    __table_args__ = (
        Index("idx_calibration_task_reviewer", "calibration_task_id", "reviewer_id"),
        Index("idx_calibration_content_expert", "content_id", "expert_config_code"),
        UniqueConstraint(
            "calibration_task_id",
            "reviewer_id",
            "expert_config_code",
            "content_id",
            name="uk_calibration_task_reviewer_expert_content",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CalibrationRecord(id={self.id}, content_id={self.content_id}, "
            f"expert_config_code={self.expert_config_code})>"
        )
