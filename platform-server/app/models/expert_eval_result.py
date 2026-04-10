"""
ExpertEvalResult model - 专家评测结果表
"""
# pylint: disable=not-callable

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import BigInteger, String, Text, JSON, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExpertEvalResult(Base):
    """ExpertEvalResult model - 专家评测结果表"""

    __tablename__ = "expert_eval_result"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="主键",
    )

    run_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="关联 expert_eval_run.id",
    )

    test_case_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="关联 test_case.id",
    )

    score: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="分数(0-100)",
    )

    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="评语",
    )

    highlights: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="原文摘录",
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

    raw_output: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="模型/专家原始返回",
    )

    rendered_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="实际下发 prompt",
    )

    model_code: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="最终使用模型",
    )

    provider_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="provider",
    )

    token_usage: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="token 使用情况",
    )

    latency_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="耗时(毫秒)",
    )

    trace_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="链路追踪 trace_id",
    )

    success: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        comment="是否成功(1/0)",
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="失败原因",
    )

    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )

