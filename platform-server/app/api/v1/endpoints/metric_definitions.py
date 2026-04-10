from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.data_query import ApiResponse
from app.core.database import get_db
from app.schemas.metric_definition import MetricDefinitionResponse, MetricDefinitionUpdate
from app.services.metric_definition_service import MetricDefinitionService

router = APIRouter()


@router.get("", response_model=ApiResponse)
async def list_metric_definitions(
    db: AsyncSession = Depends(get_db),
):
    """获取所有指标定义"""
    service = MetricDefinitionService(db)
    definitions = await service.get_all()
    # 如果数据库为空，尝试自动同步一次
    if not definitions:
        await service.sync_from_codebase()
        definitions = await service.get_all()
        
    return ApiResponse(data=[MetricDefinitionResponse.model_validate(d).model_dump() for d in definitions])


@router.put("/{metric_key}", response_model=ApiResponse)
async def update_metric_definition(
    metric_key: str,
    update_data: MetricDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新指标定义（名称、描述等）"""
    service = MetricDefinitionService(db)
    updated = await service.update(metric_key, update_data)
    if not updated:
        # 如果不存在，尝试先同步再更新（处理新添加的指标）
        await service.sync_from_codebase()
        updated = await service.update(metric_key, update_data)
        
        if not updated:
            raise HTTPException(status_code=404, detail="指标定义不存在")
            
    return ApiResponse(data=MetricDefinitionResponse.model_validate(updated).model_dump())


@router.post("/sync", response_model=ApiResponse)
async def sync_metric_definitions(
    db: AsyncSession = Depends(get_db),
):
    """从代码库同步指标定义到数据库"""
    service = MetricDefinitionService(db)
    stats = await service.sync_from_codebase()
    return ApiResponse(message="同步完成", data=stats)

