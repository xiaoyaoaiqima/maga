"""
JobCreateDraft model - Job 创建草稿
"""

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import String, Text, JSON, DateTime, BigInteger, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JobCreateDraft(Base):
    """JobCreateDraft model"""

    __tablename__ = "job_create_draft"

    # 技术主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键",
    )

    # 全局唯一 draft_id
    draft_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="全局唯一草稿ID（工具生成）",
    )

    tenant_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="租户ID",
    )

    mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="创建方式：explicit_combinations/allocation_rules/variants/ai",
    )

    draft_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="草稿 JSON（结构化）",
    )

    compiled_json: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="编译产物（预览/执行计划）",
    )

    validation_json: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="校验结果（errors/warnings/auto_fixes）",
    )

    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注",
    )

    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="Create Time",
    )

    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="Update Time",
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Created By",
    )

    updated_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Updated By",
    )

    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）",
    )

    def __repr__(self) -> str:
        return f"<JobCreateDraft(draft_id={self.draft_id}, mode={self.mode})>"



