"""
System Role-Menu association model
"""
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, BigInteger, ForeignKey, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class SysRoleMenu(Base):
    """角色菜单关联表"""
    __tablename__ = "sys_role_menu"
    
    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )
    role_id = Column(String(64), ForeignKey("sys_role.id"), nullable=False, index=True, comment="角色ID")
    menu_id = Column(String(64), ForeignKey("sys_menu.id"), nullable=False, index=True, comment="菜单ID")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    
    # 关系
    role = relationship("SysRole", back_populates="menus")
    menu = relationship("SysMenu", back_populates="roles")
    
    def __repr__(self):
        return f"<SysRoleMenu(role_id={self.role_id}, menu_id={self.menu_id})>"
