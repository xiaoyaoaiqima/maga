"""
图节点和边关系 Schemas（图可视化专用）

注意：节点/边的 CRUD 操作通过 category API 进行，这里只保留图可视化需要的查询响应类型
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field, field_serializer

from app.schemas.base import BaseSchema, PageInfo


# 节点类型
NodeLabel = Literal[
    "DIM_EMOTION",      # 情绪维度
    "DIM_IDENTITY",     # 人设
    "DIM_LANG",         # 语言表达
    "DIM_MOTIVE",       # 动机维度
    "FEATURE",          # 卖点
    "FEATURE_CORPUS",   # 卖点语料
    "PAIN",             # 痛点
    "PERSONA_ROOT",     # 人设聚合点
    "SCENE",            # 场景
]

# 关系类型
RelationType = Literal[
    "CONFLICTS_WITH",   # 不适合搭配
    "ENCOUNTERS",       # 会遇到
    "FITS_WITH",        # 适合搭配
    "FIXES",            # 解决
    "INCLUDES",         # 包含
    "LEADS_TO",         # 导致
    "SAYS_AS",          # 可以这样说
]


# ==================== Node Schemas ====================

class NodeItem(BaseSchema):
    """节点响应项"""
    id: int
    tenant_code: str
    label: str
    name: str
    description: Optional[str] = None
    corpus: Optional[list[Any]] = None  # 语料列表
    ai_instruction: Optional[dict[str, Any]] = None
    properties: Optional[dict[str, Any]] = None
    is_active: int = 1
    is_deleted: int = 0
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_serializer('id')
    def serialize_id(self, v: int) -> str:
        """序列化 ID 为字符串，避免 JavaScript 大整数精度丢失"""
        return str(v)


class NodeListQuery(BaseSchema):
    """节点列表查询参数"""
    page: int = 1
    page_size: int = 20
    tenant_code: Optional[str] = None
    label: Optional[str] = None
    keyword: Optional[str] = None  # 按 name 模糊搜索
    is_active: Optional[int] = None


class NodeListResponse(BaseSchema):
    """节点列表响应"""
    items: list[NodeItem]
    page_info: PageInfo


class NodeOptionsResponse(BaseSchema):
    """节点筛选选项"""
    labels: list[str]
    tenant_codes: list[str]


# ==================== Edge Schemas ====================

class EdgeItem(BaseSchema):
    """边响应项（图可视化需要）"""
    id: int
    tenant_code: str
    source_node_id: int
    target_node_id: int
    relation_type: str
    explanation: Optional[str] = None
    meta_data: Optional[dict[str, Any]] = None
    is_active: int = 1
    is_deleted: int = 0
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 冗余字段（用于前端展示，由后端填充）
    source_name: Optional[str] = None
    target_name: Optional[str] = None
    source_label: Optional[str] = None
    target_label: Optional[str] = None

    @field_serializer('id', 'source_node_id', 'target_node_id')
    def serialize_ids(self, v: int) -> str:
        """序列化 ID 为字符串，避免 JavaScript 大整数精度丢失"""
        return str(v)


# ==================== Graph Stats ====================

class GraphStats(BaseSchema):
    """图谱统计信息"""
    total_nodes: int
    total_edges: int
    nodes_by_label: dict[str, int]
    edges_by_relation: dict[str, int]


# ==================== Graph Visualization ====================

class GraphVisualizationQuery(BaseSchema):
    """图谱可视化查询参数"""
    tenant_code: Optional[str] = None
    min_degree: int = 0  # 最小边数，只返回边数 >= min_degree 的节点
    limit: int = 1000  # 最大返回节点数


class GraphVisualizationResponse(BaseSchema):
    """图谱可视化响应"""
    nodes: list[NodeItem]
    edges: list[EdgeItem]
    stats: dict[str, Any]  # 统计信息


# ==================== Node Neighbors ====================

class NodeNeighborsResponse(BaseSchema):
    """节点邻居响应（用于图聚焦模式，一次性返回中心节点+所有邻居+所有边）"""
    center_node: NodeItem  # 中心节点
    neighbors: list[NodeItem]  # 所有直接相连的邻居节点
    edges: list[EdgeItem]  # 中心节点与邻居之间的所有边
