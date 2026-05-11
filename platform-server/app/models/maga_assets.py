"""MAGA-owned marketing asset registry models.

These tables provide the first lightweight source-of-truth layer for product,
brand, corpus, compliance, and strategy assets imported or maintained by agents.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.content_agent import BIGINT_PK


class AssetRegistry(Base):
    """Versioned MAGA marketing asset content."""

    __tablename__ = "asset_registry"
    __table_args__ = (
        UniqueConstraint("asset_type", "asset_key", "version_no", name="uq_asset_registry_type_key_version"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="资产类型")
    asset_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="资产键")
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="展示名称")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True, comment="状态")
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="来源名称")
    source_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="来源 URI")
    source_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="来源哈希")
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, comment="资产内容")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="元信息")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="创建人")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class AssetImportRun(Base):
    """Audit row for an asset import batch."""

    __tablename__ = "asset_import_run"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="来源名称")
    source_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="来源 URI")
    source_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True, comment="来源哈希")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="succeeded", index=True, comment="状态")
    imported_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="导入资产数量")
    summary_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="导入摘要")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="创建人")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class AssetChangeRequest(Base):
    """Natural-language asset change request submitted by ops or an Asset Steward agent."""

    __tablename__ = "asset_change_request"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    source_text: Mapped[str] = mapped_column(Text, nullable=False, comment="原始需求")
    requester: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="需求方")
    context_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="上下文")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True, comment="状态")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="创建人")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class AssetChangeProposal(Base):
    """Structured proposed asset changes generated from an asset change request."""

    __tablename__ = "asset_change_proposal"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键")
    request_id: Mapped[int] = mapped_column(BIGINT_PK, nullable=False, index=True, comment="变更请求ID")
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="medium", index=True, comment="风险等级")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="摘要")
    affected_assets_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="影响资产")
    proposed_changes_json: Mapped[dict] = mapped_column(JSON, nullable=False, comment="变更草案")
    risk_notes_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="风险说明")
    smoke_test_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="冒烟测试建议")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed", index=True, comment="状态")
    applied_asset_ids_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="已应用资产ID")
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="创建人")
    applied_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="应用人")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
