"""
System User schemas
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, EmailStr


# ============== 基础 Schema ==============

class UserBase(BaseModel):
    """用户基础信息"""
    username: str = Field(..., min_length=2, max_length=64, description="用户名")
    name: Optional[str] = Field(None, max_length=64, description="姓名")
    email: Optional[str] = Field(None, max_length=128, description="邮箱")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    avatar: Optional[str] = Field(None, max_length=255, description="头像URL")
    dept_id: Optional[str] = Field(None, max_length=64, description="部门ID")
    status: int = Field(default=1, ge=0, le=1, description="状态: 0禁用 1启用")


class UserCreate(UserBase):
    """创建用户"""
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    role_ids: Optional[List[str]] = Field(default=[], description="角色ID列表")


class UserUpdate(BaseModel):
    """更新用户"""
    name: Optional[str] = Field(None, max_length=64, description="姓名")
    email: Optional[str] = Field(None, max_length=128, description="邮箱")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    avatar: Optional[str] = Field(None, max_length=255, description="头像URL")
    dept_id: Optional[str] = Field(None, max_length=64, description="部门ID")
    status: Optional[int] = Field(None, ge=0, le=1, description="状态: 0禁用 1启用")
    role_ids: Optional[List[str]] = Field(None, description="角色ID列表")


class UserResponse(UserBase):
    """用户响应"""
    id: str = Field(..., description="用户ID")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    roles: List[str] = Field(default=[], description="角色编码列表")
    role_names: List[str] = Field(default=[], description="角色名称列表")
    
    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """用户列表响应"""
    total: int = Field(..., description="总数")
    items: List[UserResponse] = Field(..., description="用户列表")


# ============== 查询参数 ==============

class UserFilters(BaseModel):
    """用户查询过滤"""
    username: Optional[str] = Field(None, description="用户名（模糊匹配）")
    name: Optional[str] = Field(None, description="姓名（模糊匹配）")
    email: Optional[str] = Field(None, description="邮箱（模糊匹配）")
    phone: Optional[str] = Field(None, description="手机号（模糊匹配）")
    status: Optional[int] = Field(None, description="状态")
    role_id: Optional[str] = Field(None, description="角色ID")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量")


# ============== 密码相关 ==============

class PasswordUpdate(BaseModel):
    """重置密码"""
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")


class PasswordChange(BaseModel):
    """修改密码（需要旧密码）"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")


# ============== 用户角色分配 ==============

class UserRoleAssign(BaseModel):
    """用户角色分配"""
    role_ids: List[str] = Field(..., description="角色ID列表")


# ============== 简单用户列表（下拉框用）==============

class UserSimpleItem(BaseModel):
    """简单用户项"""
    id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    name: Optional[str] = Field(None, description="姓名")
    
    class Config:
        from_attributes = True

