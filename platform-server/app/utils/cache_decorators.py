"""
Cache Decorators

缓存装饰器 - 简化缓存使用
"""
from contextvars import ContextVar
import json
import hashlib
from functools import wraps
from typing import Callable, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger
from app.services.dashboard_data_cache_service import MySQLDashboardDataCacheService

_cache_tenant_ctx: ContextVar[Optional[str]] = ContextVar("cache_tenant", default=None)


def cache_response(
    cache_group: str,
    ttl_seconds: int = 300,
    auto_refresh_enabled: bool = False,
    auto_refresh_interval: Optional[int] = None,
):
    """
    缓存响应装饰器

    Usage:
        @cache_response(cache_group="dashboard_summary", ttl_seconds=60)
        async def get_dashboard_summary(tenant_id: int, start_date: str, end_date: str):
            ...

    Args:
        cache_group: 缓存组
        ttl_seconds: 缓存 TTL（秒）
        auto_refresh_enabled: 是否启用自动刷新
        auto_refresh_interval: 自动刷新间隔（秒）
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取 session
            session = _get_session_from_args(args)

            if not session:
                # 没有 session，直接调用原函数
                return await func(*args, **kwargs)

            try:
                # 生成 cache_key
                cache_key = _generate_cache_key(func, args, kwargs)

                # 获取 tenant_id
                tenant_id = kwargs.get("tenant_id") or _extract_tenant_id(args)

                # 尝试从缓存获取
                cache_service = MySQLDashboardDataCacheService(session)
                cached = await cache_service.get(
                    cache_key=cache_key,
                    cache_group=cache_group,
                    check_demo=False,  # 装饰器不检查 demo 模式
                )

                if cached:
                    logger.debug(f"缓存命中: {cache_key}")
                    return cached["data"]

                # 缓存未命中，调用原函数
                logger.debug(f"缓存未命中: {cache_key}")
                data = await func(*args, **kwargs)

                # 写入缓存
                await cache_service.set(
                    cache_key=cache_key,
                    logical_key=cache_service._generate_logical_key(cache_group, kwargs),
                    cache_group=cache_group,
                    data=data,
                    ttl_seconds=ttl_seconds,
                    request_params=kwargs,
                    tenant_id=tenant_id,
                    auto_refresh_enabled=auto_refresh_enabled,
                    auto_refresh_interval=auto_refresh_interval,
                )

                return data

            except Exception as e:
                logger.error(f"缓存装饰器错误: {e}")
                # 缓存失败，降级到直接调用
                return await func(*args, **kwargs)

        return wrapper
    return decorator


def cache_demo_response(
    demo_key: Optional[str] = None,
):
    """
    演示模式装饰器（优先返回演示数据）

    Usage:
        @cache_demo_response(demo_key="dashboard_summary_demo")
        async def get_dashboard_summary(...):
            ...

    Args:
        demo_key: 演示数据键（如果为 None，使用函数名）
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            session = _get_session_from_args(args)

            if not session:
                return await func(*args, **kwargs)

            try:
                from app.services.demo_data_service import DemoDataService

                demo_service = DemoDataService(session)

                # 检查全局演示模式
                if not await demo_service.is_global_demo_enabled():
                    return await func(*args, **kwargs)

                # 生成 demo_key
                key = demo_key or func.__name__
                demo_data = await demo_service.get_demo_data(key)

                if demo_data is not None:
                    logger.info(f"返回演示数据: {key}")
                    return demo_data

                # 演示数据不存在，调用原函数
                return await func(*args, **kwargs)

            except Exception as e:
                logger.error(f"演示模式装饰器错误: {e}")
                return await func(*args, **kwargs)

        return wrapper
    return decorator


# ==================== 辅助函数 ====================

def _get_session_from_args(args) -> Optional[AsyncSession]:
    """从参数中获取 AsyncSession"""
    for arg in args:
        if isinstance(arg, AsyncSession):
            return arg
    return None


def _generate_cache_key(func: Callable, args, kwargs) -> str:
    """生成缓存键（MD5）"""
    # 排序参数
    sorted_kwargs = json.dumps(kwargs, sort_keys=True, default=str)
    key_str = f"{func.__name__}:{sorted_kwargs}"
    return hashlib.md5(key_str.encode('utf-8')).hexdigest()


def _extract_tenant_id(args) -> Optional[int]:
    """从参数中提取 tenant_id"""
    # 从 kwargs 提取
    for arg in args:
        if isinstance(arg, dict) and "tenant_id" in arg:
            return arg["tenant_id"]
        if isinstance(arg, int):
            # 假设第一个 int 参数可能是 tenant_id
            return arg
    return None


def set_cache_tenant(tenant_code: Optional[str]) -> None:
    """记录当前操作关联的租户编码，供缓存失效装饰器使用。"""
    _cache_tenant_ctx.set(tenant_code)


def invalidate_tree_cache(
    *,
    from_node: bool = False,
    from_context: bool = False,
    tenant_codes_kwarg: Optional[str] = None,
):
    """
    兼容历史分类树缓存失效装饰器。

    这里采用保守策略：
    - 优先读取显式传入的 tenant_codes_kwarg
    - 其次读取调用前通过 set_cache_tenant 写入的租户
    - 最后回退到 kwargs/args 中常见的 tenant_code
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            service = args[0] if args else None
            invalidate = getattr(service, "_invalidate_tree_cache", None)
            if not callable(invalidate):
                return result

            tenant_codes: list[str] = []
            if tenant_codes_kwarg and kwargs.get(tenant_codes_kwarg):
                raw = kwargs.get(tenant_codes_kwarg)
                if isinstance(raw, (list, tuple, set)):
                    tenant_codes.extend(str(v) for v in raw if v)
                elif raw:
                    tenant_codes.append(str(raw))

            current_tenant = _cache_tenant_ctx.get()
            if current_tenant:
                tenant_codes.append(current_tenant)

            for key in ("tenant_code",):
                if kwargs.get(key):
                    tenant_codes.append(str(kwargs[key]))

            if from_context:
                context = kwargs.get("scope_context") or kwargs.get("context") or {}
                if isinstance(context, dict):
                    tenant = context.get("tenant_code")
                    if tenant:
                        tenant_codes.append(str(tenant))

            unique_codes = [code for code in dict.fromkeys(tenant_codes) if code]
            if not unique_codes:
                unique_codes = ["default"]

            for tenant_code in unique_codes:
                try:
                    await invalidate(tenant_code)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"分类树缓存失效失败 tenant={tenant_code}: {exc}")

            return result

        return wrapper

    return decorator
