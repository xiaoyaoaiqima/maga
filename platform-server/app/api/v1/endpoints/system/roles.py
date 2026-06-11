"""
角色管理 API
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sys_role_service import SysRoleService
from app.schemas.sys_role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse,
    RoleFilters,
    RoleMenuAssign,
    RoleMenuAssignByRoleCode,
    RoleUserListResponse,
    RoleUserAssign,
    RoleSimpleItem,
)
from app.schemas.base import ResponseModel

router = APIRouter(prefix="/roles", tags=["角色管理"])


def get_role_service(db: AsyncSession = Depends(get_db)) -> SysRoleService:
    """获取角色服务实例"""
    return SysRoleService(db)


@router.post("", response_model=ResponseModel, summary="创建角色")
async def create_role(
    data: RoleCreate,
    service: SysRoleService = Depends(get_role_service)
):
    """
    创建角色
    
    - **role_code**: 角色编码（唯一）
    - **role_name**: 角色名称
    - **description**: 角色描述
    - **status**: 状态（0禁用 1启用）
    - **menu_ids**: 菜单ID列表
    """
    try:
        role = await service.create_role(data)
        return ResponseModel(code=200, message="创建成功", data=role.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{role_id}", response_model=ResponseModel, summary="更新角色")
async def update_role(
    role_id: str,
    data: RoleUpdate,
    service: SysRoleService = Depends(get_role_service)
):
    """更新角色信息"""
    role = await service.update_role(role_id, data)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return ResponseModel(code=200, message="更新成功", data=role.model_dump())


@router.delete("/{role_id}", response_model=ResponseModel, summary="删除角色")
async def delete_role(
    role_id: str,
    service: SysRoleService = Depends(get_role_service)
):
    """
    删除角色（软删除）
    
    注意：系统管理员角色不允许删除，有用户关联的角色需要先移除用户
    """
    try:
        success = await service.delete_role(role_id)
        if not success:
            raise HTTPException(status_code=404, detail="角色不存在")
        return ResponseModel(code=200, message="删除成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/assign-menus-by-role-code",
    response_model=ResponseModel,
    summary="按角色编码分配菜单（merge/replace）",
)
async def assign_role_menus_by_role_code(
    data: RoleMenuAssignByRoleCode,
    service: SysRoleService = Depends(get_role_service),
):
    """按 role_code 分配角色菜单权限（用于自动化授权）"""
    try:
        role_id, menu_ids = await service.assign_menus_by_role_code(
            role_code=data.role_code,
            menu_ids=data.menu_ids,
            mode=data.mode,
        )
    except ValueError as e:
        message = str(e)
        if message == "角色不存在":
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    return ResponseModel(
        code=200,
        message="分配成功",
        data={"role_id": role_id, "menu_ids": menu_ids},
    )


@router.get("", response_model=ResponseModel, summary="查询角色列表")
async def get_roles(
    role_code: Optional[str] = Query(None, description="角色编码"),
    role_name: Optional[str] = Query(None, description="角色名称"),
    status: Optional[int] = Query(None, description="状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    service: SysRoleService = Depends(get_role_service)
):
    """
    查询角色列表，支持分页和过滤
    
    - **role_code**: 角色编码（精确匹配）
    - **role_name**: 角色名称（模糊匹配）
    - **status**: 状态
    """
    filters = RoleFilters(
        role_code=role_code,
        role_name=role_name,
        status=status,
        page=page,
        page_size=page_size
    )
    total, items = await service.get_roles(filters)
    
    return ResponseModel(
        code=200,
        message="success",
        data=RoleListResponse(
            total=total,
            items=items
        ).model_dump()
    )


@router.get("/list/all", response_model=ResponseModel, summary="获取所有角色（下拉框用）")
async def get_all_roles(
    service: SysRoleService = Depends(get_role_service)
):
    """获取所有启用的角色，用于下拉框选择"""
    roles = await service.get_all_roles()
    return ResponseModel(
        code=200,
        message="success",
        data=[role.model_dump() for role in roles]
    )


@router.get("/{role_id}", response_model=ResponseModel, summary="获取角色详情")
async def get_role(
    role_id: str,
    service: SysRoleService = Depends(get_role_service)
):
    """获取角色详情"""
    role = await service.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return ResponseModel(code=200, message="success", data=role.model_dump())


@router.put("/{role_id}/menus", response_model=ResponseModel, summary="分配角色菜单")
async def assign_role_menus(
    role_id: str,
    data: RoleMenuAssign,
    service: SysRoleService = Depends(get_role_service)
):
    """分配角色菜单权限"""
    success = await service.assign_menus(role_id, data.menu_ids)
    if not success:
        raise HTTPException(status_code=404, detail="角色不存在")
    return ResponseModel(code=200, message="分配成功")


@router.get("/{role_id}/menus", response_model=ResponseModel, summary="获取角色菜单")
async def get_role_menus(
    role_id: str,
    service: SysRoleService = Depends(get_role_service)
):
    """获取角色的菜单ID列表"""
    menu_ids = await service.get_role_menus(role_id)
    return ResponseModel(code=200, message="success", data=menu_ids)


@router.get("/{role_id}/users", response_model=ResponseModel, summary="获取角色下的用户")
async def get_role_users(
    role_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    service: SysRoleService = Depends(get_role_service)
):
    """获取角色下的用户列表"""
    total, items = await service.get_role_users(role_id, page, page_size)
    return ResponseModel(
        code=200,
        message="success",
        data=RoleUserListResponse(
            total=total,
            items=items
        ).model_dump()
    )


@router.post("/{role_id}/users", response_model=ResponseModel, summary="添加用户到角色")
async def add_users_to_role(
    role_id: str,
    data: RoleUserAssign,
    service: SysRoleService = Depends(get_role_service)
):
    """添加用户到角色"""
    try:
        added_count = await service.add_users_to_role(role_id, data.user_ids)
        return ResponseModel(code=200, message=f"成功添加 {added_count} 个用户")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{role_id}/users/{user_id}", response_model=ResponseModel, summary="从角色移除用户")
async def remove_user_from_role(
    role_id: str,
    user_id: str,
    service: SysRoleService = Depends(get_role_service)
):
    """从角色中移除用户"""
    await service.remove_user_from_role(role_id, user_id)
    return ResponseModel(code=200, message="移除成功")
