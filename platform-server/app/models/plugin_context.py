"""
PluginContext model
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PluginContext(Base):
    """PluginContext model"""
    
    __tablename__ = "plugin_context"
    
    # 主键ID
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Primary Key"
    )
    
    variable_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="变量名（与 plugin.variable_list 中某一项对应）"
    )
    
    context_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="替换上下文变量名（用于在 plugin_config 中引用）"
    )
    
    context: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="替换上下文变量的解释/详细内容"
    )
    
    default_keywords: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="默认关键词"
    )
    
    default_corpus: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="默认语料"
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
        String(255),
        nullable=True,
        comment="上线人"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="Create Time"
    )
    
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="Update Time"
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Created By"
    )
    
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Updated By"
    )
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）"
    )
    
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    def __repr__(self) -> str:
        return f"<PluginContext(id={self.id}, context_name={self.context_name})>"

