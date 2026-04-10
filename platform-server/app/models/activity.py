"""
Activity model - 活动表
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, JSON, BigInteger, DECIMAL, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Activity(Base):
    """活动表 - 运营活动管理"""
    
    __tablename__ = "activity"
    
    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )
    
    # 活动标识
    activity_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="活动编码"
    )
    
    activity_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="活动名称"
    )
    
    # 关联租户
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="租户ID"
    )

    # 关联 Agent（活动绑定产品模板，支持多个）
    agent_code_list: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="关联 Agent 编码列表"
    )
    
    # 活动配置
    channel: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="渠道（xiaohongshu/douyin/taobao）"
    )
    
    target_audience: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="目标人群"
    )
    
    budget: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(12, 2),
        nullable=True,
        comment="预算"
    )
    
    config_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="活动配置（扩展字段）"
    )
    
    # 时间范围
    start_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="活动开始时间"
    )
    
    end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="活动结束时间"
    )
    
    # 状态
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
        comment="状态：DRAFT/RUNNING/PAUSED/COMPLETED"
    )
    
    # 上线状态
    publish_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
        index=True,
        comment="上线状态：DRAFT(草稿)/PUBLISHED(已上线)"
    )
    
    publish_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="上线时间"
    )
    
    publish_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="上线人"
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
    
    # 联合唯一约束：同租户内活动编码唯一
    __table_args__ = (
        {"comment": "活动表"},
    )
    
    def __repr__(self) -> str:
        return f"<Activity(id={self.id}, activity_code={self.activity_code}, activity_name={self.activity_name})>"
