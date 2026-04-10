"""
Trace ID 管理模块

用于分布式追踪，支持：
1. OpenTelemetry trace_id（优先）
2. 自动生成 UUID（fallback）
3. 请求级别上下文传递（使用 contextvars）
"""
import uuid
from contextvars import ContextVar
from typing import Optional

# 请求级别的上下文变量
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_span_id_ctx: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
_user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def generate_request_id() -> str:
    """生成请求 ID（UUID 格式）"""
    return str(uuid.uuid4())


def get_otel_trace_id() -> Optional[str]:
    """
    从 OpenTelemetry 获取 trace_id
    
    Returns:
        trace_id 字符串，如果没有活跃的 span 则返回 None
    """
    try:
        from opentelemetry import trace
        
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            trace_id = span.get_span_context().trace_id
            # 转换为 32 位十六进制字符串
            return format(trace_id, '032x')
    except ImportError:
        # OpenTelemetry 未安装
        pass
    except Exception:
        # 其他错误，静默失败
        pass
    return None


def get_otel_span_id() -> Optional[str]:
    """
    从 OpenTelemetry 获取 span_id
    
    Returns:
        span_id 字符串，如果没有活跃的 span 则返回 None
    """
    try:
        from opentelemetry import trace
        
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_id = span.get_span_context().span_id
            # 转换为 16 位十六进制字符串
            return format(span_id, '016x')
    except ImportError:
        pass
    except Exception:
        pass
    return None


# === Request ID 操作 ===

def set_request_id(request_id: Optional[str] = None) -> str:
    """
    设置当前请求的 request_id
    
    Args:
        request_id: 可选的请求 ID，如果不提供则自动生成
        
    Returns:
        设置的 request_id
    """
    if request_id is None:
        request_id = generate_request_id()
    _request_id_ctx.set(request_id)
    return request_id


def get_request_id() -> str:
    """
    获取当前请求的 request_id
    
    Returns:
        request_id，如果未设置则返回 "-"
    """
    return _request_id_ctx.get() or "-"


def clear_request_id() -> None:
    """清除当前请求的 request_id"""
    _request_id_ctx.set(None)


# === Trace ID 操作 ===

def set_trace_id(trace_id: Optional[str] = None) -> str:
    """
    设置当前请求的 trace_id
    
    优先使用 OpenTelemetry 的 trace_id，否则使用传入值或生成 UUID
    
    Args:
        trace_id: 可选的 trace ID
        
    Returns:
        设置的 trace_id
    """
    # 优先尝试从 OpenTelemetry 获取
    otel_trace_id = get_otel_trace_id()
    if otel_trace_id:
        _trace_id_ctx.set(otel_trace_id)
        return otel_trace_id
    
    # 使用传入值或生成新的
    if trace_id is None:
        trace_id = generate_request_id().replace("-", "")
    _trace_id_ctx.set(trace_id)
    return trace_id


def get_trace_id() -> str:
    """
    获取当前请求的 trace_id
    
    Returns:
        trace_id，如果未设置则返回 "-"
    """
    # 先尝试从 OpenTelemetry 获取最新的
    otel_trace_id = get_otel_trace_id()
    if otel_trace_id:
        return otel_trace_id
    return _trace_id_ctx.get() or "-"


def clear_trace_id() -> None:
    """清除当前请求的 trace_id"""
    _trace_id_ctx.set(None)


# === Span ID 操作 ===

def get_span_id() -> str:
    """
    获取当前请求的 span_id
    
    Returns:
        span_id，如果未设置则返回 "-"
    """
    otel_span_id = get_otel_span_id()
    if otel_span_id:
        return otel_span_id
    return _span_id_ctx.get() or "-"


def set_span_id(span_id: Optional[str] = None) -> str:
    """设置 span_id"""
    if span_id is None:
        span_id = generate_request_id()[:16].replace("-", "")
    _span_id_ctx.set(span_id)
    return span_id


def clear_span_id() -> None:
    """清除 span_id"""
    _span_id_ctx.set(None)


# === User ID 操作 ===

def set_user_id(user_id: Optional[str]) -> None:
    """设置当前请求的用户 ID"""
    _user_id_ctx.set(user_id)


def get_user_id() -> Optional[str]:
    """获取当前请求的用户 ID"""
    return _user_id_ctx.get()


def clear_user_id() -> None:
    """清除用户 ID"""
    _user_id_ctx.set(None)


# === 上下文管理 ===

def init_request_context(
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> dict:
    """
    初始化请求上下文
    
    Args:
        request_id: 可选的请求 ID
        trace_id: 可选的 trace ID（来自上游服务或请求头）
        user_id: 可选的用户 ID
        
    Returns:
        包含所有 ID 的字典
    """
    req_id = set_request_id(request_id)
    tr_id = set_trace_id(trace_id)
    sp_id = get_span_id()
    
    if user_id:
        set_user_id(user_id)
    
    return {
        "request_id": req_id,
        "trace_id": tr_id,
        "span_id": sp_id,
        "user_id": user_id,
    }


def clear_request_context() -> None:
    """清除所有请求上下文"""
    clear_request_id()
    clear_trace_id()
    clear_span_id()
    clear_user_id()


def get_trace_context() -> dict:
    """
    获取当前追踪上下文
    
    Returns:
        包含所有追踪 ID 的字典
    """
    return {
        "request_id": get_request_id(),
        "trace_id": get_trace_id(),
        "span_id": get_span_id(),
        "user_id": get_user_id(),
    }

