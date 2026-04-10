"""
分类树服务层

基于 Node + Edge 模型实现多层级分类管理
"""
from __future__ import annotations

import json
import random
import time
from typing import Any

from loguru import logger
import httpx
from sqlalchemy import and_, exists, func as sqla_func, select, tuple_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.redis import (
    cache_delete_pattern,
    cache_get,
    cache_set,
    CACHE_TTL_CATEGORY_TREE,
    CACHE_TTL_NODE_BATCH,
    invalidate_node_cache,
)
from app.models.graph import GraphEdge, GraphNode
from app.models.corpus_template import CorpusTemplate
from app.services.label_utils import (
    get_labels,
    get_label_values,
    is_global_node,
    match_filters,
    set_labels,
)
from app.utils.cache_decorators import invalidate_tree_cache, set_cache_tenant


# ID 生成计数器（避免批量操作时冲突）
_id_counter = 0


def generate_id() -> int:
    """
    生成一个唯一的整数 ID
    使用时间戳（毫秒）+ 计数器的方式
    确保在批量操作时不会冲突
    """
    global _id_counter
    _id_counter = (_id_counter + 1) % 100000  # 0-99999 循环
    timestamp = int(time.time() * 1000)  # 毫秒级时间戳
    # 格式：timestamp(毫秒) * 100000 + counter
    # 范围：约 17 位数字，在 BIGINT 范围内
    return timestamp * 100000 + _id_counter


class CategoryService:
    """分类树服务"""

    # 缓存键前缀
    CACHE_KEY_PREFIX = "kc:tree"

    def __init__(self, db: AsyncSession):
        self.db = db

    # 关键词标签（叶子节点，不作为分类显示）
    KEYWORD_LABEL = "KEYWORD"

    async def _invalidate_tree_cache(self, tenant_code: str = "default") -> None:
        """清除分类树缓存、维度缓存和节点批量缓存"""
        # 清除分类树缓存
        tree_pattern = f"{self.CACHE_KEY_PREFIX}:{tenant_code}:*"
        await cache_delete_pattern(tree_pattern)
        logger.debug(f"清除分类树缓存: {tree_pattern}")

        # 同时清除维度缓存（因为维度列表来源于顶级节点）
        dimensions_pattern = f"kc:dimensions:{tenant_code}:*"
        await cache_delete_pattern(dimensions_pattern)
        logger.debug(f"清除维度缓存: {dimensions_pattern}")

        # 清除节点批量缓存（所有 batch 缓存）
        batch_pattern = "kc:node:batch:*"
        await cache_delete_pattern(batch_pattern)
        logger.debug(f"清除节点批量缓存: {batch_pattern}")

    async def _order_corpus_fields(
        self, corpus_list: list[dict[str, Any]], tenant_code: str
    ) -> list[dict[str, Any]]:
        """
        根据 corpus 模板的 fields 定义顺序重新排序 corpus.fields
        解决 MySQL JSON 列不保证键顺序的问题
        """
        # 收集所有用到的 template_code
        template_codes = set()
        for corpus in corpus_list:
            if isinstance(corpus, dict) and "template_code" in corpus:
                template_codes.add(corpus["template_code"])

        # 批量获取模板
        templates = {}
        if template_codes:
            stmt = select(CorpusTemplate).where(
                and_(
                    CorpusTemplate.code.in_(template_codes),
                    CorpusTemplate.is_deleted == 0,
                    CorpusTemplate.tenant_code == tenant_code,
                )
            )
            result = await self.db.execute(stmt)
            for template in result.scalars():
                # 构建字段顺序映射：field_key -> index
                # 使用字段中的 order 字段来确定顺序（解决 MySQL JSON 列不保证数组元素顺序的问题）
                field_order = {}
                for field in template.fields:
                    key = field.get("key")
                    order = field.get("order")
                    if key is not None:
                        # 如果有 order 字段，使用它；否则使用一个大值（排在后面）
                        field_order[key] = order if order is not None else 999

                templates[template.code] = field_order

        # 重新排序每个 corpus 的 fields
        ordered_corpus = []
        for corpus in corpus_list:
            if not isinstance(corpus, dict):
                ordered_corpus.append(corpus)
                continue

            # 检查是否有 template_code 和 fields
            template_code = corpus.get("template_code")
            fields = corpus.get("fields")

            if (
                template_code
                and template_code in templates
                and isinstance(fields, dict)
            ):
                # 根据模板顺序重新排序
                field_order = templates[template_code]
                ordered_fields = {}
                field_keys = []  # 记录字段顺序，供 Orchestrator _corpus_to_text 使用

                # 按 field_order 的值（模板中的索引）排序字段
                # field_order 是 {field_key: index} 的映射
                sorted_keys = sorted(field_order.keys(), key=lambda k: field_order[k])

                # 先按模板顺序添加
                for key in sorted_keys:
                    if key in fields:
                        ordered_fields[key] = fields[key]
                        field_keys.append(key)
                # 添加模板中没有的自定义字段
                for key, value in fields.items():
                    if key not in field_order:
                        ordered_fields[key] = value
                        field_keys.append(key)

                new_corpus = dict(corpus)
                new_corpus["fields"] = ordered_fields
                new_corpus["field_keys"] = field_keys  # 添加字段顺序，解决 JSON 序列化后 dict 顺序丢失问题
                ordered_corpus.append(new_corpus)
            else:
                # 没有 template_code 或找不到模板，保持原样
                ordered_corpus.append(corpus)

        return ordered_corpus

    async def _sort_tree_corpus(
        self, tree: list[dict[str, Any]], tenant_code: str
    ) -> None:
        """
        递归排序树中所有节点的 corpus 字段
        直接修改 tree 结构，不返回新树
        
        Args:
            tree: 树形结构列表
            tenant_code: 租户编码
        """
        # 收集所有 corpus 并记录它们的位置
        corpus_list = []
        corpus_positions = []  # 记录每个 corpus 在树中的位置
        
        def collect_corpus(nodes: list[dict[str, Any]]) -> None:
            """递归收集所有 corpus"""
            for node in nodes:
                corpus = node.get("corpus", [])
                if corpus and isinstance(corpus, list):
                    corpus_list.extend(corpus)
                    # 记录 corpus 所属节点和索引范围
                    corpus_positions.append({
                        "node": node,
                        "start_idx": len(corpus_list) - len(corpus),
                        "end_idx": len(corpus_list)
                    })
                # 递归处理子节点
                children = node.get("children", [])
                if children:
                    collect_corpus(children)
        
        collect_corpus(tree)
        
        # 批量排序所有 corpus
        if corpus_list:
            ordered_corpus = await self._order_corpus_fields(corpus_list, tenant_code)
        else:
            ordered_corpus = []
        
        # 将排序后的 corpus 更新回树中
        for pos in corpus_positions:
            node = pos["node"]
            start_idx = pos["start_idx"]
            end_idx = pos["end_idx"]
            # 更新节点的 corpus
            node["corpus"] = ordered_corpus[start_idx:end_idx]

    async def get_tree(
        self,
        tenant_code: str = "default",
        root_category_type: str | None = None,
        brand_code: str | None = None,
        product_name: str | None = None,
        include_global: bool = True,
        is_active: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        获取完整分类树

        Args:
            tenant_code: 租户编码（保留参数以兼容旧接口）
            root_category_type: 根分类类型筛选（persona/brand/platform/content_structure/forbidden）
            brand_code: 品牌编码（按 properties.brands 筛选）
            product_name: 产品名称（按 properties.products 筛选）
            include_global: 是否包含全局语料（没有绑定品牌/产品的节点）
            is_active: 归档状态筛选（0=归档, 1=启用, None=全部）

        Returns:
            树形结构列表
        """
        # === 缓存检查 ===
        cache_key = f"kc:tree:{tenant_code}:{root_category_type or ''}:{brand_code or ''}:{product_name or ''}:{include_global}:{is_active or ''}"
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug(f"分类树缓存命中: {cache_key}")
            return cached

        # 查询所有节点，然后根据 brands/products 字段筛选

        # 1. 获取所有节点（通过 level 字段区分层级，不再过滤 KEYWORD 类型）
        # 注意：元数据节点（brand/product/tag/tag_group）存储在独立的 metadata_items 表中
        conditions = [
            GraphNode.tenant_code == tenant_code,
            GraphNode.is_deleted == 0,
        ]
        # 如果指定了 is_active，添加筛选条件
        if is_active is not None:
            conditions.append(GraphNode.is_active == is_active)
        stmt = select(GraphNode).where(and_(*conditions))
        result = await self.db.execute(stmt)
        all_categories = result.scalars().all()

        # 2. 获取所有 INCLUDES 边
        # 注意：当筛选归档节点时，也需要获取归档的边，以便正确构建树结构
        # 边的 is_active 筛选逻辑
        # - is_active=None（查询全部）：只获取启用的边（默认行为）
        # - is_active=1（只查询激活节点）：只获取启用的边
        # - is_active=0（只查询归档节点）：获取所有边（包括归档的边，以便正确构建树结构）
        edge_conditions = [
            GraphEdge.tenant_code == tenant_code,
            GraphEdge.relation_type == "INCLUDES",
            GraphEdge.is_deleted == 0,
        ]
        # 只在 is_active=0 时才获取所有边，其他情况只获取启用的边
        if is_active != 0:
            edge_conditions.append(GraphEdge.is_active == 1)

        stmt = select(GraphEdge).where(and_(*edge_conditions))
        result = await self.db.execute(stmt)
        all_edges = result.scalars().all()

        # 4. 构建父子映射（只考虑结果集中的节点）
        parent_to_children: dict[int, list[int]] = {}
        child_to_parent: dict[int, int] = {}
        all_category_ids = {c.id for c in all_categories}
        
        for edge in all_edges:
            # 只有当父节点和子节点都在结果集中时，才建立父子关系
            if edge.source_node_id in all_category_ids and edge.target_node_id in all_category_ids:
                if edge.source_node_id not in parent_to_children:
                    parent_to_children[edge.source_node_id] = []
                parent_to_children[edge.source_node_id].append(edge.target_node_id)
                child_to_parent[edge.target_node_id] = edge.source_node_id

        # 5. 找出顶级节点（没有父节点的分类，或者父节点不在结果集中）
        root_ids = [cid for cid in all_category_ids if cid not in child_to_parent]

        # 6. 构建节点映射
        node_map = {c.id: c for c in all_categories}

        # 7. 递归构建树（子节点继承父节点的 label 作为 category_type）
        def build_tree(node_id: int, parent_label: str | None = None) -> dict[str, Any] | None:
            node = node_map.get(node_id)
            if not node:
                return None

            props = node.properties or {}
            # category_type 直接使用 label 字段（根节点的 label，子节点继承）
            category_type = node.label or parent_label

            # 使用新的标签工具函数获取标签
            labels = get_labels(props)
            node_brands = labels.get("brand", [])
            node_products = labels.get("product", [])
            node_tags = labels.get("tag", [])

            # 判断是否为全局语料（没有绑定任何品牌或产品的节点）
            is_global_corpus = is_global_node(props)

            # ===== 品牌/产品筛选逻辑 =====
            # 如果指定了 brand_code 或 product_name，检查节点是否匹配
            if brand_code or product_name:
                filters = {}
                if brand_code:
                    filters["brand"] = brand_code
                if product_name:
                    filters["product"] = product_name

                # 如果节点有品牌或产品绑定，检查是否匹配
                if node_brands or node_products:
                    if not match_filters(props, filters):
                        return None  # 不匹配筛选条件，不包含此节点

            tree_node = {
                "id": str(node.id),
                "name": node.name,
                "label": node.label,
                "description": node.description,
                "corpus": node.corpus,  # 节点的语料列表（稍后排序）
                "category_type": category_type,
                "level": props.get("level", 1),
                "sort_order": props.get("sort_order", 0),
                "icon": props.get("icon"),
                "color": props.get("color"),
                "is_active": node.is_active,
                "is_global": is_global_corpus,  # 是否为全局语料
                "tenant_code": node.tenant_code,  # 原始租户编码
                # 兼容前端：继续返回 tags/brands/products，但使用新格式获取
                "tags": node_tags,
                "brands": node_brands,
                "products": node_products,
                "labels": labels,  # 新增：统一标签结构
                "properties": props,  # 完整的 properties（供前端灵活筛选）
                "children": [],
            }

            # 递归添加子节点，传递根节点的 label
            child_ids = parent_to_children.get(node_id, [])
            for child_id in child_ids:
                child_node = build_tree(child_id, category_type)
                if child_node:
                    tree_node["children"].append(child_node)

            # 按 sort_order 排序子节点
            tree_node["children"].sort(key=lambda x: x.get("sort_order", 0))

            return tree_node

        # 8. 构建根节点列表
        tree = []
        for root_id in root_ids:
            root_node = build_tree(root_id)
            if root_node:
                # 如果指定了 category_type 筛选
                if root_category_type and root_node.get("category_type") != root_category_type:
                    continue
                tree.append(root_node)

        # 按 sort_order 排序
        tree.sort(key=lambda x: x.get("sort_order", 0))

        # === 排序所有节点的 corpus 字段 ===
        # 收集所有 corpus 并批量排序（避免 N+1 查询）
        await self._sort_tree_corpus(tree, tenant_code)

        # === 写入缓存 ===
        await cache_set(cache_key, tree, CACHE_TTL_CATEGORY_TREE)

        return tree

    async def get_children(
        self,
        parent_id: int,
        tenant_code: str = "default",
        include_keywords: bool = True,
    ) -> list[dict[str, Any]]:
        """
        获取直接子节点（分类 + 关键词）

        Args:
            parent_id: 父节点 ID
            tenant_code: 租户编码
            include_keywords: 是否包含关键词

        Returns:
            子节点列表
        """
        # 获取所有子节点 ID
        stmt = select(GraphEdge.target_node_id).where(
            and_(
                GraphEdge.tenant_code == tenant_code,
                GraphEdge.source_node_id == parent_id,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
                GraphEdge.is_active == 1,
            )
        )
        result = await self.db.execute(stmt)
        child_ids = [row[0] for row in result.fetchall()]

        if not child_ids:
            return []

        # 获取子节点详情（支持任意语义化 label）
        conditions = [
            GraphNode.id.in_(child_ids),
            GraphNode.is_deleted == 0,
        ]
        # 如果不包含关键词，则排除 KEYWORD 类型
        if not include_keywords:
            conditions.append(GraphNode.label != self.KEYWORD_LABEL)

        stmt = select(GraphNode).where(and_(*conditions))
        result = await self.db.execute(stmt)
        children = result.scalars().all()

        # 检查每个子节点是否还有下级子节点
        child_ids_set = set(child_ids)
        has_children_map = await self._batch_check_has_children(list(child_ids_set))

        # 转换为字典
        result_list = []
        for child in children:
            props = child.properties or {}
            result_list.append({
                "id": str(child.id),
                "name": child.name,
                "label": child.label,
                "description": child.description,
                "category_type": child.label,  # 直接使用 label 字段作为 category_type
                "level": props.get("level"),
                "sort_order": props.get("sort_order", 0),
                "is_active": child.is_active,
                "has_children": has_children_map.get(child.id, False),
                "keywords": child.corpus or [],  # 语料字段，兼容前端
            })

        # 排序：非 KEYWORD 在前，KEYWORD 在后，按 sort_order 排序
        result_list.sort(key=lambda x: (0 if x["label"] != self.KEYWORD_LABEL else 1, x.get("sort_order", 0)))

        return result_list

    async def _batch_check_has_children(self, node_ids: list[int]) -> dict[int, bool]:
        """批量检查节点是否有子节点"""
        if not node_ids:
            return {}

        stmt = (
            select(GraphEdge.source_node_id)
            .where(
                and_(
                    GraphEdge.source_node_id.in_(node_ids),
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.is_deleted == 0,
                )
            )
            .distinct()
        )
        result = await self.db.execute(stmt)
        has_children_ids = {row[0] for row in result.fetchall()}

        return {node_id: node_id in has_children_ids for node_id in node_ids}

    async def get_sibling_labels(
        self,
        parent_id: int | None,
        tenant_code: str = "default",
    ) -> list[str]:
        """
        获取同级节点的所有 label（用于新建时参考）

        Args:
            parent_id: 父节点 ID（None 表示顶级节点）
            tenant_code: 租户编码

        Returns:
            label 列表（去重）
        """
        if parent_id:
            # 获取同一父节点下的所有子节点
            stmt = select(GraphEdge.target_node_id).where(
                and_(
                    GraphEdge.source_node_id == parent_id,
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            sibling_ids = [row[0] for row in result.fetchall()]

            if sibling_ids:
                stmt = select(GraphNode.label).where(
                    and_(
                        GraphNode.id.in_(sibling_ids),
                        GraphNode.label != self.KEYWORD_LABEL,
                        GraphNode.is_deleted == 0,
                    )
                ).distinct()
                result = await self.db.execute(stmt)
                return [row[0] for row in result.fetchall()]
            return []
        else:
            # 顶级节点：获取所有没有父节点的节点的 label
            # 先获取所有有父节点的节点 ID
            stmt = select(GraphEdge.target_node_id).where(
                and_(
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.tenant_code == tenant_code,
                    GraphEdge.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            child_ids = {row[0] for row in result.fetchall()}

            # 获取所有非 KEYWORD 节点
            stmt = select(GraphNode).where(
                and_(
                    GraphNode.tenant_code == tenant_code,
                    GraphNode.label != self.KEYWORD_LABEL,
                    GraphNode.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            all_nodes = result.scalars().all()

            # 过滤出顶级节点的 label
            root_labels = set()
            for node in all_nodes:
                if node.id not in child_ids:
                    root_labels.add(node.label)

            return list(root_labels)

    @invalidate_tree_cache()
    async def create_category(
        self,
        name: str,
        label: str | None = None,
        parent_id: int | None = None,
        category_type: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        tenant_code: str = "default",
        labels: dict[str, list[str]] | None = None,
        tags: list[str] | None = None,
        brands: list[str] | None = None,
        products: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        创建分类节点

        Args:
            name: 分类名称
            label: 语义化标签（如 "大人设"、"小人设"、"品牌"）
            parent_id: 父分类 ID（None 表示顶级分类）
            category_type: 分类类型（顶级分类必填）
            description: 描述
            icon: 图标
            color: 颜色
            tenant_code: 租户编码
            labels: 统一标签结构 {product: [...], tag_group_code: [...]}
            tags: 业务标签列表（已弃用，请使用 labels）
            brands: 品牌标签列表（已弃用，请使用 labels）
            products: 产品标签列表（已弃用，请使用 labels）

        Returns:
            创建的分类节点
        """
        # 计算层级，如果有父节点则推断 label（不再继承 category_type）
        level = 1
        inferred_label = label
        if parent_id:
            parent = await self.db.get(GraphNode, parent_id)
            if parent:
                parent_props = parent.properties or {}
                level = parent_props.get("level", 1) + 1
                # 子节点不存储 category_type，只有根节点（level=1）才存储
                # category_type 通过向上遍历到根节点获取
                # 如果没有指定 label，尝试使用同级节点的 label
                if not inferred_label:
                    sibling_labels = await self.get_sibling_labels(parent_id, tenant_code)
                    if sibling_labels:
                        inferred_label = sibling_labels[0]  # 使用同级的第一个 label
        
        # 默认使用父节点的 label 或 "分类"
        if not inferred_label:
            if parent_id:
                parent = await self.db.get(GraphNode, parent_id)
                if parent:
                    inferred_label = parent.label  # 使用父节点的 label
            if not inferred_label:
                inferred_label = "分类"  # 最终默认值

        # 业务约束：同一个 label 只能有一个顶级节点（root）
        # root 判定以"没有父 INCLUDES 边"为准，避免 level 不一致导致漏判
        # 注意：只检查启用状态的节点（is_active=1），归档节点不影响
        if not parent_id:
            parent_edge_exists = exists().where(
                and_(
                    GraphEdge.tenant_code == tenant_code,
                    GraphEdge.target_node_id == GraphNode.id,
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.is_deleted == 0,
                )
            )
            root_stmt = select(GraphNode.id, GraphNode.name).where(
                and_(
                    GraphNode.tenant_code == tenant_code,
                    GraphNode.label == inferred_label,
                    GraphNode.is_deleted == 0,
                    GraphNode.is_active == 1,  # 只检查启用状态的顶级节点
                    ~parent_edge_exists,
                )
            )
            root_result = await self.db.execute(root_stmt)
            existing_root = root_result.first()
            if existing_root:
                raise ValueError(
                    f"禁止创建：label「{inferred_label}」已存在顶级节点「{existing_root[1]}」，一个 label 只能有一个顶级节点"
                )

        # 计算 sort_order（在同级中的顺序）
        if parent_id:
            stmt = select(GraphEdge).where(
                and_(
                    GraphEdge.source_node_id == parent_id,
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            sibling_count = len(result.scalars().all())
            sort_order = sibling_count + 1
        else:
            stmt = select(GraphNode).where(
                and_(
                    GraphNode.label == "CATEGORY",
                    GraphNode.tenant_code == tenant_code,
                    GraphNode.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            all_categories = result.scalars().all()
            # 统计顶级分类数量
            root_count = sum(1 for c in all_categories if (c.properties or {}).get("level") == 1)
            sort_order = root_count + 1

        # 检查是否已存在相同 (tenant_code, label, name) 的启用节点
        # 注意：只检查 is_active=1 的节点，允许创建与已归档节点同名的新节点
        existing_stmt = select(GraphNode).where(
            and_(
                GraphNode.tenant_code == tenant_code,
                GraphNode.label == inferred_label,
                GraphNode.name == name,
                GraphNode.is_deleted == 0,
                GraphNode.is_active == 1,  # 只检查启用的节点
            )
        )
        existing_result = await self.db.execute(existing_stmt)
        existing_node = existing_result.scalar_one_or_none()
        if existing_node:
            raise ValueError(f"分类 '{name}' 在 '{inferred_label}' 下已存在")

        # 创建节点
        node_id = generate_id()
        properties = {
            "level": level,
            "sort_order": sort_order,
        }
        # category_type 不再存储在 properties 中，直接使用 label 字段
        if icon:
            properties["icon"] = icon
        if color:
            properties["color"] = color

        # 使用新的标签结构
        # 优先使用 labels 参数，兼容旧的 tags/brands/products
        final_labels: dict[str, list[str]] = {}
        if labels:
            # 直接使用新的 labels 格式
            final_labels = labels
        else:
            # 兼容旧格式
            if tags:
                final_labels["tag"] = tags
            if brands:
                final_labels["brand"] = brands
            if products:
                final_labels["product"] = products
        if final_labels:
            properties = set_labels(properties, final_labels)

        node = GraphNode(
            id=node_id,
            tenant_code=tenant_code,
            label=inferred_label,
            name=name,
            description=description,
            properties=properties,
            is_active=1,
            is_deleted=0,
        )
        self.db.add(node)

        # 如果有父节点，创建 INCLUDES 边
        if parent_id:
            edge = GraphEdge(
                id=generate_id(),
                tenant_code=tenant_code,
                source_node_id=parent_id,
                target_node_id=node_id,
                relation_type="INCLUDES",
                is_active=1,
                is_deleted=0,
            )
            self.db.add(edge)

        await self.db.commit()
        await self.db.refresh(node)

        logger.info(f"创建分类: {name}, id={node_id}, parent_id={parent_id}, level={level}")

        return {
            "id": str(node.id),
            "name": node.name,
            "label": node.label,
            "description": node.description,
            "category_type": category_type,
            "level": level,
            "sort_order": sort_order,
            "is_active": node.is_active,
            "tags": tags or [],
            "brands": brands or [],
            "products": products or [],
        }

    @invalidate_tree_cache(from_node=True)
    async def update_category(
        self,
        category_id: int,
        name: str | None = None,
        label: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        sort_order: int | None = None,
        is_active: int | None = None,
        labels: dict[str, list[str]] | None = None,
        tags: list[str] | None = None,
        brands: list[str] | None = None,
        products: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """更新分类"""
        node = await self.db.get(GraphNode, category_id)
        if not node or node.label == self.KEYWORD_LABEL:
            return None
        
        # 检查修改后是否会与已有节点冲突（同 tenant_code + label + name）
        new_label = label if label is not None else node.label
        new_name = name if name is not None else node.name
        
        if name is not None or label is not None:
            # 只有当 name 或 label 改变时才需要检查
            existing_stmt = select(GraphNode).where(
                and_(
                    GraphNode.tenant_code == node.tenant_code,
                    GraphNode.label == new_label,
                    GraphNode.name == new_name,
                    GraphNode.is_deleted == 0,
                    GraphNode.id != category_id,  # 排除自身
                )
            )
            existing_result = await self.db.execute(existing_stmt)
            existing_node = existing_result.scalar_one_or_none()
            if existing_node:
                raise ValueError(f"分类 '{new_name}' 在 '{new_label}' 下已存在，请使用其他名称")
        
        if label is not None:
            node.label = label

        if name is not None:
            node.name = name
        if description is not None:
            node.description = description
        if is_active is not None:
            node.is_active = is_active
            # 级联更新所有子节点的归档状态
            # 当归档/启用父节点时，所有子孙节点也跟着归档/启用
            await self._cascade_update_is_active(category_id, is_active, node.tenant_code)

        # 更新 properties
        # 重要：必须创建新字典，否则 SQLAlchemy 不会检测到 JSON 字段变化
        props = dict(node.properties) if node.properties else {}
        if icon is not None:
            props["icon"] = icon
        if color is not None:
            props["color"] = color
        if sort_order is not None:
            props["sort_order"] = sort_order

        # 使用新的标签结构更新标签
        # 优先使用 labels 参数，兼容旧的 tags/brands/products
        if labels is not None:
            # 直接使用新的 labels 格式
            current_labels = labels
        elif tags is not None or brands is not None or products is not None:
            # 兼容旧格式
            current_labels = get_labels(props)
            if tags is not None:
                current_labels["tag"] = tags
            if brands is not None:
                current_labels["brand"] = brands
            if products is not None:
                current_labels["product"] = products
        else:
            # 没有标签更新
            current_labels = None

        if current_labels is not None:
            # 更新到 properties
            props = set_labels(props, current_labels)

        # 赋值新字典对象，确保 SQLAlchemy 检测到变化
        node.properties = props
        # 显式标记 JSON 字段已修改（双保险）
        flag_modified(node, "properties")

        await self.db.commit()
        await self.db.refresh(node)

        # 获取更新后的标签
        labels = get_labels(props)

        return {
            "id": str(node.id),
            "name": node.name,
            "label": node.label,
            "description": node.description,
            "category_type": node.label,  # 直接使用 label 字段
            "level": props.get("level"),
            "sort_order": props.get("sort_order"),
            "is_active": node.is_active,
            # 兼容前端：继续返回 tags/brands/products
            "tags": labels.get("tag", []),
            "brands": labels.get("brand", []),
            "products": labels.get("product", []),
            "labels": labels,  # 新增：统一标签结构
            "tenant_code": node.tenant_code,  # 供装饰器清除缓存使用
        }

    async def _cascade_update_is_active(
        self,
        category_id: int,
        is_active: int,
        tenant_code: str,
    ) -> None:
        """
        级联更新所有子孙节点的归档状态

        使用递归 CTE 查询优化性能，避免加载所有边到内存

        Args:
            category_id: 父节点 ID
            is_active: 目标归档状态 (0=归档, 1=启用)
            tenant_code: 租户编码
        """
        from sqlalchemy import text

        # 使用递归 CTE 获取所有子孙节点 ID
        # 优势：数据库层面直接计算，利用索引，一次查询完成
        recursive_cte = text("""
            WITH RECURSIVE descendant_tree AS (
                -- 起始节点
                SELECT target_node_id
                FROM edges
                WHERE source_node_id = :category_id
                  AND tenant_code = :tenant_code
                  AND relation_type = 'INCLUDES'
                  AND is_deleted = 0

                UNION ALL

                -- 递归查询子孙节点
                SELECT e.target_node_id
                FROM edges e
                INNER JOIN descendant_tree dt ON e.source_node_id = dt.target_node_id
                WHERE e.tenant_code = :tenant_code
                  AND e.relation_type = 'INCLUDES'
                  AND e.is_deleted = 0
            )
            SELECT target_node_id FROM descendant_tree
        """)

        result = await self.db.execute(
            recursive_cte,
            {"category_id": category_id, "tenant_code": tenant_code}
        )
        descendant_ids = [row[0] for row in result.fetchall()]

        # 如果没有子节点，直接返回
        if not descendant_ids:
            return

        # 批量更新所有子孙节点的 is_active 状态
        update_stmt = (
            GraphNode.__table__.update()
            .where(GraphNode.id.in_(descendant_ids))
            .values(is_active=is_active)
        )
        await self.db.execute(update_stmt)

        logger.info(
            f"级联更新归档状态: parent_id={category_id}, "
            f"is_active={is_active}, affected_count={len(descendant_ids)}"
        )

    async def get_category_by_id(
        self,
        category_id: int,
    ) -> dict[str, Any] | None:
        """获取单个分类"""
        node = await self.db.get(GraphNode, category_id)
        if not node or node.is_deleted == 1 or node.label == self.KEYWORD_LABEL:
            return None
        
        # 查询父节点 ID（通过 INCLUDES 边）
        parent_id = None
        stmt = select(GraphEdge.source_node_id).where(
            and_(
                GraphEdge.target_node_id == category_id,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        ).limit(1)
        result = await self.db.execute(stmt)
        row = result.fetchone()
        if row:
            parent_id = str(row[0])
        
        props = node.properties or {}
        labels = get_labels(props)

        # 排序 corpus 字段（按模板顺序）
        corpus = node.corpus or []
        ordered_corpus = await self._order_corpus_fields(corpus, node.tenant_code)

        return {
            "id": str(node.id),
            "name": node.name,
            "label": node.label,
            "description": node.description,
            "category_type": node.label,  # 直接使用 label 字段
            "level": props.get("level"),
            "sort_order": props.get("sort_order"),
            "is_active": node.is_active,
            # 兼容前端：继续返回 tags/brands/products
            "tags": labels.get("tag", []),
            "brands": labels.get("brand", []),
            "products": labels.get("product", []),
            "labels": labels,  # 新增：统一标签结构
            "icon": props.get("icon"),
            "color": props.get("color"),
            "parent_id": parent_id,
            "corpus": ordered_corpus,  # 排序后的语料列表
        }

    async def get_root_label(
        self,
        node_id: int,
        tenant_code: str = "default",
    ) -> str | None:
        """
        获取节点所属的根分类 label（通过向上遍历到 level=1 的根节点）

        Args:
            node_id: 节点 ID
            tenant_code: 租户编码

        Returns:
            根节点的 label（如 人设/场景/卖点 等），如果找不到则返回 None
        """
        # 先检查当前节点
        node = await self.db.get(GraphNode, node_id)
        if not node or node.is_deleted == 1:
            return None

        props = node.properties or {}
        level = props.get("level", 1)

        # 如果当前就是根节点，直接返回其 label
        if level == 1:
            return node.label

        # 向上遍历找到根节点
        current_id = node_id
        visited: set[int] = set()
        max_depth = 10  # 防止无限循环

        while max_depth > 0:
            max_depth -= 1

            if current_id in visited:
                break
            visited.add(current_id)

            # 查找父节点（通过 INCLUDES 边）
            stmt = select(GraphEdge.source_node_id).where(
                and_(
                    GraphEdge.target_node_id == current_id,
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.tenant_code == tenant_code,
                    GraphEdge.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            row = result.fetchone()

            if not row:
                break

            parent_id = row[0]
            parent_node = await self.db.get(GraphNode, parent_id)
            if not parent_node:
                break

            parent_props = parent_node.properties or {}
            parent_level = parent_props.get("level", 1)

            # 找到根节点
            if parent_level == 1:
                return parent_node.label

            current_id = parent_id

        return None

    @invalidate_tree_cache(from_context=True)
    async def delete_category(self, category_id: int) -> bool:
        """
        删除分类（软删除，同时删除所有子节点和关联边）- 优化版

        注意：由于 uk_tenant_label_name 唯一键包含 is_deleted，
        在软删除前需要先物理删除已存在的软删除记录，避免冲突
        """
        node = await self.db.get(GraphNode, category_id)
        if not node or node.is_deleted == 1:
            return False

        # 一次性加载所有边（用于计算子孙节点）
        stmt = select(GraphEdge.source_node_id, GraphEdge.target_node_id).where(
            and_(
                GraphEdge.tenant_code == node.tenant_code,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        edges = result.fetchall()

        # 构建 parent -> children 映射
        parent_to_children: dict[int, list[int]] = {}
        for source_id, target_id in edges:
            if source_id not in parent_to_children:
                parent_to_children[source_id] = []
            parent_to_children[source_id].append(target_id)

        # BFS 获取所有子孙节点
        all_ids: set[int] = {category_id}
        queue = [category_id]
        while queue:
            current = queue.pop(0)
            children = parent_to_children.get(current, [])
            for child in children:
                if child not in all_ids:
                    all_ids.add(child)
                    queue.append(child)

        # 获取待删除节点的 (tenant_code, label, name) 组合
        stmt = select(GraphNode.tenant_code, GraphNode.label, GraphNode.name).where(
            GraphNode.id.in_(all_ids)
        )
        result = await self.db.execute(stmt)
        node_keys = result.fetchall()

        # 先物理删除已存在的软删除记录（避免唯一键冲突）
        for tenant_code, label, name in node_keys:
            delete_stmt = GraphNode.__table__.delete().where(
                and_(
                    GraphNode.tenant_code == tenant_code,
                    GraphNode.label == label,
                    GraphNode.name == name,
                    GraphNode.is_deleted == 1,
                )
            )
            await self.db.execute(delete_stmt)

        # 批量软删除所有节点
        stmt = (
            GraphNode.__table__.update()
            .where(GraphNode.id.in_(all_ids))
            .values(is_deleted=1)
        )
        await self.db.execute(stmt)

        # 批量软删除相关的边
        # 优化策略：先查询出将要被软删除的活跃边，检查是否有对应的已软删除边存在冲突，若有则物理删除旧的软删除边
        
        # 1. 查询所有涉及的活跃边
        active_edges_stmt = select(
            GraphEdge.tenant_code,
            GraphEdge.source_node_id,
            GraphEdge.target_node_id,
            GraphEdge.relation_type,
            GraphEdge.is_active,
        ).where(
            and_(
                GraphEdge.tenant_code == node.tenant_code,
                GraphEdge.is_deleted == 0,
                (
                    GraphEdge.source_node_id.in_(all_ids)
                    | GraphEdge.target_node_id.in_(all_ids)
                ),
            )
        )
        result = await self.db.execute(active_edges_stmt)
        active_edges = result.fetchall()
        
        if active_edges:
            edge_keys = [
                (r.tenant_code, r.source_node_id, r.target_node_id, r.relation_type, r.is_active)
                for r in active_edges
            ]
            
            # 分批处理以避免 SQL 过长，使用更小的批次和更安全的删除方式
            batch_size = 20  # 减小批次大小，避免 SQL 语句过长
            for i in range(0, len(edge_keys), batch_size):
                batch_keys = edge_keys[i:i+batch_size]
                
                # 使用显式构造 OR 条件，但批次更小，避免 SQL 语句过长
                or_conditions = []
                for key in batch_keys:
                    tenant_code, source_id, target_id, relation_type, is_active = key
                    or_conditions.append(
                        and_(
                            GraphEdge.tenant_code == tenant_code,
                            GraphEdge.source_node_id == source_id,
                            GraphEdge.target_node_id == target_id,
                            GraphEdge.relation_type == relation_type,
                            GraphEdge.is_active == is_active,
                        )
                    )
                
                # 删除冲突的软删除边
                if or_conditions:
                    delete_conflict_stmt = GraphEdge.__table__.delete().where(
                        and_(
                            GraphEdge.is_deleted == 1,
                            or_(*or_conditions)
                        )
                    )
                    await self.db.execute(delete_conflict_stmt)
                    # 每个批次后立即 flush，确保删除生效
                    await self.db.flush()

        # 3. 批量更新活跃边为软删除状态
        # 使用更安全的方式：先查询出所有需要更新的边 ID，然后逐个更新
        # 这样可以避免在更新时出现唯一键冲突
        update_edges_stmt = select(GraphEdge.id).where(
            and_(
                GraphEdge.tenant_code == node.tenant_code,
                GraphEdge.is_deleted == 0,
                (GraphEdge.source_node_id.in_(all_ids) | GraphEdge.target_node_id.in_(all_ids)),
            )
        )
        result = await self.db.execute(update_edges_stmt)
        edge_ids = [row[0] for row in result.fetchall()]
        
        if edge_ids:
            # 分批更新，每批 100 条
            batch_size = 100
            for i in range(0, len(edge_ids), batch_size):
                batch_ids = edge_ids[i:i+batch_size]
                stmt = (
                    GraphEdge.__table__.update()
                    .where(
                        and_(
                            GraphEdge.id.in_(batch_ids),
                            GraphEdge.is_deleted == 0,  # 双重检查，确保只更新活跃边
                        )
                    )
                    .values(is_deleted=1)
                )
                await self.db.execute(stmt)
                await self.db.flush()  # 每批后立即 flush

        await self.db.commit()

        logger.info(f"删除分类: id={category_id}, 共删除 {len(all_ids)} 个节点")

        # 设置需要清除缓存的租户
        set_cache_tenant(node.tenant_code)
        return True

    @invalidate_tree_cache(from_context=True)
    async def batch_delete_categories(self, category_ids: list[int]) -> dict[str, Any]:
        """
        批量删除分类（软删除，同时删除所有子节点和关联边）- 优化版

        优化策略：
        1. 一次性加载所有边
        2. 在内存中 BFS 计算子孙节点
        3. 批量 SQL UPDATE 删除

        Args:
            category_ids: 要删除的分类 ID 列表

        Returns:
            删除结果统计
        """
        if not category_ids:
            return {"deleted_count": 0, "total_nodes": 0}

        # 一次性加载所有边（用于计算子孙节点）
        stmt = select(GraphEdge.source_node_id, GraphEdge.target_node_id).where(
            and_(
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        edges = result.fetchall()

        # 构建 parent -> children 映射
        parent_to_children: dict[int, list[int]] = {}
        for source_id, target_id in edges:
            if source_id not in parent_to_children:
                parent_to_children[source_id] = []
            parent_to_children[source_id].append(target_id)

        # 一次性获取所有需要删除的节点
        all_node_ids: set[int] = set()
        deleted_count = 0

        # 批量检查节点是否存在
        stmt = select(GraphNode.id).where(
            and_(
                GraphNode.id.in_(category_ids),
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        valid_ids = {row[0] for row in result.fetchall()}

        for category_id in category_ids:
            if category_id not in valid_ids:
                continue

            # BFS 获取所有子孙节点
            queue = [category_id]
            while queue:
                current = queue.pop(0)
                if current not in all_node_ids:
                    all_node_ids.add(current)
                    children = parent_to_children.get(current, [])
                    queue.extend(children)
            deleted_count += 1

        if not all_node_ids:
            return {"deleted_count": 0, "total_nodes": 0}

        # 获取待删除节点的 (tenant_code, label, name) 组合
        stmt = select(GraphNode.tenant_code, GraphNode.label, GraphNode.name).where(
            GraphNode.id.in_(all_node_ids)
        )
        result = await self.db.execute(stmt)
        node_keys = result.fetchall()

        # 先物理删除已存在的软删除记录（避免唯一键冲突）
        # 分批处理避免单次删除过多
        batch_size = 100
        for i in range(0, len(node_keys), batch_size):
            batch = node_keys[i:i + batch_size]
            for tenant_code, label, name in batch:
                delete_stmt = GraphNode.__table__.delete().where(
                    and_(
                        GraphNode.tenant_code == tenant_code,
                        GraphNode.label == label,
                        GraphNode.name == name,
                        GraphNode.is_deleted == 1,
                    )
                )
                await self.db.execute(delete_stmt)

        # 批量软删除所有节点
        stmt = (
            GraphNode.__table__.update()
            .where(GraphNode.id.in_(all_node_ids))
            .values(is_deleted=1)
        )
        await self.db.execute(stmt)

        # 批量软删除相关的边
        # 优化策略：先查询出将要被软删除的活跃边，检查是否有对应的已软删除边存在冲突，若有则物理删除旧的软删除边
        
        # 1. 查询所有涉及的活跃边
        active_edges_stmt = select(
            GraphEdge.tenant_code,
            GraphEdge.source_node_id,
            GraphEdge.target_node_id,
            GraphEdge.relation_type,
            GraphEdge.is_active,
        ).where(
            and_(
                GraphEdge.is_deleted == 0,
                (
                    GraphEdge.source_node_id.in_(all_node_ids)
                    | GraphEdge.target_node_id.in_(all_node_ids)
                ),
            )
        )
        result = await self.db.execute(active_edges_stmt)
        active_edges = result.fetchall()
        
        if active_edges:
            edge_keys = [
                (r.tenant_code, r.source_node_id, r.target_node_id, r.relation_type, r.is_active)
                for r in active_edges
            ]
            
            # 分批处理以避免 SQL 过长，使用更小的批次和更安全的删除方式
            batch_size = 20  # 减小批次大小，避免 SQL 语句过长
            for i in range(0, len(edge_keys), batch_size):
                batch_keys = edge_keys[i:i+batch_size]
                
                # 使用显式构造 OR 条件，但批次更小，避免 SQL 语句过长
                or_conditions = []
                for key in batch_keys:
                    tenant_code, source_id, target_id, relation_type, is_active = key
                    or_conditions.append(
                        and_(
                            GraphEdge.tenant_code == tenant_code,
                            GraphEdge.source_node_id == source_id,
                            GraphEdge.target_node_id == target_id,
                            GraphEdge.relation_type == relation_type,
                            GraphEdge.is_active == is_active,
                        )
                    )
                
                # 删除冲突的软删除边
                if or_conditions:
                    delete_conflict_stmt = GraphEdge.__table__.delete().where(
                        and_(
                            GraphEdge.is_deleted == 1,
                            or_(*or_conditions)
                        )
                    )
                    await self.db.execute(delete_conflict_stmt)
                    # 每个批次后立即 flush，确保删除生效
                    await self.db.flush()

        # 3. 批量更新活跃边为软删除状态
        # 使用更安全的方式：先查询出所有需要更新的边 ID，然后分批更新
        update_edges_stmt = select(GraphEdge.id).where(
            and_(
                GraphEdge.is_deleted == 0,
                (GraphEdge.source_node_id.in_(all_node_ids) | GraphEdge.target_node_id.in_(all_node_ids)),
            )
        )
        result = await self.db.execute(update_edges_stmt)
        edge_ids = [row[0] for row in result.fetchall()]
        
        if edge_ids:
            # 分批更新，每批 100 条
            batch_size = 100
            for i in range(0, len(edge_ids), batch_size):
                batch_ids = edge_ids[i:i+batch_size]
                stmt = (
                    GraphEdge.__table__.update()
                    .where(
                        and_(
                            GraphEdge.id.in_(batch_ids),
                            GraphEdge.is_deleted == 0,  # 双重检查，确保只更新活跃边
                        )
                    )
                    .values(is_deleted=1)
                )
                await self.db.execute(stmt)
                await self.db.flush()  # 每批后立即 flush

        await self.db.commit()

        logger.info(f"批量删除分类: ids={category_ids}, 共删除 {len(all_node_ids)} 个节点")

        # 设置需要清除缓存的租户（使用 default 租户，因为大多数节点在 default 下）
        set_cache_tenant("default")
        return {
            "deleted_count": deleted_count,
            "total_nodes": len(all_node_ids),
        }

    @invalidate_tree_cache()
    async def copy_node(
        self,
        source_node_id: int,
        target_parent_id: int | None,
        tenant_code: str = "default",
    ) -> dict[str, Any]:
        """
        复制节点（含子节点和语料）到目标位置

        Args:
            source_node_id: 源节点 ID
            target_parent_id: 目标父节点 ID（None 表示复制为顶层节点）
            tenant_code: 租户编码

        Returns:
            复制结果统计
        """
        source_node = await self.db.get(GraphNode, source_node_id)
        if not source_node or source_node.is_deleted == 1:
            raise ValueError("源节点不存在")

        # 一次性加载所有边（用于计算子孙节点）
        stmt = select(GraphEdge.source_node_id, GraphEdge.target_node_id).where(
            and_(
                GraphEdge.tenant_code == tenant_code,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        edges = result.fetchall()

        # 构建 parent -> children 映射
        parent_to_children: dict[int, list[int]] = {}
        for src_id, tgt_id in edges:
            if src_id not in parent_to_children:
                parent_to_children[src_id] = []
            parent_to_children[src_id].append(tgt_id)

        # BFS 收集所有需要复制的节点 ID
        node_ids_to_copy: list[int] = []
        queue = [source_node_id]
        while queue:
            current = queue.pop(0)
            node_ids_to_copy.append(current)
            children = parent_to_children.get(current, [])
            queue.extend(children)

        # 加载所有需要复制的节点
        stmt = select(GraphNode).where(
            and_(
                GraphNode.id.in_(node_ids_to_copy),
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        nodes_map = {n.id: n for n in result.scalars().all()}

        # 创建 ID 映射：旧 ID -> 新 ID
        id_mapping: dict[int, int] = {}
        new_nodes: list[GraphNode] = []
        new_edges: list[GraphEdge] = []

        # 检查已存在的 (label, name) 组合
        existing_names_stmt = select(GraphNode.label, GraphNode.name).where(
            and_(
                GraphNode.tenant_code == tenant_code,
                GraphNode.is_deleted == 0,
            )
        )
        existing_result = await self.db.execute(existing_names_stmt)
        # 唯一性检查：(label, name)
        existing_names: set[tuple[str, str]] = {
            (r.label, r.name) for r in existing_result.fetchall()
        }

        # 按 BFS 顺序复制节点
        for old_id in node_ids_to_copy:
            old_node = nodes_map.get(old_id)
            if not old_node:
                continue

            new_id = generate_id()
            id_mapping[old_id] = new_id

            new_properties = old_node.properties.copy() if old_node.properties else {}

            # 生成不冲突的名称
            base_name = old_node.name
            new_name = base_name + "_副本" if old_id == source_node_id else base_name

            # 如果名称冲突（相同 label + name），添加数字后缀
            suffix = 1
            while (old_node.label, new_name) in existing_names:
                if old_id == source_node_id:
                    new_name = f"{base_name}_副本{suffix}"
                else:
                    new_name = f"{base_name}_{suffix}"
                suffix += 1

            # 将新名称加入已存在集合，避免同批复制的节点之间冲突
            existing_names.add((old_node.label, new_name))

            # 创建新节点
            new_node = GraphNode(
                id=new_id,
                tenant_code=tenant_code,
                label=old_node.label,
                name=new_name,
                description=old_node.description,
                properties=new_properties,
                corpus=old_node.corpus.copy() if old_node.corpus else None,
                is_active=old_node.is_active,
                is_deleted=0,
            )
            new_nodes.append(new_node)

        # 创建边
        for old_id in node_ids_to_copy:
            new_id = id_mapping.get(old_id)
            if not new_id:
                continue

            if old_id == source_node_id:
                # 源节点连接到目标父节点
                if target_parent_id is not None:
                    new_edge = GraphEdge(
                        id=generate_id(),
                        tenant_code=tenant_code,
                        source_node_id=target_parent_id,
                        target_node_id=new_id,
                        relation_type="INCLUDES",
                        is_active=1,
                        is_deleted=0,
                    )
                    new_edges.append(new_edge)
            else:
                # 子节点保持原有的父子关系
                # 找到旧的父节点
                for parent_id, children in parent_to_children.items():
                    if old_id in children:
                        new_parent_id = id_mapping.get(parent_id)
                        if new_parent_id:
                            new_edge = GraphEdge(
                                id=generate_id(),
                                tenant_code=tenant_code,
                                source_node_id=new_parent_id,
                                target_node_id=new_id,
                                relation_type="INCLUDES",
                                is_active=1,
                                is_deleted=0,
                            )
                            new_edges.append(new_edge)
                        break

        # 批量插入
        if new_nodes:
            self.db.add_all(new_nodes)
        if new_edges:
            self.db.add_all(new_edges)

        await self.db.commit()

        logger.info(
            f"复制节点完成: source={source_node_id}, target_parent={target_parent_id}, "
            f"nodes={len(new_nodes)}, edges={len(new_edges)}"
        )

        return {
            "copied_nodes": len(new_nodes),
            "new_root_id": id_mapping.get(source_node_id),
        }

    @invalidate_tree_cache(tenant_codes_kwarg="affected_tenants")
    async def copy_subtree_to_global(
        self,
        source_node_id: int,
        source_tenant_code: str,
        target_parent_id: int | None = None,
    ) -> dict[str, Any] | None:
        """
        复制节点（含子节点和语料）到全局租户

        Args:
            source_node_id: 源节点 ID
            source_tenant_code: 源租户编码
            target_parent_id: 目标父节点 ID（全局租户下的分类 ID）

        Returns:
            复制结果统计
        """
        source_node = await self.db.get(GraphNode, source_node_id)
        if not source_node or source_node.is_deleted == 1:
            return None

        global_tenant = settings.GLOBAL_TENANT_CODE

        # 一次性加载源租户的所有边（用于计算子孙节点）
        stmt = select(GraphEdge.source_node_id, GraphEdge.target_node_id).where(
            and_(
                GraphEdge.tenant_code == source_tenant_code,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        edges = result.fetchall()

        # 构建 parent -> children 映射
        parent_to_children: dict[int, list[int]] = {}
        for src_id, tgt_id in edges:
            if src_id not in parent_to_children:
                parent_to_children[src_id] = []
            parent_to_children[src_id].append(tgt_id)

        # BFS 收集所有需要复制的节点 ID
        node_ids_to_copy: list[int] = []
        queue = [source_node_id]
        while queue:
            current = queue.pop(0)
            node_ids_to_copy.append(current)
            children = parent_to_children.get(current, [])
            queue.extend(children)

        # 加载所有需要复制的节点
        stmt = select(GraphNode).where(
            and_(
                GraphNode.id.in_(node_ids_to_copy),
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        nodes_map = {n.id: n for n in result.scalars().all()}

        # 创建 ID 映射：旧 ID -> 新 ID
        id_mapping: dict[int, int] = {}
        new_nodes: list[GraphNode] = []
        new_edges: list[GraphEdge] = []

        # 按 BFS 顺序复制节点
        for old_id in node_ids_to_copy:
            old_node = nodes_map.get(old_id)
            if not old_node:
                continue

            new_id = generate_id()
            id_mapping[old_id] = new_id

            # 复制 properties 并记录来源
            new_props = old_node.properties.copy() if old_node.properties else {}
            # 清空品牌和产品绑定（升级为全局语料）- 使用新标签格式
            new_props = set_labels(new_props, {"brand": [], "product": []})
            # 记录来源
            new_props["promoted_from"] = {
                "tenant_code": source_tenant_code,
                "original_id": old_id,
            }

            # 创建新节点（使用全局租户编码）
            new_node = GraphNode(
                id=new_id,
                tenant_code=global_tenant,
                label=old_node.label,
                name=old_node.name,
                description=old_node.description,
                properties=new_props,
                corpus=old_node.corpus.copy() if old_node.corpus else None,
                is_active=old_node.is_active,
                is_deleted=0,
            )
            new_nodes.append(new_node)

        # 创建边
        for old_id in node_ids_to_copy:
            new_id = id_mapping.get(old_id)
            if not new_id:
                continue

            if old_id == source_node_id:
                # 源节点连接到目标父节点
                if target_parent_id is not None:
                    new_edge = GraphEdge(
                        id=generate_id(),
                        tenant_code=global_tenant,
                        source_node_id=target_parent_id,
                        target_node_id=new_id,
                        relation_type="INCLUDES",
                        is_active=1,
                        is_deleted=0,
                    )
                    new_edges.append(new_edge)
            else:
                # 子节点保持原有的父子关系
                for parent_id, children in parent_to_children.items():
                    if old_id in children:
                        new_parent_id = id_mapping.get(parent_id)
                        if new_parent_id:
                            new_edge = GraphEdge(
                                id=generate_id(),
                                tenant_code=global_tenant,
                                source_node_id=new_parent_id,
                                target_node_id=new_id,
                                relation_type="INCLUDES",
                                is_active=1,
                                is_deleted=0,
                            )
                            new_edges.append(new_edge)
                        break

        # 批量插入
        if new_nodes:
            self.db.add_all(new_nodes)
        if new_edges:
            self.db.add_all(new_edges)

        await self.db.commit()

        logger.info(
            f"复制到全局租户完成: source={source_node_id}, source_tenant={source_tenant_code}, "
            f"nodes={len(new_nodes)}, edges={len(new_edges)}"
        )

        return {
            "copied_nodes": len(new_nodes),
            "new_root_id": str(id_mapping.get(source_node_id)),
            "target_tenant": global_tenant,
            "affected_tenants": [source_tenant_code, global_tenant],  # 供装饰器清除缓存使用
        }

    @invalidate_tree_cache(from_context=True)
    async def move_node(
        self,
        node_id: int,
        target_parent_id: int | None,
        drop_node_id: int | None = None,
        drop_position: int = 0,
    ) -> bool:
        """
        移动节点到新的父节点下

        Args:
            node_id: 要移动的节点 ID
            target_parent_id: 目标父节点 ID（None 表示移动为顶层节点）
            drop_node_id: 放置的目标节点 ID（用于计算相对位置）
            drop_position: 相对于目标节点的位置: -1=上方, 0=内部, 1=下方

        Returns:
            是否成功
        """
        node = await self.db.get(GraphNode, node_id)
        if not node or node.is_deleted == 1:
            return False

        # 先获取旧的父子边，判断节点是否原本在顶层
        old_edge_stmt = select(GraphEdge).where(
            and_(
                GraphEdge.target_node_id == node_id,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )
        old_edge_result = await self.db.execute(old_edge_stmt)
        old_edges = old_edge_result.scalars().all()
        was_root = len(old_edges) == 0

        # 业务约束：同一个 label 只能有一个顶级节点（root）
        # 只有当真正"从非顶层移动到顶层"时才检查
        # 注意：只检查启用状态的节点（is_active=1），归档节点不影响
        if target_parent_id is None and not was_root:
            parent_edge_exists = exists().where(
                and_(
                    GraphEdge.tenant_code == node.tenant_code,
                    GraphEdge.target_node_id == GraphNode.id,
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.is_deleted == 0,
                )
            )
            root_stmt = select(GraphNode.id, GraphNode.name).where(
                and_(
                    GraphNode.tenant_code == node.tenant_code,
                    GraphNode.label == node.label,
                    GraphNode.is_deleted == 0,
                    GraphNode.is_active == 1,  # 只检查启用状态的顶级节点
                    GraphNode.id != node_id,
                    ~parent_edge_exists,
                )
            )
            root_result = await self.db.execute(root_stmt)
            existing_root = root_result.first()
            if existing_root:
                raise ValueError(
                    f"禁止移动到顶层：label「{node.label}」已存在顶级节点「{existing_root[1]}」，一个 label 只能有一个顶级节点"
                )

        # 业务约束：禁止跨 label 拖动
        # 检查目标父节点的 label 是否与移动节点的 label 一致
        if target_parent_id is not None:
            target_parent = await self.db.get(GraphNode, target_parent_id)
            if target_parent and target_parent.label != node.label:
                raise ValueError(
                    f"禁止跨 label 拖动：节点 label 为「{node.label}」，目标父节点 label 为「{target_parent.label}」"
                )

        # 删除旧的父子边（复用之前查询的结果）
        for edge in old_edges:
            edge.is_deleted = 1

        # 如果有新的父节点，创建新边
        if target_parent_id is not None:
            new_edge = GraphEdge(
                id=generate_id(),
                tenant_code=node.tenant_code,
                source_node_id=target_parent_id,
                target_node_id=node_id,
                relation_type="INCLUDES",
                is_active=1,
                is_deleted=0,
            )
            self.db.add(new_edge)

        # 更新 sort_order（使用有间隔整数方案）
        # 根据 drop_node 的 sort_order 和 drop_position 计算新的 sort_order
        # 间隔设为 100，预留足够空间
        SORT_GAP = 100
        new_sort_order = 0  # 默认值

        if drop_node_id is not None:
            drop_node = await self.db.get(GraphNode, drop_node_id)
            if drop_node and drop_node.is_deleted == 0:
                drop_props = drop_node.properties or {}
                drop_sort_order = drop_props.get("sort_order", 0)

                if drop_position == -1:
                    # 拖到上方
                    new_sort_order = drop_sort_order - SORT_GAP
                elif drop_position == 0:
                    # 拖到内部（两个节点中间）
                    new_sort_order = drop_sort_order + SORT_GAP // 2
                elif drop_position == 1:
                    # 拖到下方
                    new_sort_order = drop_sort_order + SORT_GAP

        props = node.properties or {}
        props["sort_order"] = new_sort_order
        node.properties = props
        flag_modified(node, "properties")

        await self.db.commit()

        logger.info(f"移动节点: id={node_id}, target_parent={target_parent_id}, new_sort_order={new_sort_order}")

        # 设置需要清除缓存的租户
        set_cache_tenant(node.tenant_code)
        return True

    @invalidate_tree_cache(from_node=True)
    async def update_node_corpus(
        self,
        node_id: int,
        corpus: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        更新节点的语料列表

        Args:
            node_id: 节点 ID
            corpus: 语料列表，格式: [{"text": "语料内容", "weight": 1.0}, ...]

        Returns:
            更新后的节点信息
        """
        node = await self.db.get(GraphNode, node_id)
        if not node or node.is_deleted == 1:
            return None

        node.corpus = corpus
        flag_modified(node, "corpus")
        await self.db.commit()
        await self.db.refresh(node)

        logger.info(f"更新节点语料: id={node_id}, corpus_count={len(corpus)}")

        return {
            "id": str(node.id),
            "name": node.name,
            "label": node.label,
            "description": node.description,
            "corpus": node.corpus,
            "tenant_code": node.tenant_code,  # 供装饰器清除缓存使用
        }

    @invalidate_tree_cache(from_node=True)
    async def add_corpus_item(
        self,
        node_id: int,
        text: str,
        weight: float = 1.0,
    ) -> dict[str, Any] | None:
        """
        为节点添加一条语料

        Args:
            node_id: 节点 ID
            text: 语料内容
            weight: 权重

        Returns:
            更新后的节点信息
        """
        node = await self.db.get(GraphNode, node_id)
        if not node or node.is_deleted == 1:
            return None

        # 创建新列表避免原地修改导致 SQLAlchemy 不检测变化
        current_corpus = list(node.corpus or [])
        current_corpus.append({"text": text, "weight": weight})
        node.corpus = current_corpus
        flag_modified(node, "corpus")

        await self.db.commit()
        await self.db.refresh(node)

        return {
            "id": str(node.id),
            "name": node.name,
            "corpus": node.corpus,
            "tenant_code": node.tenant_code,  # 供装饰器清除缓存使用
        }

    @invalidate_tree_cache(from_node=True)
    async def add_corpus_item_v2(
        self,
        node_id: int,
        corpus_item: dict[str, Any] | str,
    ) -> dict[str, Any] | None:
        """
        为节点添加一条语料（支持新旧两种格式）

        Args:
            node_id: 节点 ID
            corpus_item: 语料项，可以是:
                - 新格式（结构化）: {"template_code": "...", "fields": {...}}
                - 纯文本模式: 字符串，直接存储在数组中

        Returns:
            更新后的节点信息
        """
        node = await self.db.get(GraphNode, node_id)
        if not node or node.is_deleted == 1:
            return None

        # 创建新列表避免原地修改导致 SQLAlchemy 不检测变化
        current_corpus = list(node.corpus or [])
        current_corpus.append(corpus_item)
        node.corpus = current_corpus
        # 显式标记 JSON 字段已修改
        flag_modified(node, "corpus")

        await self.db.commit()
        await self.db.refresh(node)

        # 返回前重新排序 corpus.fields（按模板定义的顺序）
        ordered_corpus = await self._order_corpus_fields(node.corpus or [], node.tenant_code)

        return {
            "id": str(node.id),
            "name": node.name,
            "corpus": ordered_corpus,
            "tenant_code": node.tenant_code,  # 供装饰器清除缓存使用
        }

    @invalidate_tree_cache(from_node=True)
    async def update_corpus_item_v2(
        self,
        node_id: int,
        index: int,
        corpus_item: dict[str, Any] | str,
    ) -> dict[str, Any] | None:
        """
        更新节点的某条语料（支持新旧两种格式）

        Args:
            node_id: 节点 ID
            index: 语料索引（如果等于数组长度，则自动添加）
            corpus_item: 新的语料项，可以是:
                - 新格式（结构化）: {"template_code": "...", "fields": {...}}
                - 纯文本模式: 字符串，直接存储在数组中

        Returns:
            更新后的节点信息
        """
        node = await self.db.get(GraphNode, node_id)
        if not node or node.is_deleted == 1:
            return None

        # 创建新列表避免原地修改
        current_corpus = list(node.corpus or [])
        
        # 如果索引超出范围，返回 None
        if index < 0:
            return None
        
        # 如果索引等于数组长度，自动添加（兼容前端可能传递的边界情况）
        if index == len(current_corpus):
            current_corpus.append(corpus_item)
        elif index > len(current_corpus):
            # 索引超出范围太多，返回 None
            return None
        else:
            # 正常更新：替换指定索引的语料
            current_corpus[index] = corpus_item

        node.corpus = current_corpus
        # 显式标记 JSON 字段已修改
        flag_modified(node, "corpus")
        await self.db.commit()
        await self.db.refresh(node)

        # 返回前重新排序 corpus.fields（按模板定义的顺序）
        ordered_corpus = await self._order_corpus_fields(node.corpus or [], node.tenant_code)

        return {
            "id": str(node.id),
            "name": node.name,
            "corpus": ordered_corpus,
            "tenant_code": node.tenant_code,  # 供装饰器清除缓存使用
        }

    @invalidate_tree_cache(from_node=True)
    async def update_corpus_item(
        self,
        node_id: int,
        index: int,
        text: str,
        weight: float | None = None,
    ) -> dict[str, Any] | None:
        """
        更新节点的某条语料（旧版，保留兼容）

        Args:
            node_id: 节点 ID
            index: 语料索引
            text: 新的语料内容
            weight: 新的权重（可选）

        Returns:
            更新后的节点信息
        """
        node = await self.db.get(GraphNode, node_id)
        if not node or node.is_deleted == 1:
            return None

        # 创建新列表避免原地修改
        current_corpus = list(node.corpus or [])
        if index < 0 or index >= len(current_corpus):
            return None

        # 复制字典再修改
        current_corpus[index] = dict(current_corpus[index])
        current_corpus[index]["text"] = text
        if weight is not None:
            current_corpus[index]["weight"] = weight

        node.corpus = current_corpus
        flag_modified(node, "corpus")
        await self.db.commit()
        await self.db.refresh(node)

        return {
            "id": str(node.id),
            "name": node.name,
            "corpus": node.corpus,
            "tenant_code": node.tenant_code,  # 供装饰器清除缓存使用
        }

    @invalidate_tree_cache(from_node=True)
    async def delete_corpus_item(
        self,
        node_id: int,
        index: int,
    ) -> dict[str, Any] | None:
        """
        删除节点的某条语料

        Args:
            node_id: 节点 ID
            index: 语料索引

        Returns:
            更新后的节点信息
        """
        node = await self.db.get(GraphNode, node_id)
        if not node or node.is_deleted == 1:
            return None

        # 创建新列表避免原地修改
        current_corpus = list(node.corpus or [])
        if index < 0 or index >= len(current_corpus):
            return None

        current_corpus.pop(index)
        node.corpus = current_corpus
        flag_modified(node, "corpus")

        await self.db.commit()
        await self.db.refresh(node)

        return {
            "id": str(node.id),
            "name": node.name,
            "corpus": node.corpus,
            "tenant_code": node.tenant_code,  # 供装饰器清除缓存使用
        }

    @invalidate_tree_cache()
    async def batch_import_v2(
        self,
        parent_node_id: int | None,
        items: list[dict[str, Any]],
        tenant_code: str = "default",
    ) -> dict[str, Any]:
        """
        批量导入分类和语料（V2版本 - 性能优化版）

        优化策略：
        1. 一次性预加载所有节点和边
        2. 在内存中构建索引
        3. 批量创建节点和边
        4. 批量更新语料
        5. 只在最后做一次 commit

        Args:
            parent_node_id: 父节点 ID（None 表示导入为顶层节点）
            items: 数据列表，格式:
                [
                    {"path": ["层级1", "层级2", ...], "corpus": "语料内容"},
                    ...
                ]
            tenant_code: 租户编码

        Returns:
            导入结果统计
        """
        created_nodes = 0
        updated_nodes = 0
        total_corpus = 0
        errors: list[str] = []

        # ========== 阶段1：预加载所有现有数据 ==========
        # 一次性获取该租户下的所有节点
        stmt = select(GraphNode).where(
            and_(
                GraphNode.tenant_code == tenant_code,
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        all_nodes = {node.id: node for node in result.scalars().all()}

        # 一次性获取该租户下的所有边
        stmt = select(GraphEdge).where(
            and_(
                GraphEdge.tenant_code == tenant_code,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        all_edges = result.scalars().all()

        # 构建索引：parent_id -> [(child_id, child_name)]
        parent_to_children: dict[int | None, list[tuple[int, str]]] = {None: []}
        child_ids = set()
        for edge in all_edges:
            child_ids.add(edge.target_node_id)
            if edge.source_node_id not in parent_to_children:
                parent_to_children[edge.source_node_id] = []
            child_node = all_nodes.get(edge.target_node_id)
            if child_node:
                parent_to_children[edge.source_node_id].append(
                    (edge.target_node_id, child_node.name)
                )

        # 顶级节点（没有父节点的）
        for node_id, node in all_nodes.items():
            if node_id not in child_ids:
                parent_to_children[None].append((node_id, node.name))

        # 构建快速查找索引：(parent_id, name) -> node_id
        name_lookup: dict[tuple[int | None, str], int] = {}
        for parent_id, children in parent_to_children.items():
            for child_id, child_name in children:
                name_lookup[(parent_id, child_name)] = child_id

        # 获取父节点信息
        parent_label = "分类"
        parent_level = 0
        if parent_node_id and parent_node_id in all_nodes:
            parent = all_nodes[parent_node_id]
            parent_props = parent.properties or {}
            parent_label = parent.label or "分类"
            parent_level = parent_props.get("level", 1)

        # ========== 阶段2：处理所有导入数据 ==========
        # 收集新节点和新边
        new_nodes: list[GraphNode] = []
        new_edges: list[GraphEdge] = []
        # 需要更新语料的节点：node_id -> [corpus_texts]
        corpus_updates: dict[int, list[str]] = {}
        # 路径缓存：category_path -> node_id
        path_cache: dict[str, int] = {}
        # 记录每个父节点的子节点数量（用于计算 sort_order）
        child_counts: dict[int | None, int] = {}
        for parent_id, children in parent_to_children.items():
            child_counts[parent_id] = len(children)

        for item in items:
            path = item.get("path", [])
            corpus_text = item.get("corpus", "").strip()

            if not path:
                continue

            try:
                current_parent_id = parent_node_id
                current_level = parent_level
                current_label = parent_label
                category_path = ""
                leaf_node_id: int | None = None

                for name in path:
                    name = name.strip()
                    if not name:
                        continue

                    category_path = f"{category_path}/{name}"

                    # 检查路径缓存
                    if category_path in path_cache:
                        current_parent_id = path_cache[category_path]
                        leaf_node_id = current_parent_id
                        # 更新当前层级和标签
                        if current_parent_id in all_nodes:
                            node = all_nodes[current_parent_id]
                            current_level = (node.properties or {}).get("level", 1)
                            current_label = node.label or "分类"
                        continue

                    # 检查是否已存在
                    lookup_key = (current_parent_id, name)
                    if lookup_key in name_lookup:
                        existing_id = name_lookup[lookup_key]
                        current_parent_id = existing_id
                        leaf_node_id = existing_id
                        path_cache[category_path] = existing_id
                        # 更新当前层级和标签
                        if existing_id in all_nodes:
                            node = all_nodes[existing_id]
                            current_level = (node.properties or {}).get("level", 1)
                            current_label = node.label or "分类"
                        continue

                    # 需要创建新节点
                    node_id = generate_id()
                    new_level = current_level + 1
                    new_label = current_label  # 继承父节点标签

                    # 计算 sort_order
                    sort_order = child_counts.get(current_parent_id, 0) + 1
                    child_counts[current_parent_id] = sort_order

                    properties = {
                        "level": new_level,
                        "sort_order": sort_order,
                    }
                    # 只有根节点（level=1）才存储 category_type
                    # 子节点不再冗余存储

                    new_node = GraphNode(
                        id=node_id,
                        tenant_code=tenant_code,
                        label=new_label,
                        name=name,
                        description=None,
                        properties=properties,
                        is_active=1,
                        is_deleted=0,
                    )
                    new_nodes.append(new_node)
                    all_nodes[node_id] = new_node  # 加入索引

                    # 创建边
                    if current_parent_id is not None:
                        new_edge = GraphEdge(
                            id=generate_id(),
                            tenant_code=tenant_code,
                            source_node_id=current_parent_id,
                            target_node_id=node_id,
                            relation_type="INCLUDES",
                            is_active=1,
                            is_deleted=0,
                        )
                        new_edges.append(new_edge)

                    # 更新索引
                    name_lookup[(current_parent_id, name)] = node_id
                    if current_parent_id not in parent_to_children:
                        parent_to_children[current_parent_id] = []
                    parent_to_children[current_parent_id].append((node_id, name))

                    # 更新状态
                    path_cache[category_path] = node_id
                    current_parent_id = node_id
                    leaf_node_id = node_id
                    current_level = new_level
                    created_nodes += 1

                # 收集语料更新
                if leaf_node_id and corpus_text:
                    if leaf_node_id not in corpus_updates:
                        corpus_updates[leaf_node_id] = []
                    corpus_updates[leaf_node_id].append(corpus_text)
                    total_corpus += 1

            except Exception as e:
                logger.error(f"处理失败: {' > '.join(path)}, 错误: {e}")
                errors.append(f"处理 {' > '.join(path)} 失败: {e!s}")

        # ========== 阶段3：批量写入数据库 ==========
        # 批量添加新节点
        if new_nodes:
            self.db.add_all(new_nodes)
            logger.info(f"批量添加 {len(new_nodes)} 个新节点")

        # 批量添加新边
        if new_edges:
            self.db.add_all(new_edges)
            logger.info(f"批量添加 {len(new_edges)} 条新边")

        # 批量更新语料
        for node_id, corpus_texts in corpus_updates.items():
            node = all_nodes.get(node_id)
            if node:
                current_corpus = node.corpus or []
                existing_texts = {c.get("text") for c in current_corpus}
                new_corpus_items = [
                    {"text": text, "weight": 1.0}
                    for text in corpus_texts
                    if text not in existing_texts
                ]
                if new_corpus_items:
                    node.corpus = current_corpus + new_corpus_items
                    updated_nodes += 1

        # 一次性提交
        await self.db.commit()

        logger.info(
            f"批量导入V2完成: tenant={tenant_code}, parent={parent_node_id}, "
            f"created={created_nodes}, updated={updated_nodes}, corpus={total_corpus}"
        )

        return {
            "created_nodes": created_nodes,
            "updated_nodes": updated_nodes,
            "total_corpus": total_corpus,
            "errors": errors,
        }

    async def _find_root_node_by_name(
        self,
        name: str,
        tenant_code: str,
    ) -> int | None:
        """查找顶层节点（没有父节点的节点）"""
        # 获取所有有父节点的节点 ID
        stmt = select(GraphEdge.target_node_id).where(
            and_(
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.tenant_code == tenant_code,
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        child_ids = {row[0] for row in result.fetchall()}

        # 查找名称匹配且不是子节点的节点
        stmt = select(GraphNode).where(
            and_(
                GraphNode.tenant_code == tenant_code,
                GraphNode.name == name,
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        all_nodes = result.scalars().all()

        for node in all_nodes:
            if node.id not in child_ids:
                return node.id

        return None

    async def batch_import_categories(
        self,
        root_category_id: int,
        items: list[dict[str, Any]],
        tenant_code: str = "default",
    ) -> dict[str, Any]:
        """
        批量导入分类和关键词

        Args:
            root_category_id: 根分类 ID（如人设分类 ID）
            items: 数据列表，格式:
                [
                    {"categories": ["分类1", "分类2"], "keyword": "关键词", "corpus": "语料"},
                    ...
                ]
            tenant_code: 租户编码

        Returns:
            导入结果统计
        """
        # 验证根分类存在
        root_node = await self.db.get(GraphNode, root_category_id)
        if not root_node:
            raise ValueError(f"根分类不存在: {root_category_id}")

        # 使用根节点的 label 作为 category_type
        category_type = root_node.label or "unknown"

        created_categories = 0
        created_keywords = 0
        failed_count = 0
        errors: list[str] = []

        # 缓存已创建的分类：path -> category_id
        category_cache: dict[str, int] = {}

        # 初始化关键词服务
        keyword_service = KeywordService(self.db)

        for item in items:
            categories = item.get("categories", [])
            keyword_name = item.get("keyword", "").strip()
            corpus = item.get("corpus", "").strip()

            if not categories or not keyword_name:
                continue

            try:
                # 1. 确保分类层级存在
                current_parent_id = root_category_id
                category_path = ""

                for cat_name in categories:
                    cat_name = cat_name.strip()
                    if not cat_name:
                        continue

                    category_path = f"{category_path}/{cat_name}"

                    # 检查缓存
                    if category_path in category_cache:
                        current_parent_id = category_cache[category_path]
                        continue

                    # 查找或创建分类
                    existing = await self._find_child_by_name(
                        current_parent_id, cat_name, tenant_code
                    )
                    if existing:
                        current_parent_id = existing
                        category_cache[category_path] = existing
                    else:
                        # 创建新分类
                        result = await self.create_category(
                            name=cat_name,
                            parent_id=current_parent_id,
                            category_type=category_type,
                            tenant_code=tenant_code,
                        )
                        current_parent_id = int(result["id"])
                        category_cache[category_path] = current_parent_id
                        created_categories += 1
                        logger.info(f"创建分类: {category_path}")

                # 2. 在最终分类下创建关键词
                await keyword_service.create_keyword(
                    name=keyword_name,
                    category_id=current_parent_id,
                    description=corpus,
                    tenant_code=tenant_code,
                )
                created_keywords += 1
                logger.info(f"  创建关键词: {keyword_name}")

            except Exception as e:
                logger.error(f"导入失败: {categories} -> {keyword_name}, 错误: {e}")
                errors.append(f"'{keyword_name}' 失败: {e}")
                failed_count += 1

        return {
            "created_categories": created_categories,
            "created_keywords": created_keywords,
            "failed_count": failed_count,
            "errors": errors[:10],
        }

    async def _find_child_by_name(
        self,
        parent_id: int,
        name: str,
        tenant_code: str,
    ) -> int | None:
        """查找父分类下指定名称的子分类"""
        # 查找 INCLUDES 边
        stmt = select(GraphEdge).where(
            and_(
                GraphEdge.source_node_id == parent_id,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.tenant_code == tenant_code,
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        edges = result.scalars().all()

        for edge in edges:
            child_node = await self.db.get(GraphNode, edge.target_node_id)
            if child_node and child_node.name == name and child_node.is_deleted == 0:
                return child_node.id

        return None

    async def _find_node_by_name_and_label(
        self,
        name: str,
        label: str,
        tenant_code: str,
        dimension_type: str | None = None,
    ) -> int | None:
        """
        查找指定名称和标签的节点（用于去重检查）
        
        会同时检查：
        1. name + label 匹配
        2. name + dimension_type 匹配（兼容不同的 label 值）
        """
        # 先按 name + label 查找
        stmt = select(GraphNode).where(
            and_(
                GraphNode.name == name,
                GraphNode.label == label,
                GraphNode.tenant_code == tenant_code,
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        node = result.scalars().first()
        if node:
            return node.id
        
        # 如果没找到且提供了 dimension_type，尝试按 dimension_type 查找
        if dimension_type and dimension_type != label:
            stmt = select(GraphNode).where(
                and_(
                    GraphNode.name == name,
                    GraphNode.label == dimension_type,
                    GraphNode.tenant_code == tenant_code,
                    GraphNode.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            node = result.scalars().first()
            if node:
                return node.id
        
        # 最后尝试只按 name + tenant_code 查找，检查 label
        if dimension_type:
            stmt = select(GraphNode).where(
                and_(
                    GraphNode.name == name,
                    GraphNode.tenant_code == tenant_code,
                    GraphNode.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            nodes = result.scalars().all()
            for n in nodes:
                # 使用 label 字段代替 properties.category_type
                if n.label == dimension_type:
                    return n.id
        
        return None

    @invalidate_tree_cache()
    async def batch_import_structured(
        self,
        parent_node_id: int | None,
        dimension_type: str,
        items: list[dict[str, Any]],
        conflict_strategy: str,
        tenant_code: str = "default",
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        结构化批量导入（按维度模板导入）- 性能优化版本

        Args:
            parent_node_id: 父节点 ID（必须指定）
            dimension_type: 维度类型（如 persona、scenario）
            items: 导入数据列表，格式：[{name, corpus: [{template_code, fields}]}]
            conflict_strategy: 冲突策略 append/skip/overwrite
            tenant_code: 租户编码
            properties: 导入节点的属性设置，格式：{brands: [], products: [], tags: []}

        Returns:
            导入结果统计
        """
        import time
        start_time = time.time()
        
        logger.info(
            f"[导入开始] parent_node_id={parent_node_id}, dimension_type={dimension_type}, "
            f"tenant_code={tenant_code}, items_count={len(items)}, conflict={conflict_strategy}"
        )
        
        # 1. 获取父节点信息（用于确定 label 和 level）
        parent_label = dimension_type
        parent_level = 0
        if parent_node_id:
            parent = await self.db.get(GraphNode, parent_node_id)
            if parent and parent.is_deleted == 0:
                parent_label = parent.label
                parent_props = parent.properties or {}
                parent_level = parent_props.get("level", 1)
        
        child_level = parent_level + 1
        logger.info(f"[导入] 使用 parent_label={parent_label}, child_level={child_level}")
        
        # 2. 预加载所有同 label 的已存在节点（用于快速去重检查）
        # 同时加载节点对象用于更新语料
        # 使用小写键，确保大小写不敏感（与 MySQL utf8mb4_0900_ai_ci 一致）
        existing_nodes_map: dict[str, GraphNode] = {}  # name.lower() -> node object
        stmt = select(GraphNode).where(
            and_(
                GraphNode.label == parent_label,
                GraphNode.tenant_code == tenant_code,
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        for node in result.scalars().all():
            existing_nodes_map[node.name.lower()] = node
        
        # 3. 获取当前同级节点数量（用于计算 sort_order）
        if parent_node_id:
            stmt = select(sqla_func.count()).select_from(GraphEdge).where(
                and_(
                    GraphEdge.source_node_id == parent_node_id,
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            current_sibling_count = result.scalar() or 0
        else:
            current_sibling_count = len([n for n in existing_nodes_map.values() 
                                         if (n.properties or {}).get("level") == 1])
        
        logger.info(f"[导入] 预加载 {len(existing_nodes_map)} 个已存在节点, 当前同级数={current_sibling_count}")

        created_nodes = 0
        updated_nodes = 0
        total_corpus = 0
        errors: list[str] = []
        
        # 批量创建的节点和边
        new_nodes_to_add: list[GraphNode] = []
        new_edges_to_add: list[GraphEdge] = []
        nodes_to_update_corpus: list[tuple[GraphNode, list]] = []

        for item in items:
            node_name = item.get("name", "").strip()
            corpus_list = item.get("corpus", [])

            if not node_name:
                errors.append("节点名称为空")
                continue

            try:
                # 使用预加载的缓存快速检查（小写键，与数据库 collation 一致）
                existing_node = existing_nodes_map.get(node_name.lower())

                if existing_node:
                    # 节点已存在
                    if conflict_strategy == "skip":
                        continue
                    elif conflict_strategy == "overwrite":
                        existing_node.corpus = []
                        flag_modified(existing_node, "corpus")

                    # 追加语料（去重）- 使用集合加速
                    current_corpus = list(existing_node.corpus or [])
                    existing_json_set = {
                        json.dumps(c, ensure_ascii=False, sort_keys=True)
                        for c in current_corpus
                    }
                    added_count = 0
                    for c in corpus_list:
                        c_json = json.dumps(c, ensure_ascii=False, sort_keys=True)
                        if c_json not in existing_json_set:
                            current_corpus.append(c)
                            existing_json_set.add(c_json)
                            added_count += 1
                            total_corpus += 1
                    
                    if added_count > 0:
                        existing_node.corpus = current_corpus
                        flag_modified(existing_node, "corpus")
                        updated_nodes += 1
                else:
                    # 创建新节点（不调用 create_category，直接构建对象）
                    current_sibling_count += 1
                    node_id = generate_id()

                    node_properties: dict[str, Any] = {
                        "level": child_level,
                        "sort_order": current_sibling_count,
                    }
                    # category_type 不再存储在 properties 中，直接使用 label 字段

                    # 添加新的标签设计（labels）
                    if properties:
                        labels: dict[str, list[str]] = {}
                        if properties.get("brands"):
                            labels["brand"] = properties["brands"]
                        if properties.get("products"):
                            labels["product"] = properties["products"]
                        if properties.get("tags"):
                            labels["tag"] = properties["tags"]
                        if labels:
                            node_properties = set_labels(node_properties, labels)

                    new_node = GraphNode(
                        id=node_id,
                        tenant_code=tenant_code,
                        label=parent_label,
                        name=node_name,
                        description=None,
                        properties=node_properties,
                        corpus=corpus_list,  # 直接设置语料
                        is_active=1,
                        is_deleted=0,
                    )
                    new_nodes_to_add.append(new_node)
                    
                    # 创建边
                    if parent_node_id:
                        new_edge = GraphEdge(
                            id=generate_id(),
                            tenant_code=tenant_code,
                            source_node_id=parent_node_id,
                            target_node_id=node_id,
                            relation_type="INCLUDES",
                            is_active=1,
                            is_deleted=0,
                        )
                        new_edges_to_add.append(new_edge)
                    
                    # 更新缓存（使用小写键）
                    existing_nodes_map[node_name.lower()] = new_node
                    total_corpus += len(corpus_list)
                    created_nodes += 1

            except Exception as e:
                errors.append(f"处理节点 {node_name} 时出错: {str(e)}")
                logger.error(f"导入节点失败: {node_name}, 错误: {e}")

        # 4. 批量添加新节点和边（一次性提交）
        if new_nodes_to_add:
            self.db.add_all(new_nodes_to_add)
        if new_edges_to_add:
            self.db.add_all(new_edges_to_add)
        
        # 5. 统一提交
        await self.db.commit()

        elapsed = time.time() - start_time
        logger.info(
            f"[导入完成] 耗时={elapsed:.2f}s, 创建={created_nodes}, "
            f"更新={updated_nodes}, 语料={total_corpus}, 错误={len(errors)}"
        )

        return {
            "created_nodes": created_nodes,
            "updated_nodes": updated_nodes,
            "total_corpus": total_corpus,
            "errors": errors,
        }

    @invalidate_tree_cache()
    async def batch_import_hierarchical(
        self,
        dimension_type: str,
        items: list[dict[str, Any]],
        conflict_strategy: str,
        tenant_code: str = "default",
    ) -> dict[str, Any]:
        """
        层级批量导入（支持多级分类结构）

        Args:
            dimension_type: 维度类型/顶级分类标签（如 '违禁词'）
            items: 导入数据列表，格式：[{path: [...], name, corpus: {template_code, fields}}]
            conflict_strategy: 冲突策略 append/skip/overwrite
            tenant_code: 租户编码

        Returns:
            导入结果统计
        """
        start_time = time.time()
        
        logger.info(
            f"[层级导入开始] dimension_type={dimension_type}, "
            f"tenant_code={tenant_code}, items_count={len(items)}, conflict={conflict_strategy}"
        )
        
        # 1. 预加载所有已存在节点（用于快速查找）
        # 按 (label, name.lower()) 建立索引，确保大小写不敏感（与 MySQL utf8mb4_0900_ai_ci 一致）
        existing_nodes_map: dict[tuple[str, str], GraphNode] = {}
        stmt = select(GraphNode).where(
            and_(
                GraphNode.tenant_code == tenant_code,
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        for node in result.scalars().all():
            existing_nodes_map[(node.label, node.name.lower())] = node
        
        # 2. 预加载所有边关系
        existing_edges: set[tuple[int, int]] = set()
        stmt = select(GraphEdge).where(
            and_(
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        for edge in result.scalars().all():
            existing_edges.add((edge.source_node_id, edge.target_node_id))
        
        logger.info(f"[层级导入] 预加载 {len(existing_nodes_map)} 个节点, {len(existing_edges)} 条边")
        
        created_nodes = 0
        created_edges = 0
        updated_nodes = 0
        total_corpus = 0
        errors: list[str] = []
        
        # 用于批量提交的列表
        new_nodes_to_add: list[GraphNode] = []
        new_edges_to_add: list[GraphEdge] = []
        
        # 路径节点缓存：path_tuple -> node（包含新创建的）
        path_node_cache: dict[tuple, GraphNode] = {}
        
        for item in items:
            try:
                path = item.get("path", [])
                node_name = item.get("name", "").strip()
                corpus_data = item.get("corpus", {})
                
                if not node_name:
                    errors.append("节点名称为空")
                    continue
                
                if not path:
                    errors.append(f"节点 {node_name} 路径为空")
                    continue
                
                # 3. 确保路径上的所有层级节点都存在
                parent_node: GraphNode | None = None
                for level, path_part in enumerate(path, start=1):
                    path_tuple = tuple(path[:level])
                    
                    # 先从缓存查找
                    if path_tuple in path_node_cache:
                        parent_node = path_node_cache[path_tuple]
                        continue
                    
                    # 查找已存在的节点（使用小写键，与数据库 collation 一致）
                    cache_key = (dimension_type, path_part.lower())
                    existing = existing_nodes_map.get(cache_key)
                    
                    if existing:
                        path_node_cache[path_tuple] = existing
                        parent_node = existing
                    else:
                        # 创建新的层级节点
                        new_id = generate_id()
                        new_node = GraphNode(
                            id=new_id,
                            name=path_part,
                            label=dimension_type,
                            tenant_code=tenant_code,
                            description=f"层级 {level}: {path_part}",
                            properties={
                                "level": level,
                                "path": list(path_tuple),
                            },
                            corpus=[],
                            is_active=1,
                            is_deleted=0,
                        )
                        new_nodes_to_add.append(new_node)
                        existing_nodes_map[cache_key] = new_node  # cache_key 已是小写
                        path_node_cache[path_tuple] = new_node
                        created_nodes += 1
                        
                        # 如果有父节点，创建边
                        if parent_node:
                            edge_key = (parent_node.id, new_id)
                            if edge_key not in existing_edges:
                                new_edge = GraphEdge(
                                    id=generate_id(),
                                    source_node_id=parent_node.id,
                                    target_node_id=new_id,
                                    relation_type="INCLUDES",
                                    is_active=1,
                                    is_deleted=0,
                                )
                                new_edges_to_add.append(new_edge)
                                existing_edges.add(edge_key)
                                created_edges += 1
                        
                        parent_node = new_node
                
                # 4. 创建或更新叶子节点（关键词节点）
                # 叶子节点的 label 也是 dimension_type，便于统一管理
                # 使用小写键，与数据库 collation 一致
                leaf_key = (dimension_type, node_name.lower())
                existing_leaf = existing_nodes_map.get(leaf_key)
                
                # 构建语料
                corpus_item = {
                    "template_code": corpus_data.get("template_code", "default"),
                    "fields": corpus_data.get("fields", {}),
                }
                
                if existing_leaf:
                    # 节点已存在
                    if conflict_strategy == "skip":
                        continue
                    elif conflict_strategy == "overwrite":
                        existing_leaf.corpus = [corpus_item]
                        flag_modified(existing_leaf, "corpus")
                        updated_nodes += 1
                        total_corpus += 1
                    else:  # append
                        if not existing_leaf.corpus:
                            existing_leaf.corpus = []
                        existing_leaf.corpus.append(corpus_item)
                        flag_modified(existing_leaf, "corpus")
                        updated_nodes += 1
                        total_corpus += 1
                else:
                    # 创建新的叶子节点
                    leaf_level = len(path) + 1
                    new_id = generate_id()
                    new_leaf = GraphNode(
                        id=new_id,
                        name=node_name,
                        label=dimension_type,
                        tenant_code=tenant_code,
                        description="",
                        properties={
                            "level": leaf_level,
                            "path": path + [node_name],
                        },
                        corpus=[corpus_item],
                        is_active=1,
                        is_deleted=0,
                    )
                    new_nodes_to_add.append(new_leaf)
                    existing_nodes_map[leaf_key] = new_leaf  # leaf_key 已是小写
                    created_nodes += 1
                    total_corpus += 1
                    
                    # 创建到父节点的边
                    if parent_node:
                        edge_key = (parent_node.id, new_id)
                        if edge_key not in existing_edges:
                            new_edge = GraphEdge(
                                id=generate_id(),
                                source_node_id=parent_node.id,
                                target_node_id=new_id,
                                relation_type="INCLUDES",
                                is_active=1,
                                is_deleted=0,
                            )
                            new_edges_to_add.append(new_edge)
                            existing_edges.add(edge_key)
                            created_edges += 1
                
            except Exception as e:
                errors.append(f"处理节点 {item.get('name', '?')} 时出错: {str(e)}")
                logger.error(f"层级导入节点失败: {item}, 错误: {e}")
        
        # 5. 批量提交
        if new_nodes_to_add:
            self.db.add_all(new_nodes_to_add)
        if new_edges_to_add:
            self.db.add_all(new_edges_to_add)
        
        await self.db.commit()

        elapsed = time.time() - start_time
        logger.info(
            f"[层级导入完成] 耗时={elapsed:.2f}s, 节点={created_nodes}, "
            f"边={created_edges}, 更新={updated_nodes}, 语料={total_corpus}, 错误={len(errors)}"
        )
        
        return {
            "created_nodes": created_nodes,
            "created_edges": created_edges,
            "updated_nodes": updated_nodes,
            "total_corpus": total_corpus,
            "errors": errors,
        }

    # ==================== 关键词 CRUD 方法 ====================

    async def list_keywords(
        self,
        category_id: int,
        keyword: str | None = None,
        tenant_code: str = "default",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        获取分类下的关键词列表（分页）

        Args:
            category_id: 分类 ID
            keyword: 关键词搜索
            tenant_code: 租户编码
            page: 页码
            page_size: 每页大小

        Returns:
            (关键词列表, 总数)
        """
        # 1. 获取该分类下所有 KEYWORD 类型的子节点 ID
        stmt = select(GraphEdge.target_node_id).where(
            and_(
                GraphEdge.source_node_id == category_id,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.tenant_code == tenant_code,
                GraphEdge.is_deleted == 0,
                GraphEdge.is_active == 1,
            )
        )
        result = await self.db.execute(stmt)
        child_ids = [row[0] for row in result.fetchall()]

        if not child_ids:
            return [], 0

        # 2. 查询这些子节点中 label=KEYWORD 的节点
        conditions = [
            GraphNode.id.in_(child_ids),
            GraphNode.label == self.KEYWORD_LABEL,
            GraphNode.is_deleted == 0,
        ]
        if keyword:
            conditions.append(GraphNode.name.ilike(f"%{keyword}%"))

        # 查询总数
        count_stmt = select(sqla_func.count()).select_from(GraphNode).where(and_(*conditions))
        total = int((await self.db.execute(count_stmt)).scalar() or 0)

        # 分页查询
        stmt = (
            select(GraphNode)
            .where(and_(*conditions))
            .order_by(GraphNode.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        keywords = result.scalars().all()

        items = []
        for kw in keywords:
            props = kw.properties or {}
            items.append({
                "id": str(kw.id),
                "name": kw.name,
                "description": kw.description,
                "properties": props,
                "is_active": kw.is_active,
                "corpus": kw.corpus or [],
                "created_at": kw.created_at.strftime("%Y-%m-%d %H:%M:%S") if kw.created_at else None,
                "updated_at": kw.updated_at.strftime("%Y-%m-%d %H:%M:%S") if kw.updated_at else None,
            })

        return items, total

    @invalidate_tree_cache()
    async def create_keyword(
        self,
        name: str,
        category_id: int,
        description: str | None = None,
        properties: dict | None = None,
        tenant_code: str = "default",
    ) -> dict[str, Any]:
        """
        创建关键词

        Args:
            name: 关键词名称
            category_id: 所属分类 ID
            description: 描述
            properties: 扩展属性
            tenant_code: 租户编码

        Returns:
            创建的关键词信息
        """
        # 1. 创建 KEYWORD 节点
        keyword_id = generate_id()
        keyword_node = GraphNode(
            id=keyword_id,
            tenant_code=tenant_code,
            label=self.KEYWORD_LABEL,
            name=name,
            description=description,
            properties=properties or {},
        )
        self.db.add(keyword_node)

        # 2. 创建父子关系边
        edge_id = generate_id()
        edge = GraphEdge(
            id=edge_id,
            tenant_code=tenant_code,
            source_node_id=category_id,
            target_node_id=keyword_id,
            relation_type="INCLUDES",
        )
        self.db.add(edge)

        await self.db.commit()
        await self.db.refresh(keyword_node)

        return {
            "id": str(keyword_node.id),
            "name": keyword_node.name,
            "description": keyword_node.description,
            "properties": keyword_node.properties,
            "is_active": keyword_node.is_active,
        }

    @invalidate_tree_cache(from_context=True)
    async def update_keyword(
        self,
        keyword_id: int,
        name: str | None = None,
        description: str | None = None,
        properties: dict | None = None,
        is_active: int | None = None,
    ) -> dict[str, Any] | None:
        """
        更新关键词

        Args:
            keyword_id: 关键词 ID
            name: 名称
            description: 描述
            properties: 扩展属性
            is_active: 状态

        Returns:
            更新后的关键词信息，不存在返回 None
        """
        keyword = await self.db.get(GraphNode, keyword_id)
        if not keyword or keyword.is_deleted == 1 or keyword.label != self.KEYWORD_LABEL:
            return None

        if name is not None:
            keyword.name = name
        if description is not None:
            keyword.description = description
        if properties is not None:
            keyword.properties = properties
            flag_modified(keyword, "properties")
        if is_active is not None:
            keyword.is_active = is_active

        await self.db.commit()
        await self.db.refresh(keyword)

        # 设置 tenant_code 用于缓存失效
        set_cache_tenant(keyword.tenant_code)

        return {
            "id": str(keyword.id),
            "name": keyword.name,
            "description": keyword.description,
            "properties": keyword.properties,
            "is_active": keyword.is_active,
        }

    @invalidate_tree_cache(from_context=True)
    async def delete_keyword(self, keyword_id: int) -> bool:
        """
        删除关键词（软删除）

        Args:
            keyword_id: 关键词 ID

        Returns:
            是否删除成功
        """
        keyword = await self.db.get(GraphNode, keyword_id)
        if not keyword or keyword.is_deleted == 1 or keyword.label != self.KEYWORD_LABEL:
            return False

        keyword.is_deleted = 1
        keyword.is_active = 0

        # 同时软删除关联的边
        stmt = select(GraphEdge).where(
            and_(
                GraphEdge.target_node_id == keyword_id,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        edges = result.scalars().all()
        for edge in edges:
            edge.is_deleted = 1
            edge.is_active = 0

        await self.db.commit()

        # 设置 tenant_code 用于缓存失效
        set_cache_tenant(keyword.tenant_code)

        return True

    @invalidate_tree_cache()
    async def batch_create_keywords(
        self,
        category_id: int,
        keywords: list[dict],
        tenant_code: str = "default",
    ) -> dict[str, Any]:
        """
        批量创建关键词

        Args:
            category_id: 分类 ID
            keywords: 关键词列表 [{"name": "xxx", "description": "yyy"}, ...]
            tenant_code: 租户编码

        Returns:
            创建结果统计
        """
        created = 0
        errors = []

        for kw_data in keywords:
            try:
                name = kw_data.get("name")
                if not name:
                    errors.append({"data": kw_data, "error": "缺少 name 字段"})
                    continue

                await self.create_keyword(
                    name=name,
                    category_id=category_id,
                    description=kw_data.get("description"),
                    properties=kw_data.get("properties"),
                    tenant_code=tenant_code,
                )
                created += 1
            except Exception as e:
                errors.append({"data": kw_data, "error": str(e)})

        return {
            "created": created,
            "errors": errors,
        }


class LabelService:
    """Label 服务 - 支持语义化 label 查询"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_labels(
        self,
        tenant_code: str = "default",
        exclude_keyword: bool = True,
    ) -> list[dict[str, Any]]:
        """
        获取所有可用的 label 列表

        Args:
            tenant_code: 租户编码
            exclude_keyword: 是否排除 KEYWORD 类型

        Returns:
            label 列表，格式: [{"label": "小人设", "count": 12, "description": "细分人设"}]
        """
        conditions = [
            GraphNode.tenant_code == tenant_code,
            GraphNode.is_deleted == 0,
            GraphNode.is_active == 1,
        ]

        if exclude_keyword:
            conditions.append(GraphNode.label != "KEYWORD")

        stmt = (
            select(
                GraphNode.label,
                sqla_func.count(GraphNode.id).label("count"),
            )
            .where(and_(*conditions))
            .group_by(GraphNode.label)
            .order_by(sqla_func.count(GraphNode.id).desc())
        )

        result = await self.db.execute(stmt)
        rows = result.fetchall()

        labels = []
        for row in rows:
            labels.append({
                "label": row[0],
                "count": row[1],
                "description": self._get_label_description(row[0]),
            })

        return labels

    def _get_label_description(self, label: str) -> str:
        """获取 label 的描述"""
        descriptions = {
            "人设": "用户人设根分类",
            "大人设": "用户大类人设",
            "小人设": "细分人设，可用于变量绑定",
            "品牌": "品牌相关分类",
            "品牌分类": "品牌子分类",
            "产品": "产品分类",
            "平台": "内容平台分类",
            "平台分类": "平台子分类",
            "内容结构": "文章内容结构分类",
            "表达结构": "表达方式/风格",
            "违禁词": "违禁词和敏感词分类",
            "违禁词分类": "违禁词子分类",
            "场景": "产品使用场景",
            "KEYWORD": "关键词/语料",
        }
        return descriptions.get(label, f"{label} 类型节点")

    async def get_all_tenants(self) -> list[dict[str, Any]]:
        """
        获取所有租户列表

        Returns:
            租户列表，格式: [{"tenant_code": "2000001", "tenant_name": "美素佳儿", "count": 120}]
        """
        # 1. 查询 nodes 表，按 tenant_code 分组统计
        stmt = (
            select(
                GraphNode.tenant_code,
                sqla_func.count(GraphNode.id).label("count"),
            )
            .where(
                and_(
                    GraphNode.is_deleted == 0,
                    GraphNode.is_active == 1,
                )
            )
            .group_by(GraphNode.tenant_code)
            .order_by(sqla_func.count(GraphNode.id).desc())
        )

        result = await self.db.execute(stmt)
        rows = result.fetchall()

        # 2. 通过 Dapr 调用 Orchestrator 获取租户名称映射
        tenant_name_map: dict[str, str] = {}
        try:
            dapr_url = f"http://localhost:{settings.DAPR_HTTP_PORT}/v1.0/invoke/raap-service-orchestrator/method/api/v1/tenants/simple"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(dapr_url)
                if resp.status_code == 200:
                    data = resp.json()
                    # 响应格式: {"code": 200, "data": [{"id": 1, "tenant_code": "xxx", "tenant_name": "xxx"}]}
                    for item in data.get("data", []):
                        tenant_name_map[item["tenant_code"]] = item["tenant_name"]
        except Exception as e:
            logger.warning(f"获取租户名称失败，将使用 tenant_code 作为显示名: {e}")

        # 3. 合并结果
        return [
            {
                "tenant_code": row[0],
                "tenant_name": tenant_name_map.get(row[0], row[0]),  # fallback 到 tenant_code
                "count": row[1],
            }
            for row in rows
        ]

    async def get_nodes_by_label(
        self,
        label: str,
        tenant_code: str = "default",
        include_keywords: bool = True,
        include_parent_path: bool = True,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        按 label 查询所有 Node

        Args:
            label: 节点 label
            tenant_code: 租户编码
            include_keywords: 是否包含 keywords 字段
            include_parent_path: 是否包含父节点路径
            page: 页码
            page_size: 每页数量

        Returns:
            (节点列表, 总数)
        """
        conditions = [
            GraphNode.tenant_code == tenant_code,
            GraphNode.label == label,
            GraphNode.is_deleted == 0,
            GraphNode.is_active == 1,
        ]

        # 查询总数
        count_stmt = select(GraphNode).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = len(count_result.scalars().all())

        # 分页查询
        stmt = (
            select(GraphNode)
            .where(and_(*conditions))
            .order_by(GraphNode.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(stmt)
        nodes = result.scalars().all()

        # 构建结果
        items = []
        for node in nodes:
            item = {
                "id": str(node.id),
                "name": node.name,
                "label": node.label,
                "description": node.description,
                "is_active": node.is_active,
                "has_children": await self._has_children(node.id),
            }

            if include_keywords:
                item["keywords"] = node.corpus or []

            if include_parent_path:
                item["parent_path"] = await self._get_parent_path(node.id, tenant_code)

            items.append(item)

        return items, total

    async def _has_children(self, node_id: int) -> bool:
        """检查节点是否有子节点"""
        stmt = select(GraphEdge).where(
            and_(
                GraphEdge.source_node_id == node_id,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        ).limit(1)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _get_parent_path(
        self,
        node_id: int,
        tenant_code: str,
        max_depth: int = 10,
    ) -> list[str]:
        """
        获取节点的父节点路径

        Returns:
            父节点名称列表，从根到直接父节点，如 ["人设", "理性科学型妈妈"]
        """
        path = []
        current_id = node_id

        for _ in range(max_depth):
            # 查找父节点
            stmt = select(GraphEdge).where(
                and_(
                    GraphEdge.target_node_id == current_id,
                    GraphEdge.relation_type == "INCLUDES",
                    GraphEdge.is_deleted == 0,
                )
            ).limit(1)

            result = await self.db.execute(stmt)
            edge = result.scalar_one_or_none()

            if not edge:
                break

            parent_node = await self.db.get(GraphNode, edge.source_node_id)
            if parent_node and parent_node.is_deleted == 0:
                path.insert(0, parent_node.name)
                current_id = parent_node.id
            else:
                break

        return path

    async def batch_get_keywords(
        self,
        node_ids: list[int],
        include_children: bool = False,
        tenant_code: str = "default",
    ) -> dict[str, dict[str, Any]]:
        """
        批量获取节点的 keywords

        Args:
            node_ids: 节点 ID 列表
            include_children: 是否包含子节点的 keywords
            tenant_code: 租户编码

        Returns:
            节点 ID 到 keywords 的映射，格式:
            {
                "1001003001": {
                    "name": "发育关注型妈妈",
                    "keywords": ["重视眼脑发育..."],
                    "description": "节点描述"
                }
            }
        """
        if not node_ids:
            return {}

        # 过滤无效 ID，避免 SQL 和缓存键污染
        valid_node_ids = []
        for node_id in node_ids:
            try:
                valid_node_ids.append(int(node_id))
            except (ValueError, TypeError):
                logger.warning(f"[batch_get_keywords] 无效的节点 ID: {node_id}")

        if not valid_node_ids:
            return {}

        # 统一缓存键：tenant + include_children + node_ids(md5)
        import hashlib
        query_node_ids = sorted(set(valid_node_ids))
        node_ids_hash = hashlib.md5(",".join(str(nid) for nid in query_node_ids).encode("utf-8")).hexdigest()[:12]
        cache_key = f"kc:node:batch:kw:{tenant_code}:{int(include_children)}:{node_ids_hash}"

        cached = await cache_get(cache_key)
        if isinstance(cached, dict):
            logger.debug(f"[batch_get_keywords] 缓存命中: {cache_key}, count={len(cached)}")
            return cached

        # 查询节点（不限制 tenant_code，允许跨租户获取关键词）
        stmt = select(GraphNode).where(
            and_(
                GraphNode.id.in_(query_node_ids),
                GraphNode.is_deleted == 0,
            )
        )

        result = await self.db.execute(stmt)
        nodes = result.scalars().all()

        # 构建结果
        # 优化：一次性收集所有 corpus，避免 N+1 查询问题
        all_corpus_list = []
        node_corpus_map = {}  # node_id -> corpus_index 映射
        
        for node in nodes:
            corpus_list = node.corpus if node.corpus else []
            all_corpus_list.append(corpus_list)
            node_corpus_map[node.id] = len(all_corpus_list) - 1
        
        # 一次性排序所有 corpus（内部会批量查询模板）
        if all_corpus_list:
            ordered_corpus_list = await self._order_corpus_fields(all_corpus_list, tenant_code)
        else:
            ordered_corpus_list = []
        
        # 构建结果
        keyword_map = {}
        for node in nodes:
            corpus_idx = node_corpus_map[node.id]
            ordered_corpus = ordered_corpus_list[corpus_idx]
            
            keyword_map[str(node.id)] = {
                "name": node.name,  # 节点名称
                "label": node.label,  # 节点 label
                "corpus": ordered_corpus,  # 排序后的语料列表
                "description": node.description,
            }

        # 如果需要包含子节点的 corpus
        if include_children:
            for node_id in query_node_ids:
                child_corpus = await self._get_children_corpus(node_id, tenant_code)
                if str(node_id) in keyword_map:
                    keyword_map[str(node_id)]["children_corpus"] = child_corpus

        await cache_set(cache_key, keyword_map, ttl=CACHE_TTL_NODE_BATCH)
        logger.debug(f"[batch_get_keywords] 缓存写入: {cache_key}, ttl={CACHE_TTL_NODE_BATCH}s, count={len(keyword_map)}")

        return keyword_map

    async def _get_children_corpus(
        self,
        parent_id: int,
        tenant_code: str,
    ) -> list[str]:
        """获取子节点的所有 corpus（语料）"""
        # 查找子节点
        stmt = select(GraphEdge.target_node_id).where(
            and_(
                GraphEdge.source_node_id == parent_id,
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
            )
        )

        result = await self.db.execute(stmt)
        child_ids = [row[0] for row in result.fetchall()]

        if not child_ids:
            return []

        # 查询子节点（不限制 tenant_code，允许跨租户获取）
        child_stmt = select(GraphNode).where(
            and_(
                GraphNode.id.in_(child_ids),
                GraphNode.is_deleted == 0,
            )
        )

        child_result = await self.db.execute(child_stmt)
        children = child_result.scalars().all()

        corpus_list = []
        for child in children:
            if child.corpus:
                for c in child.corpus:
                    if isinstance(c, dict):
                        corpus_list.append(c.get("text", ""))
                    elif isinstance(c, str):
                        corpus_list.append(c)

        return corpus_list

    async def _order_corpus_fields(
        self, corpus_list: list[dict[str, Any]], tenant_code: str
    ) -> list[dict[str, Any]]:
        """
        根据 corpus 模板的 fields 定义顺序重新排序 corpus.fields
        解决 MySQL JSON 列不保证键顺序的问题
        """
        # 收集所有用到的 template_code
        template_codes = set()
        for corpus in corpus_list:
            if isinstance(corpus, dict) and "template_code" in corpus:
                template_codes.add(corpus["template_code"])

        # 批量获取模板
        templates = {}
        if template_codes:
            stmt = select(CorpusTemplate).where(
                and_(
                    CorpusTemplate.code.in_(template_codes),
                    CorpusTemplate.is_deleted == 0,
                    CorpusTemplate.tenant_code == tenant_code,
                )
            )
            result = await self.db.execute(stmt)
            for template in result.scalars():
                # 构建字段顺序映射：field_key -> index
                # 使用字段中的 order 字段来确定顺序（解决 MySQL JSON 列不保证数组元素顺序的问题）
                field_order = {}
                for field in template.fields:
                    key = field.get("key")
                    order = field.get("order")
                    if key is not None:
                        # 如果有 order 字段，使用它；否则使用一个大值（排在后面）
                        field_order[key] = order if order is not None else 999

                templates[template.code] = field_order

        # 重新排序每个 corpus 的 fields
        ordered_corpus = []
        for corpus in corpus_list:
            if not isinstance(corpus, dict):
                ordered_corpus.append(corpus)
                continue

            # 检查是否有 template_code 和 fields
            template_code = corpus.get("template_code")
            fields = corpus.get("fields")

            if (
                template_code
                and template_code in templates
                and isinstance(fields, dict)
            ):
                # 根据模板顺序重新排序
                field_order = templates[template_code]
                ordered_fields = {}
                field_keys = []  # 记录字段顺序，供 Orchestrator _corpus_to_text 使用

                # 按 field_order 的值（模板中的索引）排序字段
                # field_order 是 {field_key: index} 的映射
                sorted_keys = sorted(field_order.keys(), key=lambda k: field_order[k])

                # 先按模板顺序添加
                for key in sorted_keys:
                    if key in fields:
                        ordered_fields[key] = fields[key]
                        field_keys.append(key)
                # 添加模板中没有的自定义字段
                for key, value in fields.items():
                    if key not in field_order:
                        ordered_fields[key] = value
                        field_keys.append(key)

                new_corpus = dict(corpus)
                new_corpus["fields"] = ordered_fields
                new_corpus["field_keys"] = field_keys  # 添加字段顺序，解决 JSON 序列化后 dict 顺序丢失问题
                ordered_corpus.append(new_corpus)
            else:
                ordered_corpus.append(corpus)

        return ordered_corpus
