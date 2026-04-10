"""
Authentication endpoints
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user_id
from app.schemas.base import ResponseData
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserInfoResponse,
    MenuTreeItem,
    UserProfileUpdate,
    UserPasswordUpdate,
)
from app.services.auth_service import AuthService
from app.services.sys_user_service import SysUserService
from app.schemas.sys_user import UserUpdate, PasswordChange
from app.utils.jwt_utils import decode_token

router = APIRouter()


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """依赖注入: 认证服务"""
    return AuthService(db)
    
    
@router.post("/login", response_model=ResponseData[LoginResponse])
async def login(
    login_req: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> ResponseData[LoginResponse]:
    """
    用户登录
    
    - **username**: 用户名
    - **password**: 密码
    """
    result = await service.login(login_req)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    return ResponseData(
        code=200,
        message="登录成功",
        data=result
    )


@router.post("/logout", response_model=ResponseData[None])
async def logout(
    user_id: str = Depends(get_current_user_id),
) -> ResponseData[None]:
    """
    用户登出
    """
    # TODO: 可以实现 token 黑名单机制
    return ResponseData(
        code=200,
        message="登出成功"
    )


@router.get("/userinfo", response_model=ResponseData[UserInfoResponse])
async def get_user_info(
    user_id: str = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> ResponseData[UserInfoResponse]:
    """
    获取当前用户信息
    """
    result = await service.get_user_info(user_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return ResponseData(
        code=200,
        message="success",
        data=result
    )


@router.get("/menus", response_model=ResponseData[list[MenuTreeItem]])
async def get_user_menus(
    user_id: str = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> ResponseData[list[MenuTreeItem]]:
    """
    获取当前用户菜单
    """
    menus = await service.get_user_menus(user_id)
    
    return ResponseData(
        code=200,
        message="success",
        data=menus
    )


@router.get("/perm-codes", response_model=ResponseData[list[str]])
async def get_perm_codes(
    user_id: str = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
) -> ResponseData[list[str]]:
    """
    获取当前用户权限码列表
    """
    perm_codes = await service.get_user_perm_codes(user_id)
    
    return ResponseData(
        code=200,
        message="success",
        data=perm_codes
    )


@router.put("/profile", response_model=ResponseData[None])
async def update_profile(
    data: UserProfileUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """修改个人信息"""
    service = SysUserService(db)
    # 转换为 UserUpdate，只允许修改部分字段
    update_data = UserUpdate(
        name=data.name,
        email=data.email,
        phone=data.phone,
        avatar=data.avatar
    )
    await service.update_user(user_id, update_data)
    return ResponseData(code=200, message="修改成功")


@router.put("/password", response_model=ResponseData[None])
async def update_password(
    data: UserPasswordUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """修改当前用户密码"""
    service = SysUserService(db)
    try:
        await service.change_password(
            user_id, 
            PasswordChange(old_password=data.old_password, new_password=data.new_password)
        )
        return ResponseData(code=200, message="修改成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

