"""
Message service - 站内消息（通知）
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.models.message import Message
from app.models.message_recipient import MessageRecipient
from app.models.sys_user import SysUser
from app.schemas.message import MessageListItem, MessageListResponse, MessagePublishRequest


def _now() -> datetime:
    # 统一由 DB 时区控制；这里只是写 read_time 字段，不做任何时区转换
    return datetime.now()


class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_unread_count(self, *, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(MessageRecipient)
            .join(Message, Message.id == MessageRecipient.message_id)
            .where(
                and_(
                    MessageRecipient.user_id == user_id,
                    MessageRecipient.is_deleted == 0,
                    MessageRecipient.is_read == 0,
                    Message.is_deleted == 0,
                )
            )
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def list_messages(
        self,
        *,
        user_id: str,
        skip: int,
        limit: int,
        is_read: Optional[bool],
    ) -> MessageListResponse:
        conditions = [
            MessageRecipient.user_id == user_id,
            MessageRecipient.is_deleted == 0,
            Message.is_deleted == 0,
        ]
        if is_read is not None:
            conditions.append(MessageRecipient.is_read == (1 if is_read else 0))

        count_stmt = (
            select(func.count())
            .select_from(MessageRecipient)
            .join(Message, Message.id == MessageRecipient.message_id)
            .where(and_(*conditions))
        )
        total = int((await self.db.execute(count_stmt)).scalar() or 0)

        stmt = (
            select(MessageRecipient, Message)
            .join(Message, Message.id == MessageRecipient.message_id)
            .where(and_(*conditions))
            .order_by(Message.create_time.desc(), MessageRecipient.id.desc())
            .offset(skip)
            .limit(limit)
        )
        rows: Sequence[tuple[MessageRecipient, Message]] = (await self.db.execute(stmt)).all()

        items = [
            MessageListItem(
                recipient_id=recipient.id,
                message_id=msg.id,
                title=msg.title,
                content=msg.content,
                message_type=msg.message_type,
                link=msg.link,
                sender_name=msg.sender_name,
                is_read=recipient.is_read == 1,
                create_time=msg.create_time,
                update_time=msg.update_time,
            )
            for recipient, msg in rows
        ]

        return MessageListResponse(total=total, skip=skip, limit=limit, items=items)

    async def mark_read(self, *, user_id: str, recipient_id: int) -> bool:
        stmt = (
            update(MessageRecipient)
            .where(
                and_(
                    MessageRecipient.id == recipient_id,
                    MessageRecipient.user_id == user_id,
                    MessageRecipient.is_deleted == 0,
                )
            )
            .values(is_read=1, read_time=_now(), update_time=func.now())
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return (result.rowcount or 0) > 0

    async def mark_all_read(self, *, user_id: str) -> int:
        stmt = (
            update(MessageRecipient)
            .where(
                and_(
                    MessageRecipient.user_id == user_id,
                    MessageRecipient.is_deleted == 0,
                    MessageRecipient.is_read == 0,
                )
            )
            .values(is_read=1, read_time=_now(), update_time=func.now())
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return int(result.rowcount or 0)

    async def remove_one(self, *, user_id: str, recipient_id: int) -> bool:
        stmt = (
            update(MessageRecipient)
            .where(
                and_(
                    MessageRecipient.id == recipient_id,
                    MessageRecipient.user_id == user_id,
                    MessageRecipient.is_deleted == 0,
                )
            )
            .values(is_deleted=1, update_time=func.now())
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return (result.rowcount or 0) > 0

    async def clear_all(self, *, user_id: str) -> int:
        stmt = (
            update(MessageRecipient)
            .where(
                and_(
                    MessageRecipient.user_id == user_id,
                    MessageRecipient.is_deleted == 0,
                )
            )
            .values(is_deleted=1, update_time=func.now())
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return int(result.rowcount or 0)

    async def publish_system_message(
        self,
        *,
        publisher_user_id: str,
        publisher_name: Optional[str],
        data: MessagePublishRequest,
    ) -> tuple[int, int]:
        # 1) 解析接收人
        target_user_ids = data.target_user_ids
        if target_user_ids is None:
            stmt = select(SysUser.id).where(and_(SysUser.is_deleted == 0, SysUser.status == 1))
            target_user_ids = [row[0] for row in (await self.db.execute(stmt)).all()]
        else:
            # 去重 + 过滤空值
            target_user_ids = [uid for uid in dict.fromkeys(target_user_ids) if uid]

        if not target_user_ids:
            raise ValueError("接收人为空，无法发布消息")

        # 2) 写 message
        msg = Message(
            title=data.title,
            content=data.content,
            message_type=data.message_type or "system",
            link=data.link,
            sender_id=publisher_user_id,
            sender_name=publisher_name,
        )
        self.db.add(msg)
        await self.db.flush()  # 获取 msg.id

        # 3) 写 recipients
        recipients = [
            MessageRecipient(message_id=msg.id, user_id=uid, is_read=0, is_deleted=0)
            for uid in target_user_ids
        ]
        self.db.add_all(recipients)
        await self.db.commit()

        logger.info(
            f"[消息] 发布成功 message_id={msg.id}, recipients={len(target_user_ids)}"
        )
        return msg.id, len(target_user_ids)


