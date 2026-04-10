"""
CalibrationTasks API endpoints - 校准任务 API
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user_id, get_current_active_user
from app.models.sys_user import SysUser
from app.schemas.base import ResponseData
from app.schemas.calibration_task import (
    CalibrationTaskCreate,
    CalibrationTaskUpdate,
    CalibrationTaskResponse,
)
from app.services.calibration_task_service import CalibrationTaskService

router = APIRouter()


def _normalize_user_name(user: SysUser) -> Optional[str]:
    if user.name:
        return user.name
    if user.username:
        return user.username
    return None


@router.post("", response_model=ResponseData[CalibrationTaskResponse])
async def create_calibration_task(
    payload: CalibrationTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_active_user),
) -> ResponseData[CalibrationTaskResponse]:
    service = CalibrationTaskService(db)
    creator_name = _normalize_user_name(current_user)
    assignee_id = payload.assignee_id or current_user.id
    assignee_name = creator_name
    task = await service.create_task(
        payload=payload,
        creator_id=current_user.id,
        creator_name=creator_name,
        assignee_id=assignee_id,
        assignee_name=assignee_name,
    )
    return ResponseData(
        code=200,
        message="创建成功",
        data=CalibrationTaskResponse.model_validate(task),
    )


@router.patch("/{task_id}", response_model=ResponseData[CalibrationTaskResponse])
async def update_calibration_task(
    task_id: int,
    payload: CalibrationTaskUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user_id: str = Depends(get_current_user_id),
) -> ResponseData[CalibrationTaskResponse]:
    service = CalibrationTaskService(db)
    task = await service.update_task(task_id, payload)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ResponseData(
        code=200,
        message="更新成功",
        data=CalibrationTaskResponse.model_validate(task),
    )


@router.get("", response_model=ResponseData[List[CalibrationTaskResponse]])
async def list_calibration_tasks(
    status: Optional[str] = Query(None, description="任务状态"),
    expert_config_code: Optional[str] = Query(None, description="专家配置编码"),
    assignee_id: Optional[str] = Query(None, description="负责人ID（不传则查询所有用户）"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(1000, ge=1, le=5000, description="返回记录数"),
    db: AsyncSession = Depends(get_db),
    _current_user_id: str = Depends(get_current_user_id),
) -> ResponseData[List[CalibrationTaskResponse]]:
    service = CalibrationTaskService(db)
    tasks = await service.list_tasks(
        assignee_id=assignee_id,
        status=status,
        expert_config_code=expert_config_code,
        skip=skip,
        limit=limit,
    )
    return ResponseData(
        code=200,
        message="查询成功",
        data=[CalibrationTaskResponse.model_validate(item) for item in tasks],
    )
