"""
Content model - 文章内容表
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, String, Text, DateTime, BigInteger, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Content(Base):
    """Content model - 文章内容表"""
    
    __tablename__ = "content"
    
    # 技术主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键"
    )
    
    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="job_id"
    )
    sub_job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="sub_job_id"
    )
    content_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="文章内容 id（全局唯一）"
    )
    
    # ========== 业务归属与隔离 ==========
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True, 
        index=True, 
        comment="租户ID"
    )
    activity_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True, 
        index=True, 
        comment="活动ID"
    )
    agent_code: Mapped[Optional[str]] = mapped_column(
        String(64), 
        nullable=True, 
        index=True, 
        comment="Agent编码"
    )

    # ========== 内容分发状态 ==========
    distribution_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING",
        index=True,
        comment="分发状态：PENDING(待入库)/AVAILABLE(上架)/LOCKED(锁定)/CONSUMED(已消费)"
    )
    lock_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime, 
        nullable=True, 
        comment="锁定截止时间"
    )
    external_order_id: Mapped[Optional[str]] = mapped_column(
        String(64), 
        nullable=True, 
        index=True, 
        comment="外部订单ID（幂等）"
    )
    
    # ========== 筛选标签 ==========
    quality_score: Mapped[int] = mapped_column(
        Integer, 
        default=0, 
        index=True, 
        comment="质量分（0-100）"
    )
    tags: Mapped[Optional[dict]] = mapped_column(
        JSON, 
        nullable=True, 
        comment="标签列表"
    )

    prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="本内容对应的 prompt"
    )
    context_list: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="结构化变量映射，格式: {变量名: 上下文名}，如: {'写者': '通勤战士', '平台': '小红书'}"
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="标题"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="文章正文内容"
    )
    
    is_valid: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="是否当前有效（0不可用 1可用 null待定）"
    )
    is_test_case: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="是否为测试用例（0不是 1是）"
    )

    # ========== 上线状态 ==========
    online_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="OFFLINE",
        index=True,
        comment="上线状态：OFFLINE(下线)/ONLINE(上线)"
    )

    # ========== 锁定信息 ==========
    is_locked: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="是否锁定：0否 1是"
    )

    lock_user_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="锁定人ID"
    )

    lock_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="锁定时间"
    )

    lock_expire_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="锁定过期时间"
    )

    # ========== 使用信息 ==========
    is_used: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="是否被使用：0否 1是"
    )

    user_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="使用人ID"
    )

    use_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="使用时间"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.now(),
        comment="创建时间"
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="创建人")
    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="更新人")
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）"
    )
    plan_index: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="执行计划索引（槽位编号，从0开始）"
    )
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )

