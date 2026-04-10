"""
LLM Model Route model - 模型路由表

核心设计：
- 业务侧使用统一的 model_code（如 gpt-4o）
- 通过路由表映射到具体的 Provider + 实际模型名
- 支持自动 failover（按优先级排序，失败时切换到下一个）
- 记录成本信息用于统计
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy import String, Text, BigInteger, JSON, DateTime, Integer, SmallInteger, DECIMAL, func, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LLMModelRoute(Base):
    """模型路由表"""

    __tablename__ = "llm_model_route"

    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键"
    )

    # 模型标识
    model_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="统一模型编码（业务使用，如 gpt-4o）"
    )

    model_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="模型显示名称"
    )

    # Provider 关联
    provider_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="端点编码（关联 llm_provider_config）"
    )

    provider_model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="该端点的实际模型名（如 claude-3-5-sonnet-20241022）"
    )

    # Failover 配置
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="优先级（越大越优先，用于 failover）"
    )

    enabled: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="是否启用"
    )

    # 模型能力
    max_context_length: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="最大上下文长度"
    )

    features: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="支持的功能（vision/function_calling/json_mode）"
    )

    # 成本配置
    cost_per_1k_input: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 6),
        nullable=True,
        comment="输入成本（每 1K tokens，美元）"
    )

    cost_per_1k_output: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 6),
        nullable=True,
        comment="输出成本（每 1K tokens，美元）"
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USD",
        server_default="USD",
        comment="计价币种（USD/CNY）"
    )

    timeout_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="超时时间（秒）"
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

    # 唯一约束和索引
    __table_args__ = (
        UniqueConstraint("model_code", "provider_code", "is_deleted", name="uk_model_provider_deleted"),
        Index("idx_route_model_code", "model_code"),
        Index("idx_route_provider_code", "provider_code"),
        Index("idx_route_model_priority", "model_code", "priority"),
        Index("idx_route_enabled", "enabled"),
    )

    def __repr__(self) -> str:
        return (
            f"<LLMModelRoute(id={self.id}, model_code={self.model_code}, "
            f"provider_code={self.provider_code}, priority={self.priority})>"
        )

    @property
    def is_enabled(self) -> bool:
        """是否启用"""
        return self.enabled == 1

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """计算调用成本（美元）"""
        input_cost = Decimal("0")
        output_cost = Decimal("0")
        
        if self.cost_per_1k_input:
            input_cost = (Decimal(input_tokens) / 1000) * self.cost_per_1k_input
        
        if self.cost_per_1k_output:
            output_cost = (Decimal(output_tokens) / 1000) * self.cost_per_1k_output
        
        return input_cost + output_cost

