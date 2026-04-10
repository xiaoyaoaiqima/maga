"""
节点待审核 API - 审核与确认流程
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep
from app.schemas.base import ResponseData
from app.schemas.node_pending_audit import (
    NodeAuditRequest,
    NodeBatchAuditRequest,
    NodeBatchConfirmRequest,
    NodeConfirmRequest,
)
from app.services.node_pending_audit_service import NodePendingAuditService

router = APIRouter(prefix="/node-pending-audits", tags=["节点待审核"])
logger = logging.getLogger(__name__)


@router.get("", summary="获取待审核列表")
async def get_pending_audits(
    db: AsyncSessionDep,
    knowledge_base_file_id: Optional[int] = Query(None, description="知识库文件ID筛选"),
    audit_status: Optional[str] = Query(None, description="审核状态筛选"),
    tenant_code: Optional[str] = Query(None, description="租户编码"),
):
    """获取待审核列表"""
    service = NodePendingAuditService(db)
    items = await service.get_list(
        knowledge_base_file_id=knowledge_base_file_id,
        audit_status=audit_status,
        tenant_code=tenant_code,
    )
    return ResponseData(data={"items": [item.model_dump() for item in items], "total": len(items)})


@router.get("/summary/{knowledge_base_file_id}", summary="获取文件审核汇总")
async def get_audit_summary(
    knowledge_base_file_id: int,
    db: AsyncSessionDep,
):
    """获取文件的审核汇总信息（含各状态统计）"""
    service = NodePendingAuditService(db)
    summary = await service.get_audit_summary(knowledge_base_file_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f"文件 {knowledge_base_file_id} 不存在或无待审核记录")

    # 转换 items 为 dict
    summary["items"] = [item.model_dump() for item in summary["items"]]
    return ResponseData(data=summary)


@router.get("/{audit_id}", summary="获取单条审核记录")
async def get_pending_audit(
    audit_id: int,
    db: AsyncSessionDep,
):
    """获取单条待审核记录"""
    service = NodePendingAuditService(db)
    item = await service.get_by_id(audit_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"审核记录 {audit_id} 不存在")
    return ResponseData(data=item.model_dump())


@router.post("/{audit_id}/approve", summary="审核通过")
async def approve_audit(
    audit_id: int,
    data: NodeAuditRequest,
    db: AsyncSessionDep,
):
    """
    审核通过

    状态变更: pending → approved
    审核通过后需要再调用 confirm 接口确认才会写入 nodes 表
    """
    service = NodePendingAuditService(db)
    item = await service.approve(audit_id, data)
    if not item:
        raise HTTPException(status_code=404, detail=f"审核记录 {audit_id} 不存在")
    return ResponseData(data=item.model_dump(), message="审核通过，请确认后写入关键词语料")


@router.post("/{audit_id}/reject", summary="驳回审核")
async def reject_audit(
    audit_id: int,
    data: NodeAuditRequest,
    db: AsyncSessionDep,
):
    """
    驳回审核

    状态变更: pending/any → rejected
    驳回后可重新审核
    """
    if not data.reject_reason:
        raise HTTPException(status_code=400, detail="驳回时必须填写驳回原因")

    service = NodePendingAuditService(db)
    item = await service.reject(audit_id, data)
    if not item:
        raise HTTPException(status_code=404, detail=f"审核记录 {audit_id} 不存在")
    return ResponseData(data=item.model_dump(), message="已驳回")


@router.post("/batch/approve", summary="批量审核通过")
async def batch_approve(
    data: NodeBatchAuditRequest,
    db: AsyncSessionDep,
):
    """
    批量审核通过

    状态变更: pending → approved
    """
    if not data.ids:
        raise HTTPException(status_code=400, detail="ID 列表不能为空")

    service = NodePendingAuditService(db)
    count = await service.batch_approve(data)
    return ResponseData(data={"affected_count": count}, message=f"已批量审核通过 {count} 条记录")


@router.post("/batch/reject", summary="批量驳回")
async def batch_reject(
    data: NodeBatchAuditRequest,
    db: AsyncSessionDep,
):
    """
    批量驳回

    状态变更: any → rejected
    """
    if not data.ids:
        raise HTTPException(status_code=400, detail="ID 列表不能为空")

    if not data.reject_reason:
        raise HTTPException(status_code=400, detail="驳回时必须填写驳回原因")

    service = NodePendingAuditService(db)
    count = await service.batch_reject(data)
    return ResponseData(data={"affected_count": count}, message=f"已批量驳回 {count} 条记录")


@router.post("/{audit_id}/confirm", summary="确认并写入关键词语料")
async def confirm_audit(
    audit_id: int,
    data: NodeConfirmRequest,
    db: AsyncSessionDep,
):
    """
    确认并写入 nodes 表

    前置条件: audit_status = approved
    状态变更: approved + confirmed=0 → approved + confirmed=1，并创建 GraphNode
    """
    service = NodePendingAuditService(db)
    item = await service.confirm(audit_id, data)
    if not item:
        raise HTTPException(
            status_code=400,
            detail="确认失败，请检查记录状态是否为已通过且未确认",
        )
    return ResponseData(data=item.model_dump(), message="已确认并写入关键词语料")


@router.post("/batch/confirm", summary="批量确认并写入关键词语料")
async def batch_confirm(
    data: NodeBatchConfirmRequest,
    db: AsyncSessionDep,
):
    """
    批量确认并写入 nodes 表

    前置条件: audit_status = approved, confirmed = 0
    """
    if not data.ids:
        raise HTTPException(status_code=400, detail="ID 列表不能为空")

    service = NodePendingAuditService(db)
    result = await service.batch_confirm(data)

    message = f"成功写入 {result['success_count']} 条记录"
    if result["failed_ids"]:
        message += f"，失败 {len(result['failed_ids'])} 条: {result['failed_ids']}"

    return ResponseData(data=result, message=message)


@router.post("/{audit_id}/re-submit", summary="重新提交审核")
async def resubmit_audit(
    audit_id: int,
    db: AsyncSessionDep,
):
    """
    重新提交审核

    状态变更: rejected → pending
    """
    service = NodePendingAuditService(db)
    item = await service.get_by_id(audit_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"审核记录 {audit_id} 不存在")
    if item.audit_status != "rejected":
        raise HTTPException(status_code=400, detail="只有驳回状态的记录才能重新提交")

    # 更新状态
    from sqlalchemy import update
    from app.models.node_pending_audit import NodePendingAudit
    from datetime import datetime

    stmt = (
        update(NodePendingAudit)
        .where(NodePendingAudit.id == audit_id)
        .values(
            audit_status="pending",
            reject_reason=None,
        )
    )
    await db.execute(stmt)
    await db.commit()

    # 重新获取
    item = await service.get_by_id(audit_id)
    return ResponseData(data=item.model_dump(), message="已重新提交审核")


@router.delete("/{audit_id}", summary="删除审核记录")
async def delete_audit(
    audit_id: int,
    db: AsyncSessionDep,
):
    """
    删除审核记录

    注意：已确认并写入 nodes 的记录无法删除
    """
    service = NodePendingAuditService(db)

    # 检查是否已确认
    item = await service.get_by_id(audit_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"审核记录 {audit_id} 不存在")
    if item.confirmed:
        raise HTTPException(status_code=400, detail="已确认的记录无法删除")

    success = await service.delete(audit_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除失败")

    return ResponseData(message="删除成功")
