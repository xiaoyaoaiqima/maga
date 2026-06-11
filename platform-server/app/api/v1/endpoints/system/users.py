"""
用户管理 API
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sys_user_service import SysUserService
from app.schemas.sys_user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    UserFilters,
    UserRoleAssign,
    PasswordUpdate,
    UserSimpleItem,
)
from app.schemas.base import ResponseModel

router = APIRouter(prefix="/users", tags=["用户管理"])


def get_user_service(db: AsyncSession = Depends(get_db)) -> SysUserService:
    """获取用户服务实例"""
    return SysUserService(db)


@router.post("", response_model=ResponseModel, summary="创建用户")
async def create_user(
    data: UserCreate,
    service: SysUserService = Depends(get_user_service)
):
    """
    创建用户
    
    - **username**: 用户名（唯一）
    - **password**: 密码（至少6位）
    - **name**: 姓名
    - **email**: 邮箱
    - **phone**: 手机号
    - **status**: 状态（0禁用 1启用）
    - **role_ids**: 角色ID列表
    """
    try:
        user = await service.create_user(data)
        return ResponseModel(code=200, message="创建成功", data=user.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}", response_model=ResponseModel, summary="更新用户")
async def update_user(
    user_id: str,
    data: UserUpdate,
    service: SysUserService = Depends(get_user_service)
):
    """更新用户信息"""
    try:
        user = await service.update_user(user_id, data)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return ResponseModel(code=200, message="更新成功", data=user.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_id}", response_model=ResponseModel, summary="删除用户")
async def delete_user(
    user_id: str,
    service: SysUserService = Depends(get_user_service)
):
    """
    删除用户（软删除）
    
    注意：系统管理员账户不允许删除
    """
    try:
        success = await service.delete_user(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="用户不存在")
        return ResponseModel(code=200, message="删除成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=ResponseModel, summary="查询用户列表")
async def get_users(
    username: Optional[str] = Query(None, description="用户名"),
    name: Optional[str] = Query(None, description="姓名"),
    email: Optional[str] = Query(None, description="邮箱"),
    phone: Optional[str] = Query(None, description="手机号"),
    status: Optional[int] = Query(None, description="状态"),
    role_id: Optional[str] = Query(None, description="角色ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    service: SysUserService = Depends(get_user_service)
):
    """
    查询用户列表，支持分页和过滤
    
    - **username**: 用户名（模糊匹配）
    - **name**: 姓名（模糊匹配）
    - **email**: 邮箱（模糊匹配）
    - **phone**: 手机号（模糊匹配）
    - **status**: 状态
    - **role_id**: 角色ID
    """
    filters = UserFilters(
        username=username,
        name=name,
        email=email,
        phone=phone,
        status=status,
        role_id=role_id,
        page=page,
        page_size=page_size
    )
    total, items = await service.get_users(filters)
    
    return ResponseModel(
        code=200,
        message="success",
        data=UserListResponse(
            total=total,
            items=items
        ).model_dump()
    )


@router.get("/list/all", response_model=ResponseModel, summary="获取所有用户（下拉框用）")
async def get_all_users(
    service: SysUserService = Depends(get_user_service)
):
    """获取所有启用的用户，用于下拉框选择"""
    users = await service.get_all_users()
    return ResponseModel(
        code=200,
        message="success",
        data=[user.model_dump() for user in users]
    )


@router.get("/{user_id}", response_model=ResponseModel, summary="获取用户详情")
async def get_user(
    user_id: str,
    service: SysUserService = Depends(get_user_service)
):
    """获取用户详情"""
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ResponseModel(code=200, message="success", data=user.model_dump())


@router.put("/{user_id}/password", response_model=ResponseModel, summary="重置用户密码")
async def reset_password(
    user_id: str,
    data: PasswordUpdate,
    service: SysUserService = Depends(get_user_service)
):
    """
    重置用户密码（管理员操作）
    
    - **new_password**: 新密码（至少6位）
    """
    success = await service.reset_password(user_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ResponseModel(code=200, message="密码重置成功")


@router.put("/{user_id}/roles", response_model=ResponseModel, summary="分配用户角色")
async def assign_user_roles(
    user_id: str,
    data: UserRoleAssign,
    service: SysUserService = Depends(get_user_service)
):
    """分配用户角色"""
    success = await service.assign_roles(user_id, data.role_ids)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ResponseModel(code=200, message="分配成功")


@router.get("/{user_id}/roles", response_model=ResponseModel, summary="获取用户角色")
async def get_user_roles(
    user_id: str,
    service: SysUserService = Depends(get_user_service)
):
    """获取用户的角色ID列表"""
    role_ids = await service.get_user_roles(user_id)
    return ResponseModel(code=200, message="success", data=role_ids)
