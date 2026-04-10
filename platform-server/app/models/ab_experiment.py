"""
ABExperiment model - A/B 实验配置表

用于管理 A/B 实验，支持实验分流和结果分析
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, JSON, DateTime, Integer, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ABExperiment(Base):
    """A/B 实验配置表"""

    __tablename__ = "ab_experiment"

    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )

    # 实验标识
    experiment_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="实验ID"
    )

    experiment_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="实验名称"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="实验描述"
    )

    # 实验范围
    target_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="目标类型：expert_config/plugin/prompt/model"
    )

    target_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="目标编码（如 expert_config_code）"
    )

    # 实验分组配置
    # 格式: [{"group": "control", "weight": 50, "variant": "v1"}, ...]
    groups: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="分组配置: [{group: control, weight: 50, variant: v1}, ...]"
    )

    traffic_ratio: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        comment="实验流量占比（0-100）"
    )

    # 实验状态
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        comment="draft/running/paused/completed"
    )

    start_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="开始时间"
    )

    end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="结束时间"
    )

    # 实验指标配置
    metrics_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="指标配置: {primary: success_rate, secondary: [duration, tokens]}"
    )

    # 元数据
    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人"
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间"
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

    # 索引
    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_target", "target_type", "target_code"),
        Index("idx_created", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ABExperiment(id={self.id}, experiment_id={self.experiment_id}, "
            f"name={self.experiment_name}, status={self.status})>"
        )

    def get_group_by_hash(self, hash_value: int) -> dict:
        """
        根据哈希值获取实验分组

        Args:
            hash_value: 用于分流的哈希值（如 content_id 的哈希）

        Returns:
            分组信息 {"group": "control", "variant": "v1"}
        """
        if not self.groups:
            return {"group": "control", "variant": None}

        # 检查是否命中实验流量
        traffic_hash = hash_value % 100
        if traffic_hash >= self.traffic_ratio:
            return {"group": "control", "variant": None}

        # 按权重分配分组
        total_weight = sum(g.get("weight", 0) for g in self.groups)
        if total_weight == 0:
            return self.groups[0] if self.groups else {"group": "control", "variant": None}

        group_hash = hash_value % total_weight
        cumulative = 0
        for group in self.groups:
            cumulative += group.get("weight", 0)
            if group_hash < cumulative:
                return {
                    "group": group.get("group", "unknown"),
                    "variant": group.get("variant"),
                }

        return self.groups[-1] if self.groups else {"group": "control", "variant": None}

