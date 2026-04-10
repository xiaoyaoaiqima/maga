"""
ContentService - 内容匹配/锁定服务

提供内容匹配与锁定能力：
- 解锁用户之前锁定的内容
- 按 user_tags + context_list(上下文名) 匹配内容
- 匹配不足时按权重剔除最小权重标签兜底
- 最终随机兜底并锁定
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Sequence

from sqlalchemy import select, func, and_, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.content import Content

logger = logging.getLogger(__name__)


class ContentService:
    """内容匹配/锁定服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 内容匹配（按 agent + user_tags） ====================

    async def match_and_lock_contents(
            self,
            user_id: str,
            user_tags: Sequence[Any],
            limit: int = 3,
            lock_minutes: int = 10,
            agent_id: Optional[int] = None,
            agent_id_list: Optional[List[int]] = None,
    ) -> List[Content]:
        """
        按 agent_id + user_tags(tag_name) 匹配内容的 context_list，并锁定给 user_id。

        说明：
        - 通过 agent_id → agent.expert_prepared_job_list(job_id 列表)，限定内容来源
        - 匹配维度：使用入参 user_tags[].tag_name 与 Content.context_list 做“相似匹配”（SQL LIKE）
        - 仅返回未使用、未删除，且未锁定（或锁定已过期）的内容
        - 默认返回 3 条；不足时按权重剔除最小权重标签两次，再不足则随机兜底
        """
        if not user_id:
            raise ValueError("user_id 不能为空")

        # 0) 解锁用户之前锁定的内容
        # last_lock_content_id = await self.unlock_user_locked_contents(user_id=user_id)
        # last_lock_content_id = 0

        # 1) agent_id -> agent_code 列表
        if agent_id_list is not None:
            # 使用 agent_id_list 筛选，获取多个 agent_code
            agent_result = await self.db.execute(
                select(Agent).where(Agent.id.in_(agent_id_list), Agent.is_deleted == 0)
            )
            agents = list(agent_result.scalars().all())
            agent_code_list = [agent.agent_code for agent in agents if agent.agent_code]
            if not agent_code_list:
                return []
        else:
            # 使用单个 agent_id 筛选
            agent_result = await self.db.execute(
                select(Agent).where(Agent.id == agent_id, Agent.is_deleted == 0).limit(1)
            )
            agent = agent_result.scalar_one_or_none()
            agent_code_list = [agent.agent_code] if agent and agent.agent_code else []
            if not agent_code_list:
                return []

        # 2) 提取标签名与权重
        # - 兼容：既支持 TagInfo(Pydantic) 也支持 dict
        tag_items: List[Dict[str, Any]] = []
        for t in (user_tags or []):
            if t is None:
                continue
            if isinstance(t, dict):
                name = t.get("tag_name")
                weight = t.get("tag_weight", 0)
            else:
                name = getattr(t, "tag_name", None)
                weight = getattr(t, "tag_weight", 0)
            if name:
                try:
                    weight = float(weight)
                except Exception:
                    weight = 0.0
                tag_items.append({"tag_name": str(name), "tag_weight": weight})

        user_tag_names = [x["tag_name"] for x in tag_items]
        logger.info(f"用户标签：{tag_items}")

        # 4) 逐步匹配（完整 → 去掉最小权重标签 → 再去掉最小权重标签 → 随机兜底）
        selected_contents: List[Content] = []

        # Step 1：完整标签组合匹配
        selected_contents = await self.find_matching_contents(
            agent_code_list=agent_code_list,
            user_tag_names=user_tag_names,
            limit=limit,
        )

        if len(selected_contents) < limit:
            # Step 2：按权重去掉最小权重标签
            remaining = sorted(tag_items, key=lambda x: x["tag_weight"], reverse=True)
            while len(remaining) >= 1:
                try:
                    if len(remaining) > 1:
                        remaining = remaining[:-1]
                        selected_contents = await self.find_matching_contents(
                            agent_code_list=agent_code_list,
                            user_tag_names=[x["tag_name"] for x in remaining],
                            limit=limit,
                        )
                        if len(selected_contents) >= limit:
                            break
                    else:
                        selected_contents = await self.get_random_contents(agent_code_list=agent_code_list, limit=limit)
                        break
                except Exception:
                    selected_contents = await self.get_random_contents(agent_code_list=agent_code_list, limit=limit)
                    break

        if not selected_contents:
            return []

        # 3) 锁定选中的内容
        now = datetime.now()
        lock_expire = now + timedelta(minutes=lock_minutes)
        await self.lock_contents(
            content_ids=[c.id for c in selected_contents],
            user_id=user_id,
            lock_time=now,
            lock_expire_time=lock_expire,
        )
        return selected_contents

    # ==================== 锁定/匹配辅助方法 ====================

    async def unlock_user_locked_contents(self, user_id: str) -> int:
        """
        解锁用户锁定的内容（仅解锁未使用的锁）。

        Returns:
            int: 解锁的最后一条 content.id（用于“向后翻页/避免重复”的游标）
        """
        try:
            query = (
                select(Content)
                .where(
                    and_(
                        Content.lock_user_id == user_id,
                        Content.is_locked == 1,
                        Content.is_used == 0,
                        Content.is_deleted == 0,
                    )
                )
                .order_by(Content.id.desc())
            )
            result = await self.db.execute(query)
            items = list(result.scalars().all())

            last_id = 0
            if items:
                last_id = items[0].id
                for item in items:
                    item.is_locked = 0
                    item.lock_user_id = None
                    item.lock_time = None
                    item.lock_expire_time = None
                await self.db.commit()
            return last_id
        except Exception:
            await self.db.rollback()
            return 0

    async def find_matching_contents(
            self,
            agent_code_list: List[str],
            user_tag_names: Optional[List[str]] = None,
            limit: int = 3,
    ) -> List[Content]:
        """
        查找匹配内容（AND 组合）。
        - agent_code_list：agent_code 列表，筛选时使用 IN 条件
        - user_tag_names：每个标签要求在 Content.context_list 中"相似命中"（LIKE），多个标签之间为 AND
        """
        now = datetime.now()
        conditions = [
            Content.agent_code.in_(agent_code_list),
            Content.is_deleted == 0,
            Content.is_valid == 1,
            Content.is_test_case == 0,
            Content.online_status == 'ONLINE',
            Content.is_used == 0,
            or_(Content.is_locked == 0, Content.lock_expire_time < now),
        ]

        # 标签匹配（AND：每个标签都要在 context_list 中相似命中）
        if user_tag_names:
            for tag in user_tag_names:
                if not tag or not str(tag).strip():
                    continue
                like = f"%{tag}%"
                conditions.append(
                    cast(Content.context_list, String).like(like)
                )

        query = (
            select(Content)
            .where(and_(*conditions))
            .order_by(func.rand())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_random_contents(self, agent_code_list: List[str], limit: int = 3) -> List[Content]:
        """随机获取内容（同样遵守未删除/有效/未使用/未锁定或锁过期 + agent_code 范围）。"""
        now = datetime.now()
        query = (
            select(Content)
            .where(
                and_(
                    Content.agent_code.in_(agent_code_list),
                    Content.is_deleted == 0,
                    Content.is_valid == 1,
                    Content.is_test_case == 0,
                    Content.online_status == 'ONLINE',
                    Content.is_used == 0,
                    or_(Content.is_locked == 0, Content.lock_expire_time < now),
                )
            )
            .order_by(func.rand())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def lock_contents(
            self,
            content_ids: List[int],
            user_id: str,
            lock_time: datetime,
            lock_expire_time: datetime,
    ) -> bool:
        """锁定内容。"""
        try:
            query = select(Content).where(and_(Content.id.in_(content_ids), Content.is_deleted == 0))
            result = await self.db.execute(query)
            items = list(result.scalars().all())

            for item in items:
                item.is_locked = 1
                item.lock_user_id = user_id
                item.lock_time = lock_time
                item.lock_expire_time = lock_expire_time

            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            return False

    async def use_content(self, content_id: int, user_id: str):
        """
        使用内容（标记为已使用）。

        约束：
        - 内容必须存在且未删除
        - 必须被当前 user_id 锁定且仍处于锁定状态
        """
        try:
            now = datetime.now()
            query = select(Content).where(
                and_(
                    Content.id == content_id,
                    Content.is_deleted == 0,
                    Content.is_locked == 1,
                    Content.lock_user_id == user_id,
                )
            )
            result = await self.db.execute(query)
            item = result.scalar_one_or_none()
            if not item:
                return False, "", ""
            title = item.title
            content = item.content
            item.is_used = 1
            item.user_id = user_id
            item.use_time = now

            await self.db.commit()

            # 使用成功后，解锁该用户另外锁定的（未使用）内容
            # 当前内容已 is_used=1，不会被 unlock 条件命中
            await self.unlock_user_locked_contents(user_id=user_id)
            return True, title, content
        except Exception:
            await self.db.rollback()
            return False, "", ""

    async def update_online_status(self, content_id: int, online_status: str) -> dict:
        """
        更新单篇文章上线状态

        Returns:
            dict: {"success": bool, "message": str, "skipped_reason": str | None}
        """
        try:
            stmt = select(Content).where(Content.id == content_id, Content.is_deleted == 0)
            result = await self.db.execute(stmt)
            item = result.scalar_one_or_none()
            if not item:
                return {"success": False, "message": "文章不存在", "skipped_reason": None}

            # 下线时检查：锁定或已使用的文章不允许下线
            if online_status == "OFFLINE":
                if item.is_locked == 1:
                    return {
                        "success": False,
                        "message": "文章已被锁定，无法下线",
                        "skipped_reason": "locked"
                    }
                if item.is_used == 1:
                    return {
                        "success": False,
                        "message": "文章已被使用，无法下线",
                        "skipped_reason": "used"
                    }

            item.online_status = online_status
            await self.db.commit()
            return {"success": True, "message": "成功", "skipped_reason": None}
        except Exception as e:
            logger.error(f"Update online status failed: {str(e)}")
            await self.db.rollback()
            return {"success": False, "message": f"操作失败: {str(e)}", "skipped_reason": None}

    async def batch_update_online_status(
            self,
            job_id: Optional[str] = None,
            online_status: str = "ONLINE",
            content_ids: Optional[List[int]] = None,
    ) -> dict:
        """
        批量更新文章的上线状态

        支持两种模式：
        1. 按任务ID更新：更新该任务下所有有效且非测试的文章
        2. 按文章ID列表更新：更新指定的文章列表

        Args:
            job_id: 任务ID（与content_ids二选一）
            online_status: 上线状态（ONLINE/OFFLINE）
            content_ids: 文章ID列表（与job_id二选一）

        Returns:
            dict: {
                "updated_count": int,  # 成功更新的数量
                "skipped_locked": int,  # 因锁定跳过的数量
                "skipped_used": int,    # 因已使用跳过的数量
                "total": int            # 总共符合条件的数量
            }
        """
        try:
            # 验证参数
            if not job_id and not content_ids:
                raise ValueError("job_id 和 content_ids 必须提供其中一个")
            if job_id and content_ids:
                raise ValueError("job_id 和 content_ids 不能同时提供")

            # 构建查询条件
            if job_id:
                # 按任务ID查询：仅更新有效文章（is_valid=1）、非测试文章（is_test_case=0）且未删除的
                stmt = select(Content).where(
                    Content.job_id == job_id,
                    Content.is_valid == 1,
                    Content.is_test_case == 0,
                    Content.is_deleted == 0,
                )
            else:
                # 按文章ID列表查询
                stmt = select(Content).where(Content.id.in_(content_ids), Content.is_deleted == 0)

            result = await self.db.execute(stmt)
            items = result.scalars().all()


            updated_count = 0
            skipped_locked = 0
            skipped_used = 0


            for item in items:
                # 下线时检查：锁定或已使用的文章不允许下线
                if online_status == "OFFLINE":
                    if item.is_locked == 1:
                        skipped_locked += 1
                        continue
                    if item.is_used == 1:
                        skipped_used += 1
                        continue


                item.online_status = online_status
                updated_count += 1


            await self.db.commit()
            return {
                "updated_count": updated_count,
                "skipped_locked": skipped_locked,
                "skipped_used": skipped_used,
                "total": len(items),
            }
        except Exception as e:
            logger.error(f"Batch update online status failed: {str(e)}")
            await self.db.rollback()
            return {
                "updated_count": 0,
                "skipped_locked": 0,
                "skipped_used": 0,
                "total": 0,
            }
