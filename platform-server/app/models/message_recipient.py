"""
MessageRecipient model - 站内消息接收人（已读状态）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessageRecipient(Base):
    """站内消息接收表（每个用户一条，记录已读状态）"""

    __tablename__ = "message_recipient"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键",
    )

    message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("message.id"),
        nullable=False,
        index=True,
        comment="消息ID（message.id）",
    )

    user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="接收用户ID（sys_user.id）",
    )

    is_read: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="是否已读（0否 1是）",
    )

    read_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="阅读时间",
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


