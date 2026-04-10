"""
图节点查询 API（图可视化专用）

注意：节点的 CRUD 操作通过 categories API 进行，这里只保留图可视化需要的查询 API
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.schemas.base import PageInfo, ResponseData
from app.schemas.graph import (
    EdgeItem,
    NodeItem,
    NodeListQuery,
    NodeListResponse,
    NodeNeighborsResponse,
    NodeOptionsResponse,
)
from app.services import graph_service

router = APIRouter(prefix="/graph/nodes", tags=["graph-nodes"])


@router.get("/options", response_model=ResponseData[NodeOptionsResponse])
async def get_node_options(
    db: AsyncSessionDep,
):
    """获取节点筛选选项（labels, tenant_codes）- 图可视化筛选器需要"""
    options = await graph_service.get_node_options(session=db)
    return ResponseData(
        code=200,
        message="success",
        data=NodeOptionsResponse(**options),
    )


@router.get("")
async def list_nodes(
    db: AsyncSessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    tenant_code: Optional[str] = Query(None),
    label: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="按 name 模糊搜索"),
    is_active: Optional[int] = Query(None, description="0-禁用 1-启用"),
):
    """查询节点列表 - 图可视化搜索功能需要"""
    query = NodeListQuery(
        page=page,
        page_size=page_size,
        tenant_code=tenant_code,
        label=label,
        keyword=keyword,
        is_active=is_active,
    )
    items, total = await graph_service.list_nodes(session=db, query=query)
    total_pages = int((total + page_size - 1) // page_size) if page_size else 1
    return ResponseData(
        code=200,
        message="success",
        data=NodeListResponse(
            items=[NodeItem.model_validate(i) for i in items],
            page_info=PageInfo(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        ),
    )


@router.get("/{node_id}/neighbors", response_model=ResponseData[NodeNeighborsResponse])
async def get_node_neighbors(
    node_id: int,
    db: AsyncSessionDep,
):
    """
    获取节点及其所有直接邻居（聚焦模式专用，一次性返回）
    
    高效 API：一次请求返回中心节点 + 所有邻居节点 + 所有边
    用于前端图聚焦模式，避免多次 API 调用
    """
    result = await graph_service.get_node_neighbors(session=db, node_id=node_id)
    if result is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    
    return ResponseData(
        code=200,
        message="success",
        data=NodeNeighborsResponse(
            center_node=NodeItem.model_validate(result["center_node"]),
            neighbors=[NodeItem.model_validate(n) for n in result["neighbors"]],
            edges=[EdgeItem.model_validate(e) for e in result["edges"]],
        ),
    )
