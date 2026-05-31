"""Content-agent execution-layer endpoints."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import normalize_executor_code
from app.core.database import get_db
from app.models.llm_provider_config import LLMProviderConfig
from app.schemas.base import ResponseData
from app.schemas.content_batch_report import (
    ContentCommentBatchStartRequest,
    ContentBatchExecutionSummary,
    ContentBatchItemFeedbackRequest,
    ContentBatchItemFeedbackResponse,
    ContentBatchListResponse,
    ContentBatchReportResponse,
    ContentBatchStartRequest,
    ContentBatchStartResponse,
    ContentTrainingFeedbackSampleListResponse,
)
from app.schemas.content_agent import (
    ContentAgentArtifactCreate,
    ContentAgentArtifactResponse,
    ContentAgentClaimRequest,
    ContentAgentClaimResponse,
    ContentAgentEventCreate,
    ContentAgentEventResponse,
    ContentAgentHumanReviewRequest,
    ContentAgentHumanReviewResponse,
    ContentAgentRunCompleteRequest,
    ContentAgentRunFailRequest,
    ContentAgentRunResponse,
    ContentAgentSnapshotResponse,
    ContentAgentStartGenerationRequest,
    ContentAgentStartGenerationResponse,
    ContentAgentTaskCreate,
    ContentAgentTaskResponse,
)
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.content_batch_review_service import ContentBatchReviewService
from app.services.content_comment_batch_service import ContentCommentBatchService
from app.services.executor_invocation_service import ExecutorInvocationClient, MockExecutorInvocationClient
from app.services.unified_content_generation_service import CONTENT_GENERATE_CAPABILITY, UnifiedContentGenerationService

router = APIRouter()


def _normalized_executor_code(executor_code: str | None) -> str:
    """Treat empty/whitespace executor form input as the default MAGA worker executor."""
    return normalize_executor_code(executor_code)


def _map_protocol_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "run token" in message or "not current" in message or "stage header" in message:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


async def _model_config_with_maga_defaults(
    db: AsyncSession,
    model_config: dict[str, str | None],
) -> dict[str, str]:
    config = {key: value for key, value in model_config.items() if key in {"ge_model", "ae_model"} and value}
    if config.get("ge_model") and config.get("ae_model"):
        return config

    default_model = await _default_llm_model_code(db)
    if not default_model:
        return config

    # MAGA owns the default GE/AE model choice. Operators can still override
    # either field per generation request from the advanced settings.
    return {
        "ge_model": config.get("ge_model") or default_model,
        "ae_model": config.get("ae_model") or default_model,
    }


async def _default_llm_model_code(db: AsyncSession) -> str | None:
    result = await db.execute(
        select(LLMProviderConfig.default_model)
        .where(
            LLMProviderConfig.enabled == 1,
            LLMProviderConfig.is_deleted == 0,
            LLMProviderConfig.default_model.is_not(None),
            LLMProviderConfig.default_model != "",
        )
        .order_by(LLMProviderConfig.priority.desc(), LLMProviderConfig.id.asc())
        .limit(1)
    )
    value = result.scalar_one_or_none()
    return value.strip() if isinstance(value, str) and value.strip() else None


def _invocation_client_for_invoke_url(invoke_url: str | None):
    """Use the local deterministic mock only for explicit mock:// executor URLs."""
    if invoke_url and invoke_url.startswith("mock://"):
        return MockExecutorInvocationClient()
    return ExecutorInvocationClient()


@router.post("/generation/start", response_model=ResponseData[ContentAgentStartGenerationResponse])
async def start_generation(
    request: ContentAgentStartGenerationRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentStartGenerationResponse]:
    service = ContentAgentService(db)
    executor_code = _normalized_executor_code(request.executor_code)
    executor = await service.get_executor(executor_code)
    if not executor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="executor not found")
    invocation_client = _invocation_client_for_invoke_url(executor.invoke_url)
    orchestrator = ContentAgentOrchestrator(
        db,
        invocation_client=invocation_client,
        callback_base_url="/api/v1/content-agent",
    )
    try:
        model_config = await _model_config_with_maga_defaults(
            db, request.generation_model_config.model_dump(exclude_none=True)
        )
        unified = await UnifiedContentGenerationService(db).build_snapshot(
            content_type="article",
            business_rule={
                "rule_type": "ad_hoc_article",
                "product_topic": request.product_topic,
                "target_audience": request.target_audience,
                "persona_target": request.persona_target,
                "style": request.style,
            },
            item_no=1,
            output_fields=["title", "body"],
            model_config=model_config,
        )
        task_request = ContentAgentTaskCreate(
            task_type="content_generate",
            priority=request.priority,
            executor_code=executor_code,
            input_snapshot=unified.input_snapshot,
            asset_refs=unified.asset_refs,
            created_by=request.created_by,
        )
        result = await orchestrator.run_single_capability(task_request, capability=CONTENT_GENERATE_CAPABILITY)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    output = result.output or {}
    title = str(output.get("title") or "").strip()
    body = str(output.get("body") or "").strip()
    if not title or not body:
        raise _map_protocol_error(ValueError("content.generate returned empty article"))
    response = ContentAgentStartGenerationResponse(
        task_id=result.run.task_id,
        run_id=result.run.id,
        title=title,
        body=body,
    )
    return ResponseData(message="Generation completed", data=response)


@router.post("/batches/start", response_model=ResponseData[ContentBatchStartResponse])
async def start_batch_generation(
    request: ContentBatchStartRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchStartResponse]:
    service = ContentAgentService(db)
    executor_code = _normalized_executor_code(request.executor_code)
    executor = await service.get_executor(executor_code)
    if not executor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="executor not found")
    invocation_client = _invocation_client_for_invoke_url(executor.invoke_url)
    try:
        job = await ContentBatchPlanner(db).create_batch_plan(
            asset_key=request.asset_key,
            product_topic=request.product_topic,
            target_audience=request.target_audience,
            persona_target=request.persona_target,
            style=request.style,
            count=request.count,
            model_config=await _model_config_with_maga_defaults(
                db,
                request.generation_model_config.model_dump(exclude_none=True),
            ),
            created_by=request.created_by,
        )
        job_id = job.id
        batch_code = job.batch_code
        await db.commit()
        execution = await ContentBatchExecutionService(
            db,
            invocation_client=invocation_client,
            callback_base_url="/api/v1/content-agent",
            executor_code=executor_code,
        ).execute_batch_items(job_id, limit=job.count, created_by=request.created_by)
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(job_id)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    response = ContentBatchStartResponse(
        batch_id=job_id,
        batch_code=batch_code,
        execution=ContentBatchExecutionSummary(
            requested_limit=execution.requested_limit,
            generated_count=execution.generated_count,
            failed_count=execution.failed_count,
            item_ids=execution.item_ids,
        ),
        report=report,
    )
    return ResponseData(message="Batch generation completed", data=response)


@router.post("/comment-batches/start", response_model=ResponseData[ContentBatchStartResponse])
async def start_comment_batch_generation(
    request: ContentCommentBatchStartRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchStartResponse]:
    service = ContentAgentService(db)
    executor_code = _normalized_executor_code(request.executor_code)
    executor = await service.get_executor(executor_code)
    if not executor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="executor not found")
    invocation_client = _invocation_client_for_invoke_url(executor.invoke_url)
    try:
        execution = await ContentCommentBatchService(
            db,
            invocation_client=invocation_client,
            callback_base_url="/api/v1/content-agent",
            executor_code=executor_code,
        ).create_and_execute_batch(
            asset_key=request.asset_key,
            created_by=request.created_by,
        )
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(execution.batch_id)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    response = ContentBatchStartResponse(
        batch_id=execution.batch_id,
        batch_code=report.batch_code,
        execution=ContentBatchExecutionSummary(
            requested_limit=execution.requested_limit,
            generated_count=execution.generated_count,
            failed_count=execution.failed_count,
            item_ids=execution.item_ids,
        ),
        report=report,
    )
    return ResponseData(message="Comment batch generation completed", data=response)


@router.get("/batches", response_model=ResponseData[ContentBatchListResponse])
async def list_batches(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchListResponse]:
    batches = await ContentBatchReportService(db).list_batch_reports(limit=limit, offset=offset)
    return ResponseData(data=batches)


@router.post("/batch-items/{item_id}/feedback", response_model=ResponseData[ContentBatchItemFeedbackResponse])
async def submit_batch_item_feedback(
    item_id: int,
    request: ContentBatchItemFeedbackRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchItemFeedbackResponse]:
    service = ContentBatchReviewService(db)
    try:
        result = await service.submit_feedback(item_id, request)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(message="Operator feedback saved", data=result)


@router.get("/batches/{batch_id}/report", response_model=ResponseData[ContentBatchReportResponse])
async def get_batch_report(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchReportResponse]:
    service = ContentBatchReportService(db)
    try:
        report = await service.get_batch_report(batch_id)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(data=report)


@router.get("/training/feedback-samples", response_model=ResponseData[ContentTrainingFeedbackSampleListResponse])
async def list_training_feedback_samples(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    review_status: str | None = Query(default=None, max_length=32),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentTrainingFeedbackSampleListResponse]:
    samples = await ContentBatchReportService(db).list_training_feedback_samples(
        limit=limit,
        offset=offset,
        review_status=review_status,
    )
    return ResponseData(data=samples)


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


@router.post("/runs/{run_id}/human-review", response_model=ResponseData[ContentAgentHumanReviewResponse])
async def request_human_review(
    run_id: int,
    request: ContentAgentHumanReviewRequest,
    x_stage_call_id: str | None = Header(default=None, alias="X-Stage-Call-Id"),
    x_maga_protocol_version: str | None = Header(default=None, alias="X-Maga-Protocol-Version"),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentAgentHumanReviewResponse]:
    service = ContentAgentService(db)
    try:
        review = await service.request_human_review(
            run_id,
            request,
            stage_call_id_header=x_stage_call_id,
            protocol_version_header=x_maga_protocol_version,
        )
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
