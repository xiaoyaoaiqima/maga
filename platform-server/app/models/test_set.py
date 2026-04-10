"""
TestSet model - 测试集表
"""
# pylint: disable=not-callable

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, String, DateTime, Integer, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TestSet(Base):
    """TestSet model - 测试集表"""

    __tablename__ = "test_set"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="主键",
    )

    code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="唯一编码",
    )

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="测试集名称",
    )

    type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="text",
        comment="类型: text/image",
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="描述",
    )

    enabled: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        comment="是否启用(1/0)",
    )

    is_deleted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="软删除(1/0)",
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人",
    )

    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )

    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_test_set_code", "code"),
        Index("idx_test_set_type", "type"),
        Index("idx_test_set_enabled", "enabled"),
    )

