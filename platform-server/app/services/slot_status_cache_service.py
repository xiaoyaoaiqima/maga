"""
槽位状态缓存服务 - 优化第一次启动和 cron 扫描性能

使用 Redis 缓存槽位的占用状态，避免每次 cron 都扫描数据库。
"""
from typing import Dict, List, Set, Optional
from logging import getLogger
import json

from app.core.redis import get_redis

logger = getLogger(__name__)


class SlotStatusCacheService:
    """槽位状态缓存服务"""
    
    # 缓存键前缀
    CACHE_KEY_PREFIX = "job_slot_status"
    
    # 缓存 TTL（秒）- 5 分钟
    CACHE_TTL = 300
    
    @staticmethod
    def _get_cache_key(job_id: str) -> str:
        """获取缓存键"""
        return f"{SlotStatusCacheService.CACHE_KEY_PREFIX}:{job_id}"
    
    @staticmethod
    async def get_occupied_indexes(job_id: str) -> Optional[Set[int]]:
        """
        从缓存获取已占用的槽位索引
        
        Args:
            job_id: Job ID
        
        Returns:
            已占用的槽位索引集合，缓存不存在返回 None
        """
        try:
            redis = await get_redis()
            cache_key = SlotStatusCacheService._get_cache_key(job_id)
            
            cached_data = await redis.get(cache_key)
            if cached_data:
                occupied_list = json.loads(cached_data)
                logger.info(f"[Slot Cache] Cache hit for job_id={job_id}, occupied_count={len(occupied_list)}")
                return set(occupied_list)
            
            logger.info(f"[Slot Cache] Cache miss for job_id={job_id}")
            return None
            
        except Exception as e:
            logger.warning(f"[Slot Cache] Failed to get cache for job_id={job_id}: {e}")
            return None
    
    @staticmethod
    async def set_occupied_indexes(job_id: str, occupied_indexes: Set[int]) -> None:
        """
        设置已占用的槽位索引到缓存（DB 回填时调用）。

        同时写入 String（兼容旧读）和 Set（供 get_all_occupied_from_set 使用）。
        Set 写入为 DELETE + 单次 SADD(*members) + EXPIRE，共 3 次往返，与槽位数量无关。
        """
        try:
            redis = await get_redis()
            cache_key = SlotStatusCacheService._get_cache_key(job_id)
            set_key = f"{cache_key}:set"

            # String：保留兼容，TTL 300s
            cached_data = json.dumps(list(occupied_indexes))
            await redis.setex(cache_key, SlotStatusCacheService.CACHE_TTL, cached_data)

            # Set：回填后下次 get_all_occupied_from_set 可命中（DELETE + 单次 SADD + EXPIRE = 3 次往返）
            await redis.delete(set_key)
            if occupied_indexes:
                await redis.sadd(set_key, *occupied_indexes)
                await redis.expire(set_key, SlotStatusCacheService.CACHE_TTL)

            logger.info(
                f"[Slot Cache] Cached for job_id={job_id}, occupied_count={len(occupied_indexes)}, ttl={SlotStatusCacheService.CACHE_TTL}s"
            )

        except Exception as e:
            logger.warning(f"[Slot Cache] Failed to set cache for job_id={job_id}: {e}")
    
    @staticmethod
    async def invalidate(job_id: str) -> None:
        """
        使缓存失效（当 SubJob 状态变化时调用）。
        同时删除 String 与 Set，下次读会回填。
        """
        try:
            redis = await get_redis()
            cache_key = SlotStatusCacheService._get_cache_key(job_id)
            set_key = f"{cache_key}:set"
            await redis.delete(cache_key, set_key)
            logger.info(f"[Slot Cache] Invalidated cache for job_id={job_id}")
        except Exception as e:
            logger.warning(f"[Slot Cache] Failed to invalidate cache for job_id={job_id}: {e}")
    
    @staticmethod
    async def mark_slot_occupied(job_id: str, plan_index: int) -> None:
        """
        标记单个槽位为已占用（增量更新）
        
        Args:
            job_id: Job ID
            plan_index: 槽位索引
        """
        try:
            redis = await get_redis()
            cache_key = SlotStatusCacheService._get_cache_key(job_id)
            
            # 使用 Redis SADD 添加到集合
            await redis.sadd(f"{cache_key}:set", plan_index)
            await redis.expire(f"{cache_key}:set", SlotStatusCacheService.CACHE_TTL)
            
            logger.debug(f"[Slot Cache] Marked slot {plan_index} as occupied for job_id={job_id}")
            
        except Exception as e:
            logger.warning(f"[Slot Cache] Failed to mark slot occupied: {e}")

    @staticmethod
    async def mark_slot_released(job_id: str, plan_index: int) -> None:
        """
        释放单个槽位（增量更新）
        
        Args:
            job_id: Job ID
            plan_index: 槽位索引
        """
        try:
            redis = await get_redis()
            cache_key = SlotStatusCacheService._get_cache_key(job_id)
            set_key = f"{cache_key}:set"
            
            # 使用 Redis SREM 从集合中移除
            await redis.srem(set_key, plan_index)
            
            logger.info(f"[Slot Cache] Released slot {plan_index} for job_id={job_id}")
            
        except Exception as e:
            logger.warning(f"[Slot Cache] Failed to release slot: {e}")
    
    @staticmethod
    async def get_all_occupied_from_set(job_id: str) -> Optional[Set[int]]:
        """
        从 Redis Set 获取所有已占用槽位
        
        Args:
            job_id: Job ID
        
        Returns:
            已占用的槽位索引集合，缓存不存在返回 None
        """
        try:
            redis = await get_redis()
            cache_key = SlotStatusCacheService._get_cache_key(job_id)
            set_key = f"{cache_key}:set"
            
            # 检查 key 是否存在
            exists = await redis.exists(set_key)
            if not exists:
                return None
            
            # 获取所有成员
            members = await redis.smembers(set_key)
            occupied_set = {int(idx) for idx in members}
            
            logger.info(f"[Slot Cache] Set hit for job_id={job_id}, occupied_count={len(occupied_set)}")
            return occupied_set
            
        except Exception as e:
            logger.warning(f"[Slot Cache] Failed to get from set for job_id={job_id}: {e}")
            return None
