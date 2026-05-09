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
    ContentAgentHeartbeatRequest,
    ContentAgentHumanReviewRequest,
    ContentAgentHumanReviewResponse,
    ContentAgentRunCompleteRequest,
    ContentAgentRunFailRequest,
    ContentAgentRunResponse,
    ContentAgentSnapshotResponse,
    ContentAgentStartGenerationRequest,
    ContentAgentStartGenerationResponse,
    ContentAgentStageCallCompleteRequest,
    ContentAgentStageCallFailRequest,
    ContentAgentStageCallResponse,
    ContentAgentTaskCreate,
    ContentAgentTaskResponse,
)
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_agent_service import ContentAgentService
from app.services.executor_invocation_service import MockExecutorInvocationClient

router = APIRouter()


def _map_protocol_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "run token" in message or "not current" in message:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _task_create_from_start_request(request: ContentAgentStartGenerationRequest) -> ContentAgentTaskCreate:
    return ContentAgentTaskCreate(
        task_type="xhs_generate",
        priority=request.priority,
        executor_code=request.executor_code,
        input_snapshot={
            "brief_type": request.brief_type,
            "product_topic": request.product_topic,
            "target_audience": request.target_audience,
            "style": request.style,
        },
        created_by=request.created_by,
    )


@router.post("/generation/start", response_model=ResponseData[ContentAgentStartGenerationResponse])
async def start_generation(
    request: ContentAgentStartGenerationRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentStartGenerationResponse]:
    invocation_client = MockExecutorInvocationClient() if request.executor_code == "hermes_xhs_writer" else None
    orchestrator = ContentAgentOrchestrator(
        db,
        invocation_client=invocation_client,
        callback_base_url="/api/v1/content-agent",
    )
    try:
        result = await orchestrator.start_generation_run(_task_create_from_start_request(request))
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    response = ContentAgentStartGenerationResponse(
        task_id=result.run.task_id,
        run_id=result.run.id,
        stage_call_id=result.stage_call.stage_call_id,
        capability=result.stage_call.capability,
        stage_status=result.stage_call.status,
        invoke_mode=result.invoke_result.mode,
        output=result.stage_call.output_snapshot,
    )
    return ResponseData(message="Generation run started", data=response)


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
        raise _map_protocol_error(exc) from exc
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
        raise _map_protocol_error(exc) from exc
    return ResponseData(message="产物写入成功", data=ContentAgentArtifactResponse.model_validate(artifact))


@router.post(
    "/runs/{run_id}/stage-calls/{stage_call_id}/complete",
    response_model=ResponseData[ContentAgentStageCallResponse],
)
async def complete_stage_call(
    run_id: int,
    stage_call_id: str,
    request: ContentAgentStageCallCompleteRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentStageCallResponse]:
    service = ContentAgentService(db)
    try:
        stage_call = await service.complete_stage_call(run_id, stage_call_id, request)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(message="Stage 完成", data=ContentAgentStageCallResponse.model_validate(stage_call))


@router.post(
    "/runs/{run_id}/stage-calls/{stage_call_id}/fail",
    response_model=ResponseData[ContentAgentStageCallResponse],
)
async def fail_stage_call(
    run_id: int,
    stage_call_id: str,
    request: ContentAgentStageCallFailRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentStageCallResponse]:
    service = ContentAgentService(db)
    try:
        stage_call = await service.fail_stage_call(run_id, stage_call_id, request)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(message="Stage 失败状态已记录", data=ContentAgentStageCallResponse.model_validate(stage_call))


@router.post("/runs/{run_id}/heartbeat", response_model=ResponseData[ContentAgentRunResponse])
async def heartbeat(
    run_id: int,
    request: ContentAgentHeartbeatRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentRunResponse]:
    service = ContentAgentService(db)
    try:
        run = await service.record_heartbeat(run_id, request)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(message="Heartbeat 已记录", data=ContentAgentRunResponse.model_validate(run))


@router.post("/runs/{run_id}/human-review", response_model=ResponseData[ContentAgentHumanReviewResponse])
async def request_human_review(
    run_id: int,
    request: ContentAgentHumanReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentHumanReviewResponse]:
    service = ContentAgentService(db)
    try:
        review = await service.request_human_review(run_id, request)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(message="人审请求已记录", data=ContentAgentHumanReviewResponse.model_validate(review))


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
        raise _map_protocol_error(exc) from exc
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
        raise _map_protocol_error(exc) from exc
    return ResponseData(message="Run 失败状态已记录", data=ContentAgentRunResponse.model_validate(run))
