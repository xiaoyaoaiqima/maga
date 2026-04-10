"""
ExpertBatchScoreResult model - 专家批量评分结果表
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, DateTime, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExpertBatchScoreResult(Base):
    """ExpertBatchScoreResult model - 专家批量评分结果表"""
    
    __tablename__ = "expert_batch_score_result"
    
    # 技术主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键"
    )
    
    # 专家配置
    expert_config_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="expert_config 配置 code"
    )
    
    # 测试用例关联
    content_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="测试用例 content_id（关联 content 表）"
    )
    
    # 文章内容（冗余存储，便于查看）
    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="文章标题"
    )
    
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="文章正文"
    )
    
    # 评分结果
    score: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="评分分数 (0-100)"
    )
    
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="评分理由"
    )
    
    highlights: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="精彩原文摘录"
    )

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
    
    # 执行信息
    model_code: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="使用的模型编码"
    )
    
    execution_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="执行耗时（毫秒）"
    )
    
    # 错误信息
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息（如果失败）"
    )
    
    success: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="是否成功"
    )
    
    # 时间戳
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="创建人"
    )
    
    def __repr__(self) -> str:
        return f"<ExpertBatchScoreResult(id={self.id}, expert_config_code={self.expert_config_code}, score={self.score})>"
