"""
Message model - 站内消息（系统通知）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Message(Base):
    """站内消息表（消息主体）"""

    __tablename__ = "message"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键",
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="消息标题",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息内容",
    )

    message_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="system",
        comment="消息类型（system/todo/...）",
    )

    link: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="跳转链接（站内 path 或外部 URL）",
    )

    sender_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="发送人ID（sys_user.id）",
    )

    sender_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="发送人名称（冗余字段，便于展示）",
    )

    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.now(),
        comment="创建时间",
    )

    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）",
    )


