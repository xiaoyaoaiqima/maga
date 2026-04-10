"""
元数据管理 API

管理品牌、产品、标签等元数据配置
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.schemas.metadata import (
    LabelTypesResponse,
    MetadataItemCreate,
    MetadataItemResponse,
    MetadataItemUpdate,
    MetadataStatsResponse,
    MetadataTreeNode,
    MetadataType,
    SimpleOption,
)
from app.services.metadata_service import MetadataService

router = APIRouter(prefix="/metadata", tags=["元数据管理"])


# ==================== 响应格式 ====================


class ResponseData(BaseModel):
    """统一响应格式"""
    code: int = 200
    message: str = "success"
    data: Optional[dict | list] = None


# ==================== 通用 CRUD ====================


@router.post("/items", response_model=ResponseData)
async def create_item(
    db: AsyncSessionDep,
    data: MetadataItemCreate,
    tenant_code: str = Query(..., description="租户编码"),
):
    """
    创建元数据项
    
    支持创建：品牌(brand)、产品(product)、标签组(tag_group)、标签(tag)
    """
    service = MetadataService(db)
    result = await service.create_item(tenant_code, data)
    return ResponseData(data=result.model_dump(), message="创建成功")


@router.put("/items/{item_id}", response_model=ResponseData)
async def update_item(
    item_id: str,
    data: MetadataItemUpdate,
    db: AsyncSessionDep,
):
    """
    更新元数据项
    """
    service = MetadataService(db)
    result = await service.update_item(int(item_id), data)
    if not result:
        raise HTTPException(status_code=404, detail="元数据项不存在")
    return ResponseData(data=result.model_dump(), message="更新成功")


@router.delete("/items/{item_id}", response_model=ResponseData)
async def delete_item(
    item_id: str,
    db: AsyncSessionDep,
):
    """
    删除元数据项
    """
    service = MetadataService(db)
    success = await service.delete_item(int(item_id))
    if not success:
        raise HTTPException(status_code=404, detail="元数据项不存在")
    return ResponseData(message="删除成功")


@router.get("/items/{item_id}", response_model=ResponseData)
async def get_item(
    item_id: str,
    db: AsyncSessionDep,
):
    """
    获取单个元数据项
    """
    service = MetadataService(db)
    result = await service.get_item(int(item_id))
    if not result:
        raise HTTPException(status_code=404, detail="元数据项不存在")
    return ResponseData(data=result.model_dump())


@router.get("/items", response_model=ResponseData)
async def list_items(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
    item_type: Optional[MetadataType] = Query(None, description="元数据类型"),
    parent_id: Optional[str] = Query(None, description="父级 ID"),
    include_inactive: bool = Query(False, description="是否包含禁用项"),
):
    """
    列出元数据项
    """
    service = MetadataService(db)
    result = await service.list_items(
        tenant_code,
        item_type,
        parent_id=int(parent_id) if parent_id else None,
        include_inactive=include_inactive,
    )
    return ResponseData(data=[r.model_dump() for r in result])


# ==================== 品牌与产品 ====================


@router.get("/brands/tree", response_model=ResponseData)
async def get_brand_tree(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
):
    """
    获取品牌-产品树
    
    用于左侧树形展示
    """
    service = MetadataService(db)
    tree = await service.get_brand_tree(tenant_code)
    return ResponseData(data=[t.model_dump() for t in tree])


@router.get("/brands/options", response_model=ResponseData)
async def get_brand_options(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
):
    """
    获取品牌选项
    
    用于下拉选择
    """
    service = MetadataService(db)
    options = await service.get_brand_options(tenant_code)
    return ResponseData(data=[o.model_dump() for o in options])


@router.get("/products/options", response_model=ResponseData)
async def get_product_options(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
    brand_id: Optional[str] = Query(None, description="品牌 ID（筛选该品牌下的产品）"),
):
    """
    获取产品选项
    
    用于 scope 设置时的下拉选择
    """
    service = MetadataService(db)
    options = await service.get_product_options(
        tenant_code,
        brand_id=int(brand_id) if brand_id else None,
    )
    return ResponseData(data=[o.model_dump() for o in options])


# ==================== 标签管理 ====================


@router.get("/tags/tree", response_model=ResponseData)
async def get_tag_tree(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
):
    """
    获取标签组-标签树
    
    用于左侧树形展示
    """
    service = MetadataService(db)
    tree = await service.get_tag_tree(tenant_code)
    return ResponseData(data=[t.model_dump() for t in tree])


@router.get("/tags/options", response_model=ResponseData)
async def get_tag_options(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
    group_id: Optional[str] = Query(None, description="标签组 ID"),
):
    """
    获取标签选项
    
    用于语料编辑时的下拉选择
    """
    service = MetadataService(db)
    options = await service.get_tag_options(
        tenant_code,
        group_id=int(group_id) if group_id else None,
    )
    return ResponseData(data=[o.model_dump() for o in options])


# ==================== 统计 ====================


@router.get("/stats", response_model=ResponseData)
async def get_stats(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
):
    """
    获取元数据统计

    返回各类型元数据数量和语料统计
    """
    service = MetadataService(db)
    stats = await service.get_stats(tenant_code)
    return ResponseData(data=stats.model_dump())


# ==================== 统一标签树 ====================


@router.get("/tree", response_model=ResponseData)
async def get_unified_tree(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
):
    """
    获取统一的标签树

    合并品牌-产品树和标签组-标签树，返回所有类型的分组和标签
    用于统一的标签管理界面
    """
    service = MetadataService(db)
    tree = await service.get_unified_tree(tenant_code)
    return ResponseData(data=[t.model_dump() for t in tree])


# ==================== 统一标签类型 ====================


@router.get("/label-types", response_model=ResponseData)
async def get_label_types(
    db: AsyncSessionDep,
    tenant_code: str = Query(..., description="租户编码"),
):
    """
    获取所有标签类型（用于统一标签选择器）

    返回产品标签、标签组及其可选值
    """
    service = MetadataService(db)
    result = await service.get_label_types(tenant_code)
    return ResponseData(data=result.model_dump())
