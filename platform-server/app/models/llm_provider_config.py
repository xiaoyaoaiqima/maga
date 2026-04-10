"""
LLM Provider Config model - LLM 提供商配置表

用于管理多个 LLM 服务提供商的连接配置，支持：
- 多端点配置（AIHubMix、火山云、腾讯云等）
- API Key 安全存储（Vault 或数据库加密）
- 优先级排序
- 启用/禁用控制
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import String, Text, BigInteger, JSON, DateTime, Integer, SmallInteger, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LLMProviderConfig(Base):
    """LLM 提供商配置表"""

    __tablename__ = "llm_provider_config"

    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键"
    )

    # 基本信息
    provider_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="提供商编码（唯一标识）"
    )

    provider_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="提供商名称"
    )

    provider_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="openai_compatible",
        comment="类型：openai_compatible/gemini_native/azure"
    )

    # 连接配置
    base_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="API 端点地址"
    )

    api_key: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="API Key（Vault 模式存占位符，DB 模式存密文）"
    )

    api_key_encrypted: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="是否已加密（0=明文/占位符，1=已加密）"
    )

    # 模型配置
    default_model: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="默认模型"
    )

    available_models: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment="可用模型列表"
    )

    default_params: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="默认参数（temperature/max_tokens/top_p）"
    )

    # 限制配置
    rate_limit: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="速率限制配置"
    )

    timeout: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=120,
        comment="超时时间（秒）"
    )

    # 优先级与状态
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="优先级（越大越优先）"
    )

    enabled: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="是否启用"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="描述"
    )

    # 时间戳
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

    # 软删除
    is_deleted: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        default=0,
        comment="软删除标记"
    )

    # 索引
    __table_args__ = (
        Index("idx_provider_code", "provider_code"),
        Index("idx_provider_enabled", "enabled", "priority"),
        Index("idx_provider_type", "provider_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<LLMProviderConfig(id={self.id}, code={self.provider_code}, "
            f"name={self.provider_name}, enabled={self.enabled})>"
        )

    @property
    def is_enabled(self) -> bool:
        """是否启用"""
        return self.enabled == 1

    @property
    def is_vault_mode(self) -> bool:
        """是否为 Vault 模式（api_key 以 vault:// 开头）"""
        return self.api_key and self.api_key.startswith("vault://")

