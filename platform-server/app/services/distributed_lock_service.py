"""
Distributed Lock Service

基于 MySQL 的分布式锁服务（用于缓存预热协调）
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger


class DistributedLockService:
    """
    基于 MySQL 的分布式锁服务

    ✅ v1.4: 主要用于缓存预热协调（避免多 Pod 同时预热）
    ❌ 定时刷新不再使用分布式锁（改用 Master 节点方案）
    """

    def __init__(self, session: AsyncSession):
        # ✅ Bug#2: 构造函数强制注入 session（不能为 None）
        if session is None:
            raise ValueError("session 不能为 None")
        self.session = session
        self.table_name = "raap_dashboard_data_cache_distributed_lock"

    async def acquire_lock(
        self,
        lock_key: str,
        lock_holder: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """
        获取锁

        Args:
            lock_key: 锁键（如 "cache_warmup"）
            lock_holder: 锁持有者标识（如 "pod-1"）
            ttl_seconds: 锁超时时间（秒）

        Returns:
            True 表示获取成功，False 表示锁已被占用
        """
        lock_token = str(uuid.uuid4())
        now = datetime.now()
        expire_at = now + timedelta(seconds=ttl_seconds)

        # 先清理过期锁
        await self._cleanup_expired_locks()

        # 尝试获取锁
        sql = text(f"""
            INSERT INTO {self.table_name} (
                lock_key, lock_holder, lock_token,
                acquired_at, expire_at
            ) VALUES (
                :lock_key, :lock_holder, :lock_token,
                NOW(), :expire_at
            )
            ON DUPLICATE KEY UPDATE
                expire_at = CASE
                    WHEN expire_at < NOW() THEN :expire_at
                    ELSE expire_at
                END,
                lock_holder = CASE
                    WHEN expire_at < NOW() THEN :lock_holder
                    ELSE lock_holder
                END,
                lock_token = CASE
                    WHEN expire_at < NOW() THEN :lock_token
                    ELSE lock_token
                END,
                acquired_at = CASE
                    WHEN expire_at < NOW() THEN NOW()
                    ELSE acquired_at
                END
        """)

        await self.session.execute(sql, {
            "lock_key": lock_key,
            "lock_holder": lock_holder,
            "lock_token": lock_token,
            "expire_at": expire_at,
        })
        await self.session.commit()

        # 验证是否成功获取
        verify_sql = text(f"""
            SELECT lock_token, lock_holder
            FROM {self.table_name}
            WHERE lock_key = :lock_key
            AND lock_token = :lock_token
            AND lock_holder = :lock_holder
            AND expire_at > NOW()
        """)

        result = await self.session.execute(verify_sql, {
            "lock_key": lock_key,
            "lock_token": lock_token,
            "lock_holder": lock_holder,
        })
        row = result.fetchone()

        acquired = row is not None

        if acquired:
            logger.debug(f"获取锁成功: lock_key={lock_key}, holder={lock_holder}")
        else:
            logger.debug(f"获取锁失败: lock_key={lock_key}, holder={lock_holder}")

        return acquired

    async def release_lock(
        self,
        lock_key: str,
        lock_holder: str,
        lock_token: str,
    ) -> bool:
        """
        释放锁

        Args:
            lock_key: 锁键
            lock_holder: 锁持有者标识
            lock_token: 锁令牌（必须匹配才能释放）

        Returns:
            True 表示释放成功，False 表示锁不存在或令牌不匹配
        """
        sql = text(f"""
            DELETE FROM {self.table_name}
            WHERE lock_key = :lock_key
                AND lock_holder = :lock_holder
                AND lock_token = :lock_token
        """)

        result = await self.session.execute(sql, {
            "lock_key": lock_key,
            "lock_holder": lock_holder,
            "lock_token": lock_token,
        })
        await self.session.commit()

        released = result.rowcount > 0

        if released:
            logger.debug(f"释放锁成功: lock_key={lock_key}")
        else:
            logger.warning(f"释放锁失败: lock_key={lock_key}, 令牌不匹配或锁已过期")

        return released

    async def get_lock_status(self, lock_key: str) -> Optional[Dict]:
        """
        获取锁状态

        Args:
            lock_key: 锁键

        Returns:
            {
                "lock_key": "...",
                "lock_holder": "...",
                "acquired_at": "...",
                "expire_at": "...",
                "is_expired": False
            }
            或 None
        """
        sql = text(f"""
            SELECT lock_key, lock_holder, acquired_at, expire_at,
                   CASE WHEN expire_at < NOW() THEN 1 ELSE 0 END as is_expired
            FROM {self.table_name}
            WHERE lock_key = :lock_key
        """)

        result = await self.session.execute(sql, {"lock_key": lock_key})
        row = result.fetchone()

        if not row:
            return None

        return {
            "lock_key": row["lock_key"],
            "lock_holder": row["lock_holder"],
            "acquired_at": row["acquired_at"].isoformat(),
            "expire_at": row["expire_at"].isoformat(),
            "is_expired": row["is_expired"] == 1,
        }

    async def _cleanup_expired_locks(self) -> None:
        """清理过期锁"""
        sql = text(f"""
            DELETE FROM {self.table_name}
            WHERE expire_at < NOW()
        """)
        result = await self.session.execute(sql)
        await self.session.commit()

        if result.rowcount > 0:
            logger.debug(f"清理过期锁: {result.rowcount} 条")

    async def extend_lock(
        self,
        lock_key: str,
        lock_holder: str,
        lock_token: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """
        延长锁的有效期

        Args:
            lock_key: 锁键
            lock_holder: 锁持有者标识
            lock_token: 锁令牌
            ttl_seconds: 延长的秒数

        Returns:
            True 表示成功，False 表示失败
        """
        new_expire_at = datetime.now() + timedelta(seconds=ttl_seconds)

        sql = text(f"""
            UPDATE {self.table_name}
            SET expire_at = :expire_at
            WHERE lock_key = :lock_key
                AND lock_holder = :lock_holder
                AND lock_token = :lock_token
                AND expire_at > NOW()
        """)

        result = await self.session.execute(sql, {
            "lock_key": lock_key,
            "lock_holder": lock_holder,
            "lock_token": lock_token,
            "expire_at": new_expire_at,
        })
        await self.session.commit()

        extended = result.rowcount > 0

        if extended:
            logger.debug(f"延长锁成功: lock_key={lock_key}, ttl={ttl_seconds}s")
        else:
            logger.warning(f"延长锁失败: lock_key={lock_key}, 锁不存在或已过期")

        return extended
