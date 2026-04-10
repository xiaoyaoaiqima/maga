"""
JobVariant endpoints（方案库）

路径前缀由 api_router 注册为：/api/v1/job-variants
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.job_variant import JobVariantCreate, JobVariantResponse, JobVariantUpdate
from app.services.job_variant_service import JobVariantService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> JobVariantService:
    return JobVariantService(db)


@router.get("", response_model=ResponseData[list[JobVariantResponse]])
async def list_variants(
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    agent_code: Optional[str] = Query(None, description="Agent 编码"),
    enabled: Optional[bool] = Query(True, description="是否启用（默认 true）"),
    keyword: Optional[str] = Query(None, description="关键字（名称/备注模糊）"),
    limit: int = Query(200, ge=1, le=500, description="返回条数"),
    skip: int = Query(0, ge=0, description="偏移"),
    service: JobVariantService = Depends(get_service),
) -> ResponseData[list[JobVariantResponse]]:
    items = await service.list(
        tenant_id=tenant_id,
        agent_code=agent_code,
        enabled=enabled,
        keyword=keyword,
        limit=limit,
        skip=skip,
    )
    return ResponseData(data=[JobVariantResponse.model_validate(x) for x in items])


@router.get("/{variant_id}", response_model=ResponseData[JobVariantResponse])
async def get_variant(
    variant_id: str,
    service: JobVariantService = Depends(get_service),
) -> ResponseData[JobVariantResponse]:
    variant = await service.get(variant_id)
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return ResponseData(data=JobVariantResponse.model_validate(variant))


@router.post("", response_model=ResponseData[JobVariantResponse])
async def create_variant(
    data: JobVariantCreate,
    service: JobVariantService = Depends(get_service),
) -> ResponseData[JobVariantResponse]:
    try:
        variant = await service.create(data)
        return ResponseData(code=200, message="创建成功", data=JobVariantResponse.model_validate(variant))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{variant_id}", response_model=ResponseData[JobVariantResponse])
async def update_variant(
    variant_id: str,
    data: JobVariantUpdate,
    service: JobVariantService = Depends(get_service),
) -> ResponseData[JobVariantResponse]:
    try:
        variant = await service.update(variant_id, data)
        return ResponseData(code=200, message="更新成功", data=JobVariantResponse.model_validate(variant))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{variant_id}/disable", response_model=ResponseData[JobVariantResponse])
async def disable_variant(
    variant_id: str,
    updated_by: Optional[str] = Query(None, description="更新人（可选）"),
    service: JobVariantService = Depends(get_service),
) -> ResponseData[JobVariantResponse]:
    try:
        variant = await service.disable(variant_id, updated_by=updated_by)
        return ResponseData(code=200, message="禁用成功", data=JobVariantResponse.model_validate(variant))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{variant_id}", response_model=ResponseData[bool])
async def delete_variant(
    variant_id: str,
    updated_by: Optional[str] = Query(None, description="更新人（可选）"),
    service: JobVariantService = Depends(get_service),
) -> ResponseData[bool]:
    success = await service.delete(variant_id, updated_by=updated_by)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return ResponseData(code=200, message="删除成功", data=True)

