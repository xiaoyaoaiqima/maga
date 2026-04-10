from typing import Optional, Any
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.utils.jwt_utils import decode_token
from app.models.sys_user import SysUser
from app.services.auth_service import AuthService

# Export get_db
get_db = get_db

async def get_current_user_id(
    authorization: Optional[str] = Header(None, description="Bearer Token")
) -> str:
    """
    从 Authorization header 获取当前用户ID
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证格式",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload.user_id


async def get_current_user_id_optional(
    authorization: Optional[str] = Header(None, description="Bearer Token"),
) -> Optional[str]:
    """
    从 Authorization header 获取当前用户ID（可选）

    - 未提供/格式不合法/解码失败：返回 None
    - 解码成功：返回 user_id
    """
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    return payload.user_id


async def get_current_username(
    authorization: Optional[str] = Header(None, description="Bearer Token")
) -> Optional[str]:
    """
    从 Authorization header 获取当前用户名

    用于记录操作日志，获取用户名（name 或 username）

    Returns:
        用户名（优先返回 name，如果不存在则返回 username）
        未登录或解码失败返回 "system"
    """
    if not authorization:
        return "system"

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return "system"

    payload = decode_token(token)
    if not payload:
        return "system"

    # 优先返回 name（显示名称），如果不存在则返回 username
    return payload.name if payload.name else payload.username

async def get_current_active_user(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SysUser:
    """
    获取当前激活用户
    """
    result = await db.execute(
        select(SysUser).where(SysUser.id == user_id, SysUser.is_deleted == 0)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
        
    if user.status != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已禁用"
        )
        
    return user


def require_perm_code(perm_code: str):
    """
    权限码校验依赖（403）

    用法：
    - 在 router 上加 Depends(require_perm_code('xxx:yyy'))
    """

    async def _checker(
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
    ) -> str:
        perms = await AuthService(db).get_user_perm_codes(user_id)
        if perm_code not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return user_id

    return _checker

