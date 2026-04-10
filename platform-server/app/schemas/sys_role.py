"""
System Role schemas
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


# ============== 基础 Schema ==============

class RoleBase(BaseModel):
    """角色基础信息"""
    role_code: str = Field(..., min_length=1, max_length=64, description="角色编码")
    role_name: str = Field(..., min_length=1, max_length=64, description="角色名称")
    description: Optional[str] = Field(None, max_length=255, description="描述")
    status: int = Field(default=1, ge=0, le=1, description="状态: 0禁用 1启用")


class RoleCreate(RoleBase):
    """创建角色"""
    menu_ids: Optional[List[str]] = Field(default=[], description="菜单ID列表")


class RoleUpdate(BaseModel):
    """更新角色"""
    role_name: Optional[str] = Field(None, min_length=1, max_length=64, description="角色名称")
    description: Optional[str] = Field(None, max_length=255, description="描述")
    status: Optional[int] = Field(None, ge=0, le=1, description="状态: 0禁用 1启用")
    menu_ids: Optional[List[str]] = Field(None, description="菜单ID列表")


class RoleResponse(RoleBase):
    """角色响应"""
    id: str = Field(..., description="角色ID")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    menu_ids: List[str] = Field(default=[], description="菜单ID列表")
    
    class Config:
        from_attributes = True


class RoleListResponse(BaseModel):
    """角色列表响应"""
    total: int = Field(..., description="总数")
    items: List[RoleResponse] = Field(..., description="角色列表")


# ============== 查询参数 ==============

class RoleFilters(BaseModel):
    """角色查询过滤"""
    role_code: Optional[str] = Field(None, description="角色编码（精确匹配）")
    role_name: Optional[str] = Field(None, description="角色名称（模糊匹配）")
    status: Optional[int] = Field(None, description="状态")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量")


# ============== 角色菜单分配 ==============

class RoleMenuAssign(BaseModel):
    """角色菜单分配"""
    menu_ids: List[str] = Field(..., description="菜单ID列表")


class RoleMenuAssignByRoleCode(BaseModel):
    """按 role_code 分配角色菜单（支持 merge/replace）"""

    role_code: str = Field(..., min_length=1, max_length=64, description="角色编码（如 admin）")
    menu_ids: List[str] = Field(..., description="要授予的菜单ID列表")
    mode: str = Field(default="merge", pattern="^(merge|replace)$", description="授权模式：merge 追加；replace 覆盖")


# ============== 角色用户 ==============

class RoleUserItem(BaseModel):
    """角色下的用户"""
    id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    name: Optional[str] = Field(None, description="姓名")
    email: Optional[str] = Field(None, description="邮箱")
    avatar: Optional[str] = Field(None, description="头像")
    
    class Config:
        from_attributes = True


class RoleUserListResponse(BaseModel):
    """角色用户列表响应"""
    total: int = Field(..., description="总数")
    items: List[RoleUserItem] = Field(..., description="用户列表")


class RoleUserAssign(BaseModel):
    """角色用户分配"""
    user_ids: List[str] = Field(..., description="用户ID列表")


# ============== 简单角色列表（下拉框用）==============

class RoleSimpleItem(BaseModel):
    """简单角色项"""
    id: str = Field(..., description="角色ID")
    role_code: str = Field(..., description="角色编码")
    role_name: str = Field(..., description="角色名称")
    
    class Config:
        from_attributes = True

