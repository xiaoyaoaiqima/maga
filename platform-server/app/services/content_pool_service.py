"""
Content Pool Service
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Content
from app.models.activity import Activity
from app.schemas.content_pool import (
    ContentAcquireRequest,
    ContentItem,
    ContentTransferRequest,
    ContentTransferResponse,
)

logger = logging.getLogger(__name__)

class ContentPoolService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def acquire_contents(
        self, 
        tenant_id: int, 
        request: ContentAcquireRequest
    ) -> List[Content]:
        """
        原子性获取内容
        """
        # 1. 查找 Activity ID
        stmt_activity = select(Activity.id).where(
            Activity.tenant_id == tenant_id,
            Activity.activity_code == request.activity_code
        )
        result_activity = await self.db.execute(stmt_activity)
        activity_id = result_activity.scalar_one_or_none()
        
        if not activity_id:
            logger.warning(f"Activity not found: {request.activity_code} for tenant {tenant_id}")
            return []

        # 2. 构建查询条件
        # 状态必须是 AVAILABLE
        # 或者 (LOCKED 且 已过期) -> 懒惰回收
        now = datetime.now()
        
        # 基础过滤
        filters = [
            Content.tenant_id == tenant_id,
            Content.activity_id == activity_id,
            Content.quality_score >= request.min_score,
            # 状态检查：(AVAILABLE) OR (LOCKED AND lock_until < now)
            or_(
                Content.distribution_status == "AVAILABLE",
                and_(
                    Content.distribution_status == "LOCKED",
                    Content.lock_until < now
                )
            )
        ]
        
        if request.agent_code:
            filters.append(Content.agent_code == request.agent_code)
            
        # TODO: Handle tags filtering (JSON containment is complex in generic SQL, usually requires dialect specific)
        # If DB is MySQL 8.0, JSON_CONTAINS works.
        # For now skip tags or implement simple check if needed.

        # 3. SELECT ... FOR UPDATE SKIP LOCKED
        stmt = (
            select(Content)
            .where(and_(*filters))
            .limit(request.count)
            .with_for_update(skip_locked=True)
        )
        
        result = await self.db.execute(stmt)
        contents = result.scalars().all()
        
        if not contents:
            return []
            
        # 4. 更新状态
        lock_duration = timedelta(minutes=10) # 10分钟锁
        lock_until = now + lock_duration
        
        updated_contents = []
        for content in contents:
            content.distribution_status = "LOCKED"
            content.lock_until = lock_until
            content.external_order_id = request.external_order_id
            updated_contents.append(content)
            
        # 5. Commit (Caller handles commit usually, but here we might want to ensure atomicity within service method or depend on router)
        # Assuming router handles commit via dependency or manual commit here.
        # Since we modified objects attached to session, simple commit works.
        try:
            await self.db.commit()
            # Refresh to get updated fields if necessary? Not really needed for return values we modified.
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to lock contents: {e}")
            raise e
            
        return updated_contents

    async def ack_contents(self, tenant_id: int, content_ids: List[str]) -> int:
        """
        确认消费
        """
        stmt = (
            update(Content)
            .where(
                Content.tenant_id == tenant_id,
                Content.content_id.in_(content_ids),
                Content.distribution_status == "LOCKED"
            )
            .values(
                distribution_status="CONSUMED",
                lock_until=None
            )
        )
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def check_availability(
        self, 
        tenant_id: int, 
        activity_code: str,
        agent_code: Optional[str] = None,
        min_score: int = 60
    ) -> int:
        """
        查询库存
        """
        # Find Activity ID first
        stmt_activity = select(Activity.id).where(
            Activity.tenant_id == tenant_id,
            Activity.activity_code == activity_code
        )
        result_activity = await self.db.execute(stmt_activity)
        activity_id = result_activity.scalar_one_or_none()
        
        if not activity_id:
            return 0

        filters = [
            Content.tenant_id == tenant_id,
            Content.activity_id == activity_id,
            Content.quality_score >= min_score,
            Content.distribution_status == "AVAILABLE"
        ]
        
        if agent_code:
            filters.append(Content.agent_code == agent_code)
            
        stmt = select(func.count()).select_from(Content).where(and_(*filters))
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def transfer_contents(
        self,
        source_agent_code: str,
        target_agent_code: str,
        request: ContentTransferRequest,
    ) -> ContentTransferResponse:
        """
        将文章从一个 Agent 转移到另一个 Agent

        支持两种模式：
        1. 指定 content_ids：直接转移指定的文章
        2. 按条件筛选：根据筛选条件批量转移文章

        转移规则：
        - 只修改 agent_code 字段
        - 可选择跳过已锁定/已使用的文章
        - 记录转移操作日志
        """
        success_count = 0
        skipped_locked_count = 0
        skipped_used_count = 0
        failed_count = 0
        skipped_content_ids: List[str] = []

        try:
            # 如果指定了 content_ids，直接转移
            if request.content_ids:
                query = select(Content).where(
                    Content.content_id.in_(request.content_ids),
                    Content.agent_code == source_agent_code,
                    Content.is_deleted == 0,
                )
            else:
                # 按条件筛选转移
                filters = [
                    Content.agent_code == source_agent_code,
                    Content.is_deleted == 0,
                ]

                if request.tenant_id is not None:
                    filters.append(Content.tenant_id == request.tenant_id)
                if request.activity_id is not None:
                    filters.append(Content.activity_id == request.activity_id)
                if request.job_id:
                    filters.append(Content.job_id == request.job_id)
                if request.is_valid is not None:
                    filters.append(Content.is_valid == request.is_valid)
                if request.is_test_case is not None:
                    filters.append(Content.is_test_case == request.is_test_case)
                if request.online_status:
                    filters.append(Content.online_status == request.online_status)

                # 跳过已锁定/已使用的文章
                if request.skip_locked:
                    filters.append(
                        or_(
                            Content.is_locked == 0,
                            Content.is_locked.is_(None),
                        )
                    )
                if request.skip_used:
                    filters.append(
                        or_(
                            Content.is_used == 0,
                            Content.is_used.is_(None),
                        )
                    )

                query = select(Content).where(and_(*filters))
                query = query.limit(request.max_count)

            result = await self.db.execute(query)
            contents = result.scalars().all()

            now = datetime.now()

            for content in contents:
                # 二次检查锁定/使用状态
                if request.skip_locked and content.is_locked == 1:
                    # 检查锁定是否已过期
                    if content.lock_expire_time and content.lock_expire_time > now:
                        skipped_locked_count += 1
                        skipped_content_ids.append(content.content_id)
                        continue
                    # 锁定已过期，可以转移
                    content.is_locked = 0
                    content.lock_user_id = None
                    content.lock_time = None
                    content.lock_expire_time = None

                if request.skip_used and content.is_used == 1:
                    skipped_used_count += 1
                    skipped_content_ids.append(content.content_id)
                    continue

                # 执行转移：只修改 agent_code
                old_agent_code = content.agent_code
                content.agent_code = target_agent_code
                content.update_time = now

                # 记录转移日志到 remark 字段
                transfer_note = f"[Transfer] {now.strftime('%Y-%m-%d %H:%M:%S')}: {old_agent_code} -> {target_agent_code}"
                if content.remark:
                    content.remark = f"{content.remark}\n{transfer_note}"
                else:
                    content.remark = transfer_note

                success_count += 1

            await self.db.commit()

            logger.info(
                f"Content transfer completed: {source_agent_code} -> {target_agent_code}, "
                f"success={success_count}, skipped_locked={skipped_locked_count}, "
                f"skipped_used={skipped_used_count}"
            )

            return ContentTransferResponse(
                success_count=success_count,
                skipped_locked_count=skipped_locked_count,
                skipped_used_count=skipped_used_count,
                failed_count=failed_count,
                skipped_content_ids=skipped_content_ids if skipped_content_ids else None,
            )

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Content transfer failed: {e}")
            raise e

