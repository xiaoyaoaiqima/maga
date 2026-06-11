"""Core MAGA content-workbench models for the clean schema path.

This module intentionally excludes legacy models from the old system. Import it
when creating a fresh MAGA schema for the MAGA + Hermes execution paradigm.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.maga_assets import AssetChangeProposal, AssetChangeRequest, AssetImportRun, AssetRegistry
from app.models.content_agent import (
    BIGINT_PK,
    ContentAgentArtifact,
    ContentAgentEvent,
    ContentAgentHumanReview,
    ContentAgentRun,
    ContentAgentStageCall,
    ContentAgentTask,
    ContentBatchJob,
    ContentBatchItem,
    ContentBatchItemVersion,
    ContentFeedback,
    ExecutorRegistry,
)
from app.models.llm_model_route import LLMModelRoute
from app.models.llm_provider_config import LLMProviderConfig
from app.models.expert_config import ExpertConfig
from app.models.agent import Agent


class ContentBrief(Base):
    """Business brief owned by MAGA before it is converted into executable tasks."""

    __tablename__ = "content_brief"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    brief_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True, comment="Brief 编码")
    brief_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="Brief 类型")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Brief 标题")
    brand_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment="品牌ID")
    product_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="产品ID列表")
    campaign_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="活动名称")
    objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="内容目标")
    target_audience: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="目标人群")
    persona_target: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="目标人设")
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="xhs", index=True, comment="渠道")
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="xhs", index=True, comment="平台")
    content_format: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="内容格式")
    desired_style: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="期望风格")
    required_keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="必含关键词")
    forbidden_keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="禁用关键词")
    must_messages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="必达信息")
    constraints: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="约束条件")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True, comment="状态")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="创建人")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class BriefSnapshot(Base):
    """Immutable execution snapshot derived from a ContentBrief and asset state."""

    __tablename__ = "brief_snapshot"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    brief_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="Brief ID")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="快照版本")
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, comment="执行快照")
    source_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="源数据哈希")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


MAGA_CORE_MODELS = (
    ExecutorRegistry,
    ContentBrief,
    BriefSnapshot,
    ContentBatchJob,
    ContentBatchItem,
    ContentBatchItemVersion,
    ContentFeedback,
    ContentAgentTask,
    ContentAgentRun,
    ContentAgentStageCall,
    ContentAgentEvent,
    ContentAgentArtifact,
    ContentAgentHumanReview,
    AssetRegistry,
    AssetImportRun,
    AssetChangeRequest,
    AssetChangeProposal,
    LLMProviderConfig,
    LLMModelRoute,
    ExpertConfig,
    Agent,
)

MAGA_CORE_TABLE_NAMES = tuple(model.__tablename__ for model in MAGA_CORE_MODELS)
