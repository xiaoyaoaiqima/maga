"""
MySQL Dashboard Data Cache Service

基于 MySQL 的 Dashboard 数据缓存服务实现
"""
import json
import gzip
import hashlib
import random
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger


class DecimalEncoder(json.JSONEncoder):
    """自定义 JSON encoder，处理 Decimal、date、datetime 类型"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


class MySQLDashboardDataCacheService:
    """
    MySQL Dashboard 数据缓存服务

    功能:
    1. 缓存 Dashboard 数据查询结果
    2. 支持 logical_key + physical_key 双键设计
    3. 支持数据压缩（>100KB 自动 gzip）
    4. 支持 demo 模式优先返回
    5. 异步更新 hit_count（1% 采样）
    6. 软删除 + 夜间批清
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.cache_table = "raap_dashboard_data_cache_response"
        self.demo_table = "raap_dashboard_data_cache_demo_config"

    # ==================== 核心方法 ====================

    async def get(
        self,
        cache_key: str,
        cache_group: str,
        check_demo: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存数据

        Args:
            cache_key: 缓存键（MD5）
            cache_group: 缓存组（如 "dashboard_summary", "metric_query"）
            check_demo: 是否检查演示模式（默认 True）

        Returns:
            {
                "data": Any,  # 缓存数据
                "meta": {
                    "cache_key": str,
                    "logical_key": str,
                    "cache_watermark": str,
                    "data_freshness_seconds": int,
                    "refresh_status": str,
                    "from_cache": bool,
                    "from_demo": bool,
                }
            }
            或 None（缓存不存在/已过期）
        """
        # 1. 优先检查演示模式
        if check_demo:
            demo_data = await self._get_demo_data(cache_key)
            if demo_data is not None:
                logger.debug(f"✅ Demo data found for cache_key={cache_key}")
                return {
                    "data": demo_data,
                    "meta": {
                        "cache_key": cache_key,
                        "logical_key": f"demo:{cache_key}",
                        "cache_watermark": datetime.now().isoformat(),
                        "data_freshness_seconds": 0,
                        "refresh_status": "demo",
                        "from_cache": False,
                        "from_demo": True,
                    }
                }

        # 2. 查询缓存
        logger.info(f"DEBUG: Querying cache with cache_key={cache_key}, cache_group={cache_group}")
        sql = text(f"""
            SELECT
                response_data,
                response_compressed,
                request_params,
                cache_watermark,
                TIMESTAMPDIFF(SECOND, cache_watermark, NOW()) as data_freshness_seconds,
                refresh_status,
                logical_key,
                response_data_size
            FROM {self.cache_table}
            WHERE cache_key = :cache_key
                AND cache_group = :cache_group
                AND is_expired = 0
                AND expires_at > NOW()
        """)

        result = await self.session.execute(sql, {
            "cache_key": cache_key,
            "cache_group": cache_group,
        })
        row = result.fetchone()
        # ✅ 转换 tuple 为 dict (按列顺序)
        if row:
            row = {
                "response_data": row[0],
                "response_compressed": row[1],
                "request_params": row[2],
                "cache_watermark": row[3],
                "data_freshness_seconds": row[4],
                "refresh_status": row[5],
                "logical_key": row[6],
                "response_data_size": row[7],
            }

        logger.info(f"DEBUG: Query result row={row is not None}")
        if not row:
            logger.warning(f"Cache miss: cache_key={cache_key}, cache_group={cache_group}")
            return None

        logger.info(f"DEBUG: Cache found, logical_key={row['logical_key']}")

        # 3. 解压缩数据
        try:
            data = await self._decompress_data(
                row["response_data"],
                row["response_compressed"],
            )
            logger.info(f"DEBUG: Data decompressed successfully")
        except Exception as e:
            logger.error(f"Failed to decompress cache data: {e}")
            return None

        # 4. ✅ P0-1: 异步更新 hit_count（1% 采样）
        if random.random() < 0.01:
            await self._increment_hit_count_async(cache_key)

        return {
            "data": data,
            "meta": {
                "cache_key": cache_key,
                "logical_key": row["logical_key"],
                "cache_watermark": row["cache_watermark"].isoformat(),
                "data_freshness_seconds": row["data_freshness_seconds"],
                "refresh_status": row["refresh_status"],
                "from_cache": True,
                "from_demo": False,
            }
        }

    async def set(
        self,
        cache_key: str,
        logical_key: str,
        cache_group: str,
        data: Any,
        ttl_seconds: int = 300,
        request_params: Optional[Dict] = None,
        tenant_id: Optional[int] = None,
        auto_refresh_enabled: bool = False,
        auto_refresh_interval: Optional[int] = None,
    ) -> None:
        """
        设置缓存

        Args:
            cache_key: 缓存键（MD5）
            logical_key: 逻辑键（语义化）
            cache_group: 缓存组
            data: 缓存数据
            ttl_seconds: TTL（秒）
            request_params: 请求参数
            tenant_id: 租户 ID
            auto_refresh_enabled: 是否启用自动刷新
            auto_refresh_interval: 自动刷新间隔（秒）
        """
        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl_seconds)

        # ✅ P1-5: 生成 logical_key（如果未提供）
        if not logical_key:
            logical_key = self._generate_logical_key(cache_group, request_params or {})

        # ✅ P1-6: 压缩数据（>100KB）
        # 序列化数据（处理 Decimal 类型）
        response_data_json = json.dumps(data, ensure_ascii=False, cls=DecimalEncoder)
        response_data_size = len(response_data_json.encode('utf-8'))
        MAX_RESPONSE_SIZE = 1024 * 1024  # 1MB

        if response_data_size > MAX_RESPONSE_SIZE:
            raise ValueError(f"Response too large: {response_data_size} bytes")

        # 压缩
        compressed_data = None
        if response_data_size > 100 * 1024:  # >100KB
            compressed_data = gzip.compress(response_data_json.encode('utf-8'))
            logger.debug(f"Compressed data: {response_data_size} -> {len(compressed_data)} bytes")

        # ✅ P1-8: 计算下次刷新时间（含 jitter）
        next_refresh_at = None
        if auto_refresh_enabled and auto_refresh_interval:
            jitter = int(auto_refresh_interval * 0.2 * (random.random() * 2 - 1))
            next_refresh_at = now + timedelta(seconds=auto_refresh_interval + jitter)

        # ✅ P0-4: 使用 cache_watermark（缓存生成时间）
        # ✅ Bug#4: request_params 直接传 dict（让 MySQL 驱动处理 JSON）
        sql = text(f"""
            INSERT INTO {self.cache_table} (
                cache_key, logical_key, cache_group,
                response_data, response_compressed, response_data_size,
                request_params, tenant_id,
                cache_watermark, expires_at, is_expired,
                ttl_seconds, auto_refresh_enabled, auto_refresh_interval,
                next_refresh_at, refresh_status,
                created_at, updated_at
            ) VALUES (
                :cache_key, :logical_key, :cache_group,
                :response_data, :response_compressed, :response_data_size,
                :request_params, :tenant_id,
                :cache_watermark, :expires_at, 0,
                :ttl_seconds, :auto_refresh_enabled, :auto_refresh_interval,
                :next_refresh_at, 'idle',
                NOW(), NOW()
            )
            ON DUPLICATE KEY UPDATE
                response_data = VALUES(response_data),
                response_compressed = VALUES(response_compressed),
                response_data_size = VALUES(response_data_size),
                request_params = VALUES(request_params),
                cache_watermark = VALUES(cache_watermark),
                expires_at = VALUES(expires_at),
                is_expired = 0,
                ttl_seconds = VALUES(ttl_seconds),
                auto_refresh_enabled = VALUES(auto_refresh_enabled),
                auto_refresh_interval = VALUES(auto_refresh_interval),
                next_refresh_at = VALUES(next_refresh_at),
                refresh_status = 'idle',
                updated_at = NOW()
        """)

        await self.session.execute(sql, {
            "cache_key": cache_key,
            "logical_key": logical_key,
            "cache_group": cache_group,
            "response_data": response_data_json if not compressed_data else None,
            "response_compressed": compressed_data,
            "response_data_size": response_data_size,
            "request_params": json.dumps(request_params, ensure_ascii=False) if request_params else None,  # ✅ 转换为 JSON 字符串
            "tenant_id": tenant_id,
            "cache_watermark": now,  # ✅ P0-4
            "expires_at": expires_at,
            "ttl_seconds": ttl_seconds,
            "auto_refresh_enabled": 1 if auto_refresh_enabled else 0,
            "auto_refresh_interval": auto_refresh_interval,
            "next_refresh_at": next_refresh_at,
        })
        await self.session.commit()

        logger.info(f"Cache set: {logical_key} (size={response_data_size}, compressed={compressed_data is not None})")

    async def delete(
        self,
        cache_key: str,
        cache_group: str,
    ) -> bool:
        """删除缓存"""
        sql = text(f"""
            UPDATE {self.cache_table}
            SET is_expired = 1,
                expired_reason = 'manual_delete'
            WHERE cache_key = :cache_key
                AND cache_group = :cache_group
        """)

        result = await self.session.execute(sql, {
            "cache_key": cache_key,
            "cache_group": cache_group,
        })
        await self.session.commit()

        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"Cache deleted: {cache_key}")

        return deleted

    # ==================== 清理方法 ====================

    async def cleanup_expired(self, batch_size: int = 1000) -> int:
        """
        ✅ P1-7: 清理过期缓存（软删除 + 夜间批清）

        Args:
            batch_size: 批处理大小

        Returns:
            清理的记录数
        """
        now = datetime.now()
        current_hour = now.hour

        # ✅ P1-7: 白天（6:00-22:00）：仅软删除
        if 6 <= current_hour < 22:
            result = await self.session.execute(text(f"""
                UPDATE {self.cache_table}
                SET is_expired = 1,
                    expired_reason = 'ttl_expired'
                WHERE expires_at < NOW()
                    AND is_expired = 0
                LIMIT :batch_size
            """), {"batch_size": batch_size})
            marked = result.rowcount
            logger.info(f"Soft delete expired cache: {marked} 条")
            return marked
        else:
            # ✅ P1-7: 夜间（22:00-6:00）：物理删除
            total_deleted = 0
            while True:
                result = await self.session.execute(text(f"""
                    DELETE FROM {self.cache_table}
                    WHERE is_expired = 1 OR expires_at < NOW()
                    LIMIT :batch_size
                """), {"batch_size": batch_size})
                batch_deleted = result.rowcount
                total_deleted += batch_deleted
                await self.session.commit()
                if batch_deleted < batch_size:
                    break
            logger.info(f"Physical delete expired cache: {total_deleted} 条")
            return total_deleted

    async def cleanup_history(self, days_to_keep: int = 30) -> int:
        """
        ✅ P1-7: 清理刷新历史（保留 N 天）

        Args:
            days_to_keep: 保留天数

        Returns:
            清理的记录数
        """
        history_table = "raap_dashboard_data_cache_refresh_history"

        result = await self.session.execute(text(f"""
            DELETE FROM {history_table}
            WHERE refreshed_at < DATE_SUB(NOW(), INTERVAL :days_to_keep DAY)
        """), {"days_to_keep": days_to_keep})

        await self.session.commit()
        deleted = result.rowcount

        logger.info(f"Clean refresh history: {deleted} 条 (keep {days_to_keep} days)")
        return deleted

    # ==================== 辅助方法 ====================

    async def _get_demo_data(self, cache_key: str) -> Optional[Any]:
        """获取演示数据"""
        # 检查全局开关
        if not await self._is_global_demo_enabled():
            return None

        # 查询演示配置
        sql = text(f"""
            SELECT
                demo_type, static_data, dynamic_rule_type, dynamic_rule_config
            FROM {self.demo_table}
            WHERE demo_key = :demo_key
                AND demo_enabled = 1
                AND (valid_from IS NULL OR valid_from <= NOW())
                AND (valid_until IS NULL OR valid_until >= NOW())
        """)

        result = await self.session.execute(sql, {"demo_key": cache_key})
        row = result.fetchone()

        if not row:
            return None

        # 根据类型返回数据
        if row["demo_type"] == "static":
            return row["static_data"]
        elif row["demo_type"] == "dynamic":
            return await self._generate_dynamic_data(row)
        else:
            logger.warning(f"Unknown demo type: {row['demo_type']}")
            return None

    async def _is_global_demo_enabled(self) -> bool:
        """✅ Bug#3: 检查全局演示模式开关"""
        GLOBAL_DEMO_KEY = "__global__"

        sql = text(f"""
            SELECT demo_enabled
            FROM {self.demo_table}
            WHERE demo_key = :global_demo_key
        """)

        result = await self.session.execute(sql, {"global_demo_key": GLOBAL_DEMO_KEY})
        row = result.fetchone()
        
        # fetchone() 返回 tuple，使用整数索引
        return row and row[0] == 1

    async def _generate_dynamic_data(self, config_row) -> Any:
        """生成动态演示数据"""
        import math

        rule_type = config_row["dynamic_rule_type"]
        rule_config = json.loads(config_row["dynamic_rule_config"]) if config_row["dynamic_rule_config"] else {}

        if rule_type == "increment":
            return await self._generate_increment_data(rule_config)
        elif rule_type == "range":
            return await self._generate_range_data(rule_config)
        elif rule_type == "random":
            return await self._generate_random_data(rule_config)
        elif rule_type == "function":
            return await self._generate_function_data(rule_config)
        else:
            logger.warning(f"Unknown dynamic rule type: {rule_type}")
            return None

    async def _generate_increment_data(self, config: Dict) -> Any:
        """生成累加数据"""
        base_value = config.get("base_value", 0)
        increment = config.get("increment", 0)
        interval = config.get("interval_seconds", 60)
        currencies = config.get("currencies", [])

        now = datetime.now()
        base_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_seconds = (now - base_time).total_seconds()
        steps = int(elapsed_seconds / interval)

        current_value = base_value + (increment * steps)

        if currencies:
            return [
                {
                    "currency": currency,
                    "total_cost": current_value * (1.0 if currency == "USD" else 7.5)
                }
                for currency in currencies
            ]
        else:
            return {"total_cost": current_value}

    async def _generate_range_data(self, config: Dict) -> Any:
        """生成范围数据"""
        import random

        min_val = config.get("min", 0)
        max_val = config.get("max", 1000)
        data_points = config.get("data_points", 10)

        return [
            {
                "value": random.uniform(min_val, max_val),
                "timestamp": (datetime.now() - timedelta(seconds=i * 60)).isoformat()
            }
            for i in range(data_points)
        ]

    async def _generate_random_data(self, config: Dict) -> Any:
        """生成随机数据"""
        import random
        return random.uniform(config.get("min", 0), config.get("max", 1000))

    async def _generate_function_data(self, config: Dict) -> Any:
        """生成函数数据"""
        import math

        function_name = config.get("function", "sine_wave")
        data_points = config.get("data_points", 30)

        if function_name == "sine_wave":
            amplitude = config.get("amplitude", 500)
            period = config.get("period", 86400)
            offset = config.get("offset", 1000)

            now = datetime.now()
            base_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elapsed_seconds = (now - base_time).total_seconds()

            data = []
            for i in range(data_points):
                t = elapsed_seconds - (i * (period / data_points))
                value = offset + amplitude * math.sin(2 * math.pi * t / period)
                data.append({
                    "timestamp": (now - timedelta(seconds=i * (period / data_points))).isoformat(),
                    "value": value
                })

            return data
        else:
            logger.warning(f"Unknown function type: {function_name}")
            return None

    def _generate_logical_key(self, cache_group: str, params: Dict) -> str:
        """
        ✅ P1-5: 生成语义化逻辑键

        Args:
            cache_group: 缓存组
            params: 请求参数

        Returns:
            logical_key (如 "metric_query:cost_by_job:2025-01-01:2025-01-31:page=1:page_size=500")
        """
        metric_key = params.get('metric_key', 'unknown')
        start_date = params.get('start_date', '')
        end_date = params.get('end_date', '')

        # 基础键
        base_key = f"{cache_group}:{metric_key}:{start_date}:{end_date}"

        # 如果是分页查询，添加分页参数
        if 'page' in params and 'page_size' in params:
            page = params['page']
            page_size = params['page_size']
            return f"{base_key}:page={page}:page_size={page_size}"

        return base_key

    async def _decompress_data(
        self,
        response_data: Optional[str],
        response_compressed: Optional[bytes],
    ) -> Any:
        """解压缩数据"""
        if response_compressed:
            # gzip 解压
            decompressed = gzip.decompress(response_compressed)
            return json.loads(decompressed.decode('utf-8'))
        elif response_data:
            # 直接返回 JSON
            return response_data if isinstance(response_data, dict) else json.loads(response_data)
        else:
            return None

    async def _increment_hit_count_async(self, cache_key: str) -> None:
        """
        ✅ P0-1: 异步更新 hit_count（1% 采样）

        Args:
            cache_key: 缓存键
        """
        try:
            from app.core.database import get_db_context

            async with get_db_context() as session:
                await session.execute(text(f"""
                    UPDATE {self.cache_table}
                    SET hit_count = hit_count + 1,
                        last_hit_at = NOW()
                    WHERE cache_key = :cache_key
                """), {"cache_key": cache_key})
                await session.commit()
        except Exception as e:
            logger.debug(f"Hit_count update failed (ignorable): {e}")

    @staticmethod
    def generate_cache_key(
        endpoint: str,
        params: Dict,
        tenant_id: Optional[int] = None,
    ) -> str:
        """
        生成缓存键（MD5）

        Args:
            endpoint: API endpoint
            params: 请求参数
            tenant_id: 租户 ID

        Returns:
            MD5 hash
        """
        # 排序参数（确保相同参数不同顺序生成相同 key）
        sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=False)

        # 拼接
        key_str = f"{endpoint}:{sorted_params}"
        if tenant_id:
            key_str += f":{tenant_id}"

        # MD5
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
