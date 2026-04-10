"""
TestCase model - 测试用例表
"""
# pylint: disable=not-callable

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import BigInteger, String, Text, JSON, DateTime, Integer, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TestCase(Base):
    """TestCase model - 测试用例表"""

    __tablename__ = "test_case"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="主键",
    )

    test_set_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="测试集编码（应用层关联）",
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="标题",
    )

    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="正文（文本类型）",
    )

    image_url: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
        comment="图片URL（图片类型）",
    )

    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="原始字段/扩展信息",
    )

    tags: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="标签",
    )

    content_md5: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="content/image_url 的 md5，用于去重",
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
        comment="软删(1/0)",
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

    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人",
    )

    __table_args__ = (
        Index("idx_test_case_test_set_code", "test_set_code"),
    )

