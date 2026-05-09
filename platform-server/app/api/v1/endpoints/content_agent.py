"""Content-agent execution-layer endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.content_agent import (
    ContentAgentArtifactCreate,
    ContentAgentArtifactResponse,
    ContentAgentClaimRequest,
    ContentAgentClaimResponse,
    ContentAgentEventCreate,
    ContentAgentEventResponse,
    ContentAgentRunCompleteRequest,
    ContentAgentRunFailRequest,
    ContentAgentRunResponse,
    ContentAgentSnapshotResponse,
    ContentAgentTaskCreate,
    ContentAgentTaskResponse,
)
from app.services.content_agent_service import ContentAgentService

router = APIRouter()


@router.post("/tasks", response_model=ResponseData[ContentAgentTaskResponse])
async def create_task(
    request: ContentAgentTaskCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentTaskResponse]:
    service = ContentAgentService(db)
    task = await service.create_task(request)
    return ResponseData(message="任务创建成功", data=ContentAgentTaskResponse.model_validate(task))


@router.post("/tasks/claim", response_model=ResponseData[ContentAgentClaimResponse])
async def claim_task(
    request: ContentAgentClaimRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentClaimResponse]:
    service = ContentAgentService(db)
    claim = await service.claim_task(request)
    return ResponseData(data=claim)


@router.get("/tasks/{task_id}/snapshot", response_model=ResponseData[ContentAgentSnapshotResponse])
async def get_task_snapshot(
    task_id: int,
    run_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentSnapshotResponse]:
    service = ContentAgentService(db)
    snapshot = await service.get_task_snapshot(task_id, run_id=run_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容任务不存在")
    return ResponseData(data=snapshot)


@router.post("/runs/{run_id}/events", response_model=ResponseData[ContentAgentEventResponse])
async def create_event(
    run_id: int,
    request: ContentAgentEventCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentEventResponse]:
    service = ContentAgentService(db)
    try:
        event = await service.create_event(run_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ResponseData(message="事件写入成功", data=ContentAgentEventResponse.model_validate(event))


@router.post("/runs/{run_id}/artifacts", response_model=ResponseData[ContentAgentArtifactResponse])
async def create_artifact(
    run_id: int,
    request: ContentAgentArtifactCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentArtifactResponse]:
    service = ContentAgentService(db)
    try:
        artifact = await service.create_artifact(run_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ResponseData(message="产物写入成功", data=ContentAgentArtifactResponse.model_validate(artifact))


@router.post("/runs/{run_id}/complete", response_model=ResponseData[ContentAgentRunResponse])
async def complete_run(
    run_id: int,
    request: ContentAgentRunCompleteRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentRunResponse]:
    service = ContentAgentService(db)
    try:
        run = await service.complete_run(run_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ResponseData(message="Run 完成", data=ContentAgentRunResponse.model_validate(run))


@router.post("/runs/{run_id}/fail", response_model=ResponseData[ContentAgentRunResponse])
async def fail_run(
    run_id: int,
    request: ContentAgentRunFailRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentRunResponse]:
    service = ContentAgentService(db)
    try:
        run = await service.fail_run(run_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ResponseData(message="Run 失败状态已记录", data=ContentAgentRunResponse.model_validate(run))
