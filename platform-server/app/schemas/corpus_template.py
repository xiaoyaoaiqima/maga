"""
语料模板 Schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from app.schemas.base import BaseSchema


class TemplateField(BaseSchema):
    """模板字段定义"""
    key: str = Field(..., description="字段键名")
    label: str = Field(..., description="字段显示名称")
    type: str = Field(default="textarea", description="字段类型: textarea/input/select")
    required: bool = Field(default=False, description="是否必填")
    placeholder: Optional[str] = Field(default=None, description="占位提示文字")
    options: Optional[list[str]] = Field(default=None, description="选项列表（type=select时使用）")
    order: Optional[int] = Field(default=None, description="字段顺序，用于解决 MySQL JSON 列不保证顺序的问题")


class CorpusTemplateItem(BaseSchema):
    """模板响应项"""
    id: int
    code: str
    name: str
    category_type: str
    fields: list[TemplateField]
    description: Optional[str] = None
    tenant_code: str = "default"
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    node_count: int = Field(default=0, description="使用该模板的节点数量")


class CorpusTemplateCreate(BaseSchema):
    """创建模板请求"""
    code: Optional[str] = Field(default=None, max_length=50, description="模板编码（不传则自动生成 template-xxx 格式）")
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    category_type: str = Field(..., min_length=1, max_length=50, description="分类类型")
    fields: list[TemplateField] = Field(..., description="字段定义列表")
    description: Optional[str] = Field(default=None, max_length=500, description="模板描述")
    tenant_code: str = Field(default="default", max_length=50, description="租户编码")


class CorpusTemplateUpdate(BaseSchema):
    """更新模板请求"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    fields: Optional[list[TemplateField]] = None
    description: Optional[str] = Field(default=None, max_length=500)


class CorpusTemplateListQuery(BaseSchema):
    """模板列表查询参数"""
    category_type: Optional[str] = None
    tenant_code: Optional[str] = None


class CorpusTemplateListResponse(BaseSchema):
    """模板列表响应"""
    items: list[CorpusTemplateItem]
    total: int


# ==================== 结构化 Corpus ====================

class StructuredCorpus(BaseSchema):
    """结构化语料格式（新格式）"""
    template_code: str = Field(..., description="使用的模板编码")
    fields: dict[str, Any] = Field(..., description="字段值，key 对应模板的 field.key")


class CorpusValue(BaseSchema):
    """语料值（兼容新旧格式）"""
    # 旧格式字段
    text: Optional[str] = None
    weight: Optional[float] = 1.0
    # 新格式会使用 StructuredCorpus
