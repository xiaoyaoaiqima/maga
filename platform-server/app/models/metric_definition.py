"""
Metric Definition model - 指标定义表
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetricDefinition(Base):
    """指标定义表 - 存储指标的元数据和解释"""
    
    __tablename__ = "metric_definition"
    
    # 主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Primary Key"
    )
    
    # 核心标识
    metric_key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
        comment="指标 Key (对应代码/SQL中的标识)"
    )
    
    metric_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="指标名称 (中文)"
    )
    
    # 详细定义
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="指标定义/解释说明"
    )
    
    category: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="指标分类 (Dashboard, Cost, GE, AG, RLHF等)"
    )

    unit: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="单位 (e.g. %, $, ms, 个)"
    )
    
    # 扩展字段
    display_format: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="显示格式 (number, currency, percentage)"
    )
    
    display_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="显示排序权重"
    )
    
    # 审计字段
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

