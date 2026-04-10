"""
元数据管理 Schema

管理品牌、产品、标签等元数据配置
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MetadataType(str, Enum):
    """元数据类型"""
    BRAND = "brand"           # 品牌
    PRODUCT = "product"       # 产品
    TAG_GROUP = "tag_group"   # 标签组
    TAG = "tag"               # 标签


class MetadataItemBase(BaseModel):
    """元数据项基础字段"""
    name: str = Field(..., min_length=1, max_length=100, description="名称")
    code: Optional[str] = Field(None, max_length=50, description="编码（可选，用于程序引用）")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    icon: Optional[str] = Field(None, max_length=50, description="图标")
    color: Optional[str] = Field(None, max_length=20, description="颜色")
    sort_order: int = Field(0, description="排序顺序")


class MetadataItemCreate(MetadataItemBase):
    """创建元数据项"""
    item_type: str = Field(..., min_length=1, max_length=50, description="元数据类型（支持自定义类型）")
    parent_id: Optional[str] = Field(None, description="父级 ID（产品属于品牌，标签属于标签组）")


class MetadataItemUpdate(BaseModel):
    """更新元数据项"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="名称")
    code: Optional[str] = Field(None, max_length=50, description="编码")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    icon: Optional[str] = Field(None, max_length=50, description="图标")
    color: Optional[str] = Field(None, max_length=20, description="颜色")
    sort_order: Optional[int] = Field(None, description="排序顺序")
    is_active: Optional[int] = Field(None, description="是否启用")


class MetadataItemResponse(MetadataItemBase):
    """元数据项响应"""
    id: str = Field(..., description="ID")
    item_type: str = Field(..., description="元数据类型")
    parent_id: Optional[str] = Field(None, description="父级 ID")
    parent_name: Optional[str] = Field(None, description="父级名称")
    is_active: int = Field(1, description="是否启用")
    corpus_count: int = Field(0, description="关联的语料数量")
    children_count: int = Field(0, description="子项数量")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class MetadataTreeNode(BaseModel):
    """元数据树节点（用于树形展示）"""
    id: str
    key: str  # 同 id，用于前端 Tree 组件
    title: str  # 显示名称
    name: str
    code: Optional[str] = None
    item_type: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: int = 0
    is_active: int = 1
    corpus_count: int = 0
    children: list["MetadataTreeNode"] = Field(default_factory=list)


class BrandWithProducts(BaseModel):
    """品牌及其产品列表"""
    id: str
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    products: list[MetadataItemResponse] = Field(default_factory=list)
    total_corpus_count: int = Field(0, description="品牌下所有语料数量")


class TagGroupWithTags(BaseModel):
    """标签组及其标签列表"""
    id: str
    name: str
    description: Optional[str] = None
    tags: list[MetadataItemResponse] = Field(default_factory=list)


class MetadataStatsResponse(BaseModel):
    """元数据统计响应"""
    brand_count: int = Field(0, description="品牌数量")
    product_count: int = Field(0, description="产品数量")
    tag_group_count: int = Field(0, description="标签组数量")
    tag_count: int = Field(0, description="标签数量")
    global_corpus_count: int = Field(0, description="全局语料数量")
    brand_corpus_count: int = Field(0, description="品牌级语料数量")
    product_corpus_count: int = Field(0, description="产品级语料数量")


class SimpleOption(BaseModel):
    """简单选项（用于下拉选择）"""
    value: str = Field(..., description="值（通常是 name）")
    label: str = Field(..., description="显示标签")
    id: Optional[str] = Field(None, description="ID")


class LabelTypeOption(BaseModel):
    """标签类型的可选值"""
    value: str = Field(..., description="值")
    label: str = Field(..., description="显示标签")


class LabelType(BaseModel):
    """标签类型（用于统一标签选择器）"""
    key: str = Field(..., description="类型标识（如 product, campaign, season）")
    name: str = Field(..., description="类型名称")
    icon: str = Field(default="🏷️", description="图标")
    color: str = Field(default="#6b7280", description="颜色")
    multi_select: bool = Field(default=True, description="是否支持多选")
    options: list[LabelTypeOption] = Field(default_factory=list, description="可选值列表")


class LabelTypesResponse(BaseModel):
    """标签类型列表响应"""
    label_types: list[LabelType] = Field(default_factory=list, description="标签类型列表")
