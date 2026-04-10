"""
ExpertBusinessResult schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import Field

from app.schemas.base import BaseSchema


class ExpertBusinessResultCreate(BaseSchema):
    """Create ExpertBusinessResult schema"""
    job_id: str = Field(..., description="job_id")
    sub_job_id: str = Field(..., description="sub_job_id")
    content_id: str = Field(..., description="content_id")
    expert_task_id: Optional[int] = Field(default=None, description="expert_task.id")
    expert_config_code: str = Field(..., description="expert_config_code")
    expert_config_name: str = Field(..., description="expert_config_name")
    model_code: Optional[str] = Field(default=None, description="使用的模型编码")
    business_type: str = Field(..., description="业务类型")
    plugin_config_snapshot: Optional[List[Dict[str, Any]]] = Field(default=None, description="插件配置快照")
    prompt: Optional[str] = Field(default=None, description="使用的 prompt")
    business_result: Dict[str, Any] = Field(..., description="业务返回结果")
    status: str = Field(default="SUCCESS", description="状态")
    plan_index: Optional[int] = Field(default=None, description="执行计划索引")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class ExpertBusinessResultResponse(BaseSchema):
    """ExpertBusinessResult response schema"""
    id: int
    job_id: str
    sub_job_id: str
    content_id: str
    expert_task_id: Optional[int] = None
    expert_config_code: str
    expert_config_name: str
    model_code: Optional[str] = None
    business_type: str
    plugin_config_snapshot: Optional[List[Dict[str, Any]]] = None
    prompt: Optional[str] = None
    business_result: Dict[str, Any]
    status: str
    plan_index: Optional[int] = None
    error_message: Optional[str] = None
    create_time: Optional[datetime] = None

    class Config:
        from_attributes = True

