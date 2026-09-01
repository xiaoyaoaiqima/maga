"""
ExpertConfig model
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, BigInteger, Integer, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExpertConfig(Base):
    """ExpertConfig model"""
    
    __tablename__ = "expert_config"
    
    # 主键ID
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )
    
    # 归属租户（NULL 表示全局共享）
    tenant_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="归属租户编码（NULL 表示全局共享）"
    )
    
    expert_config_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="expert_config 配置 code"
    )
    
    expert_config_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="expert_config 名称"
    )
    
    expert_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="业务类型：GENERATION/SCORE/REWRITE/... 等"
    )
    
    expert_app: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="expert的app（Dapr app ID，如 content-executor）"
    )
    
    expert_service: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="expert的service名称"
    )
    
    expert_func: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="expert 的方法标识（历史遗留命名；当前作为 HTTP path 的一段，如 ReviewBan）"
    )
    
    expert_func_name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="expert_func 的显示名称（用于图表展示，如：内容质量、品牌匹配）"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="expert 配置描述"
    )
    
    model_code: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="使用的模型编码"
    )
    
    model_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="模型参数配置，例：{\"temperature\":0.7,\"max_tokens\":2048}"
    )
    
    plugin_config: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="插件配置数组，格式: [{plugin_code, variable_mapping}]"
    )
    
    prompt_template: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="prompt 模板（所有 plugin 渲染结果拼接后的最终模板）"
    )
    
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=True,
        comment="是否可用"
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
        return f"<ExpertConfig(id={self.id}, expert_config_code={self.expert_config_code})>"
