"""
LogicExpert model
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, Integer, DateTime, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LogicExpert(Base):
    """逻辑专家配置表"""

    __tablename__ = "logic_expert"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键",
    )

    expert_group: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="专家组名称",
    )

    expert_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="专家名称",
    )

    expert_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="专家类型（CRITIC/BAN/REWRITE等）",
    )

    expert_app: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="专家所属 App（Dapr app id）",
    )

    expert_service: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="专家服务名称",
    )

    expert_func: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="专家函数名",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="专家说明",
    )

    enabled: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="是否启用(1/0)",
    )

    is_deleted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="软删(1/0)",
    )

    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间",
    )

    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间",
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人",
    )

    updated_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="更新人",
    )

    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注",
    )

    __table_args__ = (
        UniqueConstraint("expert_type", "expert_func", name="uq_logic_expert_type_func"),
        Index("idx_logic_expert_type", "expert_type"),
        Index("idx_logic_expert_func", "expert_func"),
        Index("idx_logic_expert_enabled", "enabled"),
        Index("idx_logic_expert_deleted", "is_deleted"),
    )

    def __repr__(self) -> str:
        return f"<LogicExpert(id={self.id}, expert_func={self.expert_func}, expert_type={self.expert_type})>"
