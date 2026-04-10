"""
Authentication schemas
"""
from datetime import datetime
from typing import Optional, List

from pydantic import Field

from app.schemas.base import BaseSchema


class LoginRequest(BaseSchema):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")
    token_expire_minutes: Optional[int] = Field(
        default=None,
        ge=5,  # 最小 5 分钟
        le=43200,  # 最大 30 天
        description="Token 过期时间（分钟），不传则使用系统默认值"
    )


class LoginResponse(BaseSchema):
    """登录响应"""
    id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    name: Optional[str] = Field(default=None, description="姓名")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    token: str = Field(..., description="访问令牌")
    access_token: str = Field(..., description="访问令牌（兼容字段）")
    expire_time: int = Field(..., description="过期时间戳（秒）")


class UserInfoResponse(BaseSchema):
    """用户信息响应"""
    id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    name: Optional[str] = Field(default=None, description="姓名")
    email: Optional[str] = Field(default=None, description="邮箱")
    phone: Optional[str] = Field(default=None, description="手机号")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    dept_id: Optional[str] = Field(default=None, description="部门ID")
    status: int = Field(default=1, description="状态")
    roles: List[str] = Field(default=[], description="角色编码列表")
    permissions: List[str] = Field(default=[], description="权限码列表")


class MenuTreeItem(BaseSchema):
    """菜单树节点"""
    id: str = Field(..., description="菜单ID")
    parent_id: str = Field(default="0", description="父菜单ID")
    menu_name: str = Field(..., description="菜单名称")
    menu_type: str = Field(..., description="类型: M目录 C菜单 F按钮")
    path: Optional[str] = Field(default=None, description="路由路径")
    component: Optional[str] = Field(default=None, description="组件路径")
    icon: Optional[str] = Field(default=None, description="图标")
    perm_code: Optional[str] = Field(default=None, description="权限标识")
    sort_order: int = Field(default=0, description="排序")
    visible: int = Field(default=1, description="是否可见")
    children: List["MenuTreeItem"] = Field(default=[], description="子菜单")


class MenuListResponse(BaseSchema):
    """菜单列表响应"""
    menus: List[MenuTreeItem] = Field(default=[], description="菜单树")


class PermCodeResponse(BaseSchema):
    """权限码列表响应"""
    perm_codes: List[str] = Field(default=[], description="权限码列表")


class UserProfileUpdate(BaseSchema):
    """个人信息更新"""
    name: Optional[str] = Field(None, max_length=64, description="姓名")
    email: Optional[str] = Field(None, max_length=128, description="邮箱")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    avatar: Optional[str] = Field(None, max_length=255, description="头像URL")


class UserPasswordUpdate(BaseSchema):
    """修改密码"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")

