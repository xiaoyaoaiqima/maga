"""
System Menu schemas
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


# ============== 基础 Schema ==============

class MenuBase(BaseModel):
    """菜单基础信息"""
    menu_name: str = Field(..., min_length=1, max_length=64, description="菜单名称")
    menu_type: str = Field(..., pattern="^[MCF]$", description="类型: M目录 C菜单 F按钮")
    parent_id: str = Field(default="0", description="父菜单ID")
    path: Optional[str] = Field(None, max_length=255, description="路由路径")
    component: Optional[str] = Field(None, max_length=255, description="组件路径")
    icon: Optional[str] = Field(None, max_length=64, description="图标")
    perm_code: Optional[str] = Field(None, max_length=128, description="权限标识")
    sort_order: int = Field(default=0, description="排序")
    visible: int = Field(default=1, ge=0, le=1, description="是否可见: 0否 1是")
    status: int = Field(default=1, ge=0, le=1, description="状态: 0禁用 1启用")


class MenuCreate(MenuBase):
    """创建菜单"""
    pass


class MenuUpdate(BaseModel):
    """更新菜单"""
    menu_name: Optional[str] = Field(None, min_length=1, max_length=64, description="菜单名称")
    menu_type: Optional[str] = Field(None, pattern="^[MCF]$", description="类型: M目录 C菜单 F按钮")
    parent_id: Optional[str] = Field(None, description="父菜单ID")
    path: Optional[str] = Field(None, max_length=255, description="路由路径")
    component: Optional[str] = Field(None, max_length=255, description="组件路径")
    icon: Optional[str] = Field(None, max_length=64, description="图标")
    perm_code: Optional[str] = Field(None, max_length=128, description="权限标识")
    sort_order: Optional[int] = Field(None, description="排序")
    visible: Optional[int] = Field(None, ge=0, le=1, description="是否可见")
    status: Optional[int] = Field(None, ge=0, le=1, description="状态")


class MenuResponse(MenuBase):
    """菜单响应"""
    id: str = Field(..., description="菜单ID")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    
    class Config:
        from_attributes = True


class MenuTreeItem(BaseModel):
    """菜单树节点"""
    id: str = Field(..., description="菜单ID")
    parent_id: str = Field(default="0", description="父菜单ID")
    menu_name: str = Field(..., description="菜单名称")
    menu_type: str = Field(..., description="类型")
    path: Optional[str] = Field(None, description="路由路径")
    component: Optional[str] = Field(None, description="组件路径")
    icon: Optional[str] = Field(None, description="图标")
    perm_code: Optional[str] = Field(None, description="权限标识")
    sort_order: int = Field(default=0, description="排序")
    visible: int = Field(default=1, description="是否可见")
    children: List["MenuTreeItem"] = Field(default=[], description="子菜单")
    
    class Config:
        from_attributes = True


# 用于权限配置的简化菜单树
class MenuTreeSimple(BaseModel):
    """简化菜单树（用于角色权限配置）"""
    key: str = Field(..., description="菜单ID")
    title: str = Field(..., description="菜单名称")
    children: List["MenuTreeSimple"] = Field(default=[], description="子菜单")


# ============== 查询参数 ==============

class MenuFilters(BaseModel):
    """菜单查询过滤"""
    menu_name: Optional[str] = Field(None, description="菜单名称（模糊匹配）")
    menu_type: Optional[str] = Field(None, description="类型")
    status: Optional[int] = Field(None, description="状态")


# ============== 导入相关 ==============

class MenuImportItem(BaseModel):
    """单个导入菜单项"""
    id: Optional[str] = Field(None, description="原菜单ID（用于保持层级关系）")
    parent_id: str = Field(default="0", description="父菜单ID")
    menu_name: str = Field(..., min_length=1, max_length=64, description="菜单名称")
    menu_type: str = Field(..., pattern="^[MCF]$", description="类型: M目录 C菜单 F按钮")
    path: Optional[str] = Field(None, max_length=255, description="路由路径")
    component: Optional[str] = Field(None, max_length=255, description="组件路径")
    icon: Optional[str] = Field(None, max_length=64, description="图标")
    perm_code: Optional[str] = Field(None, max_length=128, description="权限标识")
    sort_order: int = Field(default=0, description="排序")
    visible: int = Field(default=1, ge=0, le=1, description="是否可见")


class MenuImportRequest(BaseModel):
    """菜单导入请求"""
    menus: List[MenuImportItem] = Field(..., min_length=1, description="菜单列表")
    mode: str = Field(default="append", pattern="^(append|replace)$", description="导入模式: append追加 replace覆盖")
    role_codes: List[str] = Field(default=["admin"], description="分配给哪些角色")


class MenuImportResult(BaseModel):
    """菜单导入结果"""
    total: int = Field(..., description="总数")
    created: int = Field(..., description="新建数量")
    skipped: int = Field(..., description="跳过数量（已存在）")
    skipped_paths: List[str] = Field(default=[], description="跳过的路由路径")
    assigned_roles: List[str] = Field(default=[], description="已分配权限的角色")


# 解决循环引用
MenuTreeItem.model_rebuild()
MenuTreeSimple.model_rebuild()

