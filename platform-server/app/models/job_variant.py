"""
JobVariant model - Variant 方案库（可复用的组合模板）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, JSON, String, Text, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JobVariant(Base):
    """JobVariant model"""

    __tablename__ = "job_variant"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键",
    )

    variant_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="全局唯一 Variant ID（工具生成）",
    )

    tenant_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="租户ID（NULL 表示全局共享）",
    )

    agent_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="关联 Agent 编码（用于限定该 Variant 适配的专家编排）",
    )

    variant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Variant 名称",
    )

    tags: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="标签（JSON 数组）",
    )

    expert_config_code_list: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Expert 编排顺序（快照）",
    )

    expert_param_config: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="组合模板参数（expert_code -> plugin_config_snapshot[]）",
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用",
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
        return f"<JobVariant(variant_id={self.variant_id}, name={self.variant_name})>"

