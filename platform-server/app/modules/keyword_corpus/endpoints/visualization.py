"""
图谱可视化 API
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.schemas.base import ResponseData
from app.schemas.graph import (
    EdgeItem,
    GraphVisualizationQuery,
    GraphVisualizationResponse,
    NodeItem,
)
from app.services import graph_service

router = APIRouter(prefix="/graph/visualization", tags=["graph-visualization"])


@router.get("", response_model=ResponseData[GraphVisualizationResponse])
async def get_graph_visualization(
    db: AsyncSessionDep,
    tenant_code: Optional[str] = Query(None, description="租户编码"),
    min_degree: int = Query(0, ge=0, description="最小边数，只返回边数 >= min_degree 的节点"),
    limit: int = Query(1000, ge=1, le=5000, description="最大返回节点数"),
):
    """
    获取图谱可视化数据
    
    高效策略：
    1. 后端计算节点度数并过滤
    2. 只返回关联的节点和边
    3. 支持 min_degree 过滤低连接度节点
    """
    query = GraphVisualizationQuery(
        tenant_code=tenant_code,
        min_degree=min_degree,
        limit=limit,
    )
    
    result = await graph_service.get_graph_visualization_data(session=db, query=query)
    
    # 转换为响应格式
    nodes = [NodeItem.model_validate(n) for n in result["nodes"]]
    edges = [EdgeItem.model_validate(e) for e in result["edges"]]
    
    return ResponseData(
        code=200,
        message="success",
        data=GraphVisualizationResponse(
            nodes=nodes,
            edges=edges,
            stats=result["stats"],
        ),
    )
