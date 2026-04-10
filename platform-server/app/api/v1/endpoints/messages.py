"""
Messages endpoints - 站内消息（通知）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_current_user_id, get_db, require_perm_code
from app.schemas.base import ResponseData
from app.schemas.message import (
    MessageListResponse,
    MessagePublishRequest,
    MessagePublishResponse,
    UnreadCountResponse,
)
from app.services.message_service import MessageService

router = APIRouter(prefix="/messages", tags=["messages"])


def get_message_service(db: AsyncSession = Depends(get_db)) -> MessageService:
    return MessageService(db)


@router.get("/unread-count", response_model=ResponseData[UnreadCountResponse])
async def get_unread_count(
    user_id: str = Depends(get_current_user_id),
    service: MessageService = Depends(get_message_service),
) -> ResponseData[UnreadCountResponse]:
    count = await service.get_unread_count(user_id=user_id)
    return ResponseData(code=200, message="success", data=UnreadCountResponse(count=count))


@router.get("", response_model=ResponseData[MessageListResponse])
async def list_messages(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    is_read: bool | None = Query(None, description="筛选已读状态"),
    user_id: str = Depends(get_current_user_id),
    service: MessageService = Depends(get_message_service),
) -> ResponseData[MessageListResponse]:
    data = await service.list_messages(
        user_id=user_id,
        skip=skip,
        limit=limit,
        is_read=is_read,
    )
    return ResponseData(code=200, message="success", data=data)


@router.post("/{recipient_id}/read", response_model=ResponseData[None])
async def mark_read(
    recipient_id: int,
    user_id: str = Depends(get_current_user_id),
    service: MessageService = Depends(get_message_service),
) -> ResponseData[None]:
    ok = await service.mark_read(user_id=user_id, recipient_id=recipient_id)
    if not ok:
        raise HTTPException(status_code=404, detail="消息不存在或无权限")
    return ResponseData(code=200, message="success", data=None)


@router.post("/read-all", response_model=ResponseData[None])
async def mark_all_read(
    user_id: str = Depends(get_current_user_id),
    service: MessageService = Depends(get_message_service),
) -> ResponseData[None]:
    await service.mark_all_read(user_id=user_id)
    return ResponseData(code=200, message="success", data=None)


@router.delete("/{recipient_id}", response_model=ResponseData[None])
async def remove_one(
    recipient_id: int,
    user_id: str = Depends(get_current_user_id),
    service: MessageService = Depends(get_message_service),
) -> ResponseData[None]:
    ok = await service.remove_one(user_id=user_id, recipient_id=recipient_id)
    if not ok:
        raise HTTPException(status_code=404, detail="消息不存在或无权限")
    return ResponseData(code=200, message="success", data=None)


@router.delete("", response_model=ResponseData[None], summary="清空当前用户消息")
async def clear_all(
    user_id: str = Depends(get_current_user_id),
    service: MessageService = Depends(get_message_service),
) -> ResponseData[None]:
    await service.clear_all(user_id=user_id)
    return ResponseData(code=200, message="success", data=None)


@router.post(
    "/admin/publish",
    response_model=ResponseData[MessagePublishResponse],
    dependencies=[Depends(require_perm_code("message:publish"))],
)
async def publish_message(
    data: MessagePublishRequest,
    user=Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> ResponseData[MessagePublishResponse]:
    try:
        message_id, recipient_count = await service.publish_system_message(
            publisher_user_id=user.id,
            publisher_name=user.name,
            data=data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ResponseData(
        code=200,
        message="success",
        data=MessagePublishResponse(
            message_id=message_id,
            recipient_count=recipient_count,
        ),
    )


