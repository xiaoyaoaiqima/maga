"""
节点待审核服务
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph import GraphNode
from app.models.node_pending_audit import NodePendingAudit
from app.schemas.node_pending_audit import (
    NodeAuditRequest,
    NodeBatchAuditRequest,
    NodeBatchConfirmRequest,
    NodeConfirmRequest,
    NodePendingAuditCreate,
    NodePendingAuditItem,
)

logger = logging.getLogger(__name__)


class NodePendingAuditService:
    """节点待审核服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_list(
        self,
        knowledge_base_file_id: Optional[int] = None,
        audit_status: Optional[str] = None,
        tenant_code: Optional[str] = None,
    ) -> list[NodePendingAuditItem]:
        """获取待审核列表"""
        conditions = [NodePendingAudit.is_deleted == 0]

        if knowledge_base_file_id:
            conditions.append(NodePendingAudit.file_pool_id == knowledge_base_file_id)
        if audit_status:
            conditions.append(NodePendingAudit.audit_status == audit_status)
        if tenant_code:
            conditions.append(NodePendingAudit.tenant_code == tenant_code)

        stmt = (
            select(NodePendingAudit)
            .where(and_(*conditions))
            .order_by(NodePendingAudit.row_number)
        )

        result = await self.db.execute(stmt)
        audits = result.scalars().all()

        return [self._to_item(a) for a in audits]

    async def get_by_id(self, id: int) -> Optional[NodePendingAuditItem]:
        """根据 ID 获取"""
        stmt = select(NodePendingAudit).where(
            and_(
                NodePendingAudit.id == id,
                NodePendingAudit.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        audit = result.scalar_one_or_none()

        if not audit:
            return None

        return self._to_item(audit)

    async def get_by_knowledge_base_file(self, knowledge_base_file_id: int) -> list[NodePendingAuditItem]:
        """获取文件下的所有待审核记录"""
        stmt = select(NodePendingAudit).where(
            and_(
                NodePendingAudit.file_pool_id == knowledge_base_file_id,
                NodePendingAudit.is_deleted == 0,
            )
        ).order_by(NodePendingAudit.row_number)

        result = await self.db.execute(stmt)
        audits = result.scalars().all()

        return [self._to_item(a) for a in audits]

    async def create_batch(self, items: list[NodePendingAuditCreate]) -> list[NodePendingAuditItem]:
        """批量创建待审核记录"""
        audit_records = [
            NodePendingAudit(
                tenant_code=item.tenant_code,
                file_pool_id=item.file_pool_id,
                label=item.label,
                name=item.name,
                description=item.description,
                corpus=item.corpus,
                ai_instruction=item.ai_instruction,
                properties=item.properties,
                row_number=item.row_number,
            )
            for item in items
        ]

        self.db.add_all(audit_records)
        await self.db.commit()

        logger.info(f"批量创建待审核记录: {len(audit_records)} 条")
        return [self._to_item(a) for a in audit_records]

    async def approve(self, id: int, data: NodeAuditRequest) -> Optional[NodePendingAuditItem]:
        """审核通过（状态改为 approved，等待确认后写入 nodes）"""
        stmt = select(NodePendingAudit).where(
            and_(
                NodePendingAudit.id == id,
                NodePendingAudit.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        audit = result.scalar_one_or_none()

        if not audit:
            return None

        audit.audit_status = "approved"
        audit.audited_by = data.audited_by
        audit.audited_at = datetime.now()

        await self.db.commit()
        await self.db.refresh(audit)

        logger.info(f"审核通过: {id}")
        return self._to_item(audit)

    async def reject(self, id: int, data: NodeAuditRequest) -> Optional[NodePendingAuditItem]:
        """驳回（可重新审核）"""
        stmt = select(NodePendingAudit).where(
            and_(
                NodePendingAudit.id == id,
                NodePendingAudit.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        audit = result.scalar_one_or_none()

        if not audit:
            return None

        audit.audit_status = "rejected"
        audit.audited_by = data.audited_by
        audit.audited_at = datetime.now()
        audit.reject_reason = data.reject_reason

        await self.db.commit()
        await self.db.refresh(audit)

        logger.info(f"驳回审核: {id}, 原因: {data.reject_reason}")
        return self._to_item(audit)

    async def batch_approve(self, data: NodeBatchAuditRequest) -> int:
        """批量审核通过"""
        stmt = (
            update(NodePendingAudit)
            .where(
                and_(
                    NodePendingAudit.id.in_(data.ids),
                    NodePendingAudit.is_deleted == 0,
                )
            )
            .values(
                audit_status="approved",
                audited_by=data.audited_by,
                audited_at=datetime.now(),
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        logger.info(f"批量审核通过: {result.rowcount} 条")
        return result.rowcount

    async def batch_reject(self, data: NodeBatchAuditRequest) -> int:
        """批量驳回"""
        stmt = (
            update(NodePendingAudit)
            .where(
                and_(
                    NodePendingAudit.id.in_(data.ids),
                    NodePendingAudit.is_deleted == 0,
                )
            )
            .values(
                audit_status="rejected",
                audited_by=data.audited_by,
                audited_at=datetime.now(),
                reject_reason=data.reject_reason,
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        logger.info(f"批量驳回: {result.rowcount} 条")
        return result.rowcount

    async def confirm(self, id: int, data: NodeConfirmRequest) -> Optional[NodePendingAuditItem]:
        """确认并写入 nodes 表"""
        stmt = select(NodePendingAudit).where(
            and_(
                NodePendingAudit.id == id,
                NodePendingAudit.is_deleted == 0,
                NodePendingAudit.audit_status == "approved",
                NodePendingAudit.confirmed == 0,
            )
        )
        result = await self.db.execute(stmt)
        audit = result.scalar_one_or_none()

        if not audit:
            return None

        # 创建 GraphNode 记录
        node = GraphNode(
            tenant_code=audit.tenant_code,
            label=audit.label,
            name=audit.name,
            description=audit.description,
            corpus=audit.corpus,
            ai_instruction=audit.ai_instruction,
            properties=audit.properties,
            is_active=1,
            is_deleted=0,
        )

        self.db.add(node)
        await self.db.flush()  # 获取 node.id

        # 更新审核记录
        audit.confirmed = 1
        audit.confirmed_by = data.confirmed_by
        audit.confirmed_at = datetime.now()
        audit.node_id = node.id

        await self.db.commit()
        await self.db.refresh(audit)

        logger.info(f"确认并写入 nodes: audit_id={id}, node_id={node.id}")
        return self._to_item(audit)

    async def batch_confirm(self, data: NodeBatchConfirmRequest) -> dict:
        """批量确认并写入 nodes 表"""
        # 查询待确认的记录
        stmt = select(NodePendingAudit).where(
            and_(
                NodePendingAudit.id.in_(data.ids),
                NodePendingAudit.is_deleted == 0,
                NodePendingAudit.audit_status == "approved",
                NodePendingAudit.confirmed == 0,
            )
        )
        result = await self.db.execute(stmt)
        audits = result.scalars().all()

        success_count = 0
        failed_ids = []

        for audit in audits:
            try:
                # 创建 GraphNode 记录
                node = GraphNode(
                    tenant_code=audit.tenant_code,
                    label=audit.label,
                    name=audit.name,
                    description=audit.description,
                    corpus=audit.corpus,
                    ai_instruction=audit.ai_instruction,
                    properties=audit.properties,
                    is_active=1,
                    is_deleted=0,
                )

                self.db.add(node)
                await self.db.flush()

                # 更新审核记录
                audit.confirmed = 1
                audit.confirmed_by = data.confirmed_by
                audit.confirmed_at = datetime.now()
                audit.node_id = node.id

                success_count += 1
            except Exception as e:
                logger.error(f"确认失败: audit_id={audit.id}, error={e}")
                failed_ids.append(audit.id)

        await self.db.commit()

        logger.info(f"批量确认完成: 成功={success_count}, 失败={len(failed_ids)}")
        return {
            "success_count": success_count,
            "failed_ids": failed_ids,
        }

    async def get_audit_summary(self, knowledge_base_file_id: int) -> Optional[dict]:
        """获取文件审核汇总"""
        # 获取文件信息
        from app.models.knowledge_base_file import KnowledgeBaseFile

        fp_stmt = select(KnowledgeBaseFile).where(
            and_(
                KnowledgeBaseFile.id == knowledge_base_file_id,
                KnowledgeBaseFile.is_deleted == 0,
            )
        )
        fp_result = await self.db.execute(fp_stmt)
        file_pool = fp_result.scalar_one_or_none()

        if not file_pool:
            return None

        # 统计各状态数量
        count_stmt = select(
            NodePendingAudit.audit_status,
            NodePendingAudit.confirmed,
        ).where(
            and_(
                NodePendingAudit.file_pool_id == knowledge_base_file_id,
                NodePendingAudit.is_deleted == 0,
            )
        )

        count_result = await self.db.execute(count_stmt)
        records = count_result.all()

        total_count = len(records)
        pending_count = sum(1 for s, c in records if s == "pending")
        approved_count = sum(1 for s, c in records if s == "approved")
        rejected_count = sum(1 for s, c in records if s == "rejected")
        confirmed_count = sum(1 for s, c in records if c == 1)

        # 获取详细记录
        items = await self.get_by_knowledge_base_file(knowledge_base_file_id)

        return {
            "knowledge_base_file_id": knowledge_base_file_id,
            "file_name": file_pool.file_name,
            "category_type": file_pool.category_type,
            "total_count": total_count,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "confirmed_count": confirmed_count,
            "items": items,
        }

    async def delete(self, id: int) -> bool:
        """删除待审核记录"""
        stmt = select(NodePendingAudit).where(
            and_(
                NodePendingAudit.id == id,
                NodePendingAudit.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        audit = result.scalar_one_or_none()

        if not audit:
            return False

        audit.is_deleted = 1
        await self.db.commit()

        logger.info(f"删除待审核记录: {id}")
        return True

    def _to_item(self, audit: NodePendingAudit) -> NodePendingAuditItem:
        """转换为响应项"""
        return NodePendingAuditItem(
            id=audit.id,
            tenant_code=audit.tenant_code,
            file_pool_id=audit.file_pool_id,
            label=audit.label,
            name=audit.name,
            description=audit.description,
            corpus=audit.corpus,
            ai_instruction=audit.ai_instruction,
            properties=audit.properties,
            row_number=audit.row_number,
            audit_status=audit.audit_status,
            audited_by=audit.audited_by,
            audited_at=audit.audited_at,
            reject_reason=audit.reject_reason,
            confirmed=audit.confirmed,
            confirmed_at=audit.confirmed_at,
            confirmed_by=audit.confirmed_by,
            node_id=audit.node_id,
            created_at=audit.created_at,
        )
