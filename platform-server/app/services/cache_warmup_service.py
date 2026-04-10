"""
Cache Warmup Service

缓存预热服务 - 在系统启动时预加载热点数据
"""
import os
from typing import Callable, Dict, List
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger
from app.services.dashboard_data_cache_service import MySQLDashboardDataCacheService
from app.services.distributed_lock_service import DistributedLockService


class CacheWarmupService:
    """
    缓存预热服务

    功能:
    1. 系统启动时自动预热热点数据
    2. 支持手动触发预热
    3. 使用分布式锁避免多 Pod 同时预热
    4. 支持分批预热（控制并发）
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.cache_table = "raap_dashboard_data_cache_warmup_config"
        self.query_functions: Dict[str, Callable] = {}

        # 检查是否启用预热
        self.warmup_enabled = os.getenv("CACHE_WARMUP_ON_STARTUP", "true").lower() == "true"

    def register_query_function(self, endpoint: str, func: Callable) -> None:
        """
        注册查询函数

        Args:
            endpoint: API endpoint（如 "/api/v1/dashboard/summary"）
            func: 查询函数（async 函数，接收 **kwargs）
        """
        self.query_functions[endpoint] = func
        logger.debug(f"注册查询函数: {endpoint}")

    async def warmup_all(
        self,
        lock_ttl: int = 600,
        batch_size: int = 10,
    ) -> Dict[str, int]:
        """
        预热所有配置的缓存

        Args:
            lock_ttl: 分布式锁 TTL（秒）
            batch_size: 批处理大小

        Returns:
            {
                "total": int,  # 总数
                "success": int,  # 成功数
                "failed": int,  # 失败数
                "skipped": int,  # 跳过数
            }
        """
        if not self.warmup_enabled:
            logger.info("缓存预热未启用，跳过")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        logger.info("开始缓存预热...")

        # 1. 获取分布式锁（避免多 Pod 同时预热）
        lock_service = DistributedLockService(self.session)
        lock_holder = self._get_pod_name()
        lock_key = "cache_warmup"

        lock_acquired = await lock_service.acquire_lock(
            lock_key=lock_key,
            lock_holder=lock_holder,
            ttl_seconds=lock_ttl,
        )

        if not lock_acquired:
            logger.info(f"缓存预热锁已被其他 Pod 持有，跳过预热")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        try:
            # 2. 查询预热配置
            warmup_items = await self._get_warmup_items()

            if not warmup_items:
                logger.info("没有配置的预热项")
                return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

            logger.info(f"找到 {len(warmup_items)} 个预热项")

            # 3. 按 priority 排序
            warmup_items.sort(key=lambda x: x.get("priority", 100))

            # 4. 分批预热
            stats = {"total": len(warmup_items), "success": 0, "failed": 0, "skipped": 0}

            for i in range(0, len(warmup_items), batch_size):
                batch = warmup_items[i:i + batch_size]
                logger.info(f"预热批次 {i // batch_size + 1}: {len(batch)} 项")

                for item in batch:
                    result = await self._warmup_single_item(item)
                    if result == "success":
                        stats["success"] += 1
                    elif result == "failed":
                        stats["failed"] += 1
                    else:
                        stats["skipped"] += 1

            logger.info(f"缓存预热完成: {stats}")
            return stats

        finally:
            # 5. 释放锁
            await lock_service.release_lock(
                lock_key=lock_key,
                lock_holder=lock_holder,
                lock_token=await self._get_lock_token(lock_key),
            )

    async def _get_warmup_items(self) -> List[Dict]:
        """
        获取预热配置列表

        Returns:
            [
                {
                    "id": int,
                    "cache_key": str,
                    "logical_key": str,
                    "cache_group": str,
                    "endpoint": str,
                    "request_params": dict,
                    "priority": int,
                    "enabled": bool,
                }
            ]
        """
        sql = text(f"""
            SELECT
                id, cache_key, logical_key, cache_group,
                endpoint, request_params, priority, enabled
            FROM {self.cache_table}
            WHERE enabled = 1
            ORDER BY priority ASC, id ASC
        """)

        result = await self.session.execute(sql)
        rows = result.fetchall()

        # 获取列名
        columns = result.keys()

        return [
            {
                "id": row[0],
                "cache_key": row[1],
                "logical_key": row[2],
                "cache_group": row[3],
                "endpoint": row[4],
                "request_params": row[5] if isinstance(row[5], dict) else {},
                "priority": row[6],
                "enabled": row[7] == 1,
            }
            for row in rows
        ]

    async def _warmup_single_item(self, item: Dict) -> str:
        """
        ✅ Bug#1: 预热单个缓存项

        Args:
            item: 预热配置项

        Returns:
            "success" | "failed" | "skipped"
        """
        cache_key = item["cache_key"]
        logical_key = item["logical_key"]
        cache_group = item["cache_group"]
        endpoint = item["endpoint"]
        request_params = item["request_params"]

        try:
            logger.info(f"预热缓存: {logical_key}")

            # 1. 检查查询函数是否已注册
            query_func = self.query_functions.get(endpoint)
            if not query_func:
                logger.warning(f"查询函数未注册: {endpoint}，跳过")
                return "skipped"

            # 2. 执行查询
            data = await query_func(**request_params)

            # 3. 写入缓存
            cache_service = MySQLDashboardDataCacheService(self.session)

            # ✅ Bug#1: 生成 cache_key
            import hashlib
            import json
            sorted_params = json.dumps(request_params, sort_keys=True, ensure_ascii=False)
            key_str = f"{endpoint}:{sorted_params}"
            cache_key = hashlib.md5(key_str.encode('utf-8')).hexdigest()

            # ✅ Bug#1: 生成 logical_key（如果未提供）
            if not logical_key:
                logical_key = cache_service._generate_logical_key(cache_group, request_params)

            # ✅ Bug#1: 调用 set() 方法（移除已废弃的参数）
            await cache_service.set(
                cache_key=cache_key,
                logical_key=logical_key,
                cache_group=cache_group,
                data=data,
                ttl_seconds=600,  # 预热数据默认 10 分钟 TTL
                request_params=request_params,
                auto_refresh_enabled=True,
                auto_refresh_interval=300,  # 5 分钟刷新
            )

            logger.info(f"✅ 预热成功: {logical_key}")
            return "success"

        except Exception as e:
            logger.error(f"❌ 预热失败: {logical_key}, error: {e}")
            return "failed"

    def _get_pod_name(self) -> str:
        """获取 Pod 标识"""
        return os.getenv("POD_NAME", os.getenv("HOSTNAME", "unknown-pod"))

    async def _get_lock_token(self, lock_key: str) -> str:
        """获取锁令牌"""
        lock_service = DistributedLockService(self.session)
        lock_status = await lock_service.get_lock_status(lock_key)
        return lock_status["lock_token"] if lock_status else ""
