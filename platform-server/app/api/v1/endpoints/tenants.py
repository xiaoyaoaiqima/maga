"""
租户管理 API
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.tenant_service import TenantService
from app.schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantListResponse,
    TenantFilters,
    TenantSimpleItem,
)
from app.schemas.base import ResponseModel

router = APIRouter(prefix="/tenants", tags=["租户管理"])


def get_tenant_service(db: AsyncSession = Depends(get_db)) -> TenantService:
    """获取租户服务实例"""
    return TenantService(db)


@router.post("", response_model=ResponseModel, summary="创建租户")
async def create_tenant(
    data: TenantCreate,
    service: TenantService = Depends(get_tenant_service)
):
    """
    创建租户
    
    - **tenant_code**: 租户编码（唯一）
    - **tenant_name**: 租户名称
    - **contact_name**: 联系人姓名
    - **contact_phone**: 联系电话
    - **contact_email**: 联系邮箱
    - **quota_config**: 配额配置
    - **status**: 状态（ACTIVE/SUSPENDED/EXPIRED）
    - **expire_time**: 服务到期时间
    """
    try:
        tenant = await service.create_tenant(data)
        return ResponseModel(code=200, message="创建成功", data=tenant.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=ResponseModel, summary="获取租户列表")
async def list_tenants(
    tenant_code: Optional[str] = Query(None, description="租户编码（模糊匹配）"),
    tenant_name: Optional[str] = Query(None, description="租户名称（模糊匹配）"),
    status: Optional[str] = Query(None, description="状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    service: TenantService = Depends(get_tenant_service)
):
    """获取租户列表（分页）"""
    filters = TenantFilters(
        tenant_code=tenant_code,
        tenant_name=tenant_name,
        status=status,
        page=page,
        page_size=page_size
    )
    total, items = await service.list_tenants(filters)
    return ResponseModel(
        code=200,
        message="success",
        data=TenantListResponse(total=total, items=items).model_dump()
    )


@router.get("/simple", response_model=ResponseModel, summary="获取简单租户列表")
async def list_tenants_simple(
    service: TenantService = Depends(get_tenant_service)
):
    """获取简单租户列表（用于下拉框）"""
    items = await service.list_simple()
    return ResponseModel(
        code=200,
        message="success",
        data=[item.model_dump() for item in items]
    )


@router.get("/{tenant_id}", response_model=ResponseModel, summary="获取租户详情")
async def get_tenant(
    tenant_id: int,
    service: TenantService = Depends(get_tenant_service)
):
    """获取租户详情"""
    tenant = await service.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    return ResponseModel(code=200, message="success", data=tenant.model_dump())


@router.put("/{tenant_id}", response_model=ResponseModel, summary="更新租户")
async def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    service: TenantService = Depends(get_tenant_service)
):
    """更新租户信息"""
    tenant = await service.update_tenant(tenant_id, data)
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    return ResponseModel(code=200, message="更新成功", data=tenant.model_dump())


@router.delete("/{tenant_id}", response_model=ResponseModel, summary="删除租户")
async def delete_tenant(
    tenant_id: int,
    service: TenantService = Depends(get_tenant_service)
):
    """删除租户（软删除）"""
    success = await service.delete_tenant(tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="租户不存在")
    return ResponseModel(code=200, message="删除成功")
