"""
Cache Refresh Scheduler

Master 节点定时刷新调度器
"""
import os
import random
import asyncio
from typing import Dict, Callable
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger
from app.services.dashboard_data_cache_service import MySQLDashboardDataCacheService


class CacheRefreshScheduler:
    """
    缓存刷新调度器

    ✅ v1.4: 仅 Master 节点执行定时刷新
    ✅ P0-3: 引入 refresh 状态机，避免重复刷新
    ✅ P1-8: timeout + 退避 + jitter
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.query_functions: Dict[str, Callable] = {}

        # ✅ v1.4: 检查是否为 Master 节点
        self.is_master = os.getenv("RAAP_ORCHESTRATOR_MASTER", "false").lower() == "true"

        if self.is_master:
            logger.info("✅ 当前节点为 Master，定时任务已启用")
        else:
            logger.info("❌ 当前节点为 Worker，定时任务已跳过")

    def register_query_function(self, cache_group: str, func: Callable) -> None:
        """注册查询函数"""
        self.query_functions[cache_group] = func
        logger.debug(f"注册查询函数: {cache_group}")

    async def refresh_all_pending(self):
        """
        刷新所有待更新的缓存

        ✅ P0-3: 引入 refresh 状态机，避免重复刷新
        ✅ P1-8: timeout + 退避 + jitter
        ✅ v1.4: 仅 Master 节点执行
        """
        # ✅ v1.4: 非 Master 节点直接返回
        if not self.is_master:
            logger.debug("当前节点为 Worker，跳过定时刷新")
            return

        logger.info("🔄 开始刷新待更新的缓存...")

        # 1. ✅ P0-3: 领取 idle 状态的缓存（状态机）
        pending_items = await self._claim_idle_caches(limit=50)

        if not pending_items:
            logger.debug("没有待刷新的缓存")
            return

        logger.info(f"✅ 已领取 {len(pending_items)} 个缓存任务")

        # 2. 并发刷新（限制并发数，避免数据库压力）
        success_count = 0
        failed_count = 0
        timeout_count = 0

        semaphore = asyncio.Semaphore(5)  # 最多 5 个并发刷新

        async def refresh_with_timeout(item):
            async with semaphore:
                try:
                    # ✅ P1-8: 单次刷新超时（避免任务卡死）
                    await asyncio.wait_for(
                        self._refresh_single_cache(item),
                        timeout=300  # 5 分钟超时
                    )
                    return "success"
                except asyncio.TimeoutError:
                    logger.error(f"⏰ 刷新超时: {item['logical_key']}")
                    await self._handle_refresh_timeout(item)
                    return "timeout"
                except Exception as e:
                    logger.error(f"❌ 刷新失败: {item['logical_key']}, error: {e}")
                    await self._handle_refresh_failure(item, str(e))
                    return "failed"

        # 3. 并发执行
        results = await asyncio.gather(*[
            refresh_with_timeout(item) for item in pending_items
        ], return_exceptions=True)

        # 4. 统计结果
        for result in results:
            if result == "success":
                success_count += 1
            elif result == "timeout":
                timeout_count += 1
            else:
                failed_count += 1

        logger.info(f"✅ 缓存刷新完成: 成功 {success_count}, 失败 {failed_count}, 超时 {timeout_count}")

    async def _claim_idle_caches(self, limit: int = 50):
        """
        ✅ P0-3: 领取 idle 状态的缓存（状态机核心逻辑）

        UPDATE ... SET refresh_status='pending'
        WHERE refresh_status='idle' AND next_refresh_at <= NOW()
        LIMIT 50
        """
        cache_table = "raap_dashboard_data_cache_response"

        # 1. 领取（原子操作）
        sql = text(f"""
            UPDATE {cache_table}
            SET refresh_status = 'pending',
                claimed_at = NOW(),
                claimed_by = :POD_NAME
            WHERE id IN (
                SELECT id FROM {cache_table}
                WHERE refresh_status = 'idle'
                    AND auto_refresh_enabled = 1
                    AND is_expired = 0
                    AND next_refresh_at <= NOW()
                ORDER BY next_refresh_at ASC
                LIMIT :limit
            )
            RETURNING id, cache_key, logical_key, cache_group, request_params, auto_refresh_interval
        """)

        result = await self.session.execute(sql, {
            "limit": limit,
            "POD_NAME": self._get_pod_name(),
        })

        claimed = result.fetchall()
        await self.session.commit()

        return [dict(row) for row in claimed]

    async def _refresh_single_cache(self, item: Dict):
        """刷新单个缓存"""
        cache_key = item["cache_key"]
        logical_key = item["logical_key"]
        cache_group = item["cache_group"]
        request_params = item["request_params"]
        refresh_interval = item["auto_refresh_interval"]

        logger.info(f"🔄 开始刷新: {logical_key}")

        # 1. ✅ P0-3: 更新状态为 processing
        await self._update_refresh_status(cache_key, "processing")

        # 2. 执行查询
        query_func = self.query_functions.get(cache_group)
        if not query_func:
            raise ValueError(f"未找到查询函数: {cache_group}")

        fresh_data = await query_func(**request_params)

        # 3. 更新缓存
        cache_service = MySQLDashboardDataCacheService(self.session)
        await cache_service.set(
            cache_key=cache_key,
            logical_key=logical_key,
            cache_group=cache_group,
            data=fresh_data,
            ttl_seconds=refresh_interval * 2,  # TTL = 2 * 刷新间隔
            request_params=request_params,
            auto_refresh_enabled=True,
            auto_refresh_interval=refresh_interval,
        )

        # 4. ✅ P1-8: 计算下次刷新时间（含 jitter）
        jitter = int(refresh_interval * 0.2 * (random.random() * 2 - 1))
        next_refresh = datetime.now() + timedelta(seconds=refresh_interval + jitter)

        # 5. ✅ P0-3: 更新状态为 idle（刷新成功）
        await self._update_refresh_status(cache_key, "idle", next_refresh=next_refresh, refresh_status="success")

        logger.info(f"✅ 刷新成功: {logical_key}")

    async def _update_refresh_status(
        self,
        cache_key: str,
        status: str,
        next_refresh: datetime = None,
        refresh_status: str = None,
        error_message: str = None,
    ):
        """更新刷新状态"""
        cache_table = "raap_dashboard_data_cache_response"

        updates = {
            "refresh_status": status,
            "last_refresh_at": datetime.now(),
        }

        if next_refresh:
            updates["next_refresh_at"] = next_refresh

        if refresh_status:
            updates["last_refresh_status"] = refresh_status

        if error_message:
            updates["last_refresh_error"] = error_message

        set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])

        sql = text(f"""
            UPDATE {cache_table}
            SET {set_clause}
            WHERE cache_key = :cache_key
        """)

        await self.session.execute(sql, {**updates, "cache_key": cache_key})
        await self.session.commit()

    async def _handle_refresh_timeout(self, item: Dict):
        """处理刷新超时（P1-8: 退避）"""
        cache_key = item["cache_key"]
        refresh_interval = item.get("auto_refresh_interval", 300)

        # ✅ P1-8: 退避策略（timeout 后 2x interval 再试）
        backoff_next_refresh = datetime.now() + timedelta(seconds=refresh_interval * 2)

        await self._update_refresh_status(
            cache_key,
            status="timeout",
            next_refresh=backoff_next_refresh,
            refresh_status="timeout",
            error_message="Refresh timeout after 300s",
        )

    async def _handle_refresh_failure(self, item: Dict, error: str):
        """处理刷新失败（P1-8: 退避）"""
        cache_key = item["cache_key"]
        refresh_interval = item.get("auto_refresh_interval", 300)

        # ✅ P1-8: 退避策略（失败后 1.5x interval 再试）
        backoff_next_refresh = datetime.now() + timedelta(seconds=int(refresh_interval * 1.5))

        await self._update_refresh_status(
            cache_key,
            status="idle",  # 失败后回 idle，允许重试
            next_refresh=backoff_next_refresh,
            refresh_status="failed",
            error_message=error[:1000],  # 截断到 1000 字符
        )

    def _get_pod_name(self) -> str:
        """获取 Pod 标识"""
        return os.getenv("POD_NAME", os.getenv("HOSTNAME", "unknown-pod"))
