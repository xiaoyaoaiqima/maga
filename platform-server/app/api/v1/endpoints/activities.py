"""
活动管理 API
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.activity_service import ActivityService
from app.schemas.activity import (
    ActivityCreate,
    ActivityUpdate,
    ActivityResponse,
    ActivityListResponse,
    ActivityFilters,
    ActivitySimpleItem,
    ActivityStatusUpdate,
)
from app.schemas.base import ResponseModel

router = APIRouter(prefix="/activities", tags=["活动管理"])


def get_activity_service(db: AsyncSession = Depends(get_db)) -> ActivityService:
    """获取活动服务实例"""
    return ActivityService(db)


@router.post("", response_model=ResponseModel, summary="创建活动")
async def create_activity(
    data: ActivityCreate,
    service: ActivityService = Depends(get_activity_service)
):
    """
    创建活动
    
    - **activity_code**: 活动编码（同租户下唯一）
    - **activity_name**: 活动名称
    - **tenant_id**: 租户ID
    - **channel**: 渠道（xiaohongshu/douyin/taobao）
    - **target_audience**: 目标人群
    - **budget**: 预算
    - **config_json**: 活动配置
    - **start_time**: 开始时间
    - **end_time**: 结束时间
    - **status**: 状态（DRAFT/RUNNING/PAUSED/COMPLETED）
    """
    try:
        activity = await service.create_activity(data)
        return ResponseModel(code=200, message="创建成功", data=activity.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=ResponseModel, summary="获取活动列表")
async def list_activities(
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    activity_code: Optional[str] = Query(None, description="活动编码（模糊匹配）"),
    activity_name: Optional[str] = Query(None, description="活动名称（模糊匹配）"),
    channel: Optional[str] = Query(None, description="渠道"),
    status: Optional[str] = Query(None, description="状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    service: ActivityService = Depends(get_activity_service)
):
    """获取活动列表（分页）"""
    filters = ActivityFilters(
        tenant_id=tenant_id,
        activity_code=activity_code,
        activity_name=activity_name,
        channel=channel,
        status=status,
        page=page,
        page_size=page_size
    )
    total, items = await service.list_activities(filters)
    return ResponseModel(
        code=200,
        message="success",
        data=ActivityListResponse(total=total, items=items).model_dump()
    )


@router.get("/simple", response_model=ResponseModel, summary="获取简单活动列表")
async def list_activities_simple(
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    service: ActivityService = Depends(get_activity_service)
):
    """获取简单活动列表（用于下拉框）"""
    items = await service.list_simple(tenant_id)
    return ResponseModel(
        code=200,
        message="success",
        data=[item.model_dump() for item in items]
    )


@router.get("/{activity_id}", response_model=ResponseModel, summary="获取活动详情")
async def get_activity(
    activity_id: int,
    service: ActivityService = Depends(get_activity_service)
):
    """获取活动详情"""
    activity = await service.get_activity(activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="活动不存在")
    return ResponseModel(code=200, message="success", data=activity.model_dump())


@router.put("/{activity_id}", response_model=ResponseModel, summary="更新活动")
async def update_activity(
    activity_id: int,
    data: ActivityUpdate,
    service: ActivityService = Depends(get_activity_service)
):
    """更新活动信息"""
    activity = await service.update_activity(activity_id, data)
    if not activity:
        raise HTTPException(status_code=404, detail="活动不存在")
    return ResponseModel(code=200, message="更新成功", data=activity.model_dump())


@router.put("/{activity_id}/status", response_model=ResponseModel, summary="更新活动状态")
async def update_activity_status(
    activity_id: int,
    data: ActivityStatusUpdate,
    service: ActivityService = Depends(get_activity_service)
):
    """更新活动状态"""
    activity = await service.update_status(activity_id, data)
    if not activity:
        raise HTTPException(status_code=404, detail="活动不存在")
    return ResponseModel(code=200, message="更新成功", data=activity.model_dump())


@router.delete("/{activity_id}", response_model=ResponseModel, summary="删除活动")
async def delete_activity(
    activity_id: int,
    service: ActivityService = Depends(get_activity_service)
):
    """删除活动（软删除）"""
    success = await service.delete_activity(activity_id)
    if not success:
        raise HTTPException(status_code=404, detail="活动不存在")
    return ResponseModel(code=200, message="删除成功")
