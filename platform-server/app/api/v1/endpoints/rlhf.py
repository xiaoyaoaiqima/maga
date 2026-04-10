from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.core.logger import get_logger
from app.services.rlhf_service import RLHFService
from app.schemas.rlhf import (
    RLHFFeedbackOut,
    RLHFFeedbackUpdate,
    RLHFLikeRequest,
    RLHFAdoptRequest,
    RLHFScoreRequest,
    RLHFTagRequest,
    RLHFLockResponse,
    RLHFInspectionRequest,
    RLHFSummaryRequest,
    RLHFSummaryResponse,
    RLHFSummarizeCommentRequest,
    RLHFSummarizeCommentResponse,
    RLHFIssueTagCreate,
    RLHFIssueTagUpdate,
    RLHFIssueTagOut,
    RLHFOperationHistoryOut,
    RLHFStatsSummary,
    RLHFReviewerStats,
)
from app.schemas.common import PageResult
from app.schemas.base import ResponseData

router = APIRouter(prefix="/rlhf", tags=["rlhf"])
logger = get_logger()

# --- Content Management ---

@router.get("/contents", response_model=ResponseData[PageResult[RLHFFeedbackOut]])
async def list_contents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    job_id: Optional[str] = None,
    review_status: Optional[str] = None,
    inspection_status: Optional[str] = Query(None, description="抽检状态: PENDING/IN_PROGRESS/PASSED/FAILED"),
    like_status: Optional[int] = None,
    adopt_status: Optional[int] = None,
    keyword: Optional[str] = None,
    exclude_locked: bool = Query(False, description="是否排除其他用户锁定的文章（多用户审核模式）"),
    ge_expert_code: Optional[str] = Query(None, description="按生成专家（Agent）代码筛选"),
    tenant_id: Optional[int] = Query(None, description="按租户ID筛选"),
    only_ban_passed: bool = Query(False, description="仅显示合规通过的文章（排除 BAN 类型专家不通过的）"),
    reviewer_id: Optional[str] = Query(None, description="按审核人ID筛选（喜欢/不喜欢操作人）"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """获取待审核内容列表
    
    Args:
        exclude_locked: 启用后，会排除其他用户锁定且未过期的文章，确保多用户不会审核同一篇文章
        ge_expert_code: 按生成专家（Agent）代码筛选
        tenant_id: 按租户ID筛选（通过关联 Content 表实现）
        only_ban_passed: 仅显示合规通过的文章（排除有 BAN 类型专家不通过的文章）
        reviewer_id: 按审核人ID筛选（喜欢/不喜欢操作人）
    """
    service = RLHFService(db)
    items, total = await service.list(
        page=page, 
        page_size=page_size, 
        job_id=job_id, 
        review_status=review_status,
        inspection_status=inspection_status,
        like_status=like_status,
        adopt_status=adopt_status,
        keyword=keyword,
        reviewer_id=reviewer_id,
        exclude_locked_by_others=exclude_locked,
        current_user_id=str(current_user.id) if exclude_locked else None,
        ge_expert_code=ge_expert_code,
        tenant_id=tenant_id,
        only_ban_passed=only_ban_passed,
    )
    return ResponseData(data=PageResult(items=items, total=total, page=page, page_size=page_size))


@router.get("/review-status-options", response_model=ResponseData[List[dict]])
async def get_review_status_options():
    """获取审核状态选项列表"""
    options = [
        {"value": "PENDING", "label": "待审核"},
        {"value": "IN_PROGRESS", "label": "审核中"},
        {"value": "LIKED", "label": "喜欢"},
        {"value": "DISLIKED", "label": "不喜欢"},
    ]
    return ResponseData(data=options)


@router.get("/reviewers", response_model=ResponseData[List[dict]])
async def get_reviewers(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """获取审核人列表（用于下拉筛选）
    
    返回所有进行过审核操作（喜欢/不喜欢）的用户列表
    """
    service = RLHFService(db)
    reviewer_stats = await service.get_reviewer_stats()
    # 转换为下拉选项格式
    reviewers = [
        {"value": r["reviewer_id"], "label": r["reviewer_name"]}
        for r in reviewer_stats
        if r["reviewer_id"]  # 过滤掉空的 reviewer_id
    ]
    return ResponseData(data=reviewers)


@router.get("/contents/random", response_model=ResponseData[List[RLHFFeedbackOut]])
async def get_random_contents(
    count: int = Query(1, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """随机获取N篇待审核内容并自动锁定"""
    service = RLHFService(db)
    items = await service.get_random_pending(
        count, 
        user_id=str(current_user.id), 
        user_name=current_user.username or current_user.email
    )
    return ResponseData(data=items)

@router.get("/contents/{id}", response_model=ResponseData[RLHFFeedbackOut])
async def get_content(
    id: int = Path(..., title="Feedback ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """获取内容详情（包含 context_list）"""
    service = RLHFService(db)
    item = await service.get(id, with_context=True)
    if not item:
        raise HTTPException(status_code=404, detail="Content not found")
    return ResponseData(data=RLHFFeedbackOut(**item))

@router.post("/contents/{id}/lock", response_model=ResponseData[RLHFLockResponse])
async def lock_content(
    id: int = Path(..., title="Feedback ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """锁定内容"""
    service = RLHFService(db)
    try:
        await service.lock(id, str(current_user.id), current_user.username or current_user.email)
        item = await service.get(id, with_context=False)
        return ResponseData(data={"success": True, "message": "Locked successfully", "lock_expire_time": item["lock_expire_time"] if item else None})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/contents/{id}/unlock", response_model=ResponseData[RLHFLockResponse])
async def unlock_content(
    id: int = Path(..., title="Feedback ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """解锁内容"""
    service = RLHFService(db)
    try:
        await service.unlock(id, str(current_user.id))
        return ResponseData(data={"success": True, "message": "Unlocked successfully"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/contents/batch-lock", response_model=ResponseData[dict])
async def batch_lock_contents(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """批量锁定文章（用于多用户审核场景）
    
    请求体: { "ids": [1, 2, 3] }
    返回: { "success_count": 2, "failed_count": 1, "success_ids": [1, 2], "failed_ids": [3] }
    """
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="ids is required")
    
    service = RLHFService(db)
    result = await service.batch_lock(
        ids, 
        str(current_user.id), 
        current_user.username or current_user.email
    )
    return ResponseData(data=result)


@router.post("/contents/batch-unlock", response_model=ResponseData[dict])
async def batch_unlock_contents(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """批量解锁文章
    
    请求体: { "ids": [1, 2, 3] }
    """
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="ids is required")
    
    service = RLHFService(db)
    result = await service.batch_unlock(ids, str(current_user.id))
    return ResponseData(data=result)


@router.post("/contents/unlock-all", response_model=ResponseData[dict])
async def unlock_all_my_contents(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """解锁当前用户锁定的所有文章（用于离开审核页面时调用）"""
    service = RLHFService(db)
    count = await service.unlock_all_by_user(str(current_user.id))
    return ResponseData(data={"success": True, "unlocked_count": count})


@router.post("/contents/renew-locks", response_model=ResponseData[dict])
async def renew_locks(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """心跳续锁 - 延长锁定时间（前端每 5 分钟调用一次）
    
    请求体: { "ids": [1, 2, 3] }
    返回: { "success": true, "renewed_count": 3, "new_expire_time": "..." }
    """
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="ids is required")
    
    service = RLHFService(db)
    result = await service.renew_locks(ids, str(current_user.id))
    return ResponseData(data=result)


@router.post("/contents/cleanup-expired-locks", response_model=ResponseData[dict])
async def cleanup_expired_locks(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """清理过期锁定（管理接口，可由定时任务或手动触发）
    
    用于处理前端异常退出导致的僵尸锁定
    """
    service = RLHFService(db)
    count = await service.cleanup_expired_locks()
    return ResponseData(data={"success": True, "cleaned_count": count})


@router.put("/contents/{id}", response_model=ResponseData[RLHFFeedbackOut])
async def update_content(
    id: int = Path(..., title="Feedback ID"),
    data: RLHFFeedbackUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """修改内容"""
    service = RLHFService(db)
    try:
        result = await service.update_content(
            id, 
            data, 
            str(current_user.id), 
            current_user.username or current_user.email
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/contents/{id}/refine", response_model=ResponseData[RLHFFeedbackOut])
async def refine_content(
    id: int = Path(..., title="Feedback ID"),
    data: dict = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """原文精修 - 保存精修后的标题和内容
    
    请求体: { "refined_title": "精修后标题", "refined_content": "精修后内容" }
    
    同时更新:
    1. rlhf_feedback 表的 modified_title, modified_content
    2. content 表的 title, content, tags (添加 modified 标记)
    """
    service = RLHFService(db)
    try:
        result = await service.refine_content(
            id,
            data.get("refined_title"),
            data.get("refined_content"),
            str(current_user.id),
            current_user.username or current_user.email
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/contents/{id}/review-status", response_model=ResponseData[RLHFFeedbackOut])
async def update_review_status(
    id: int = Path(..., title="Feedback ID"),
    data: dict = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """更新审核状态（喜欢/不喜欢），可附带修改意见和问题标签"""
    service = RLHFService(db)
    try:
        result = await service.update_review_status(
            id,
            data.get("review_status"),
            str(current_user.id),
            current_user.username or current_user.email,
            comment=data.get("comment"),
            issue_tag_names=data.get("issue_tag_names"),
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/contents/{id}/inspection", response_model=ResponseData[RLHFFeedbackOut])
async def inspection_content(
    id: int = Path(..., title="Feedback ID"),
    data: RLHFInspectionRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """抽检判定"""
    service = RLHFService(db)
    try:
        result = await service.inspection(
            id, 
            data, 
            str(current_user.id), 
            current_user.username or current_user.email
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/contents/{id}/suggest-tags", response_model=ResponseData[RLHFSummaryResponse])
async def suggest_tags(
    id: int = Path(..., title="Feedback ID"),
    data: RLHFSummaryRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """根据划词评论和人工意见，利用 AI 总结问题标签"""
    service = RLHFService(db)
    try:
        tags = await service.suggest_tags(id, data)
        return ResponseData(data=RLHFSummaryResponse(tags=tags))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Summary failed: {str(e)}")


@router.post("/contents/{id}/summarize-comment", response_model=ResponseData[RLHFSummarizeCommentResponse])
async def summarize_comment(
    id: int = Path(..., title="Feedback ID"),
    data: RLHFSummarizeCommentRequest = RLHFSummarizeCommentRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """AI 总结意见 - 根据原文和划词评论生成修改意见"""
    service = RLHFService(db)
    try:
        comment = await service.summarize_comment(id, data)
        return ResponseData(data=RLHFSummarizeCommentResponse(comment=comment))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 总结意见失败: {str(e)}")


# --- Review Operations ---

@router.post("/contents/{id}/like", response_model=ResponseData[RLHFFeedbackOut])
async def like_content(
    id: int = Path(..., title="Feedback ID"),
    data: RLHFLikeRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """喜欢/不喜欢"""
    service = RLHFService(db)
    try:
        result = await service.like(
            id, 
            data, 
            str(current_user.id), 
            current_user.username or current_user.email
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/contents/{id}/adopt", response_model=ResponseData[RLHFFeedbackOut])
async def adopt_content(
    id: int = Path(..., title="Feedback ID"),
    data: RLHFAdoptRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """采纳/不采纳/废弃"""
    service = RLHFService(db)
    try:
        result = await service.adopt(
            id, 
            data, 
            str(current_user.id), 
            current_user.username or current_user.email
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/contents/{id}/score", response_model=ResponseData[RLHFFeedbackOut])
async def score_content(
    id: int = Path(..., title="Feedback ID"),
    data: RLHFScoreRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """评分"""
    service = RLHFService(db)
    try:
        result = await service.score(
            id, 
            data, 
            str(current_user.id), 
            current_user.username or current_user.email
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/contents/{id}/tags", response_model=ResponseData[RLHFFeedbackOut])
async def tag_content(
    id: int = Path(..., title="Feedback ID"),
    data: RLHFTagRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """添加标签 (复用 score 接口逻辑，仅更新标签)"""
    # 实际上 score 接口已经支持更新标签，这里为了 API 语义清晰单独提供，或者复用 score 逻辑
    # 我们可以复用 score 方法，只需允许 score 字段可选（但 Schema 中是必填）。
    # 为了简化，这里要求前端调用 score 接口一并提交，或者修改 service 支持仅更新标签。
    # 根据设计文档，tags 是单独接口。我们调整 service 的 score 方法或者新增 update_tags 方法。
    # 这里暂时让它复用 score 接口，但如果前端只传 tags 可能会报错。
    # 鉴于 score 接口 schema 中 score 是必填，我们建议前端在最后一步提交所有信息。
    # 如果需要单独更新标签，可以在 service 中新增方法。
    
    # 这里简单实现为：复用 score 逻辑，但如果 score 为 0 则保持原值？
    # 不，最简单的办法是前端在提交标签时也提交当前评分。
    # 或者我们实现一个 update_tags 方法。
    raise HTTPException(status_code=501, detail="Please use /score endpoint to update tags along with scores")

@router.get("/contents/{id}/history", response_model=ResponseData[List[RLHFOperationHistoryOut]])
async def get_content_history(
    id: int = Path(..., title="Feedback ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """获取审核历史"""
    service = RLHFService(db)
    items = await service.get_history(id)
    return ResponseData(data=items)

# --- Issue Tags Management ---

@router.get("/issue-tags", response_model=ResponseData[List[RLHFIssueTagOut]])
async def list_issue_tags(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """获取问题标签列表"""
    service = RLHFService(db)
    items = await service.list_tags()
    return ResponseData(data=items)

@router.post("/issue-tags", response_model=ResponseData[RLHFIssueTagOut])
async def create_issue_tag(
    data: RLHFIssueTagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """创建问题标签"""
    service = RLHFService(db)
    result = await service.create_tag(data, str(current_user.id))
    return ResponseData(data=result)

@router.put("/issue-tags/{id}", response_model=ResponseData[RLHFIssueTagOut])
async def update_issue_tag(
    id: int,
    data: RLHFIssueTagUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """更新问题标签"""
    service = RLHFService(db)
    tag = await service.update_tag(id, data, str(current_user.id))
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return ResponseData(data=tag)

@router.delete("/issue-tags/{id}", response_model=ResponseData[dict])
async def delete_issue_tag(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """删除问题标签"""
    service = RLHFService(db)
    success = await service.delete_tag(id)
    if not success:
        raise HTTPException(status_code=404, detail="Tag not found")
    return ResponseData(data={"success": True})

# --- Stats ---

@router.get("/stats/summary", response_model=ResponseData[RLHFStatsSummary])
async def get_stats_summary(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """获取统计摘要"""
    service = RLHFService(db)
    result = await service.get_stats_summary()
    return ResponseData(data=result)

@router.get("/stats/by-reviewer", response_model=ResponseData[List[RLHFReviewerStats]])
async def get_reviewer_stats(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_active_user),
):
    """按审核人统计"""
    service = RLHFService(db)
    result = await service.get_reviewer_stats()
    return ResponseData(data=result)

