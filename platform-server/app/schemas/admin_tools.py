"""
Admin Tools Schemas
用于「系统设置 -> 管理工具」异步任务的创建/查询/结果展示
"""

from datetime import datetime, date
from typing import Optional, Any, Literal

from pydantic import BaseModel, Field, ConfigDict


TaskStatus = Literal["pending", "running", "success", "failed", "cancelled"]


class AdminToolTaskCreateRequest(BaseModel):
    """
    创建管理工具任务

    task_type 建议枚举：
    - pricing_audit
    - trace_field_repair
    - route_upsert_from_usage
    - cost_backfill
    - rebuild_daily_stats
    - verify_report
    """

    task_type: str = Field(..., min_length=1, max_length=64)
    params: Optional[dict[str, Any]] = None


class AdminToolTaskResponse(BaseModel):
    id: int
    task_type: str
    status: TaskStatus
    progress: int
    message: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created_by: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AdminToolTaskListResponse(BaseModel):
    items: list[AdminToolTaskResponse]
    total: int


class AdminToolTaskListQuery(BaseModel):
    status: Optional[str] = None
    task_type: Optional[str] = None
    created_by: Optional[str] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=200)


