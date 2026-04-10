"""
System Menu model
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, String, Integer, DateTime, Text, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class SysMenu(Base):
    """系统菜单表"""
    __tablename__ = "sys_menu"
    
    id = Column(String(64), primary_key=True, comment="菜单ID")
    parent_id = Column(String(64), default="0", comment="父菜单ID")
    menu_name = Column(String(64), nullable=False, comment="菜单名称")
    menu_type = Column(String(1), nullable=False, comment="类型: M目录 C菜单 F按钮")
    path = Column(String(255), nullable=True, comment="路由路径")
    component = Column(String(255), nullable=True, comment="组件路径")
    icon = Column(String(64), nullable=True, comment="图标")
    perm_code = Column(String(128), nullable=True, comment="权限标识")
    sort_order = Column(Integer, default=0, comment="排序")
    visible = Column(Integer, default=1, comment="是否可见: 0否 1是")
    status = Column(Integer, default=1, comment="状态: 0禁用 1启用")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    is_deleted = Column(Integer, default=0, comment="是否删除: 0否 1是")
    
    # 关系
    roles = relationship("SysRoleMenu", back_populates="menu", lazy="selectin")
    
    def __repr__(self):
        return f"<SysMenu(id={self.id}, menu_name={self.menu_name})>"

