"""
CalibrationTask schemas - 校准任务
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema


class CalibrationTaskBase(BaseSchema):
    """校准任务基础 Schema"""

    task_code: Optional[str] = Field(default=None, description="任务编码")
    task_name: str = Field(..., description="任务名称")
    status: str = Field(default="PENDING", description="状态：PENDING/IN_PROGRESS/DONE/CANCELLED")
    assignee_id: Optional[str] = Field(default=None, description="指派人ID")
    assignee_name: Optional[str] = Field(default=None, description="指派人姓名")
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    finish_time: Optional[datetime] = Field(default=None, description="完成时间")
    due_time: Optional[datetime] = Field(default=None, description="截止时间")
    remark: Optional[str] = Field(default=None, description="备注")


class CalibrationTaskCreate(BaseModel):
    """创建校准任务"""

    task_code: Optional[str] = None
    task_name: Optional[str] = None
    assignee_id: Optional[str] = None
    due_time: Optional[datetime] = None
    remark: Optional[str] = None


class CalibrationTaskUpdate(BaseModel):
    """更新校准任务"""

    task_name: Optional[str] = None
    status: Optional[str] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    start_time: Optional[datetime] = None
    finish_time: Optional[datetime] = None
    due_time: Optional[datetime] = None
    remark: Optional[str] = None


class CalibrationTaskResponse(CalibrationTaskBase):
    """校准任务响应"""

    id: int
    created_by: Optional[str] = None
    created_name: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


class CalibrationTaskListResponse(BaseModel):
    """任务列表"""

    items: List[CalibrationTaskResponse]
