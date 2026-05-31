"""Content-generation flow Expert management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.content_generation_expert import (
    ContentGenerationAuditFlowResponse,
    ContentGenerationExpertListResponse,
    ContentGenerationExpertPreviewRequest,
    ContentGenerationExpertPreviewResponse,
    ContentGenerationExpertResponse,
    ContentGenerationExpertUpsertRequest,
)
from app.services.business_forbidden_term_service import BusinessForbiddenTermService
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
    business_terms = await BusinessForbiddenTermService(db).list_terms()
    return ResponseData(
        data=ContentGenerationExpertListResponse(
            items=await service.list_flow_experts(),
            audit_flow=ContentGenerationAuditFlowResponse(
                source="maga_forbidden_term_review",
                max_rewrite_rounds=MAX_FORBIDDEN_TERM_REWRITE_ROUNDS,
                rewrite_capability=CONTENT_REWRITE_CAPABILITY,
                static_forbidden_terms=list(STATIC_FORBIDDEN_TERMS),
                business_forbidden_terms=business_terms,
            ),
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
