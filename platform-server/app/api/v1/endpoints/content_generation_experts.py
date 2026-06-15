"""Content-generation flow Expert management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.content_generation_expert import (
    BusinessForbiddenTermListResponse,
    BusinessForbiddenTermStatusRequest,
    BusinessForbiddenTermUpsertRequest,
    CommentDeliveryLedgerCheckRequest,
    CommentDeliveryLedgerCheckResponse,
    CommentDeliveryLedgerDuplicateHit,
    CommentDeliveryLedgerImportRequest,
    CommentDeliveryLedgerImportResponse,
    CommentDeliveryLedgerListResponse,
    ContentGenerationAuditFlowResponse,
    ContentGenerationExpertListResponse,
    ContentGenerationExpertPreviewRequest,
    ContentGenerationExpertPreviewResponse,
    ContentGenerationExpertResponse,
    ContentGenerationExpertUpsertRequest,
)
from app.services.business_forbidden_term_service import A2_SENTIMENT_COMMENT_ASSET_KEY, BusinessForbiddenTermService
from app.services.comment_delivery_ledger_service import (
    CommentDeliveryLedgerService,
    ledger_entry_to_dict,
)
from app.services.content_generation_expert_service import (
    CONTENT_REWRITE_CAPABILITY,
    ContentGenerationExpertService,
)
from app.services.forbidden_term_review_service import (
    MAX_FORBIDDEN_TERM_REWRITE_ROUNDS,
    STATIC_FORBIDDEN_TERMS,
)

router = APIRouter()


@router.get("/experts", response_model=ResponseData[ContentGenerationExpertListResponse])
async def list_content_generation_experts(
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentGenerationExpertListResponse]:
    service = ContentGenerationExpertService(db)
    term_service = BusinessForbiddenTermService(db)
    business_terms = await term_service.list_terms(asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY, include_default=False)
    business_entries = await term_service.list_entries(asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY, include_default=False)
    return ResponseData(
        data=ContentGenerationExpertListResponse(
            items=await service.list_flow_experts(),
            audit_flow=ContentGenerationAuditFlowResponse(
                source="maga_forbidden_term_review",
                max_rewrite_rounds=MAX_FORBIDDEN_TERM_REWRITE_ROUNDS,
                rewrite_capability=CONTENT_REWRITE_CAPABILITY,
                static_forbidden_terms=list(STATIC_FORBIDDEN_TERMS),
                business_forbidden_terms=business_terms,
                business_forbidden_term_entries=business_entries,
            ),
        )
    )


@router.get("/business-forbidden-terms", response_model=ResponseData[BusinessForbiddenTermListResponse])
async def list_business_forbidden_terms(
    asset_key: str = Query(default=A2_SENTIMENT_COMMENT_ASSET_KEY, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[BusinessForbiddenTermListResponse]:
    entries = await BusinessForbiddenTermService(db).list_entries(asset_key=asset_key, include_default=False)
    return ResponseData(data=BusinessForbiddenTermListResponse(asset_key=asset_key, items=entries))


@router.post("/business-forbidden-terms", response_model=ResponseData[BusinessForbiddenTermListResponse])
async def upsert_business_forbidden_terms(
    request: BusinessForbiddenTermUpsertRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[BusinessForbiddenTermListResponse]:
    asset_key = request.asset_key or A2_SENTIMENT_COMMENT_ASSET_KEY
    service = BusinessForbiddenTermService(db)
    try:
        await service.upsert_entries(
            asset_key=asset_key,
            entries=[entry.model_dump() for entry in request.entries],
            created_by=request.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    entries = await service.list_entries(asset_key=asset_key, include_default=False)
    return ResponseData(message="保存成功", data=BusinessForbiddenTermListResponse(asset_key=asset_key, items=entries))


@router.patch("/business-forbidden-terms/status", response_model=ResponseData[BusinessForbiddenTermListResponse])
@router.put("/business-forbidden-terms/status", response_model=ResponseData[BusinessForbiddenTermListResponse])
async def update_business_forbidden_term_status(
    request: BusinessForbiddenTermStatusRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[BusinessForbiddenTermListResponse]:
    asset_key = request.asset_key or A2_SENTIMENT_COMMENT_ASSET_KEY
    service = BusinessForbiddenTermService(db)
    try:
        await service.set_enabled(
            asset_key=asset_key,
            term=request.term,
            enabled=request.enabled,
            created_by=request.updated_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    entries = await service.list_entries(asset_key=asset_key, include_default=False)
    return ResponseData(message="保存成功", data=BusinessForbiddenTermListResponse(asset_key=asset_key, items=entries))


@router.get("/comment-delivery-ledger", response_model=ResponseData[CommentDeliveryLedgerListResponse])
async def list_comment_delivery_ledger(
    asset_key: str = Query(default=A2_SENTIMENT_COMMENT_ASSET_KEY, max_length=128),
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[CommentDeliveryLedgerListResponse]:
    service = CommentDeliveryLedgerService(db)
    items, total = await service.list_entries(asset_key=asset_key, q=q, limit=limit, offset=offset)
    return ResponseData(
        data=CommentDeliveryLedgerListResponse(
            asset_key=asset_key,
            total=total,
            items=[ledger_entry_to_dict(item) for item in items],
        )
    )


@router.post("/comment-delivery-ledger/import", response_model=ResponseData[CommentDeliveryLedgerImportResponse])
async def import_comment_delivery_ledger(
    request: CommentDeliveryLedgerImportRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[CommentDeliveryLedgerImportResponse]:
    asset_key = request.asset_key or A2_SENTIMENT_COMMENT_ASSET_KEY
    result = await CommentDeliveryLedgerService(db).upsert_many(
        asset_key=asset_key,
        entries=[entry.model_dump() for entry in request.entries],
        source_type=request.source_type,
        source_uri=request.source_uri,
        delivered_by=request.delivered_by,
    )
    return ResponseData(
        message="导入成功",
        data=CommentDeliveryLedgerImportResponse(
            asset_key=result.asset_key,
            imported_rows=result.imported_rows,
            skipped_existing_rows=result.skipped_existing_rows,
            skipped_input_duplicate_rows=result.skipped_input_duplicate_rows,
            total_input_rows=result.total_input_rows,
        ),
    )


@router.post("/comment-delivery-ledger/check", response_model=ResponseData[CommentDeliveryLedgerCheckResponse])
async def check_comment_delivery_ledger(
    request: CommentDeliveryLedgerCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[CommentDeliveryLedgerCheckResponse]:
    asset_key = request.asset_key or A2_SENTIMENT_COMMENT_ASSET_KEY
    service = CommentDeliveryLedgerService(db)
    existing = await service.exists_many(asset_key=asset_key, comments=request.comments)
    hits = []
    for index, comment in enumerate(request.comments):
        normalized = service.normalize_comment(comment)
        entry = existing.get(normalized)
        if entry is None:
            continue
        hits.append(
            CommentDeliveryLedgerDuplicateHit(
                index=index,
                comment_text=comment,
                normalized_comment=normalized,
                ledger_entry=ledger_entry_to_dict(entry),
            )
        )
    return ResponseData(
        data=CommentDeliveryLedgerCheckResponse(
            asset_key=asset_key,
            duplicate_count=len(hits),
            hits=hits,
        )
    )


@router.put("/experts/{expert_config_code}", response_model=ResponseData[ContentGenerationExpertResponse])
async def upsert_content_generation_expert(
    expert_config_code: str,
    request: ContentGenerationExpertUpsertRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentGenerationExpertResponse]:
    service = ContentGenerationExpertService(db)
    try:
        expert = await service.upsert_flow_expert(expert_config_code, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseData(message="保存成功", data=expert)


@router.post(
    "/experts/{expert_config_code}/preview",
    response_model=ResponseData[ContentGenerationExpertPreviewResponse],
)
async def preview_content_generation_expert_prompt(
    expert_config_code: str,
    request: ContentGenerationExpertPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ContentGenerationExpertPreviewResponse]:
    service = ContentGenerationExpertService(db)
    try:
        result = await service.preview_prompt(
            expert_config_code=expert_config_code,
            content_type=request.content_type,
            previous_content=request.previous_content,
            business_rule=request.business_rule,
            selected_keywords=request.selected_keywords,
            forbidden_hits=request.forbidden_hits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseData(data=ContentGenerationExpertPreviewResponse(**result))
