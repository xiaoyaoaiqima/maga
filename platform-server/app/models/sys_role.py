"""
System Role model
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, String, Integer, DateTime, Text, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class SysRole(Base):
    """系统角色表"""
    __tablename__ = "sys_role"
    
    id = Column(String(64), primary_key=True, comment="角色ID")
    role_code = Column(String(64), unique=True, nullable=False, index=True, comment="角色编码")
    role_name = Column(String(64), nullable=False, comment="角色名称")
    description = Column(String(255), nullable=True, comment="描述")
    status = Column(Integer, default=1, comment="状态: 0禁用 1启用")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    is_deleted = Column(Integer, default=0, comment="是否删除: 0否 1是")
    
    # 关系
    users = relationship("SysUserRole", back_populates="role", lazy="selectin")
    menus = relationship("SysRoleMenu", back_populates="role", lazy="selectin")
    
    def __repr__(self):
        return f"<SysRole(id={self.id}, role_code={self.role_code})>"

