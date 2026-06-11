"""Realtime Chat API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseModel
from app.schemas.chat import ChatMessageRequest
from app.services.chat_service import ChatService

router = APIRouter()


def get_chat_service(db: AsyncSession = Depends(get_db)) -> ChatService:
    """Get chat service instance."""
    return ChatService(db)


@router.post("/messages", response_model=ResponseModel, summary="发送实时聊天消息")
async def send_chat_message(
    request: ChatMessageRequest,
    service: ChatService = Depends(get_chat_service),
):
    try:
        result = await service.send_message(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ResponseModel(code=200, message="success", data=result.model_dump())
