"""
图节点和边关系查询服务（图可视化专用）

注意：节点/边的 CRUD 操作通过 category_service 进行，这里只保留图可视化需要的查询功能
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph import GraphEdge, GraphNode
from app.schemas.graph import (
    GraphVisualizationQuery,
    NodeListQuery,
)


# ==================== Node Query (图可视化专用) ====================

async def list_nodes(*, session: AsyncSession, query: NodeListQuery) -> tuple[list[GraphNode], int]:
    """查询节点列表（图可视化搜索功能需要）"""
    conditions = [GraphNode.is_deleted == 0]
    
    if query.tenant_code:
        conditions.append(GraphNode.tenant_code == query.tenant_code)
    if query.label:
        conditions.append(GraphNode.label == query.label)
    if query.keyword:
        conditions.append(GraphNode.name.like(f"%{query.keyword.strip()}%"))
    if query.is_active is not None:
        conditions.append(GraphNode.is_active == query.is_active)

    stmt = select(GraphNode).where(and_(*conditions)).order_by(GraphNode.updated_at.desc(), GraphNode.id.desc())
    count_stmt = select(func.count()).select_from(GraphNode).where(and_(*conditions))

    total = int((await session.execute(count_stmt)).scalar() or 0)
    page = max(int(query.page), 1)
    page_size = max(int(query.page_size), 1)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    items = (await session.execute(stmt)).scalars().all()
    return list(items), total


async def get_node_options(*, session: AsyncSession) -> dict:
    """获取节点筛选选项（图可视化筛选器需要）"""
    labels_stmt = (
        select(GraphNode.label)
        .where(GraphNode.is_deleted == 0)
        .distinct()
        .order_by(GraphNode.label)
    )
    tenant_codes_stmt = (
        select(GraphNode.tenant_code)
        .where(GraphNode.is_deleted == 0)
        .distinct()
        .order_by(GraphNode.tenant_code)
    )
    
    labels = [row[0] for row in (await session.execute(labels_stmt)).fetchall() if row[0]]
    tenant_codes = [row[0] for row in (await session.execute(tenant_codes_stmt)).fetchall() if row[0]]
    
    return {"labels": labels, "tenant_codes": tenant_codes}


# ==================== Graph Stats ====================

async def get_graph_stats(*, session: AsyncSession, tenant_code: Optional[str] = None) -> dict:
    """获取图谱统计信息"""
    node_conditions = [GraphNode.is_deleted == 0]
    edge_conditions = [GraphEdge.is_deleted == 0]
    
    if tenant_code:
        node_conditions.append(GraphNode.tenant_code == tenant_code)
        edge_conditions.append(GraphEdge.tenant_code == tenant_code)

    # 节点总数
    total_nodes = int((await session.execute(
        select(func.count()).select_from(GraphNode).where(and_(*node_conditions))
    )).scalar() or 0)
    
    # 边总数
    total_edges = int((await session.execute(
        select(func.count()).select_from(GraphEdge).where(and_(*edge_conditions))
    )).scalar() or 0)
    
    # 按 label 分组统计节点
    nodes_by_label_stmt = (
        select(GraphNode.label, func.count())
        .where(and_(*node_conditions))
        .group_by(GraphNode.label)
    )
    nodes_by_label = {row[0]: row[1] for row in (await session.execute(nodes_by_label_stmt)).fetchall()}
    
    # 按 relation_type 分组统计边
    edges_by_relation_stmt = (
        select(GraphEdge.relation_type, func.count())
        .where(and_(*edge_conditions))
        .group_by(GraphEdge.relation_type)
    )
    edges_by_relation = {row[0]: row[1] for row in (await session.execute(edges_by_relation_stmt)).fetchall()}
    
    return {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "nodes_by_label": nodes_by_label,
        "edges_by_relation": edges_by_relation,
    }


# ==================== Graph Visualization ====================

async def get_graph_visualization_data(
    *,
    session: AsyncSession,
    query: GraphVisualizationQuery,
) -> dict:
    """
    获取图谱可视化数据（优化版）

    高效策略：
    1. 使用 SQLAlchemy ORM 聚合计算节点度数
    2. 在数据库层面过滤和限制
    3. 只加载必要的数据
    """

    # Step 1: 计算每个节点的度数（使用纯 ORM）
    # 构建基础查询条件
    edge_base_conditions = [
        GraphEdge.is_deleted == 0,
        GraphEdge.is_active == 1
    ]
    if query.tenant_code:
        edge_base_conditions.append(GraphEdge.tenant_code == query.tenant_code)

    # 查询作为 source 的节点的度数
    source_degree_stmt = (
        select(
            GraphEdge.source_node_id.label("node_id"),
            func.count().label("cnt")
        )
        .where(and_(*edge_base_conditions))
        .group_by(GraphEdge.source_node_id)
    )

    # 查询作为 target 的节点的度数
    target_degree_stmt = (
        select(
            GraphEdge.target_node_id.label("node_id"),
            func.count().label("cnt")
        )
        .where(and_(*edge_base_conditions))
        .group_by(GraphEdge.target_node_id)
    )

    # 合并两个查询并聚合
    combined = union_all(source_degree_stmt, target_degree_stmt).alias("edge_counts")

    degree_stmt = (
        select(
            combined.c.node_id,
            func.sum(combined.c.cnt).label("degree")
        )
        .group_by(combined.c.node_id)
        .having(func.sum(combined.c.cnt) >= query.min_degree)
        .order_by(func.sum(combined.c.cnt).desc())
        .limit(query.limit)
    )

    degree_result = await session.execute(degree_stmt)
    node_degrees = {row[0]: int(row[1]) for row in degree_result.fetchall()}
    
    if not node_degrees:
        return {
            "nodes": [],
            "edges": [],
            "stats": {"total_nodes": 0, "total_edges": 0, "filtered_nodes": 0, "filtered_edges": 0, "min_degree": query.min_degree},
        }
    
    valid_node_ids = set(node_degrees.keys())
    
    # Step 2: 查询过滤后的节点详情
    node_conditions = [
        GraphNode.is_deleted == 0, 
        GraphNode.is_active == 1,
        GraphNode.id.in_(valid_node_ids)
    ]
    if query.tenant_code:
        node_conditions.append(GraphNode.tenant_code == query.tenant_code)
    
    nodes_stmt = select(GraphNode).where(and_(*node_conditions))
    filtered_nodes = list((await session.execute(nodes_stmt)).scalars().all())
    
    # Step 3: 查询两端节点都在有效集合中的边
    edge_conditions = [
        GraphEdge.is_deleted == 0, 
        GraphEdge.is_active == 1,
        GraphEdge.source_node_id.in_(valid_node_ids),
        GraphEdge.target_node_id.in_(valid_node_ids)
    ]
    if query.tenant_code:
        edge_conditions.append(GraphEdge.tenant_code == query.tenant_code)
    
    edges_stmt = select(GraphEdge).where(and_(*edge_conditions))
    filtered_edges_raw = list((await session.execute(edges_stmt)).scalars().all())
    
    # Step 4: 为边填充节点名称
    node_map = {node.id: node for node in filtered_nodes}
    enriched_edges = []
    for edge in filtered_edges_raw:
        source_node = node_map.get(edge.source_node_id)
        target_node = node_map.get(edge.target_node_id)
        enriched_edges.append({
            "id": edge.id,
            "tenant_code": edge.tenant_code,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "relation_type": edge.relation_type,
            "explanation": edge.explanation,
            "meta_data": edge.meta_data,
            "is_active": edge.is_active,
            "is_deleted": edge.is_deleted,
            "created_at": edge.created_at,
            "updated_at": edge.updated_at,
            "source_name": source_node.name if source_node else None,
            "target_name": target_node.name if target_node else None,
            "source_label": source_node.label if source_node else None,
            "target_label": target_node.label if target_node else None,
        })
    
    # Step 5: 统计信息
    stats = {
        "total_nodes": len(node_degrees),
        "total_edges": len(filtered_edges_raw),
        "filtered_nodes": len(filtered_nodes),
        "filtered_edges": len(enriched_edges),
        "min_degree": query.min_degree,
    }
    
    return {
        "nodes": filtered_nodes,
        "edges": enriched_edges,
        "stats": stats,
    }


# ==================== Node Neighbors (聚焦模式专用) ====================

async def get_node_neighbors(
    *,
    session: AsyncSession,
    node_id: int,
) -> Optional[dict]:
    """
    获取节点及其所有直接邻居（一次性返回，用于图聚焦模式）
    
    高效策略：
    1. 一次查询获取所有相关边
    2. 一次批量查询获取所有邻居节点
    3. 返回完整数据，前端无需多次请求
    
    Returns:
        {
            "center_node": NodeItem,
            "neighbors": list[NodeItem],
            "edges": list[EdgeItem]
        }
    """
    # Step 1: 获取中心节点
    center_node = await session.get(GraphNode, node_id)
    if center_node is None or center_node.is_deleted != 0:
        return None
    
    # Step 2: 一次查询获取所有相关边（中心节点作为 source 或 target）
    edges_stmt = select(GraphEdge).where(
        and_(
            GraphEdge.is_deleted == 0,
            GraphEdge.is_active == 1,
            (GraphEdge.source_node_id == node_id) | (GraphEdge.target_node_id == node_id)
        )
    )
    edges_result = await session.execute(edges_stmt)
    edges = list(edges_result.scalars().all())
    
    # Step 3: 收集所有邻居节点 ID
    neighbor_ids = set()
    for edge in edges:
        if edge.source_node_id != node_id:
            neighbor_ids.add(edge.source_node_id)
        if edge.target_node_id != node_id:
            neighbor_ids.add(edge.target_node_id)
    
    # Step 4: 一次批量查询获取所有邻居节点
    neighbors = []
    if neighbor_ids:
        neighbors_stmt = select(GraphNode).where(
            and_(
                GraphNode.is_deleted == 0,
                GraphNode.id.in_(neighbor_ids)
            )
        )
        neighbors_result = await session.execute(neighbors_stmt)
        neighbors = list(neighbors_result.scalars().all())
    
    # Step 5: 构建 node_map 用于填充边的冗余字段
    node_map = {center_node.id: center_node}
    for n in neighbors:
        node_map[n.id] = n
    
    # Step 6: 为边填充节点名称
    enriched_edges = []
    for edge in edges:
        source_node = node_map.get(edge.source_node_id)
        target_node = node_map.get(edge.target_node_id)
        enriched_edges.append({
            "id": edge.id,
            "tenant_code": edge.tenant_code,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "relation_type": edge.relation_type,
            "explanation": edge.explanation,
            "meta_data": edge.meta_data,
            "is_active": edge.is_active,
            "is_deleted": edge.is_deleted,
            "created_at": edge.created_at,
            "updated_at": edge.updated_at,
            "source_name": source_node.name if source_node else None,
            "target_name": target_node.name if target_node else None,
            "source_label": source_node.label if source_node else None,
            "target_label": target_node.label if target_node else None,
        })
    
    return {
        "center_node": center_node,
        "neighbors": neighbors,
        "edges": enriched_edges,
    }
