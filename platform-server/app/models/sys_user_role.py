"""
System User-Role association model
"""
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, BigInteger, ForeignKey, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class SysUserRole(Base):
    """用户角色关联表"""
    __tablename__ = "sys_user_role"
    
    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )
    user_id = Column(String(64), ForeignKey("sys_user.id"), nullable=False, index=True, comment="用户ID")
    role_id = Column(String(64), ForeignKey("sys_role.id"), nullable=False, index=True, comment="角色ID")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    
    # 关系
    user = relationship("SysUser", back_populates="roles")
    role = relationship("SysRole", back_populates="users")
    
    def __repr__(self):
        return f"<SysUserRole(user_id={self.user_id}, role_id={self.role_id})>"
