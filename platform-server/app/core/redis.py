"""
Redis connection management with monitoring
"""
import json
import time
from typing import Any, Optional
from urllib.parse import quote

import redis.asyncio as aioredis
from loguru import logger
from redis.asyncio import Redis

from app.core.config import settings

_redis_client: Optional[Redis] = None

# 缓存过期时间（秒）
CACHE_TTL_CATEGORY_TREE = 300  # 分类树缓存 5 分钟
CACHE_TTL_METADATA = 300  # 元数据选项缓存 5 分钟
CACHE_TTL_DIMENSIONS = 600  # 维度缓存 10 分钟

# 节点缓存过期时间（秒）
CACHE_TTL_NODE_BASIC = 600  # 节点基本信息 10 分钟
CACHE_TTL_NODE_CORPUS = 3600  # corpus 1 小时（变化频率低）
CACHE_TTL_NODE_BATCH = 300  # 批量查询 5 分钟

# ==================== 缓存监控指标 ====================

_cache_metrics = {
    "hits": 0,          # 缓存命中次数
    "misses": 0,        # 缓存未命中次数
    "sets": 0,          # 缓存写入次数
    "deletes": 0,       # 缓存删除次数
    "errors": 0,        # 缓存错误次数
    "latency_ms": [],   # 请求延迟（毫秒）
}


def get_cache_metrics() -> dict[str, Any]:
    """获取缓存指标统计"""
    total_requests = _cache_metrics["hits"] + _cache_metrics["misses"]
    hit_rate = _cache_metrics["hits"] / total_requests if total_requests > 0 else 0

    latency_list = _cache_metrics["latency_ms"]
    avg_latency = sum(latency_list) / len(latency_list) if latency_list else 0
    p95_latency = sorted(latency_list)[int(len(latency_list) * 0.95)] if latency_list else 0
    p99_latency = sorted(latency_list)[int(len(latency_list) * 0.99)] if latency_list else 0

    return {
        "hits": _cache_metrics["hits"],
        "misses": _cache_metrics["misses"],
        "hit_rate": f"{hit_rate * 100:.2f}%",
        "sets": _cache_metrics["sets"],
        "deletes": _cache_metrics["deletes"],
        "errors": _cache_metrics["errors"],
        "total_requests": total_requests,
        "avg_latency_ms": f"{avg_latency:.2f}",
        "p95_latency_ms": f"{p95_latency:.2f}",
        "p99_latency_ms": f"{p99_latency:.2f}",
    }


def reset_cache_metrics() -> None:
    """重置缓存指标"""
    global _cache_metrics
    _cache_metrics = {
        "hits": 0,
        "misses": 0,
        "sets": 0,
        "deletes": 0,
        "errors": 0,
        "latency_ms": [],
    }
    logger.info("缓存指标已重置")


async def get_redis() -> Redis:
    """
    Get Redis client instance
    """
    global _redis_client
    
    if _redis_client is None:
        # URL 编码密码，防止特殊字符（如 # % 等）破坏 URL 解析
        encoded_password = quote(settings.REDIS_PASSWORD, safe="") if settings.REDIS_PASSWORD else ""
        _redis_client = await aioredis.from_url(
            f"redis://:{encoded_password}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=settings.REDIS_TIMEOUT,
            socket_connect_timeout=settings.REDIS_TIMEOUT,
        )
    
    return _redis_client


async def close_redis():
    """Close Redis connection"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


async def cache_get(key: str) -> Optional[Any]:
    """
    从缓存获取数据（带监控）

    Args:
        key: 缓存键

    Returns:
        缓存的数据（已反序列化），未命中则返回 None
    """
    start_time = time.time()
    try:
        redis = await get_redis()
        data = await redis.get(key)

        # 记录延迟
        latency_ms = (time.time() - start_time) * 1000
        _cache_metrics["latency_ms"].append(latency_ms)

        if data:
            _cache_metrics["hits"] += 1
            logger.debug(f"✅ 缓存命中: {key} ({latency_ms:.2f}ms)")
            return json.loads(data)

        _cache_metrics["misses"] += 1
        logger.debug(f"❌ 缓存未命中: {key} ({latency_ms:.2f}ms)")
        return None
    except Exception as e:
        _cache_metrics["errors"] += 1
        latency_ms = (time.time() - start_time) * 1000
        logger.warning(f"⚠️ 缓存读取失败: {key}, error: {e} ({latency_ms:.2f}ms)")
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    设置缓存数据（带监控）

    Args:
        key: 缓存键
        value: 要缓存的数据（会被 JSON 序列化）
        ttl: 过期时间（秒）

    Returns:
        是否成功
    """
    start_time = time.time()
    try:
        redis = await get_redis()
        await redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))

        latency_ms = (time.time() - start_time) * 1000
        _cache_metrics["sets"] += 1
        _cache_metrics["latency_ms"].append(latency_ms)

        logger.debug(f"💾 缓存写入: {key}, ttl={ttl}s ({latency_ms:.2f}ms)")
        return True
    except Exception as e:
        _cache_metrics["errors"] += 1
        latency_ms = (time.time() - start_time) * 1000
        logger.warning(f"⚠️ 缓存写入失败: {key}, error: {e} ({latency_ms:.2f}ms)")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """
    删除匹配模式的缓存键（带监控）

    Args:
        pattern: 匹配模式，如 "kc:tree:*"

    Returns:
        删除的键数量
    """
    start_time = time.time()
    try:
        redis = await get_redis()
        keys = []
        async for key in redis.scan_iter(match=pattern, count=100):
            keys.append(key)
        if keys:
            deleted = await redis.delete(*keys)
            latency_ms = (time.time() - start_time) * 1000
            _cache_metrics["deletes"] += deleted
            logger.info(f"🗑️ 缓存清除: pattern={pattern}, count={deleted} ({latency_ms:.2f}ms)")
            return deleted
        return 0
    except Exception as e:
        _cache_metrics["errors"] += 1
        latency_ms = (time.time() - start_time) * 1000
        logger.warning(f"⚠️ 缓存清除失败: {pattern}, error: {e} ({latency_ms:.2f}ms)")
        return 0


async def invalidate_node_cache(node_id: int | str) -> int:
    """
    使单个节点的所有缓存失效

    Args:
        node_id: 节点ID

    Returns:
        删除的键数量
    """
    node_id_str = str(node_id)
    patterns = [
        f"kc:node:basic:{node_id_str}",
        f"kc:node:corpus:{node_id_str}",
        f"kc:node:batch:*",  # 批量缓存包含此节点
    ]

    total_deleted = 0
    for pattern in patterns:
        if "*" in pattern:
            total_deleted += await cache_delete_pattern(pattern)
        else:
            try:
                redis = await get_redis()
                deleted = await redis.delete(pattern)
                if deleted:
                    logger.debug(f"节点缓存删除: {pattern}, count={deleted}")
                    total_deleted += deleted
            except Exception as e:
                logger.warning(f"节点缓存删除失败: {pattern}, error: {e}")

    logger.info(f"节点缓存失效: node_id={node_id_str}, total_deleted={total_deleted}")
    return total_deleted


