"""
Rate limiter using sliding window algorithm

Supports Redis-based distributed rate limiting with in-memory fallback.
"""
import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request
from loguru import logger
from redis.asyncio import Redis

from app.core.config import settings


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    requests: int  # Number of requests allowed
    window: int  # Time window in seconds


@dataclass
class RateLimitResult:
    """Rate limit check result"""
    allowed: bool
    remaining: int
    reset_at: int


def _get_rate_limit_configs() -> dict[str, RateLimitConfig]:
    """Get rate limit configurations from settings"""
    return {
        "default": RateLimitConfig(
            requests=settings.RATE_LIMIT_DEFAULT_REQUESTS,
            window=settings.RATE_LIMIT_DEFAULT_WINDOW,
        ),
    }


# 延迟加载配置（确保 settings 已初始化）
_RATE_LIMIT_CONFIGS: dict[str, RateLimitConfig] | None = None


def get_rate_limit_configs() -> dict[str, RateLimitConfig]:
    """Get rate limit configurations (cached)"""
    global _RATE_LIMIT_CONFIGS
    if _RATE_LIMIT_CONFIGS is None:
        _RATE_LIMIT_CONFIGS = _get_rate_limit_configs()
    return _RATE_LIMIT_CONFIGS


class InMemoryRateLimiter:
    """In-memory rate limiter for single-instance deployments"""

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> RateLimitResult:
        """Check if request is allowed"""
        async with self._lock:
            now = time.time()
            window_start = now - config.window

            # Get existing requests for this key
            requests = self._requests[key]

            # Remove old requests outside the window
            requests[:] = [req_time for req_time in requests if req_time > window_start]

            # Check if limit exceeded
            current_count = len(requests)
            remaining = max(0, config.requests - current_count)

            if current_count >= config.requests:
                # Calculate when the oldest request will expire
                oldest_request = min(requests) if requests else now
                reset_at = int(oldest_request + config.window)
                return RateLimitResult(allowed=False, remaining=0, reset_at=reset_at)

            # Add current request
            requests.append(now)
            reset_at = int(now + config.window)

            return RateLimitResult(
                allowed=True,
                remaining=config.requests - current_count - 1,
                reset_at=reset_at,
            )

    def cleanup(self, older_than: float = 3600):
        """Clean up old entries (call periodically)"""
        cutoff = time.time() - older_than
        keys_to_delete = [
            key
            for key, requests in self._requests.items()
            if requests and max(requests) < cutoff
        ]
        for key in keys_to_delete:
            del self._requests[key]


class RedisRateLimiter:
    """Redis-based distributed rate limiter using sliding window"""

    def __init__(self, redis: Redis):
        self._redis = redis

    async def check(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> RateLimitResult:
        """
        Check if request is allowed using Redis sorted set

        Uses a sorted set where:
        - Score = request timestamp
        - Members = unique request IDs (timestamp + random)

        This provides O(log(N)) cleanup and counting.
        """
        now = time.time()
        window_start = now - config.window
        redis_key = f"ratelimit:{key}"

        try:
            # Remove old requests outside the window
            await self._redis.zremrangebyscore(redis_key, 0, window_start)

            # Count current requests in the window
            current_count = await self._redis.zcard(redis_key)

            if current_count >= config.requests:
                # Get the oldest request's expiration time
                oldest = await self._redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    reset_at = int(oldest[0][1] + config.window)
                else:
                    reset_at = int(now + config.window)

                return RateLimitResult(allowed=False, remaining=0, reset_at=reset_at)

            # Add current request
            await self._redis.zadd(redis_key, {str(now): now})
            # Set expiry to window size to auto-clean
            await self._redis.expire(redis_key, config.window)

            remaining = config.requests - current_count - 1
            reset_at = int(now + config.window)

            return RateLimitResult(allowed=True, remaining=remaining, reset_at=reset_at)

        except Exception as e:
            logger.warning(f"[RateLimiter] Redis error, falling back to allow: {e}")
            # Fail open - allow request if Redis is down
            return RateLimitResult(allowed=True, remaining=config.requests, reset_at=int(now + config.window))


class RateLimiter:
    """Rate limiter with automatic fallback"""

    def __init__(self, redis: Optional[Redis] = None):
        self._redis_limiter: Optional[RedisRateLimiter] = None
        self._memory_limiter = InMemoryRateLimiter()

        if redis:
            self._redis_limiter = RedisRateLimiter(redis)
            self._use_redis = True
        else:
            self._use_redis = False

    async def check(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> RateLimitResult:
        """Check rate limit"""
        if self._use_redis and self._redis_limiter:
            return await self._redis_limiter.check(key, config)
        return await self._memory_limiter.check(key, config)

    async def cleanup_old_entries(self):
        """Periodic cleanup for in-memory store"""
        if not self._use_redis:
            self._memory_limiter.cleanup()


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter(redis: Optional[Redis] = None) -> RateLimiter:
    """Get rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(redis)
    return _rate_limiter


async def check_rate_limit(
    request: Request,
    app_id: str,
    redis: Optional[Redis] = None,
) -> RateLimitResult:
    """
    Check rate limit for a request

    Args:
        request: FastAPI request object
        app_id: Target service ID
        redis: Optional Redis client

    Returns:
        RateLimitResult with allowed status and headers info

    Raises:
        HTTPException: If rate limit exceeded (429)
    """
    # Get client identifier (IP or user ID if authenticated)
    client_ip = _get_client_ip(request)

    # Use user ID from header if available (for authenticated requests)
    user_id = request.headers.get("X-User-Id")
    if user_id:
        identifier = f"{app_id}:user:{user_id}"
    else:
        identifier = f"{app_id}:ip:{client_ip}"

    # Get rate limit config for this service
    rate_limit_configs = get_rate_limit_configs()
    config = rate_limit_configs.get(app_id, rate_limit_configs["default"])

    # Check rate limit
    limiter = await get_rate_limiter(redis)
    result = await limiter.check(identifier, config)

    if not result.allowed:
        logger.info(
            f"[RateLimiter] Limit exceeded for {identifier}: "
            f"{config.requests} requests per {config.window}s"
        )
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "请求过于频繁，请稍后再试",
                "retry_after": result.reset_at - int(time.time()),
            },
        )

    return result


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request headers"""
    # Check forwarded headers (proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct connection
    if request.client:
        return request.client.host

    return "unknown"
