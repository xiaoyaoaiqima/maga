import json
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select, update, func, desc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.expert_caller import ExpertCaller, TraceData
from loguru import logger

from app.models.rlhf_feedback import RLHFFeedback
from app.models.rlhf_operation_history import RLHFOperationHistory
from app.models.rlhf_issue_tag import RLHFIssueTag
from app.models.rlhf_daily_stats import RLHFDailyStats
from app.models.expert_call_trace import ExpertCallTrace
from app.models.content import Content
from app.models.expert_business_result import ExpertBusinessResult
from app.models.expert_config import ExpertConfig
from app.schemas.rlhf import (
    RLHFFeedbackCreate,
    RLHFFeedbackUpdate,
    RLHFIssueTagCreate,
    RLHFIssueTagUpdate,
    RLHFLikeRequest,
    RLHFAdoptRequest,
    RLHFScoreRequest,
    RLHFInspectionRequest,
    RLHFSummaryRequest,
    RLHFSummarizeCommentRequest,
)

class RLHFService:
    # 【方案C】每个用户最大锁定数量限制
    MAX_LOCKED_PER_USER = 20
    
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Feedback CRUD ---

    async def get(self, id: int, with_context: bool = True) -> Optional[Dict[str, Any]]:
        """获取 Feedback 详情，可选关联获取 context_list"""
        result = await self.db.execute(select(RLHFFeedback).where(RLHFFeedback.id == id, RLHFFeedback.is_deleted == 0))
        feedback = result.scalar_one_or_none()
        if not feedback:
            return None
        
        # 转换为 dict
        feedback_dict = {
            "id": feedback.id,
            "job_id": feedback.job_id,
            "sub_job_id": feedback.sub_job_id,
            "content_id": feedback.content_id,
            "trace_id": feedback.trace_id,
            "title": feedback.title,
            "content": feedback.content,
            "modified_title": feedback.modified_title,
            "modified_content": feedback.modified_content,
            "modify_count": feedback.modify_count,
            "ge_expert_code": feedback.ge_expert_code,
            "ag_expert_codes": feedback.ag_expert_codes,
            "model_code": feedback.model_code,
            "like_status": feedback.like_status,
            "like_reason": feedback.like_reason,
            "like_user_id": feedback.like_user_id,
            "like_user_name": feedback.like_user_name,
            "like_time": feedback.like_time,
            "adopt_status": feedback.adopt_status,
            "adopt_reason": feedback.adopt_reason,
            "adopt_user_id": feedback.adopt_user_id,
            "adopt_user_name": feedback.adopt_user_name,
            "adopt_time": feedback.adopt_time,
            "discard_reason_type": feedback.discard_reason_type,
            "discard_comment": feedback.discard_comment,
            "improvement_suggestion": feedback.improvement_suggestion,
            "content_score": float(feedback.content_score) if feedback.content_score else 0,
            "model_score": float(feedback.model_score) if feedback.model_score else 0,
            "issue_tag_ids": feedback.issue_tag_ids,
            "custom_issue_tags": feedback.custom_issue_tags,
            "annotations": feedback.annotations,
            "review_status": feedback.review_status,
            "is_locked": feedback.is_locked,
            "lock_user_id": feedback.lock_user_id,
            "lock_user_name": feedback.lock_user_name,
            "lock_time": feedback.lock_time,
            "lock_expire_time": feedback.lock_expire_time,
            "inspection_status": feedback.inspection_status,
            "inspection_result": feedback.inspection_result,
            "inspection_comment": feedback.inspection_comment,
            "inspection_user_id": feedback.inspection_user_id,
            "inspection_user_name": feedback.inspection_user_name,
            "inspection_time": feedback.inspection_time,
            "review_user_id": feedback.review_user_id,
            "review_user_name": feedback.review_user_name,
            "review_time": feedback.review_time,
            "created_at": feedback.created_at,
            "updated_at": feedback.updated_at,
            "context_list": None,
        }
        
        # 关联获取 context_list
        if with_context and feedback.content_id:
            content_result = await self.db.execute(
                select(Content).where(Content.content_id == feedback.content_id)
            )
            content = content_result.scalar_one_or_none()
            if content:
                feedback_dict["context_list"] = content.context_list
        
        return feedback_dict
    
    async def get_raw(self, id: int) -> Optional[RLHFFeedback]:
        """获取原始 Feedback 对象（用于内部操作）"""
        result = await self.db.execute(select(RLHFFeedback).where(RLHFFeedback.id == id, RLHFFeedback.is_deleted == 0))
        return result.scalar_one_or_none()

    async def get_by_content_id(self, content_id: str) -> Optional[RLHFFeedback]:
        result = await self.db.execute(
            select(RLHFFeedback).where(RLHFFeedback.content_id == content_id, RLHFFeedback.is_deleted == 0)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        job_id: Optional[str] = None,
        review_status: Optional[str] = None,
        inspection_status: Optional[str] = None,
        like_status: Optional[int] = None,
        adopt_status: Optional[int] = None,
        keyword: Optional[str] = None,
        reviewer_id: Optional[str] = None,
        exclude_locked_by_others: bool = False,
        current_user_id: Optional[str] = None,
        ge_expert_code: Optional[str] = None,
        tenant_id: Optional[int] = None,
        only_ban_passed: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        query = select(RLHFFeedback).where(RLHFFeedback.is_deleted == 0)

        if job_id:
            query = query.where(RLHFFeedback.job_id == job_id)
        if review_status:
            query = query.where(RLHFFeedback.review_status == review_status)
        if inspection_status:
            query = query.where(RLHFFeedback.inspection_status == inspection_status)
        if like_status is not None:
            query = query.where(RLHFFeedback.like_status == like_status)
        if adopt_status is not None:
            query = query.where(RLHFFeedback.adopt_status == adopt_status)

        # 租户 + Agent 筛选：通过关联 Content 表获取 content_id，再反查 rlhf_feedback.content_id
        # 说明：
        # - 这里的 ge_expert_code 实际代表“Agent（专家组合）编码”，应当匹配 content.agent_code
        # - rlhf_feedback.ge_expert_code 是“生文专家”概念，不能用于此处筛选
        if tenant_id is not None or ge_expert_code:
            content_filters = [Content.is_deleted == 0]
            if tenant_id is not None:
                content_filters.append(Content.tenant_id == tenant_id)
            if ge_expert_code:
                content_filters.append(Content.agent_code == ge_expert_code)

            content_subquery = select(Content.content_id).where(and_(*content_filters))
            query = query.where(RLHFFeedback.content_id.in_(content_subquery))
        
        if reviewer_id:
            # 筛选由特定审核人审核（喜欢/不喜欢）的文章
            # 匹配 review_user_id 或 like_user_id
            logger.info(f"[RLHF] Filtering by reviewer_id: {reviewer_id}")
            query = query.where(
                or_(
                    RLHFFeedback.review_user_id == reviewer_id,
                    RLHFFeedback.like_user_id == reviewer_id,
                )
            )
        
        # 锁定过滤逻辑已废弃：允许多用户同时查看和抽检同一篇文章
        # if exclude_locked_by_others and current_user_id:
        #     query = query.where(
        #         or_(
        #             RLHFFeedback.is_locked == 0,  # 未锁定
        #             RLHFFeedback.lock_user_id == current_user_id,  # 自己锁定的
        #             RLHFFeedback.lock_expire_time < datetime.now(),  # 锁定已过期
        #             RLHFFeedback.lock_expire_time.is_(None),  # 没有过期时间
        #         )
        #     )

        if keyword:
            query = query.where(
                or_(
                    RLHFFeedback.title.ilike(f"%{keyword}%"),
                    RLHFFeedback.content.ilike(f"%{keyword}%"),
                    RLHFFeedback.content_id.ilike(f"%{keyword}%")
                )
            )

        # 仅显示合规通过的文章（需要满足：有 BAN 结果 且 所有 BAN 都通过）
        if only_ban_passed:
            from sqlalchemy import text
            
            # 子查询1：找出有 BAN 结果的 content_id（确保文章有 BAN 审核）
            has_ban_result_subquery = (
                select(ExpertBusinessResult.content_id)
                .join(
                    ExpertConfig,
                    ExpertBusinessResult.expert_config_code == ExpertConfig.expert_config_code
                )
                .where(
                    ExpertConfig.expert_type == "BAN",
                    ExpertConfig.is_deleted == 0,
                    ExpertBusinessResult.is_deleted == 0,
                )
                .distinct()
            )
            
            # 子查询2：找出有 BAN 失败记录的 content_id
            # BAN 失败条件：passed != 1 且 score != 1（即没有明确的通过标识）
            ban_failed_subquery = (
                select(ExpertBusinessResult.content_id)
                .join(
                    ExpertConfig,
                    ExpertBusinessResult.expert_config_code == ExpertConfig.expert_config_code
                )
                .where(
                    ExpertConfig.expert_type == "BAN",
                    ExpertConfig.is_deleted == 0,
                    ExpertBusinessResult.is_deleted == 0,
                    # 失败条件：passed 不等于 1，且 score 也不等于 1
                    # 使用 COALESCE 处理 NULL 值，默认为 0（失败）
                    text("""
                        NOT (
                            COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(expert_business_result.business_result, '$.passed')) AS SIGNED), 0) = 1
                            OR COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(expert_business_result.business_result, '$.score')) AS SIGNED), 0) = 1
                        )
                    """)
                )
                .distinct()
            )
            
            # 筛选条件：有 BAN 结果 且 没有任何失败的 BAN 结果
            query = query.where(
                RLHFFeedback.content_id.in_(has_ban_result_subquery),
                RLHFFeedback.content_id.notin_(ban_failed_subquery)
            )

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Paging
        query = query.order_by(RLHFFeedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        feedbacks = (await self.db.execute(query)).scalars().all()

        # 批量获取 context_list：收集所有 content_id，一次性查询 Content 表
        content_ids = [f.content_id for f in feedbacks if f.content_id]
        context_map: Dict[str, Any] = {}
        if content_ids:
            content_result = await self.db.execute(
                select(Content.content_id, Content.context_list).where(
                    Content.content_id.in_(content_ids),
                    Content.is_deleted == 0
                )
            )
            for row in content_result:
                context_map[row.content_id] = row.context_list

        # 转换为字典列表，附加 context_list
        items = []
        for feedback in feedbacks:
            feedback_dict = {
                "id": feedback.id,
                "job_id": feedback.job_id,
                "sub_job_id": feedback.sub_job_id,
                "content_id": feedback.content_id,
                "trace_id": feedback.trace_id,
                "title": feedback.title,
                "content": feedback.content,
                "modified_title": feedback.modified_title,
                "modified_content": feedback.modified_content,
                "modify_count": feedback.modify_count,
                "ge_expert_code": feedback.ge_expert_code,
                "ag_expert_codes": feedback.ag_expert_codes,
                "model_code": feedback.model_code,
                "like_status": feedback.like_status,
                "like_reason": feedback.like_reason,
                "like_user_id": feedback.like_user_id,
                "like_user_name": feedback.like_user_name,
                "like_time": feedback.like_time,
                "adopt_status": feedback.adopt_status,
                "adopt_reason": feedback.adopt_reason,
                "adopt_user_id": feedback.adopt_user_id,
                "adopt_user_name": feedback.adopt_user_name,
                "adopt_time": feedback.adopt_time,
                "discard_reason_type": feedback.discard_reason_type,
                "discard_comment": feedback.discard_comment,
                "improvement_suggestion": feedback.improvement_suggestion,
                "content_score": float(feedback.content_score) if feedback.content_score else 0,
                "model_score": float(feedback.model_score) if feedback.model_score else 0,
                "issue_tag_ids": feedback.issue_tag_ids,
                "custom_issue_tags": feedback.custom_issue_tags,
                "annotations": feedback.annotations,
                "review_status": feedback.review_status,
                "is_locked": feedback.is_locked,
                "lock_user_id": feedback.lock_user_id,
                "lock_user_name": feedback.lock_user_name,
                "lock_time": feedback.lock_time,
                "lock_expire_time": feedback.lock_expire_time,
                "inspection_status": feedback.inspection_status,
                "inspection_result": feedback.inspection_result,
                "inspection_comment": feedback.inspection_comment,
                "inspection_user_id": feedback.inspection_user_id,
                "inspection_user_name": feedback.inspection_user_name,
                "inspection_time": feedback.inspection_time,
                "review_user_id": feedback.review_user_id,
                "review_user_name": feedback.review_user_name,
                "review_time": feedback.review_time,
                "created_at": feedback.created_at,
                "updated_at": feedback.updated_at,
                # 附加 context_list
                "context_list": context_map.get(feedback.content_id) if feedback.content_id else None,
            }
            items.append(feedback_dict)

        return items, total

    async def create(self, feedback_in: RLHFFeedbackCreate) -> RLHFFeedback:
        feedback = RLHFFeedback(**feedback_in.model_dump())
        self.db.add(feedback)
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def get_random_pending(self, count: int = 1, user_id: str = None, user_name: str = None) -> List[RLHFFeedback]:
        """随机获取并锁定 Pending 状态的内容"""
        # 1. 查找未锁定的 Pending 记录
        query = select(RLHFFeedback).where(
            RLHFFeedback.review_status == "PENDING",
            or_(
                RLHFFeedback.is_locked == 0,
                RLHFFeedback.lock_expire_time < datetime.now()
            ),
            RLHFFeedback.is_deleted == 0
        ).order_by(func.random()).limit(count)
        
        items = (await self.db.execute(query)).scalars().all()
        
        # 2. 自动锁定
        results = []
        for item in items:
            try:
                await self.lock(item.id, user_id, user_name)
                # 重新获取以确保状态最新
                await self.db.refresh(item)
                results.append(item)
            except Exception as e:
                logger.warning(f"Failed to auto-lock feedback {item.id}: {e}")
        
        return results

    # --- Actions ---

    async def lock(self, id: int, user_id: str, user_name: str) -> bool:
        """
        原子锁定 - 使用 FOR UPDATE 确保并发安全
        
        参考 MySQL InnoDB 行级锁设计：
        - 使用 SELECT ... FOR UPDATE 获取行级排他锁
        - 在同一事务中完成检查和更新，避免竞态条件
        """
        now = datetime.now()
        
        # 使用 FOR UPDATE 获取行级排他锁
        # 修改：移除锁定限制，允许多用户同时进入详情页（原本会抛出已被锁定的错误）
        stmt = (
            select(RLHFFeedback)
            .where(
                RLHFFeedback.id == id,
                RLHFFeedback.is_deleted == 0
            )
            .with_for_update()  # 行级排他锁
        )
        
        result = await self.db.execute(stmt)
        feedback = result.scalar_one_or_none()
        
        if not feedback:
            # 可能是记录不存在，或者被其他用户锁定
            # 尝试获取记录以提供更准确的错误信息
            check_stmt = select(RLHFFeedback).where(
                RLHFFeedback.id == id,
                RLHFFeedback.is_deleted == 0
            )
            check_result = await self.db.execute(check_stmt)
            existing = check_result.scalar_one_or_none()
            
            if not existing:
                raise ValueError("Feedback not found")
            else:
                raise ValueError(f"Content is locked by {existing.lock_user_name or 'another user'}")
        
        # 在同一事务中更新锁定信息
        feedback.is_locked = 1
        feedback.lock_user_id = user_id
        feedback.lock_user_name = user_name
        feedback.lock_time = now
        feedback.lock_expire_time = now + timedelta(minutes=30)
        
        await self._log_operation(feedback, "LOCK", None, None, operator_id=user_id, operator_name=user_name)
        await self.db.commit()
        return True

    async def unlock(self, id: int, user_id: str) -> bool:
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")

        # 只能解锁自己的，除非是管理员（这里简化处理）
        if feedback.is_locked == 1 and feedback.lock_user_id != user_id:
            # 暂时允许解锁过期的
             if feedback.lock_expire_time and feedback.lock_expire_time > datetime.now():
                raise ValueError("Cannot unlock content locked by others")

        feedback.is_locked = 0
        feedback.lock_user_id = None
        feedback.lock_user_name = None
        feedback.lock_expire_time = None
        
        await self._log_operation(feedback, "UNLOCK", None, None, operator_id=user_id, operator_name="")
        await self.db.commit()
        return True

    async def get_user_locked_count(self, user_id: str) -> int:
        """获取用户当前锁定的文章数量（未过期的）"""
        now = datetime.now()
        result = await self.db.execute(
            select(func.count(RLHFFeedback.id)).where(
                RLHFFeedback.is_locked == 1,
                RLHFFeedback.lock_user_id == user_id,
                RLHFFeedback.lock_expire_time > now,
                RLHFFeedback.is_deleted == 0,
            )
        )
        return result.scalar() or 0

    async def get_user_locked_ids_ordered_by_time(self, user_id: str, exclude_ids: List[int] = None) -> List[int]:
        """获取用户锁定的文章ID列表，按锁定时间升序排列（最早的在前）"""
        now = datetime.now()
        query = select(RLHFFeedback.id).where(
            RLHFFeedback.is_locked == 1,
            RLHFFeedback.lock_user_id == user_id,
            RLHFFeedback.lock_expire_time > now,
            RLHFFeedback.is_deleted == 0,
        )
        if exclude_ids:
            query = query.where(RLHFFeedback.id.notin_(exclude_ids))
        query = query.order_by(RLHFFeedback.lock_time.asc())
        result = await self.db.execute(query)
        return [row[0] for row in result.fetchall()]

    async def batch_lock(self, ids: List[int], user_id: str, user_name: str) -> Dict[str, Any]:
        """
        批量获取文章（原锁定逻辑已废弃，现在仅用于记录当前操作人）
        
        不再限制最大锁定数量，不再自动解锁。
        """
        now = datetime.now()
        auto_unlocked_ids = []
        
        # 3. 批量获取行（移除 SKIP LOCKED，允许多用户“锁定”同一篇文章）
        # 修改：不再排除已被锁定的行，确保所有人都能成功“加载”文章
        stmt = (
            select(RLHFFeedback)
            .where(
                RLHFFeedback.id.in_(ids),
                RLHFFeedback.is_deleted == 0
            )
            .with_for_update()  # 行级排他锁
        )
        
        result = await self.db.execute(stmt)
        feedbacks = result.scalars().all()
        
        # 4. 在同一事务中更新所有可锁定的行
        success_ids = []
        for feedback in feedbacks:
            feedback.is_locked = 1
            feedback.lock_user_id = user_id
            feedback.lock_user_name = user_name
            feedback.lock_time = now
            feedback.lock_expire_time = now + timedelta(minutes=30)
            success_ids.append(feedback.id)
        
        # 5. 单一事务提交
        await self.db.commit()
        
        # 6. 计算失败的 ID（请求的 ID 中未能锁定的）
        failed_ids = [id for id in ids if id not in success_ids]
        
        result_dict = {
            "success_count": len(success_ids),
            "failed_count": len(failed_ids),
            "success_ids": success_ids,
            "failed_ids": failed_ids,
            "auto_unlocked_ids": auto_unlocked_ids,
            "auto_unlocked_count": len(auto_unlocked_ids),
        }
        
        if auto_unlocked_ids:
            result_dict["message"] = f"当前锁定文章超过{self.MAX_LOCKED_PER_USER}篇，已自动解锁最早锁定的 {len(auto_unlocked_ids)} 篇文章"
        
        return result_dict

    async def batch_unlock(self, ids: List[int], user_id: str) -> Dict[str, Any]:
        """
        批量解锁文章 - 使用单一 UPDATE 语句提高效率
        
        只能解锁自己锁定的文章或已过期的锁定
        """
        now = datetime.now()
        
        # 1. 先查询哪些 ID 可以被解锁（MySQL 不支持 RETURNING）
        check_stmt = select(RLHFFeedback.id).where(
            RLHFFeedback.id.in_(ids),
            RLHFFeedback.is_deleted == 0,
            RLHFFeedback.is_locked == 1,
            or_(
                RLHFFeedback.lock_user_id == user_id,
                RLHFFeedback.lock_expire_time < now,
                RLHFFeedback.lock_expire_time.is_(None),
            )
        )
        check_result = await self.db.execute(check_stmt)
        unlockable_ids = [row[0] for row in check_result.fetchall()]
        
        if unlockable_ids:
            # 2. 批量解锁
            await self.db.execute(
                update(RLHFFeedback)
                .where(RLHFFeedback.id.in_(unlockable_ids))
                .values(
                    is_locked=0,
                    lock_user_id=None,
                    lock_user_name=None,
                    lock_expire_time=None,
                )
            )
            await self.db.commit()
        
        # 计算失败的 ID
        failed_ids = [id for id in ids if id not in unlockable_ids]
        
        return {
            "success_count": len(unlockable_ids),
            "failed_count": len(failed_ids),
            "success_ids": unlockable_ids,
            "failed_ids": failed_ids,
        }

    async def unlock_all_by_user(self, user_id: str) -> int:
        """解锁当前用户锁定的所有文章（用于用户离开页面时调用）"""
        result = await self.db.execute(
            update(RLHFFeedback)
            .where(
                RLHFFeedback.is_locked == 1,
                RLHFFeedback.lock_user_id == user_id,
                RLHFFeedback.is_deleted == 0
            )
            .values(
                is_locked=0,
                lock_user_id=None,
                lock_user_name=None,
                lock_expire_time=None
            )
        )
        await self.db.commit()
        return result.rowcount

    async def cleanup_expired_locks(self) -> int:
        """
        清理过期锁定 - 定时任务或手动触发
        
        用于处理前端异常退出（浏览器崩溃、网络断开等）导致的僵尸锁定
        """
        now = datetime.now()
        result = await self.db.execute(
            update(RLHFFeedback)
            .where(
                RLHFFeedback.is_locked == 1,
                RLHFFeedback.lock_expire_time < now,
                RLHFFeedback.is_deleted == 0,
            )
            .values(
                is_locked=0,
                lock_user_id=None,
                lock_user_name=None,
                lock_expire_time=None,
            )
        )
        await self.db.commit()
        return result.rowcount

    async def renew_locks(self, ids: List[int], user_id: str) -> Dict[str, Any]:
        """
        心跳续锁 - 延长锁定时间
        
        前端定期调用（如每 5 分钟），延长当前用户锁定的文章的过期时间
        只能续锁自己锁定的文章
        """
        now = datetime.now()
        new_expire_time = now + timedelta(minutes=30)
        
        # 只更新当前用户锁定且未过期的文章
        result = await self.db.execute(
            update(RLHFFeedback)
            .where(
                RLHFFeedback.id.in_(ids),
                RLHFFeedback.is_locked == 1,
                RLHFFeedback.lock_user_id == user_id,
                RLHFFeedback.lock_expire_time > now,  # 只续锁未过期的
                RLHFFeedback.is_deleted == 0,
            )
            .values(lock_expire_time=new_expire_time)
        )
        await self.db.commit()
        
        renewed_count = result.rowcount
        return {
            "success": True,
            "renewed_count": renewed_count,
            "new_expire_time": new_expire_time.isoformat(),
        }

    async def like(self, id: int, data: RLHFLikeRequest, user_id: str, user_name: str) -> RLHFFeedback:
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")

        # 校验
        if data.status == -1 and not data.improvement_suggestion:
             raise ValueError("Improvement suggestion is required for dislike")

        before = {"like_status": feedback.like_status, "like_reason": feedback.like_reason}
        
        feedback.like_status = data.status
        feedback.like_reason = data.reason
        feedback.like_user_id = user_id
        feedback.like_user_name = user_name
        feedback.like_time = datetime.now()
        
        if data.improvement_suggestion:
            feedback.improvement_suggestion = data.improvement_suggestion

        after = {"like_status": data.status, "like_reason": data.reason}
        
        # 用户点击喜欢/不喜欢判定后，主流程审核标记为 COMPLETED
        feedback.review_status = "COMPLETED"
        
        await self._log_operation(
            feedback, 
            "LIKE" if data.status == 1 else "DISLIKE", 
            before, 
            after, 
            reason=data.reason,
            improvement=data.improvement_suggestion,
            operator_id=user_id, 
            operator_name=user_name
        )
        
        # 上报 Trace
        await self._report_trace(
            feedback, 
            "rlhf_like", 
            user_id, 
            user_name, 
            {
                "status": data.status, 
                "reason": data.reason
            }
        )
        
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def adopt(self, id: int, data: RLHFAdoptRequest, user_id: str, user_name: str) -> RLHFFeedback:
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")

        if data.status == -1 and not data.improvement_suggestion:
             raise ValueError("Improvement suggestion is required for reject")

        before = {"adopt_status": feedback.adopt_status, "adopt_reason": feedback.adopt_reason}
        
        feedback.adopt_status = data.status
        feedback.adopt_reason = data.reason
        feedback.adopt_user_id = user_id
        feedback.adopt_user_name = user_name
        feedback.adopt_time = datetime.now()
        
        if data.discard_reason_type:
            feedback.discard_reason_type = data.discard_reason_type
        
        if data.improvement_suggestion:
            feedback.improvement_suggestion = data.improvement_suggestion

        after = {"adopt_status": data.status, "adopt_reason": data.reason}
        
        op_type = "ADOPT"
        if data.status == -1: op_type = "REJECT"
        elif data.status == 2: op_type = "DISCARD"

        await self._log_operation(
            feedback, 
            op_type, 
            before, 
            after, 
            reason=data.reason,
            improvement=data.improvement_suggestion,
            operator_id=user_id, 
            operator_name=user_name
        )
        
        # 上报 Trace
        await self._report_trace(
            feedback, 
            "rlhf_adopt", 
            user_id, 
            user_name, 
            {
                "status": data.status, 
                "reason": data.reason,
                "discard_type": data.discard_reason_type
            }
        )

        # 如果已完成关键步骤，更新 review_status 为 COMPLETED (简单逻辑：采纳/废弃即完成，或只打分？这里保持 IN_PROGRESS，需打分后才可能完成，或者由前端手动触发？
        # 按照设计：流程是 喜欢 -> 采纳 -> 评分。
        # 这里暂不自动 COMPLETED，除非...
        
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def score(self, id: int, data: RLHFScoreRequest, user_id: str, user_name: str) -> RLHFFeedback:
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")

        before = {
            "content_score": str(feedback.content_score), 
            "model_score": str(feedback.model_score),
            "issue_tag_ids": feedback.issue_tag_ids,
            "modified_title": feedback.modified_title,
            "modified_content": feedback.modified_content
        }
        
        feedback.content_score = data.content_score
        feedback.model_score = data.model_score
        
        if data.issue_tag_ids is not None:
            feedback.issue_tag_ids = data.issue_tag_ids
        if data.custom_issue_tags is not None:
            feedback.custom_issue_tags = data.custom_issue_tags

        # Handle content updates if provided during scoring
        content_changed = False
        if data.modified_title is not None and data.modified_title != feedback.modified_title:
            feedback.modified_title = data.modified_title
            content_changed = True
        if data.modified_content is not None and data.modified_content != feedback.modified_content:
            feedback.modified_content = data.modified_content
            content_changed = True
            
        if content_changed:
            feedback.modify_count += 1

        after = {
            "content_score": data.content_score,
            "model_score": data.model_score,
            "issue_tag_ids": data.issue_tag_ids,
            "modified_title": feedback.modified_title,
            "modified_content": feedback.modified_content
        }
        
        await self._log_operation(
            feedback, 
            "SCORE", 
            before, 
            after, 
            operator_id=user_id, 
            operator_name=user_name
        )

        # 评分通常是最后一步，可以标记为 COMPLETED 并解锁
        feedback.review_status = "COMPLETED"
        feedback.is_locked = 0  # 自动解锁
        
        # 上报 Trace
        await self._report_trace(
            feedback, 
            "rlhf_score", 
            user_id, 
            user_name, 
            after
        )

        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def update_content(self, id: int, data: RLHFFeedbackUpdate, user_id: str, user_name: str) -> RLHFFeedback:
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")
        
        before = {
            "modified_title": feedback.modified_title,
            "modified_content": feedback.modified_content,
            "annotations": feedback.annotations,
            "improvement_suggestion": feedback.improvement_suggestion,
            "issue_tag_ids": feedback.issue_tag_ids,
        }
        
        changed = False
        if data.modified_title is not None:
            feedback.modified_title = data.modified_title
            changed = True
        if data.modified_content is not None:
            feedback.modified_content = data.modified_content
            changed = True
        if data.annotations is not None:
            feedback.annotations = data.annotations
            changed = True
        
        # 保存 AI 生成的修改意见
        if data.improvement_suggestion is not None:
            feedback.improvement_suggestion = data.improvement_suggestion
            changed = True
        
        # 处理问题标签（标签名转换为标签ID）
        if data.issue_tag_names is not None:
            final_tag_ids = []
            for tag_name in data.issue_tag_names:
                tag_name = tag_name.strip()
                if not tag_name:
                    continue
                
                # 查找是否存在
                stmt = select(RLHFIssueTag).where(
                    RLHFIssueTag.tag_name == tag_name, 
                    RLHFIssueTag.is_deleted == 0
                )
                res = await self.db.execute(stmt)
                existing_tag = res.scalar_one_or_none()
                
                if existing_tag:
                    final_tag_ids.append(existing_tag.id)
                else:
                    # 自动创建新标签
                    import uuid
                    tag_code = f"tag_{uuid.uuid4().hex[:8]}"
                    
                    new_tag = RLHFIssueTag(
                        tag_code=tag_code,
                        tag_name=tag_name,
                        tag_category="OTHER",
                        created_by=user_id
                    )
                    self.db.add(new_tag)
                    await self.db.flush()
                    final_tag_ids.append(new_tag.id)
            
            feedback.issue_tag_ids = final_tag_ids if final_tag_ids else None
            changed = True
            
        if changed:
            feedback.modify_count += 1
            # 状态流转逻辑：
            # 1. 如果是初始状态 (PENDING)，只要有了划词评论 (annotations) 就转为"审核中" (IN_PROGRESS)
            if feedback.review_status == "PENDING" and data.annotations is not None:
                feedback.review_status = "IN_PROGRESS"
            # 2. 如果主流程已完成 (COMPLETED)，再次修改划词评论则进入"抽检中" (IN_INSPECTION)
            elif feedback.review_status == "COMPLETED" and data.annotations is not None:
                feedback.review_status = "IN_INSPECTION"
            
        after = {
            "modified_title": feedback.modified_title,
            "modified_content": feedback.modified_content,
            "annotations": feedback.annotations,
            "improvement_suggestion": feedback.improvement_suggestion,
            "issue_tag_ids": feedback.issue_tag_ids,
        }
        
        await self._log_operation(
            feedback, 
            "EDIT", 
            before, 
            after, 
            operator_id=user_id, 
            operator_name=user_name
        )
        
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def refine_content(
        self, 
        id: int, 
        refined_title: Optional[str],
        refined_content: Optional[str],
        user_id: str, 
        user_name: str
    ) -> RLHFFeedback:
        """
        原文精修 - 保存精修后的标题和内容
        
        同时更新:
        1. rlhf_feedback 表的 modified_title, modified_content
        2. content 表的 title, content, tags (添加 modified 标记)
        """
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")
        
        before = {
            "modified_title": feedback.modified_title,
            "modified_content": feedback.modified_content,
        }
        
        changed = False
        
        # 更新 rlhf_feedback 表
        if refined_title is not None:
            feedback.modified_title = refined_title
            changed = True
        if refined_content is not None:
            feedback.modified_content = refined_content
            changed = True
        
        if changed:
            feedback.modify_count += 1
            feedback.updated_by = user_id
        
        # 同步更新 content 表
        if feedback.content_id:
            content_result = await self.db.execute(
                select(Content).where(Content.content_id == feedback.content_id)
            )
            content = content_result.scalar_one_or_none()
            if content:
                if refined_title is not None:
                    content.title = refined_title
                if refined_content is not None:
                    content.content = refined_content
                
                # 更新 tags，添加 modified 标记
                existing_tags = content.tags or {}
                existing_tags["modified"] = True
                content.tags = existing_tags
        
        after = {
            "modified_title": feedback.modified_title,
            "modified_content": feedback.modified_content,
        }
        
        await self._log_operation(
            feedback, 
            "REFINE", 
            before, 
            after, 
            operator_id=user_id, 
            operator_name=user_name
        )
        
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def update_review_status(
        self, id: int, review_status: str, user_id: str, user_name: str,
        comment: str = None,
        issue_tag_names: List[str] = None
    ) -> RLHFFeedback:
        """更新审核状态（喜欢/不喜欢），可附带修改意见和问题标签"""
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")

        valid_statuses = ["PENDING", "IN_PROGRESS", "LIKED", "DISLIKED"]
        if review_status not in valid_statuses:
            raise ValueError(f"Invalid review_status, must be one of {valid_statuses}")

        before = {"review_status": feedback.review_status}
        feedback.review_status = review_status
        
        # 记录审核人信息
        feedback.review_user_id = user_id
        feedback.review_user_name = user_name
        feedback.review_time = datetime.now()
        feedback.updated_by = user_id
        
        # 记录修改意见（存入 improvement_suggestion 字段）
        if comment and comment.strip():
            feedback.improvement_suggestion = comment.strip()
        
        # 处理问题标签
        if issue_tag_names:
            final_tag_ids = []
            for tag_name in issue_tag_names:
                tag_name = tag_name.strip()
                if not tag_name:
                    continue
                
                # 查找是否存在
                stmt = select(RLHFIssueTag).where(
                    RLHFIssueTag.tag_name == tag_name, 
                    RLHFIssueTag.is_deleted == 0
                )
                res = await self.db.execute(stmt)
                existing_tag = res.scalar_one_or_none()
                
                if existing_tag:
                    final_tag_ids.append(existing_tag.id)
                else:
                    # 自动创建新标签
                    import uuid
                    tag_code = f"tag_{uuid.uuid4().hex[:8]}"
                    
                    new_tag = RLHFIssueTag(
                        tag_code=tag_code,
                        tag_name=tag_name,
                        tag_category="OTHER",
                        created_by=user_id
                    )
                    self.db.add(new_tag)
                    await self.db.flush()
                    final_tag_ids.append(new_tag.id)
            
            feedback.issue_tag_ids = final_tag_ids
        
        after = {"review_status": feedback.review_status, "comment": comment, "issue_tag_names": issue_tag_names}

        await self._log_operation(
            feedback,
            "REVIEW",
            before,
            after,
            reason=comment,
            operator_id=user_id,
            operator_name=user_name,
        )

        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def inspection(self, id: int, data: RLHFInspectionRequest, user_id: str, user_name: str) -> RLHFFeedback:
        """抽检操作"""
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")
        
        # 校验：必须有划词评论（annotations）且必须有抽检意见（comment）
        if not feedback.annotations or len(feedback.annotations) == 0:
            raise ValueError("必须先添加划词评论才能提交抽检结果")
        
        if not data.comment or not data.comment.strip():
            raise ValueError("必须填写抽检意见才能提交抽检结果")

        # 处理标签映射与新增（注意：issue_tag_names 可能是空列表 []，需要区分 None 和 []）
        if data.issue_tag_names is not None:
            final_tag_ids = []
            for tag_name in data.issue_tag_names:
                tag_name = tag_name.strip()
                if not tag_name: continue
                
                # 查找是否存在
                stmt = select(RLHFIssueTag).where(RLHFIssueTag.tag_name == tag_name, RLHFIssueTag.is_deleted == 0)
                res = await self.db.execute(stmt)
                existing_tag = res.scalar_one_or_none()
                
                if existing_tag:
                    final_tag_ids.append(existing_tag.id)
                else:
                    # 自动创建新标签
                    import uuid
                    # 生成简单的 tag_code
                    tag_code = f"tag_{uuid.uuid4().hex[:8]}"
                    
                    new_tag = RLHFIssueTag(
                        tag_code=tag_code,
                        tag_name=tag_name,
                        tag_category="OTHER",
                        created_by=user_id
                    )
                    self.db.add(new_tag)
                    await self.db.flush() # 获取 ID
                    final_tag_ids.append(new_tag.id)
            
            # 更新标签ID列表（包括空列表，以支持清空标签）
            feedback.issue_tag_ids = final_tag_ids if final_tag_ids else None

        # 验证结果值
        if data.result not in ("PASSED", "FAILED"):
            raise ValueError("Invalid inspection result, must be PASSED or FAILED")
        
        before = {
            "review_status": feedback.review_status,
            "inspection_status": feedback.inspection_status,
            "inspection_result": feedback.inspection_result,
            "inspection_comment": feedback.inspection_comment,
        }
        
        # 根据结果设置状态
        feedback.inspection_status = data.result  # PASSED 或 FAILED
        feedback.inspection_result = data.result
        feedback.inspection_comment = data.comment
        # 同时存储到 improvement_suggestion 字段，确保 AI 修改意见可以被正确读取
        feedback.improvement_suggestion = data.comment
        feedback.inspection_user_id = user_id
        feedback.inspection_user_name = user_name
        feedback.inspection_time = datetime.now()
        feedback.is_locked = 0  # 抽检完成后解锁
        
        # 更新 review_status 以匹配 UI 逻辑
        if data.result == "PASSED":
            feedback.review_status = "INSPECTION_PASSED"
        elif data.result == "FAILED":
            feedback.review_status = "INSPECTION_FAILED"
        
        after = {
            "review_status": feedback.review_status,
            "inspection_status": data.result,
            "inspection_result": data.result,
            "inspection_comment": data.comment,
            "issue_tag_names": data.issue_tag_names, # 记录抽检时的标签
        }
        
        await self._log_operation(
            feedback,
            f"INSPECTION_{data.result}",
            before,
            after,
            reason=data.comment,
            operator_id=user_id,
            operator_name=user_name,
        )
        
        # 上报 Trace
        await self._report_trace(
            feedback,
            "rlhf_inspection",
            user_id,
            user_name,
            {"result": data.result, "comment": data.comment},
        )
        
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback
    
    async def lock_for_inspection(self, id: int, user_id: str, user_name: str) -> bool:
        """锁定内容进行抽检"""
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")
        
        # 检查是否已被其他人锁定
        if (
            feedback.is_locked == 1
            and feedback.lock_user_id != user_id
            and feedback.lock_expire_time
            and feedback.lock_expire_time > datetime.now()
        ):
            raise ValueError(f"Content is locked by {feedback.lock_user_name}")
        
        feedback.is_locked = 1
        feedback.lock_user_id = user_id
        feedback.lock_user_name = user_name
        feedback.lock_time = datetime.now()
        feedback.lock_expire_time = datetime.now() + timedelta(minutes=30)
        feedback.inspection_status = "IN_PROGRESS"
        
        await self._log_operation(feedback, "INSPECTION_LOCK", None, None, operator_id=user_id, operator_name=user_name)
        await self.db.commit()
        return True

    async def suggest_tags(self, id: int, data: RLHFSummaryRequest) -> List[str]:
        """AI 建议问题标签 - 通过 Dapr 调用 AG 专家服务"""
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")
        
        # 1. 准备请求参数
        payload = {
            "annotations": feedback.annotations or [],
            "comment": data.comment,
            "model_code": "deepseek-v4-flash"
        }
        
        # 2. 调用 AG 专家系统
        try:
            # 使用 ExpertCaller 调用 raap-service-ag
            result = await ExpertCaller.call_expert_http(
                expert_app="raap-service-ag",
                method_path="/api/v1/rlhf.RLHFExpertService/SummarizeTags",
                payload=payload,
                trace_data=TraceData(
                    job_id=feedback.job_id,
                    sub_job_id=feedback.sub_job_id,
                    content_id=feedback.content_id,
                    trace_id=feedback.trace_id
                )
            )
            
            # ExpertCaller 在 trace_info 存在时会包装一层 {"response": ..., "trace_info": ...}
            real_result = result.get("response") if isinstance(result, dict) and "response" in result else result
            
            if isinstance(real_result, dict) and real_result.get("success"):
                return real_result.get("tags", [])
            else:
                msg = real_result.get('message') if isinstance(real_result, dict) else "Unknown error"
                logger.error(f"AG suggest tags failed: {msg}")
                return []
                
        except Exception as e:
            logger.error(f"Call AG suggest tags failed: {e}")
            return []

    async def summarize_comment(self, id: int, data: RLHFSummarizeCommentRequest) -> str:
        """AI 总结意见 - 根据原文和划词评论/精修内容生成修改意见
        
        支持三种模式：
        1. 划词评论模式：基于 annotations 生成意见
        2. 精修内容模式：对比 content（原文）和 modified_content（精修内容）生成意见
        3. 综合模式：两者都有时，结合生成综合意见
        """
        feedback = await self.get_raw(id)
        if not feedback:
            raise ValueError("Feedback not found")
        
        # 获取划词评论
        annotations = feedback.annotations or []
        
        # 获取原文内容
        original_content = feedback.content or ""
        
        # 获取精修内容
        refined_content = feedback.modified_content
        
        # 判断是否有精修内容（精修内容需要与原文不同才有意义）
        has_refined = (
            refined_content is not None 
            and refined_content.strip() 
            and refined_content.strip() != original_content.strip()
        )
        
        # 判断是否有划词评论
        has_annotations = len(annotations) > 0
        
        # 检查：如果两者都没有，报错
        if not has_annotations and not has_refined:
            raise ValueError("请先添加划词评论或进行原文精修，才能生成 AI 意见")
        
        # 检查原文内容
        if not original_content:
            raise ValueError("原文内容为空，无法生成意见")
        
        # 准备请求参数（新版参数）
        payload = {
            "original_content": original_content,
            "annotations": annotations,
            "refined_content": refined_content if has_refined else None,
            "model_code": data.model_code
        }
        
        # 调用 AG 专家系统
        try:
            result = await ExpertCaller.call_expert_http(
                expert_app="raap-service-ag",
                method_path="/api/v1/rlhf.RLHFExpertService/SummarizeComment",
                payload=payload,
                trace_data=TraceData(
                    job_id=feedback.job_id,
                    sub_job_id=feedback.sub_job_id,
                    content_id=feedback.content_id,
                    trace_id=feedback.trace_id
                )
            )
            
            # ExpertCaller 在 trace_info 存在时会包装一层 {"response": ..., "trace_info": ...}
            real_result = result.get("response") if isinstance(result, dict) and "response" in result else result
            
            if isinstance(real_result, dict) and real_result.get("success"):
                return real_result.get("comment", "")
            else:
                msg = real_result.get('message') if isinstance(real_result, dict) else "Unknown error"
                logger.error(f"AG summarize comment failed: {msg}")
                raise ValueError(f"AI 总结失败: {msg}")
                
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Call AG summarize comment failed: {e}")
            raise ValueError(f"调用 AI 服务失败: {str(e)}")

    # --- History ---
    
    async def get_history(self, feedback_id: int) -> List[RLHFOperationHistory]:
        result = await self.db.execute(
            select(RLHFOperationHistory)
            .where(RLHFOperationHistory.feedback_id == feedback_id)
            .order_by(RLHFOperationHistory.operation_time.asc())
        )
        return list(result.scalars().all())

    async def _log_operation(
        self, 
        feedback: RLHFFeedback, 
        op_type: str, 
        before: Any, 
        after: Any, 
        operator_id: str, 
        operator_name: str,
        reason: str = None,
        improvement: str = None
    ):
        history = RLHFOperationHistory(
            feedback_id=feedback.id,
            operation_type=op_type,
            before_value=before,
            after_value=after,
            reason=reason,
            improvement_suggestion=improvement,
            operator_id=operator_id,
            operator_name=operator_name,
            operation_time=datetime.now()
        )
        self.db.add(history)

    async def _report_trace(
        self,
        feedback: RLHFFeedback,
        stage: str,
        user_id: str,
        user_name: str,
        result_summary: dict
    ):
        # 确保 trace_id 存在（RLHFFeedback 中可能是 None，但 ExpertCallTrace 中必须有值）
        trace_id = feedback.trace_id
        if not trace_id:
            import uuid
            trace_id = str(uuid.uuid4())

        trace = ExpertCallTrace(
            job_id=feedback.job_id,
            sub_job_id=feedback.sub_job_id,
            content_id=feedback.content_id,
            trace_id=trace_id,
            span_id=f"rlhf-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            stage=stage,
            status="success",
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=0,
            
            rlhf_feedback_id=feedback.id,
            reviewer_id=user_id,
            reviewer_name=user_name,
            
            result_summary=result_summary,
            caller_service="raap-service-orchestrator",
            
            # 补充必填字段
            service_app="raap-service-orchestrator",
            service_method=f"rlhf/{stage}",
        )
        self.db.add(trace)

    # --- Issue Tags ---
    
    async def list_tags(self) -> List[RLHFIssueTag]:
        result = await self.db.execute(
            select(RLHFIssueTag)
            .where(RLHFIssueTag.is_deleted == 0)
            .order_by(RLHFIssueTag.sort_order.asc())
        )
        return list(result.scalars().all())

    async def create_tag(self, tag_in: RLHFIssueTagCreate, user_id: str) -> RLHFIssueTag:
        tag = RLHFIssueTag(**tag_in.model_dump(), created_by=user_id)
        self.db.add(tag)
        await self.db.commit()
        await self.db.refresh(tag)
        return tag
    
    async def update_tag(self, id: int, tag_in: RLHFIssueTagUpdate, user_id: str) -> Optional[RLHFIssueTag]:
        tag = await self.db.get(RLHFIssueTag, id)
        if not tag: return None
        
        for k, v in tag_in.model_dump(exclude_unset=True).items():
            setattr(tag, k, v)
        tag.updated_by = user_id
        
        await self.db.commit()
        await self.db.refresh(tag)
        return tag

    async def delete_tag(self, id: int) -> bool:
        tag = await self.db.get(RLHFIssueTag, id)
        if not tag: return False
        tag.is_deleted = 1
        await self.db.commit()
        return True

    # --- Stats ---

    async def get_stats_summary(self) -> dict:
        """获取总体统计摘要"""
        # 使用 func.count 统计
        total = await self.db.scalar(select(func.count(RLHFFeedback.id)).where(RLHFFeedback.is_deleted == 0))
        pending = await self.db.scalar(select(func.count(RLHFFeedback.id)).where(RLHFFeedback.is_deleted == 0, RLHFFeedback.review_status == "PENDING"))
        completed = await self.db.scalar(select(func.count(RLHFFeedback.id)).where(RLHFFeedback.is_deleted == 0, RLHFFeedback.review_status == "COMPLETED"))
        
        like_count = await self.db.scalar(select(func.count(RLHFFeedback.id)).where(RLHFFeedback.is_deleted == 0, RLHFFeedback.like_status == 1))
        adopt_count = await self.db.scalar(select(func.count(RLHFFeedback.id)).where(RLHFFeedback.is_deleted == 0, RLHFFeedback.adopt_status == 1))
        
        # 评分平均值
        avg_score = await self.db.scalar(select(func.avg(RLHFFeedback.content_score)).where(RLHFFeedback.is_deleted == 0, RLHFFeedback.content_score > 0))
        
        return {
            "total_count": total or 0,
            "pending_count": pending or 0,
            "completed_count": completed or 0,
            "like_rate": round(like_count / total * 100, 2) if total and total > 0 else 0,
            "adopt_rate": round(adopt_count / total * 100, 2) if total and total > 0 else 0,
            "avg_content_score": float(avg_score) if avg_score else 0
        }

    async def get_daily_stats(self, days: int = 7) -> List[dict]:
        """获取每日审核趋势"""
        start_date = datetime.now() - timedelta(days=days)
        # 按天分组统计完成数量
        stmt = (
            select(
                func.date(RLHFFeedback.updated_at).label("date"),
                func.count(RLHFFeedback.id).label("count"),
                func.avg(func.nullif(RLHFFeedback.content_score, 0)).label("avg_score")
            )
            .where(
                RLHFFeedback.is_deleted == 0,
                RLHFFeedback.review_status == "COMPLETED",
                RLHFFeedback.updated_at >= start_date
            )
            .group_by(func.date(RLHFFeedback.updated_at))
            .order_by(func.date(RLHFFeedback.updated_at))
        )
        
        results = (await self.db.execute(stmt)).all()
        return [{"stat_date": str(r.date), "total_count": r.count, "avg_content_score": float(r.avg_score or 0)} for r in results]

    async def get_reviewer_stats(self) -> List[dict]:
        """按审核人统计
        
        获取所有进行过审核操作（喜欢/不喜欢）的用户列表
        同时查询 review_user_id 和 like_user_id，合并去重
        """
        reviewer_map: Dict[str, dict] = {}
        
        # 统计 review_user_id（通过 update_review_status API 设置）
        stmt_review = (
            select(
                RLHFFeedback.review_user_id,
                RLHFFeedback.review_user_name,
                func.count(RLHFFeedback.id).label("total"),
            )
            .where(
                RLHFFeedback.is_deleted == 0,
                RLHFFeedback.review_user_id.is_not(None),
            )
            .group_by(RLHFFeedback.review_user_id, RLHFFeedback.review_user_name)
        )
        results_review = (await self.db.execute(stmt_review)).all()
        
        for r in results_review:
            if r.review_user_id:
                reviewer_map[r.review_user_id] = {
                    "reviewer_id": r.review_user_id,
                    "reviewer_name": r.review_user_name or "Unknown",
                    "total_count": r.total,
                }
        
        # 统计 like_user_id（通过 like API 设置）
        stmt_like = (
            select(
                RLHFFeedback.like_user_id,
                RLHFFeedback.like_user_name,
                func.count(RLHFFeedback.id).label("total"),
            )
            .where(
                RLHFFeedback.is_deleted == 0,
                RLHFFeedback.like_user_id.is_not(None),
            )
            .group_by(RLHFFeedback.like_user_id, RLHFFeedback.like_user_name)
        )
        results_like = (await self.db.execute(stmt_like)).all()
        
        for r in results_like:
            if r.like_user_id:
                if r.like_user_id in reviewer_map:
                    # 已存在，更新用户名（如果为空）
                    if not reviewer_map[r.like_user_id].get("reviewer_name") or reviewer_map[r.like_user_id].get("reviewer_name") == "Unknown":
                        reviewer_map[r.like_user_id]["reviewer_name"] = r.like_user_name or "Unknown"
                else:
                    reviewer_map[r.like_user_id] = {
                        "reviewer_id": r.like_user_id,
                        "reviewer_name": r.like_user_name or "Unknown",
                        "total_count": r.total,
                    }
        
        stats = []
        for data in reviewer_map.values():
            stats.append({
                "reviewer_id": data.get("reviewer_id"),
                "reviewer_name": data.get("reviewer_name", "Unknown"),
                "total_count": data.get("total_count", 0),
                "like_count": 0,
                "adopt_count": 0,
                "avg_score": 0,
            })
            
        return stats
