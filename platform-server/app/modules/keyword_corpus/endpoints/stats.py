"""
图谱统计 API
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.schemas.base import ResponseData
from app.schemas.graph import GraphStats
from app.services import graph_service

router = APIRouter(prefix="/graph/stats", tags=["graph-stats"])


@router.get("", response_model=ResponseData[GraphStats])
async def get_graph_stats(
    db: AsyncSessionDep,
    tenant_code: Optional[str] = Query(None, description="按租户筛选"),
):
    """获取图谱统计信息"""
    stats = await graph_service.get_graph_stats(session=db, tenant_code=tenant_code)
    return ResponseData(
        code=200,
        message="success",
        data=GraphStats(**stats),
    )
