"""
节点待审核模型 - 解析后暂存，等待审核后进入 nodes
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NodePendingAudit(Base):
    """
    节点待审核表 - 解析后的数据暂存，等待审核后写入 nodes 表

    数据来源：从 KnowledgeBaseFile（上传的文件）解析出的每一行
    审核流程：pending(待审核) → approved(已通过) → 确认后写入 nodes
                  ↓
                rejected(已驳回) → 可重新审核
    """
    __tablename__ = "node_pending_audits"

    # 主键与标识
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键ID")
    tenant_code: Mapped[str] = mapped_column(String(50), nullable=False, default="default", comment="租户编码")

    # 关联到具体的上传文件（逻辑外键，不设数据库外键约束）
    knowledge_base_file_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="关联的上传文件ID（knowledge_base_files表）"
    )

    # 节点数据（与 nodes 表结构对齐）
    label: Mapped[str] = mapped_column(String(50), nullable=False, comment="节点类型/语义标签 (从 category_type 映射)")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="节点名称")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="节点描述")
    corpus: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="语料列表")
    ai_instruction: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="AI 指令")
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="扩展数据")

    # 原始行号（便于定位问题）
    row_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="Excel 原始行号")

    # 审核状态
    audit_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="审核状态: pending-待审核 | approved-已通过 | rejected-已驳回",
    )

    # 审核信息
    audited_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="审核人ID")
    audited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="审核时间")
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="驳回原因")

    # 确认状态（approved 后需要额外确认才能写入 nodes）
    confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否已确认: 0-未确认 1-已确认")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="确认时间")
    confirmed_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="确认人ID")

    # 写入 nodes 表后的追踪
    node_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="写入 nodes 表后的节点ID")

    # 审计字段
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 软删除
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="软删除: 0-正常 1-已删除")

    __table_args__ = (
        Index("idx_npa_file_pool", "knowledge_base_file_id"),
        Index("idx_npa_tenant", "tenant_code"),
        Index("idx_npa_audit_status", "audit_status"),
        Index("idx_npa_confirmed", "confirmed"),
        Index("idx_npa_label", "label"),
        Index("idx_npa_tenant_status", "tenant_code", "audit_status"),
        Index("idx_npa_file_status", "knowledge_base_file_id", "audit_status"),
    )
