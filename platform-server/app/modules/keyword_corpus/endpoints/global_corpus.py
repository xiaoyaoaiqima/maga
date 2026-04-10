"""
全局公共语料库 API

用于超级管理员管理全局通用语料
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionDep, get_db
from app.services.category_service import CategoryService

router = APIRouter(prefix="/global-corpus", tags=["全局语料管理"])


# ==================== 请求/响应 Schema ====================


class GlobalCorpusCreate(BaseModel):
    """创建全局语料请求"""

    name: str = Field(..., min_length=1, max_length=100, description="语料名称")
    label: Optional[str] = Field(
        default=None, max_length=50, description="语义化标签"
    )
    parent_id: Optional[str] = Field(
        default=None, description="父分类 ID（空表示顶级分类）"
    )
    category_type: Optional[str] = Field(
        default=None, description="分类类型（顶级分类必填）"
    )
    description: Optional[str] = Field(default=None, max_length=500, description="描述")
    icon: Optional[str] = Field(default=None, max_length=50, description="图标")
    color: Optional[str] = Field(default=None, max_length=20, description="颜色")


class PromoteToGlobalRequest(BaseModel):
    """提升语料到全局"""

    source_node_id: str = Field(..., description="源节点 ID")
    source_tenant_code: str = Field(..., description="源租户编码")
    target_parent_id: Optional[str] = Field(
        default=None, description="目标父节点 ID（全局分类 ID）"
    )
    copy_children: bool = Field(default=True, description="是否复制子节点")


class ResponseData(BaseModel):
    """统一响应格式"""

    code: int = 0
    message: str = "success"
    data: Optional[dict | list] = None


# ==================== 全局语料 API ====================


@router.get("/tree", response_model=ResponseData)
async def get_global_corpus_tree(
    db: AsyncSessionDep,
    category_type: Optional[str] = Query(default=None, description="分类类型筛选"),
):
    """
    获取全局公共语料树

    仅返回全局租户 (__global__) 下的语料
    """
    service = CategoryService(db)
    tree = await service.get_tree(
        tenant_code=settings.GLOBAL_TENANT_CODE,
        root_category_type=category_type,
        include_global=False,  # 不需要再包含全局，因为本身就是全局
    )
    return ResponseData(data=tree)


@router.post("/", response_model=ResponseData)
async def create_global_corpus(
    data: GlobalCorpusCreate,
    db: AsyncSessionDep,
):
    """
    创建全局语料分类

    需要超级管理员权限
    """
    service = CategoryService(db)

    parent_id = int(data.parent_id) if data.parent_id else None

    result = await service.create_category(
        name=data.name,
        label=data.label,
        parent_id=parent_id,
        category_type=data.category_type,
        description=data.description,
        icon=data.icon,
        color=data.color,
        tenant_code=settings.GLOBAL_TENANT_CODE,
    )

    return ResponseData(data=result, message="全局语料创建成功")


@router.post("/promote", response_model=ResponseData)
async def promote_to_global(
    data: PromoteToGlobalRequest,
    db: AsyncSessionDep,
):
    """
    将租户语料提升为全局语料

    复制语料节点到全局租户，保留原始节点

    需要超级管理员权限
    """
    service = CategoryService(db)

    source_id = int(data.source_node_id)
    target_parent = int(data.target_parent_id) if data.target_parent_id else None

    # 使用复制功能，但目标是全局租户
    result = await service.copy_subtree_to_global(
        source_node_id=source_id,
        source_tenant_code=data.source_tenant_code,
        target_parent_id=target_parent,
    )

    if not result:
        raise HTTPException(status_code=404, detail="源节点不存在")

    return ResponseData(data=result, message="语料已提升为全局")


@router.get("/stats", response_model=ResponseData)
async def get_global_corpus_stats(
    db: AsyncSessionDep,
):
    """
    获取全局语料统计

    返回各分类类型的语料数量
    """
    from sqlalchemy import and_, func, select

    from app.models.graph import GraphNode

    # 统计全局语料数量
    stmt = (
        select(
            func.count(GraphNode.id).label("total_count"),
        )
        .where(
            and_(
                GraphNode.tenant_code == settings.GLOBAL_TENANT_CODE,
                GraphNode.is_deleted == 0,
                GraphNode.is_active == 1,
            )
        )
    )
    result = await db.execute(stmt)
    row = result.fetchone()
    total_count = row.total_count if row else 0

    return ResponseData(
        data={
            "total_count": total_count,
            "tenant_code": settings.GLOBAL_TENANT_CODE,
        }
    )
