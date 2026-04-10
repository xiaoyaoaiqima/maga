"""
节点待审核 Schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSchema


class NodePendingAuditItem(BaseSchema):
    """待审核节点响应项"""
    id: int
    tenant_code: str
    knowledge_base_file_id: int
    label: str
    name: str
    description: Optional[str] = None
    corpus: Optional[list] = None
    ai_instruction: Optional[dict] = None
    properties: Optional[dict] = None
    row_number: int
    audit_status: str
    audited_by: Optional[str] = None
    audited_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    confirmed: int
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    node_id: Optional[int] = None
    created_at: datetime


class NodePendingAuditCreate(BaseSchema):
    """创建待审核节点（内部使用）"""
    tenant_code: str
    knowledge_base_file_id: int
    label: str
    name: str
    description: Optional[str] = None
    corpus: Optional[list] = None
    ai_instruction: Optional[dict] = None
    properties: Optional[dict] = None
    row_number: int


class NodeAuditRequest(BaseSchema):
    """审核请求"""
    audited_by: str = Field(..., description="审核人ID")
    reject_reason: Optional[str] = Field(default=None, description="驳回原因（驳回时必填）")


class NodeBatchAuditRequest(BaseSchema):
    """批量审核请求"""
    ids: list[int] = Field(..., description="待审核节点ID列表")
    audited_by: str = Field(..., description="审核人ID")
    reject_reason: Optional[str] = Field(default=None, description="驳回原因（驳回时必填）")


class NodeConfirmRequest(BaseSchema):
    """确认请求（审核通过后，确认写入 nodes 表）"""
    confirmed_by: str = Field(..., description="确认人ID")


class NodeBatchConfirmRequest(BaseSchema):
    """批量确认请求"""
    ids: list[int] = Field(..., description="待确认节点ID列表")
    confirmed_by: str = Field(..., description="确认人ID")


class KnowledgeBaseFileAuditSummary(BaseSchema):
    """文件审核汇总（按文件分组展示）"""
    knowledge_base_file_id: int
    file_name: str
    category_type: str
    total_count: int
    pending_count: int
    approved_count: int
    rejected_count: int
    confirmed_count: int
    items: list[NodePendingAuditItem]
