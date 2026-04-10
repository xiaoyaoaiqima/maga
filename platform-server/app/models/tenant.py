"""
Tenant model - 租户表
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, JSON, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tenant(Base):
    """租户表 - 多甲方数据隔离"""
    
    __tablename__ = "tenant"
    
    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )
    
    # 租户标识
    tenant_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="租户编码（唯一标识）"
    )
    
    tenant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="租户名称"
    )
    
    # 联系信息
    contact_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="联系人姓名"
    )
    
    contact_phone: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="联系电话"
    )
    
    contact_email: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="联系邮箱"
    )
    
    # 配额与限制
    quota_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="配额配置（日限额、月限额、并发数等）"
    )

    # 鉴权凭证 (AK/SK)
    access_key: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
        comment="Access Key (AK)"
    )
    
    secret_key: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Secret Key (SK)"
    )
    
    # 状态
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ACTIVE",
        comment="状态：ACTIVE/SUSPENDED/EXPIRED"
    )
    
    expire_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="服务到期时间"
    )
    
    # 元信息
    enabled: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=True,
        comment="是否启用：0禁用 1启用"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
    )
    
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间"
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人"
    )
    
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="更新人"
    )
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=True,
        comment="是否删除：0否 1是"
    )
    
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, tenant_code={self.tenant_code}, tenant_name={self.tenant_name})>"
