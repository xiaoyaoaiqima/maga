"""
Message schemas - 站内消息（通知）
"""

from typing import Optional, List

from pydantic import BaseModel, Field

from app.schemas.base import TimestampSchema


class MessageListItem(TimestampSchema):
    """消息列表项（面向前端展示）"""

    recipient_id: int = Field(..., description="接收记录ID（message_recipient.id）")
    message_id: int = Field(..., description="消息ID（message.id）")
    title: str = Field(..., description="标题")
    content: str = Field(..., description="内容")
    message_type: str = Field(default="system", description="消息类型")
    link: Optional[str] = Field(default=None, description="跳转链接")
    sender_name: Optional[str] = Field(default=None, description="发送人名称")
    is_read: bool = Field(default=False, description="是否已读")


class MessageListResponse(BaseModel):
    """分页列表响应"""

    total: int = Field(..., ge=0)
    skip: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    items: List[MessageListItem] = Field(default_factory=list)


class UnreadCountResponse(BaseModel):
    count: int = Field(..., ge=0, description="未读数量")


class MessagePublishRequest(BaseModel):
    """发布系统消息（admin）"""

    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    link: Optional[str] = Field(default=None, max_length=255)
    message_type: str = Field(default="system", max_length=32)
    target_user_ids: Optional[List[str]] = Field(
        default=None,
        description="指定接收用户ID列表；不传表示全员",
    )


class MessagePublishResponse(BaseModel):
    message_id: int = Field(..., description="创建的 message.id")
    recipient_count: int = Field(..., ge=0, description="接收人数")


