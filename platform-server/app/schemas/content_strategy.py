"""
内容策略 Schemas

v3 简化：
- 统一使用 defined_combinations 存储组合（前端直接管理）
- 前端统一渲染全部组合 + 删减操作 + 重新生成（后悔药）
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field, field_serializer, field_validator

from app.schemas.base import BaseSchema, PageInfo


# ==================== 节点池和组合配置 ====================

class NodePoolConfig(BaseSchema):
    """
    节点池配置（v3 新结构）

    每个维度的节点池配置，包含节点ID列表和选择模式
    """
    node_ids: list[str] = Field(default_factory=list, description="节点ID列表")
    select_mode: Literal["single", "multiple"] = Field(
        "multiple",
        description="选择模式：single-分开使用 / multiple-合在一起使用"
    )

    @field_validator("select_mode", mode="before")
    @classmethod
    def normalize_select_mode(cls, v: Any) -> str:
        """
        兼容旧版本数据，自动转换过时的值

        旧版本使用的值：
        - "all" → "single" (所有节点分开使用)
        - "random" → "single" (随机选择单个节点)
        """
        if v == "all" or v == "random":
            return "single"
        return v


class DefinedCombination(BaseSchema):
    """手动定义的组合"""
    id: str = Field(..., description="组合ID，如 combo_0")
    name: str = Field(..., description="组合名称，如 创业妈妈 + 换季")
    nodes: dict[str, str] = Field(..., description="维度到节点ID的映射，如 {persona: node_id, scenario: node_id}")


class StrategySettings(BaseSchema):
    """策略高级设置"""
    include_corpus: bool = Field(True, description="获取组合时是否包含语料")


class ScopeContext(BaseSchema):
    """
    Scope 上下文，用于策略的产品/品牌绑定

    用于控制策略在不同品牌/产品下的回退机制
    """
    level: Literal["global", "brand", "product"] = Field(
        "product",
        description="级别：global(全局) / brand(品牌) / product(产品)"
    )
    brand_code: Optional[str] = Field(None, description="品牌编码，如 2000001")
    brand_name: Optional[str] = Field(None, description="品牌名称，如 皇家美素佳儿")
    product_name: Optional[str] = Field(None, description="产品名称，如 旺玥")
    fallback_enabled: Optional[bool] = Field(
        True,
        description="是否启用回退机制（Product > Brand > Global）"
    )


# ==================== 策略 CRUD Schemas ====================

class ContentStrategyCreate(BaseSchema):
    """创建内容策略请求"""
    name: str = Field(..., min_length=1, max_length=100, description="策略名称")
    description: Optional[str] = Field(None, max_length=500, description="策略描述")

    # v3 节点池（新结构，包含 select_mode）
    node_pools: Optional[dict[str, NodePoolConfig]] = Field(
        None,
        description="""
        节点池配置（v3 新结构），格式:
        {
            "persona": {"node_ids": ["id1", "id2"], "select_mode": "multiple"},
            "scenario": {"node_ids": ["id3"], "select_mode": "single"}
        }
        """
    )
    defined_combinations: Optional[list[DefinedCombination]] = Field(
        None, description="组合列表（前端管理的笛卡尔积）"
    )

    # 组合规则
    max_combinations: int = Field(
        200, ge=1, le=1000, description="最大组合数量"
    )
    settings: Optional[StrategySettings] = Field(None, description="高级设置")

    # 标签
    tags: Optional[list[str]] = Field(None, description="策略标签，用于分类和快速筛选")

    # Scope 上下文（产品/品牌绑定）
    scope_context: Optional[ScopeContext] = Field(None, description="Scope 上下文，用于策略的产品/品牌绑定")

    tenant_code: str = Field("default", description="租户编码")


class ContentStrategyUpdate(BaseSchema):
    """更新内容策略请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="策略名称")
    description: Optional[str] = Field(None, max_length=500, description="策略描述")

    # v3 节点池（新结构，包含 select_mode）
    node_pools: Optional[dict[str, NodePoolConfig]] = Field(
        None, 
        description="节点池配置（v3 新结构，包含 node_ids 和 select_mode）"
    )
    defined_combinations: Optional[list[DefinedCombination]] = Field(
        None, description="组合列表"
    )

    # 组合规则
    max_combinations: Optional[int] = Field(
        None, ge=1, le=1000, description="最大组合数量"
    )
    settings: Optional[StrategySettings] = Field(None, description="高级设置")

    # 标签
    tags: Optional[list[str]] = Field(None, description="策略标签")

    # Scope 上下文（产品/品牌绑定）
    scope_context: Optional[ScopeContext] = Field(None, description="Scope 上下文，用于策略的产品/品牌绑定")

    is_active: Optional[int] = Field(None, description="状态：0-禁用/归档 1-启用")


class ContentStrategyItem(BaseSchema):
    """内容策略响应项"""
    id: int
    name: str
    description: Optional[str] = None

    # v3 节点池（新结构，包含 select_mode）
    # 使用 dict[str, Any] 避免 Pydantic v2 对嵌套 dict 类型的严格验证
    node_pools: Optional[dict[str, Any]] = Field(
        None,
        description="""
        节点池配置（v3 新结构），格式:
        {
            "persona": {"node_ids": ["id1", "id2"], "select_mode": "multiple"},
            "scenario": {"node_ids": ["id3"], "select_mode": "single"}
        }
        """
    )
    defined_combinations: Optional[list[dict[str, Any]]] = None
    combinations_count: int = Field(0, description="组合数量（计算字段）")

    # 组合规则
    max_combinations: int
    settings: Optional[dict[str, Any]] = None

    # 标签
    tags: Optional[list[str]] = Field(None, description="策略标签")

    # 其他
    tenant_code: str
    is_active: int
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    @field_serializer("id")
    def serialize_id(self, v: int) -> str:
        """序列化 ID 为字符串"""
        return str(v)


class ContentStrategyListResponse(BaseSchema):
    """内容策略列表响应"""
    items: list[ContentStrategyItem]
    page_info: PageInfo


# ==================== 组合获取 Schemas ====================

class NodeInfo(BaseSchema):
    """节点信息"""
    id: str
    name: str
    label: str
    corpus: Optional[list[dict[str, Any]]] = None
    description: Optional[str] = None


class CombinationItem(BaseSchema):
    """单个组合项"""
    id: str = Field(..., description="组合ID")
    name: str = Field(..., description="组合名称")
    nodes: dict[str, NodeInfo] = Field(..., description="维度 -> 节点信息的映射")


class GetCombinationsResponse(BaseSchema):
    """获取组合列表响应"""
    strategy_id: str
    strategy_name: str
    combination_mode: str
    total_count: int
    combinations: list[CombinationItem]


# ==================== 旧版生成接口（保留向后兼容）====================

class GenerateCombinationsRequest(BaseSchema):
    """生成组合请求（已废弃，保留向后兼容）"""
    count: int = Field(10, ge=1, le=100, description="生成组合数量")
    overrides: Optional[dict[str, list[str]]] = Field(None, description="覆盖默认配置")


class GenerateCombinationsResponse(BaseSchema):
    """生成组合响应（已废弃，保留向后兼容）"""
    strategy_id: str
    strategy_name: str
    total_count: int
    combinations: list[CombinationItem]


# ==================== 多策略合并 Schemas（strategy_v3）====================

class StrategySelectionItem(BaseSchema):
    """策略选择项"""
    strategy_id: str = Field(..., description="策略ID")
    selected_combo_ids: Optional[list[str]] = Field(
        None, description="选中的组合ID列表（不传则使用全部组合）"
    )


class MergeStrategyCombinationsRequest(BaseSchema):
    """多策略合并请求"""
    strategy_selections: list[StrategySelectionItem] = Field(
        ..., min_length=1, description="策略选择列表"
    )
    include_corpus: bool = Field(True, description="是否包含语料")
    target_count: int | None = Field(None, ge=1, le=2000, description="目标组合数量（默认100）")
    sample_mode: Literal["first", "primary_strategy", "random"] = Field(
        "first", description="采样模式：first=前N个, primary_strategy=主策略优先, random=全随机"
    )
    primary_strategy_id: int | None = Field(None, description="主策略ID（sample_mode=primary_strategy时必填）")


class SourceComboRef(BaseSchema):
    """来源组合引用"""
    strategy_id: str
    combo_id: str


class SourceStrategyRef(BaseSchema):
    """来源策略引用"""
    strategy_id: str
    strategy_name: str


class DimensionConflict(BaseSchema):
    """维度冲突信息"""
    dimension: str = Field(..., description="冲突的维度")
    strategy_1_id: str = Field(..., description="第一个策略ID")
    strategy_1_name: str = Field(..., description="第一个策略名称")
    strategy_2_id: str = Field(..., description="第二个策略ID")
    strategy_2_name: str = Field(..., description="第二个策略名称")


class MergedCombinationItem(BaseSchema):
    """合并后的组合项"""
    id: str = Field(..., description="合并组合ID")
    name: str = Field(..., description="合并组合名称")
    source_combos: list[SourceComboRef] = Field(..., description="来源组合列表")
    merged_nodes: dict[str, Any] = Field(..., description="合并后的节点信息 (维度 -> 节点)")


class MergeStrategyCombinationsResponse(BaseSchema):
    """多策略合并响应"""
    merged_dimensions: list[str] = Field(..., description="合并后的维度列表")
    dimension_conflicts: list[DimensionConflict] = Field(
        default_factory=list, description="维度冲突列表（如果有）"
    )
    source_strategies: list[SourceStrategyRef] = Field(..., description="来源策略列表")
    total_count: int = Field(..., description="合并组合总数")
    merged_combinations: list[MergedCombinationItem] = Field(..., description="合并后的组合列表")
