"""
Prompt optimizer workbench models.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PromptAsset(Base):
    """提示词资产"""

    __tablename__ = "prompt_asset"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    tenant_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment="租户编码")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="提示词名称")
    prompt_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="generation",
        comment="提示词类型: generation/critic/other",
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="描述")
    current_version_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="当前版本ID")
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="标签")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否删除")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


class PromptVersion(Base):
    """提示词版本"""

    __tablename__ = "prompt_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    prompt_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="提示词资产ID")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="提示词内容")
    parent_version_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="父版本ID")
    source_run_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="来源优化任务ID")
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="变更摘要")
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="创建人")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class PromptIssue(Base):
    """提示词问题/人类意见/失败样本"""

    __tablename__ = "prompt_issue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    prompt_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="提示词资产ID")
    prompt_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="提示词版本ID")
    issue_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="human_opinion",
        comment="问题类型: human_opinion/review_problem/batch_case",
    )
    problem_text: Mapped[str] = mapped_column(Text, nullable=False, comment="问题描述/人类意见")
    generated_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="生成内容")
    generated_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="生成标题")
    issue_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展元数据")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class PromptOptimizerRun(Base):
    """提示词优化任务"""

    __tablename__ = "prompt_optimizer_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    prompt_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="提示词资产ID")
    prompt_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="提示词版本ID")
    issue_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="问题ID")
    mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="优化模式: local_patch/global_refactor/critic_patch/batch_patch",
    )
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="模型")
    base_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="模型 API 地址")
    temperature: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="温度参数")
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="最大输出 token")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True, comment="状态")
    input_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="输入快照")
    raw_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="模型原始输出")
    parsed_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="解析后的输出")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


class PromptPatch(Base):
    """提示词 patch 建议"""

    __tablename__ = "prompt_patch"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="优化任务ID")
    patch_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="patch 顺序")
    operation: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="操作: replace/delete/insert_after/insert_before",
    )
    old_text: Mapped[str] = mapped_column(Text, nullable=False, comment="原文或定位锚点")
    new_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="新文本")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="修改原因")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True, comment="审阅状态")
    edited_new_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="人工编辑后的新文本")
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="人工审阅备注")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


class PromptEvaluation(Base):
    """提示词修改后验证记录"""

    __tablename__ = "prompt_evaluation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    prompt_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="提示词资产ID")
    base_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="基准版本ID")
    candidate_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="候选版本ID")
    test_set_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="测试集ID")
    result_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="验证结果快照")
    human_score: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="人工评分")
    critic_score: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="审核评分")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="验证摘要")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
