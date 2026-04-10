"""
CalibrationRecords API endpoints - 校准工作台记录 API
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user_id, get_current_active_user
from app.models.sys_user import SysUser
from app.schemas.base import ResponseData
from app.schemas.calibration_record import (
    CalibrationRecordBatchCreate,
    CalibrationRecordResponse,
    CalibrationRecordCreate,
)
from app.services.calibration_record_service import CalibrationRecordService

router = APIRouter()


def _normalize_reviewer_name(user: SysUser) -> Optional[str]:
    if user.name:
        return user.name
    if user.username:
        return user.username
    return None


def _validate_record(item: CalibrationRecordCreate) -> None:
    if item.expert_type == "BAN":
        if item.human_passed is None:
            raise HTTPException(status_code=400, detail="BAN 类型必须填写通过/不通过")
        return
    if item.expert_type == "CRITIC":
        if item.human_score_value is None:
            raise HTTPException(status_code=400, detail="CRITIC 类型必须填写评分")
        return
    raise HTTPException(status_code=400, detail="专家类型不支持")


@router.post("", response_model=ResponseData[List[CalibrationRecordResponse]])
async def create_calibration_records(
    payload: CalibrationRecordBatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(get_current_active_user),
) -> ResponseData[List[CalibrationRecordResponse]]:
    if not payload.records:
        raise HTTPException(status_code=400, detail="请提交至少一条校准记录")

    for record in payload.records:
        _validate_record(record)

    service = CalibrationRecordService(db)
    reviewer_name = _normalize_reviewer_name(current_user)
    records = await service.create_records(
        records=payload.records,
        reviewer_id=current_user.id,
        reviewer_name=reviewer_name,
    )
    return ResponseData(
        code=200,
        message="保存成功",
        data=[CalibrationRecordResponse.model_validate(item) for item in records],
    )


@router.get("", response_model=ResponseData[List[CalibrationRecordResponse]])
async def list_calibration_records(
    calibration_task_id: Optional[int] = Query(None, description="校准任务ID（不传则查询所有任务）"),
    content_ids: Optional[List[str]] = Query(None, description="内容ID列表"),
    expert_config_codes: Optional[List[str]] = Query(None, description="专家配置编码列表"),
    reviewer_id: Optional[str] = Query(None, description="校准人ID（不传则查询所有校准人）"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(1000, ge=1, le=5000, description="返回记录数"),
    db: AsyncSession = Depends(get_db),
    _current_user_id: str = Depends(get_current_user_id),
) -> ResponseData[List[CalibrationRecordResponse]]:
    service = CalibrationRecordService(db)
    records = await service.list_records(
        calibration_task_id=calibration_task_id,
        content_ids=content_ids,
        expert_config_codes=expert_config_codes,
        reviewer_id=reviewer_id,
        skip=skip,
        limit=limit,
    )
    return ResponseData(
        code=200,
        message="查询成功",
        data=[CalibrationRecordResponse.model_validate(item) for item in records],
    )
