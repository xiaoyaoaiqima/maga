"""
CriticScoreDailyStats model - Critic 每日统计聚合表
"""
# pylint: disable=not-callable
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, BigInteger, Integer, Float, JSON, DateTime, Date, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CriticScoreDailyStats(Base):
    """Critic 每日统计聚合表"""
    
    __tablename__ = "critic_score_daily_stats"
    
    # 主键ID
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键"
    )
    
    stat_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="统计日期"
    )

    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="job",
        index=True,
        comment="来源类型：job/eval_run/debug",
    )

    dataset_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="数据集标识（eval_run/test_case 场景）",
    )
    
    expert_config_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Expert 配置编码"
    )
    
    expert_func: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Critic 函数名"
    )
    
    model_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="模型编码"
    )
    
    total_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="总评分次数"
    )
    
    passed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="通过次数"
    )
    
    avg_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="平均分"
    )
    
    min_score: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="最低分"
    )
    
    max_score: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="最高分"
    )
    
    p50_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="P50 分数"
    )
    
    p90_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="P90 分数"
    )
    
    avg_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="平均耗时（毫秒）"
    )
    
    problem_context_top10: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Top10 问题上下文及出现次数"
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
    
    # 唯一约束
    __table_args__ = (
        UniqueConstraint(
            "stat_date", "source_type", "dataset_code", "expert_config_code", "expert_func", "model_code",
            name="uq_critic_daily_stats"
        ),
        Index("idx_stat_date_func", "stat_date", "expert_func"),
    )
    
    def __repr__(self) -> str:
        return f"<CriticScoreDailyStats(id={self.id}, stat_date={self.stat_date}, expert_func={self.expert_func})>"
