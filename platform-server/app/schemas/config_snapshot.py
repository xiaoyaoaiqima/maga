"""
配置快照 Schema
"""
from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import Field
from enum import Enum

from app.schemas.base import BaseSchema


class EntityType(str, Enum):
    """实体类型"""
    PLUGIN = "plugin"
    PLUGIN_CONTEXT = "plugin_context"
    EXPERT_CONFIG = "expert_config"


class SnapshotType(str, Enum):
    """快照类型"""
    DRAFT = "draft"       # 草稿（自动保存）
    VERSION = "version"   # 版本（正式保存时创建）


class SnapshotSave(BaseSchema):
    """保存快照请求"""
    entity_type: EntityType = Field(..., description="实体类型")
    entity_id: Optional[int] = Field(default=None, description="实体ID，新增时为空")
    entity_code: str = Field(..., max_length=255, description="实体编码")
    content: Dict[str, Any] = Field(..., description="快照内容")
    snapshot_type: SnapshotType = Field(default=SnapshotType.DRAFT, description="快照类型")
    description: Optional[str] = Field(default=None, max_length=500, description="版本描述")


class SnapshotResponse(BaseSchema):
    """快照响应"""
    id: int
    entity_type: str
    entity_id: Optional[int]
    entity_code: str
    snapshot_type: str
    content: Dict[str, Any]
    version: int
    description: Optional[str]
    create_time: Optional[datetime]
    created_by: Optional[str]


class SnapshotListResponse(BaseSchema):
    """快照列表响应"""
    items: List[SnapshotResponse]
    total: int


class DraftCheckResponse(BaseSchema):
    """草稿检查响应"""
    has_draft: bool
    draft: Optional[SnapshotResponse] = None

