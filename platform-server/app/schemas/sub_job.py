"""
SubJob schemas

v2 重构：
- 新增 plugin_snapshots 字段：插件快照缓存
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import Field

from app.schemas.base import BaseSchema


class SubJobCreate(BaseSchema):
    """Create SubJob schema"""
    job_id: str = Field(..., description="job_id")
    sub_job_id: str = Field(..., description="sub_job_id")
    content_id: str = Field(..., description="content_id")
    expert_list: List[str] = Field(..., description="需要执行的 expert_config_code 列表")
    expert_complete_list: Optional[List[str]] = Field(default=None, description="已完成的 expert_config_code 列表")
    status: str = Field(default="RUNNING", description="状态")
    plan_index: Optional[int] = Field(default=None, description="执行计划索引")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    # v2 新增
    plugin_snapshots: Optional[Dict[str, Any]] = Field(default=None, description="插件快照缓存")


class SubJobUpdate(BaseSchema):
    """Update SubJob schema"""
    expert_complete_list: Optional[List[str]] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    # v2 新增
    plugin_snapshots: Optional[Dict[str, Any]] = Field(default=None, description="插件快照缓存")


class SubJobResponse(BaseSchema):
    """SubJob response schema"""
    id: int
    job_id: str
    sub_job_id: str
    content_id: str
    expert_list: List[str]
    expert_complete_list: Optional[List[str]] = None
    status: str
    plan_index: Optional[int] = None
    error_message: Optional[str] = None
    # v2 新增
    plugin_snapshots: Optional[Dict[str, Any]] = Field(default=None, description="插件快照缓存")
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True


# ========== 快照相关 Schemas ==========

class SnapshotEntry(BaseSchema):
    """快照条目"""
    source: str = Field(..., description="数据来源: strategy / context_name")
    strategy_id: Optional[int] = Field(None, description="策略ID")
    label: Optional[str] = Field(None, description="节点的 label")
    node_id: Optional[str] = Field(None, description="节点ID")
    node_name: Optional[str] = Field(None, description="节点名称")
    corpus_id: Optional[int] = Field(None, description="语料索引")
    corpus_text: str = Field(..., description="语料文本")


class PluginSnapshot(BaseSchema):
    """插件快照"""
    plugin_code: str = Field(..., description="插件编码")
    snapshot: Dict[str, SnapshotEntry] = Field(..., description="变量名 -> 快照条目")

