"""
System User model
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, String, Integer, DateTime, Text, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class SysUser(Base):
    """系统用户表"""
    __tablename__ = "sys_user"
    
    id = Column(String(64), primary_key=True, comment="用户ID")
    username = Column(String(64), unique=True, nullable=False, index=True, comment="用户名")
    password = Column(String(255), nullable=False, comment="密码(bcrypt)")
    name = Column(String(64), nullable=True, comment="姓名")
    email = Column(String(128), nullable=True, comment="邮箱")
    phone = Column(String(20), nullable=True, comment="手机号")
    avatar = Column(String(255), nullable=True, comment="头像URL")
    dept_id = Column(String(64), nullable=True, comment="部门ID")
    status = Column(Integer, default=1, comment="状态: 0禁用 1启用")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    is_deleted = Column(Integer, default=0, comment="是否删除: 0否 1是")
    
    # 关系
    roles = relationship("SysUserRole", back_populates="user", lazy="selectin")
    
    def __repr__(self):
        return f"<SysUser(id={self.id}, username={self.username})>"

