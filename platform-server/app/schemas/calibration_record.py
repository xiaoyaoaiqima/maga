"""
CalibrationRecord schemas - 校准工作台记录
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema


class CalibrationRecordBase(BaseSchema):
    """校准记录基础 Schema"""

    calibration_task_id: int = Field(..., description="校准任务ID")
    content_row_id: int = Field(..., description="content表主键ID")
    content_id: str = Field(..., description="内容ID（全局唯一）")
    job_id: Optional[str] = Field(default=None, description="Job ID")
    sub_job_id: Optional[str] = Field(default=None, description="Sub Job ID")
    expert_config_code: str = Field(..., description="专家配置编码")
    expert_func: str = Field(..., description="专家函数名")
    expert_type: str = Field(..., description="专家类型（CRITIC/BAN）")
    human_score_value: Optional[int] = Field(default=None, ge=0, le=100, description="人工评分（0-100）")
    human_passed: Optional[bool] = Field(default=None, description="人工通过（1=通过/0=不通过）")
    remark: Optional[str] = Field(default=None, description="备注")


class CalibrationRecordCreate(CalibrationRecordBase):
    """创建校准记录 Schema"""


class CalibrationRecordBatchCreate(BaseModel):
    """批量创建校准记录 Schema"""

    records: List[CalibrationRecordCreate]


class CalibrationRecordResponse(CalibrationRecordBase):
    """校准记录响应 Schema"""

    id: int
    reviewer_id: str
    reviewer_name: Optional[str] = None
    create_time: Optional[datetime] = None
    
    # AI评分相关字段（从 critic_score_record 关联获取）
    ai_score: Optional[int] = Field(default=None, description="AI评分（0-100，从critic_score_record关联）")
    ai_passed: Optional[bool] = Field(default=None, description="AI通过状态（从critic_score_record关联）")
    ai_score_version: Optional[int] = Field(default=None, description="AI评分版本号")
