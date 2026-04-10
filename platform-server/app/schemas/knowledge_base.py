"""
知识库 Schemas（KnowledgeBase - 文档容器）
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


class KnowledgeBaseItem(BaseSchema):
    """知识库响应项"""
    id: int
    code: str
    name: str
    description: Optional[str] = None
    enabled: int

    # 前端期望的字段名：file_count
    file_count: int

    total_parsed_count: int

    # 前端期望的字段名：create_time / update_time
    create_time: datetime = Field(alias="created_at", serialization_alias="create_time")
    update_time: Optional[datetime] = Field(None, alias="updated_at", serialization_alias="update_time")

    created_by: Optional[str] = None

    model_config = {"populate_by_name": True}


class KnowledgeBaseCreate(BaseSchema):
    """创建知识库请求"""
    code: Optional[str] = Field(None, max_length=100, description="编码（留空自动生成）")
    name: str = Field(..., max_length=255, description="知识库名称")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    enabled: int = Field(1, description="启用状态: 0-禁用 1-启用")
    created_by: Optional[str] = Field(None, max_length=64, description="创建人ID")


class KnowledgeBaseUpdate(BaseSchema):
    """更新知识库请求"""
    name: Optional[str] = Field(None, max_length=255, description="知识库名称")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    enabled: Optional[int] = Field(None, description="启用状态: 0-禁用 1-启用")


class KnowledgeBaseListQuery(BaseSchema):
    """知识库列表查询参数"""
    keyword: Optional[str] = None
    enabled: Optional[bool] = None
