"""
PluginContext schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


class PluginContextBase(BaseSchema):
    """PluginContext base schema"""
    variable_name: Optional[str] = Field(default=None, max_length=255, description="变量名")
    context_name: Optional[str] = Field(default=None, max_length=255, description="上下文变量名")
    context: Optional[str] = Field(default=None, description="上下文内容")
    default_keywords: Optional[Dict[str, Any]] = Field(default=None, description="默认关键词")
    default_corpus: Optional[Dict[str, Any]] = Field(default=None, description="默认语料")
    remark: Optional[str] = Field(default=None, description="备注")


class PluginContextCreate(PluginContextBase):
    """PluginContext create schema"""
    pass


class PluginContextUpdate(BaseSchema):
    """PluginContext update schema"""
    variable_name: Optional[str] = Field(default=None, max_length=255)
    context_name: Optional[str] = Field(default=None, max_length=255)
    context: Optional[str] = None
    default_keywords: Optional[Dict[str, Any]] = None
    default_corpus: Optional[Dict[str, Any]] = None
    remark: Optional[str] = None


class PluginContextInDB(PluginContextBase, TimestampSchema):
    """PluginContext in database schema"""
    id: int
    publish_status: str = Field(default="DRAFT", description="上线状态：DRAFT(草稿)/PUBLISHED(已上线)")
    publish_time: Optional[datetime] = Field(default=None, description="上线时间")
    publish_by: Optional[str] = Field(default=None, description="上线人")
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_deleted: int = 0


class PluginContextResponse(PluginContextInDB):
    """PluginContext response schema"""
    pass

