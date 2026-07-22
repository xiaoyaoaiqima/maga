"""Content-agent execution-layer endpoints."""
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import normalize_executor_code
from app.core.database import get_db
from app.models.llm_model_route import LLMModelRoute
from app.models.llm_provider_config import LLMProviderConfig
from app.schemas.base import ResponseData
from app.schemas.content_batch_report import (
    ContentBatchBusinessUsabilityReviewRequest,
    ContentBatchBusinessUsabilityReviewResponse,
    ContentBatchClaimPublicDiseaseShadowReviewRequest,
    ContentBatchClaimPublicDiseaseShadowReviewResponse,
    ContentBatchContentFitShadowReviewRequest,
    ContentBatchContentFitShadowReviewResponse,
    ContentBatchFluencyShadowReviewRequest,
    ContentBatchFluencyShadowReviewResponse,
    ContentBatchFocusedPipelineShadowReviewRequest,
    ContentBatchFocusedPipelineShadowReviewResponse,
    ContentBatchTemporalLogicShadowReviewRequest,
    ContentBatchTemporalLogicShadowReviewResponse,
    ContentCommentBatchReviewReplayRequest,
    ContentCommentBatchReviewReplayResponse,
    ContentCommentBatchStartRequest,
    ContentBatchExecutionSummary,
    ContentBatchFeedbackInsightResponse,
    ContentBatchItemFeedbackRequest,
    ContentBatchItemFeedbackResponse,
    ContentBatchListResponse,
    ContentGenerationPreflightRequest,
    ContentGenerationPreflightResponse,
    ContentBatchReportResponse,
    ContentBatchStartRequest,
    ContentBatchStartResponse,
    ContentFeedbackSampleListResponse,
    ContentPPLProfileListResponse,
    ContentPPLRunStartRequest,
    ContentPPLRunStartResponse,
)
from app.schemas.prompt_debug import (
    PromptDebugHistoryGroupDetail,
    PromptDebugHistoryListResponse,
    PromptDebugRequest,
    PromptDebugResponse,
    PromptDebugTokenUsage,
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
    ContentAgentTaskCreate,
    ContentAgentTaskResponse,
)
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.content_batch_review_service import ContentBatchReviewService
from app.services.content_comment_batch_service import ContentCommentBatchService
from app.services.content_generation_ppl_profile_service import ContentGenerationPPLProfileService
from app.services.executor_invocation_service import (
    ExecutorInvocationClient,
    MockExecutorInvocationClient,
    call_direct_llm,
)
from app.services.content_generation_preflight_service import ContentGenerationPreflightService
from app.services.prompt_debug_history_service import PromptDebugHistoryService

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
    model_config: dict[str, Any],
) -> dict[str, Any]:
    allowed_keys = {
        "provider_code",
        "model_code",
        "ge_model",
        "ae_model",
        "temperature",
        "max_tokens",
        "system_prompt",
    }
    config = {key: value for key, value in model_config.items() if key in allowed_keys and value is not None and value != ""}
    provider = await _default_llm_provider_config(db, provider_code=config.get("provider_code"))
    if not provider:
        return config

    default_model = str(provider.default_model or "").strip()
    if default_model:
        config["model_code"] = config.get("model_code") or default_model
        config["ge_model"] = config.get("ge_model") or default_model
        config["ae_model"] = config.get("ae_model") or default_model
    config["provider_code"] = provider.provider_code
    for key, value in (provider.default_params or {}).items():
        if key in {"temperature", "max_tokens"} and value is not None and key not in config:
            config[key] = value
    return config


async def _model_config_rotation_with_maga_defaults(
    db: AsyncSession,
    *,
    base_model_config: dict[str, Any],
    rotation: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for raw_item in rotation:
        item = {key: value for key, value in raw_item.items() if value is not None and value != ""}
        merged = {**base_model_config, **item}
        model_code = str(item.get("model_code") or "").strip()
        if model_code:
            merged["ge_model"] = item.get("ge_model") or model_code
            merged["ae_model"] = item.get("ae_model") or model_code
        configs.append(await _model_config_with_maga_defaults(db, merged))
    return configs


async def _default_llm_provider_config(
    db: AsyncSession,
    *,
    provider_code: str | None = None,
) -> LLMProviderConfig | None:
    conditions = [
        LLMProviderConfig.enabled == 1,
        LLMProviderConfig.is_deleted == 0,
    ]
    if provider_code:
        conditions.append(LLMProviderConfig.provider_code == provider_code)
    result = await db.execute(
        select(LLMProviderConfig)
        .where(*conditions)
        .order_by(LLMProviderConfig.priority.desc(), LLMProviderConfig.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _prompt_debug_model_config(
    db: AsyncSession,
    *,
    model_code: str,
) -> dict[str, Any]:
    route_result = await db.execute(
        select(LLMModelRoute)
        .where(
            LLMModelRoute.model_code == model_code,
            LLMModelRoute.enabled == 1,
            LLMModelRoute.is_deleted == 0,
        )
        .order_by(LLMModelRoute.priority.desc(), LLMModelRoute.id.asc())
        .limit(1)
    )
    route = route_result.scalar_one_or_none()
    provider = await _default_llm_provider_config(
        db,
        provider_code=route.provider_code if route else None,
    )
    provider_model = str((route.provider_model if route else None) or model_code)
    config: dict[str, Any] = {
        "model_code": provider_model,
        "provider_model": provider_model,
        "route_model_code": model_code,
    }
    if not provider:
        return config
    config.update(
        {
            "provider_code": provider.provider_code,
            "base_url": provider.base_url,
            "api_key": provider.api_key,
        }
    )
    return config


def _invocation_client_for_invoke_url(invoke_url: str | None):
    """Use the local deterministic mock only for explicit mock:// executor URLs."""
    if invoke_url and invoke_url.startswith("mock://"):
        return MockExecutorInvocationClient()
    return ExecutorInvocationClient()


@router.get("/ppl-runs/profiles", response_model=ResponseData[ContentPPLProfileListResponse])
async def list_ppl_profiles() -> ResponseData[ContentPPLProfileListResponse]:
    profiles = ContentGenerationPPLProfileService().list_profiles()
    return ResponseData(data=ContentPPLProfileListResponse(items=profiles))


@router.post("/ppl-runs/start", response_model=ResponseData[ContentPPLRunStartResponse])
async def start_ppl_generation(
    request: ContentPPLRunStartRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentPPLRunStartResponse]:
    service = ContentGenerationPPLProfileService()
    try:
        profile = service.require_profile(request.profile_code)
        if profile.content_type == "article":
            batch_response = await start_batch_generation(
                service.build_article_request(profile, request),
                db,
            )
        else:
            batch_response = await start_comment_batch_generation(
                service.build_comment_request(profile, request),
                db,
            )
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc

    if not batch_response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PPL run returned empty response",
        )
    response = ContentPPLRunStartResponse(
        **batch_response.data.model_dump(),
        profile=profile.response(),
    )
    return ResponseData(message=batch_response.message, data=response)


@router.post("/prompt-debug/run", response_model=ResponseData[PromptDebugResponse])
async def run_prompt_debug(
    request: PromptDebugRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptDebugResponse]:
    """Run one raw prompt and persist the workbench execution history."""
    run_group_id = request.run_group_id or uuid4().hex
    try:
        result = await call_direct_llm(
            model_config=await _prompt_debug_model_config(db, model_code=request.model_code),
            system_prompt=request.system_prompt or "",
            user_prompt=request.prompt,
            temperature=request.temperature if request.temperature is not None else 0.7,
            max_tokens=request.max_tokens if request.max_tokens is not None else 1500,
        )
    except Exception as exc:
        response = PromptDebugResponse(
            success=False,
            model_code=request.model_code,
            error_message=str(exc),
            run_group_id=run_group_id,
        )
        history = await PromptDebugHistoryService(db).create(
            request=request,
            response=response,
            run_group_id=run_group_id,
        )
        response.history_id = history.id
        return ResponseData(
            message="Prompt 调试失败",
            data=response,
        )

    response = PromptDebugResponse(
        success=True,
        content=result.content,
        model_code=result.model_code,
        provider_code=result.provider_code,
        provider_model=result.provider_model,
        usage=PromptDebugTokenUsage(**result.usage),
        latency_ms=result.latency_ms,
        run_group_id=run_group_id,
    )
    history = await PromptDebugHistoryService(db).create(
        request=request,
        response=response,
        run_group_id=run_group_id,
    )
    response.history_id = history.id
    return ResponseData(
        message="Prompt 调试完成",
        data=response,
    )


@router.get(
    "/prompt-debug/history",
    response_model=ResponseData[PromptDebugHistoryListResponse],
)
async def list_prompt_debug_history(
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptDebugHistoryListResponse]:
    items = await PromptDebugHistoryService(db).list_groups(limit=limit)
    return ResponseData(data=PromptDebugHistoryListResponse(items=items))


@router.get(
    "/prompt-debug/history/{run_group_id}",
    response_model=ResponseData[PromptDebugHistoryGroupDetail],
)
async def get_prompt_debug_history(
    run_group_id: str,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptDebugHistoryGroupDetail]:
    detail = await PromptDebugHistoryService(db).get_group(run_group_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调试历史不存在")
    return ResponseData(data=detail)


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
        model_config = await _model_config_with_maga_defaults(
            db,
            request.generation_model_config.model_dump(exclude_none=True),
        )
        job = await ContentBatchPlanner(db).create_batch_plan(
            asset_key=request.asset_key,
            rule_id=request.rule_id,
            source_row_no=request.source_row_no,
            product_topic=request.product_topic,
            target_audience=request.target_audience,
            persona_target=request.persona_target,
            style=request.style,
            count=request.count,
            articles_per_prompt=request.articles_per_prompt,
            postprocess_mode=request.postprocess_mode,
            keyword_asset_key=request.keyword_asset_key,
            prompt_mode=request.prompt_mode,
            draft_corpus=request.draft_corpus,
            draft_selling_painpoint_group=request.draft_selling_painpoint_group,
            draft_rule_id=request.draft_rule_id,
            draft_source_row_no=request.draft_source_row_no,
            model_config=model_config,
            model_config_rotation=await _model_config_rotation_with_maga_defaults(
                db,
                base_model_config=model_config,
                rotation=[item.model_dump(exclude_none=True) for item in request.model_config_rotation],
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
        await db.commit()
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
            scenario_code=request.scenario_code,
            keyword_asset_key=request.keyword_asset_key,
            quality_guard_profile_key=request.quality_guard_profile_key,
            business_rule=request.business_rule,
            rule_id=request.rule_id,
            rule_ids=request.rule_ids,
            source_row_no=request.source_row_no,
            draft_corpus=request.draft_corpus,
            draft_rule_id=request.draft_rule_id,
            draft_source_row_no=request.draft_source_row_no,
            draft_comment_prompt_bundle=request.draft_comment_prompt_bundle,
            comment_prompt_slots=request.comment_prompt_slots,
            comment_batch_variation_review=request.comment_batch_variation_review,
            comment_delivery_selection=request.comment_delivery_selection,
            comment_post_context=request.comment_post_context,
            count=request.count,
            concurrency=request.concurrency,
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


@router.post(
    "/comment-batches/{batch_id}/review-replay",
    response_model=ResponseData[ContentCommentBatchReviewReplayResponse],
    response_model_exclude_none=True,
)
async def replay_comment_batch_review(
    batch_id: int,
    request: ContentCommentBatchReviewReplayRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentCommentBatchReviewReplayResponse]:
    try:
        result = await ContentCommentBatchService(
            db,
            callback_base_url="/api/v1/content-agent",
        ).replay_review(
            batch_id,
            item_nos=request.item_nos,
            created_by=request.created_by,
        )
        await db.commit()
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(batch_id, include_details=True)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(
        message="Comment batch review replay completed",
        data=ContentCommentBatchReviewReplayResponse(
            batch_id=result.batch_id,
            reviewed_count=result.reviewed_count,
            skipped_count=result.skipped_count,
            reviewed_item_nos=result.reviewed_item_nos,
            skipped_item_nos=result.skipped_item_nos,
            changed_pass_item_nos=result.changed_pass_item_nos,
            body_changed_item_nos=result.body_changed_item_nos,
            report=report,
        ),
    )


@router.post("/preflight-check", response_model=ResponseData[ContentGenerationPreflightResponse])
async def check_content_generation_preflight(
    request: ContentGenerationPreflightRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentGenerationPreflightResponse]:
    result = await ContentGenerationPreflightService(db).check(
        asset_key=request.asset_key,
        asset_type=request.asset_type,
        executor_code=_normalized_executor_code(request.executor_code),
    )
    return ResponseData(
        message="Content generation preflight checked",
        data=result,
    )


@router.get("/batches", response_model=ResponseData[ContentBatchListResponse])
async def list_batches(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    asset_key: str | None = Query(default=None, max_length=128),
    rule_id: str | None = Query(default=None, max_length=128),
    source_row_no: int | None = Query(default=None, ge=1),
    keyword: str | None = Query(default=None, max_length=255),
    product_topic: str | None = Query(default=None, max_length=255),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchListResponse]:
    batches = await ContentBatchReportService(db).list_batch_reports(
        limit=limit,
        offset=offset,
        asset_key=asset_key,
        rule_id=rule_id,
        source_row_no=source_row_no,
        keyword=keyword,
        product_topic=product_topic,
    )
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


@router.get(
    "/batches/{batch_id}/report",
    response_model=ResponseData[ContentBatchReportResponse],
    response_model_exclude_none=True,
)
async def get_batch_report(
    batch_id: int,
    full: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchReportResponse]:
    service = ContentBatchReportService(db)
    try:
        report = await service.get_batch_report(batch_id, include_details=full)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(data=report)


@router.post(
    "/batches/{batch_id}/business-usability-review",
    response_model=ResponseData[ContentBatchBusinessUsabilityReviewResponse],
    response_model_exclude_none=True,
)
async def review_batch_business_usability(
    batch_id: int,
    request: ContentBatchBusinessUsabilityReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchBusinessUsabilityReviewResponse]:
    try:
        result = await ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
        ).review_business_usability_items(
            batch_id,
            force=request.force,
            limit=request.limit,
            concurrency=request.concurrency,
        )
        await db.commit()
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(batch_id, include_details=True)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(
        message="Business usability review completed",
        data=ContentBatchBusinessUsabilityReviewResponse(
            batch_id=result.batch_id,
            reviewed_count=result.reviewed_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
            reviewed_item_nos=result.reviewed_item_nos,
            skipped_item_nos=result.skipped_item_nos,
            failed_items=result.failed_items,
            tier_counts=result.tier_counts,
            report=report,
        ),
    )


@router.post(
    "/batches/{batch_id}/temporal-logic-shadow-review",
    response_model=ResponseData[ContentBatchTemporalLogicShadowReviewResponse],
    response_model_exclude_none=True,
)
async def review_batch_temporal_logic_shadow(
    batch_id: int,
    request: ContentBatchTemporalLogicShadowReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchTemporalLogicShadowReviewResponse]:
    try:
        result = await ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
        ).review_temporal_logic_shadow_items(
            batch_id,
            force=request.force,
            limit=request.limit,
            concurrency=request.concurrency,
        )
        await db.commit()
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(batch_id, include_details=True)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(
        message="Temporal logic shadow review completed",
        data=ContentBatchTemporalLogicShadowReviewResponse(
            batch_id=result.batch_id,
            reviewed_count=result.reviewed_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
            reviewed_item_nos=result.reviewed_item_nos,
            skipped_item_nos=result.skipped_item_nos,
            failed_items=result.failed_items,
            label_counts=result.label_counts,
            usage_totals=result.usage_totals,
            latency_totals=result.latency_totals,
            report=report,
        ),
    )


@router.post(
    "/batches/{batch_id}/claim-public-disease-shadow-review",
    response_model=ResponseData[ContentBatchClaimPublicDiseaseShadowReviewResponse],
    response_model_exclude_none=True,
)
async def review_batch_claim_public_disease_shadow(
    batch_id: int,
    request: ContentBatchClaimPublicDiseaseShadowReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchClaimPublicDiseaseShadowReviewResponse]:
    try:
        result = await ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
        ).review_claim_public_disease_shadow_items(
            batch_id,
            force=request.force,
            limit=request.limit,
            concurrency=request.concurrency,
        )
        await db.commit()
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(batch_id, include_details=True)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(
        message="Claim and public disease shadow review completed",
        data=ContentBatchClaimPublicDiseaseShadowReviewResponse(
            batch_id=result.batch_id,
            reviewed_count=result.reviewed_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
            reviewed_item_nos=result.reviewed_item_nos,
            skipped_item_nos=result.skipped_item_nos,
            failed_items=result.failed_items,
            label_counts=result.label_counts,
            usage_totals=result.usage_totals,
            latency_totals=result.latency_totals,
            report=report,
        ),
    )


@router.post(
    "/batches/{batch_id}/content-fit-shadow-review",
    response_model=ResponseData[ContentBatchContentFitShadowReviewResponse],
    response_model_exclude_none=True,
)
async def review_batch_content_fit_shadow(
    batch_id: int,
    request: ContentBatchContentFitShadowReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchContentFitShadowReviewResponse]:
    try:
        result = await ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
        ).review_content_fit_shadow_items(
            batch_id,
            force=request.force,
            limit=request.limit,
            concurrency=request.concurrency,
        )
        await db.commit()
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(batch_id, include_details=True)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(
        message="Content fit shadow review completed",
        data=ContentBatchContentFitShadowReviewResponse(
            batch_id=result.batch_id,
            reviewed_count=result.reviewed_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
            reviewed_item_nos=result.reviewed_item_nos,
            skipped_item_nos=result.skipped_item_nos,
            failed_items=result.failed_items,
            label_counts=result.label_counts,
            usage_totals=result.usage_totals,
            latency_totals=result.latency_totals,
            report=report,
        ),
    )


@router.post(
    "/batches/{batch_id}/fluency-shadow-review",
    response_model=ResponseData[ContentBatchFluencyShadowReviewResponse],
    response_model_exclude_none=True,
)
async def review_batch_fluency_shadow(
    batch_id: int,
    request: ContentBatchFluencyShadowReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchFluencyShadowReviewResponse]:
    try:
        result = await ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
        ).review_fluency_shadow_items(
            batch_id,
            force=request.force,
            limit=request.limit,
            concurrency=request.concurrency,
        )
        await db.commit()
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(batch_id, include_details=True)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(
        message="Fluency shadow review completed",
        data=ContentBatchFluencyShadowReviewResponse(
            batch_id=result.batch_id,
            reviewed_count=result.reviewed_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
            reviewed_item_nos=result.reviewed_item_nos,
            skipped_item_nos=result.skipped_item_nos,
            failed_items=result.failed_items,
            label_counts=result.label_counts,
            usage_totals=result.usage_totals,
            latency_totals=result.latency_totals,
            report=report,
        ),
    )


@router.post(
    "/batches/{batch_id}/focused-pipeline-shadow-review",
    response_model=ResponseData[ContentBatchFocusedPipelineShadowReviewResponse],
    response_model_exclude_none=True,
)
async def review_batch_focused_pipeline_shadow(
    batch_id: int,
    request: ContentBatchFocusedPipelineShadowReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchFocusedPipelineShadowReviewResponse]:
    try:
        result = await ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
        ).review_focused_pipeline_shadow_items(
            batch_id,
            force=request.force,
            limit=request.limit,
            concurrency=request.concurrency,
            rehearse_rewrites=request.rehearse_rewrites,
        )
        await db.commit()
        db.expire_all()
        report = await ContentBatchReportService(db).get_batch_report(batch_id, include_details=True)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(
        message="Focused review pipeline shadow validation completed",
        data=ContentBatchFocusedPipelineShadowReviewResponse(
            batch_id=result.batch_id,
            reviewed_count=result.reviewed_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count,
            reviewed_item_nos=result.reviewed_item_nos,
            skipped_item_nos=result.skipped_item_nos,
            failed_items=result.failed_items,
            decision_counts=result.decision_counts,
            rewrite_mode_counts=result.rewrite_mode_counts,
            comparison_counts=result.comparison_counts,
            mismatch_item_nos=result.mismatch_item_nos,
            action_comparison_counts=result.action_comparison_counts,
            action_mismatch_item_nos=result.action_mismatch_item_nos,
            rewrite_rehearsal_counts=result.rewrite_rehearsal_counts,
            accepted_rewrite_item_nos=result.accepted_rewrite_item_nos,
            manual_review_item_nos=result.manual_review_item_nos,
            usage_totals=result.usage_totals,
            latency_totals=result.latency_totals,
            report=report,
        ),
    )


@router.get("/batches/{batch_id}/export.xlsx")
async def export_batch_report_excel(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ContentBatchReportService(db)
    try:
        filename, content = await service.export_batch_report_excel(batch_id)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    quoted_filename = quote(filename)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
        },
    )


@router.get("/batches/{batch_id}/export-article-pool.csv")
async def export_batch_article_pool_csv(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ContentBatchReportService(db)
    try:
        filename, content = await service.export_article_pool_csv(batch_id)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    quoted_filename = quote(filename)
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
        },
    )


@router.get("/batches/{batch_id}/feedback-insights", response_model=ResponseData[ContentBatchFeedbackInsightResponse])
async def get_batch_feedback_insights(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentBatchFeedbackInsightResponse]:
    service = ContentBatchReportService(db)
    try:
        insights = await service.build_feedback_insights(batch_id)
    except ValueError as exc:
        raise _map_protocol_error(exc) from exc
    return ResponseData(data=insights)


@router.get("/feedback-samples", response_model=ResponseData[ContentFeedbackSampleListResponse])
async def list_feedback_samples(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    review_status: str | None = Query(default=None, max_length=32),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentFeedbackSampleListResponse]:
    samples = await ContentBatchReportService(db).list_feedback_samples(
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
