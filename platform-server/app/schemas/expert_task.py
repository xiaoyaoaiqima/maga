"""
ExpertTask schemas
"""
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


class ExpertTaskBase(BaseSchema):
    """ExpertTask base schema"""
    job_id: str = Field(..., max_length=64, description="对应 job.job_id")
    expert_config_code: str = Field(..., max_length=64, description="对应 expert_config.expert_config_code")
    cron_expression: str = Field(..., max_length=255, description="cron 表达式")
    misfire_policy: int = Field(default=1, description="计划执行错误策略：1立即执行 2执行一次 3放弃执行")
    concurrent: int = Field(default=0, description="是否并发执行：0允许 1禁止")
    status: int = Field(default=0, description="0待执行 1执行中 2暂停 3完成（一次性任务）")
    remark: Optional[str] = Field(default=None, description="备注")


class ExpertTaskCreate(ExpertTaskBase):
    """ExpertTask create schema"""
    pass


class ExpertTaskUpdate(BaseSchema):
    """ExpertTask update schema"""
    cron_expression: Optional[str] = Field(default=None, max_length=255)
    misfire_policy: Optional[int] = None
    concurrent: Optional[int] = None
    status: Optional[int] = None
    remark: Optional[str] = None


class ExpertTaskInDB(ExpertTaskBase, TimestampSchema):
    """ExpertTask in database schema"""
    id: int
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_deleted: int = 0


class ExpertTaskResponse(ExpertTaskInDB):
    """ExpertTask response schema"""
    pass

