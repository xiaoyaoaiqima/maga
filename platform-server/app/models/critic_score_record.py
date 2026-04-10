"""
CriticScoreRecord model - Critic 评分结果明细表
"""
# pylint: disable=not-callable
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, Integer, JSON, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CriticScoreRecord(Base):
    """Critic 评分结果明细表"""
    
    __tablename__ = "critic_score_record"
    
    # 主键ID
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键"
    )
    
    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Job ID"
    )
    
    sub_job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Sub Job ID"
    )
    
    content_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="内容 ID"
    )

    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="job",
        index=True,
        comment="来源类型：job/eval_run/debug",
    )

    # === job 场景专属字段 ===
    tenant_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="租户ID（job场景）",
    )

    activity_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="活动ID（job场景）",
    )

    # === eval_run 场景专属字段 ===
    dataset_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="数据集标识（eval_run/test_case 场景）",
    )

    run_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="eval_run id（批量测试场景）",
    )

    test_case_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="test_case id（批量测试场景）",
    )

    # === debug 场景专属字段 ===
    debug_history_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="调试历史ID（debug场景）",
    )
    
    expert_task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ExpertTask ID"
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
        comment="Critic 函数名（CriticIllegal/CriticGrace 等）"
    )
    
    expert_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="CRITIC",
        server_default="CRITIC",
        index=True,
        comment="专家类型：BAN（合规封禁）/ CRITIC（质量评分）"
    )
    
    model_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="模型编码"
    )
    
    provider_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Provider 编码"
    )
    
    score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        index=True,
        comment="评分（0-100）"
    )
    
    passed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        index=True,
        comment="是否通过（1=通过，0=不通过）"
    )
    
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="评分理由"
    )

    highlights: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="精彩原文摘录",
    )
    
    problem_context_list: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="问题上下文列表"
    )

    # 更直观的字段命名（推荐使用）
    problem_tags: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="问题标签（从模型输出解析）",
    )

    problem_snippets: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="问题片段列表（用于高亮展示）",
    )
    
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="耗时（毫秒）"
    )
    
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="关联 expert_call_trace"
    )
    
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="版本号（同 content_id + expert_func 递增）"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        index=True,
        comment="创建时间"
    )
    
    # 复合索引
    __table_args__ = (
        Index("idx_content_func", "content_id", "expert_func"),
        Index("idx_job_func", "job_id", "expert_func"),
        Index("idx_model_date", "model_code", "create_time"),
        Index("idx_passed_date", "passed", "create_time"),
        # 优化专家筛选查询：先按 expert_config_code 查找，再关联 content_id
        Index("idx_expert_content", "expert_config_code", "content_id"),
    )
    
    def __repr__(self) -> str:
        return f"<CriticScoreRecord(id={self.id}, content_id={self.content_id}, score={self.score})>"
