"""
RAAP 追踪 SDK - 上下文管理

使用 Python contextvars 管理追踪上下文，支持异步环境
"""
from contextvars import ContextVar
from typing import Optional

from .models import TraceContext

# 上下文变量
_trace_context_var: ContextVar[Optional[TraceContext]] = ContextVar(
    "trace_context", default=None
)

# 当前 Span ID（用于构建调用链路）
_current_span_id_var: ContextVar[Optional[str]] = ContextVar(
    "current_span_id", default=None
)


def set_context(context: TraceContext) -> None:
    """
    设置当前请求的追踪上下文

    Args:
        context: 追踪上下文
    """
    _trace_context_var.set(context)


def get_current_context() -> Optional[TraceContext]:
    """
    获取当前请求的追踪上下文

    Returns:
        追踪上下文，如果未设置则返回 None
    """
    return _trace_context_var.get()


def clear_context() -> None:
    """清除当前请求的追踪上下文"""
    _trace_context_var.set(None)
    _current_span_id_var.set(None)


def set_current_span_id(span_id: str) -> None:
    """
    设置当前 Span ID

    Args:
        span_id: Span ID
    """
    _current_span_id_var.set(span_id)


def get_current_span_id() -> Optional[str]:
    """
    获取当前 Span ID

    Returns:
        Span ID，如果未设置则返回 None
    """
    return _current_span_id_var.get()


class TraceContextManager:
    """
    追踪上下文管理器

    支持同步和异步上下文管理：

    Usage (同步):
        with TraceContextManager(context):
            # 在此范围内可以通过 get_current_context() 获取上下文
            do_something()

    Usage (异步):
        async with TraceContextManager(context):
            await some_async_function()
    """

    def __init__(self, context: TraceContext):
        """
        初始化上下文管理器

        Args:
            context: 追踪上下文
        """
        self.context = context
        self._context_token = None
        self._span_token = None

    def __enter__(self):
        """进入上下文"""
        self._context_token = _trace_context_var.set(self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if self._context_token is not None:
            _trace_context_var.reset(self._context_token)
        if self._span_token is not None:
            _current_span_id_var.reset(self._span_token)
        return False

    async def __aenter__(self):
        """异步进入上下文"""
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步退出上下文"""
        return self.__exit__(exc_type, exc_val, exc_tb)


class SpanContextManager:
    """
    Span 上下文管理器

    用于管理 parent_span_id 的传递：

    Usage:
        with SpanContextManager(span_id):
            # 子调用可以通过 get_current_span_id() 获取 parent_span_id
            await child_call()
    """

    def __init__(self, span_id: str):
        """
        初始化 Span 上下文管理器

        Args:
            span_id: 当前 Span ID
        """
        self.span_id = span_id
        self._token = None

    def __enter__(self):
        """进入上下文"""
        self._token = _current_span_id_var.set(self.span_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if self._token is not None:
            _current_span_id_var.reset(self._token)
        return False

    async def __aenter__(self):
        """异步进入上下文"""
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步退出上下文"""
        return self.__exit__(exc_type, exc_val, exc_tb)

