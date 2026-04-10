"""
RAAP 追踪 SDK

为 RAAP 微服务提供统一的调用追踪能力，支持：
- 三层标识体系（job_id, sub_job_id/content_id, trace_id/span_id）
- 自动追踪装饰器 @traced
- 上下文管理（contextvars）
- gRPC 上报到 Orchestrator

Usage:
    from raap_trace_sdk import (
        TraceContext,
        SpanData,
        TraceReporter,
        traced,
        set_context,
        get_current_context,
        TraceContextManager,
    )

    # 初始化上报器
    from raap_trace_sdk import init_reporter
    init_reporter(orchestrator_app_id="raap-service-orchestrator")

    # 设置追踪上下文
    context = TraceContext(
        job_id="job-abc123",
        sub_job_id="sub-test-xyz789",
        trace_id="trace-123456",
    )
    set_context(context)

    # 使用装饰器自动追踪
    @traced(stage="ge_generation")
    async def generate_content(prompt: str):
        result = await llm_call(prompt)
        return {
            "generated": True,
            "content_id": result.content_id,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
        }
"""

__version__ = "0.1.0"

# 数据模型
from .models import TraceContext, SpanData

# 上下文管理
from .context import (
    set_context,
    get_current_context,
    clear_context,
    set_current_span_id,
    get_current_span_id,
    TraceContextManager,
    SpanContextManager,
)

# 上报器
from .reporter import (
    TraceReporter,
    get_reporter,
    set_reporter,
    init_reporter,
)

# 装饰器
from .decorator import traced, traced_sync

# 工具函数
from .utils import (
    generate_trace_id,
    generate_span_id,
    generate_sub_job_id,
    generate_content_id,
    timestamp_to_ms,
    ms_to_datetime,
    calculate_duration_ms,
)

__all__ = [
    # 版本
    "__version__",
    # 数据模型
    "TraceContext",
    "SpanData",
    # 上下文管理
    "set_context",
    "get_current_context",
    "clear_context",
    "set_current_span_id",
    "get_current_span_id",
    "TraceContextManager",
    "SpanContextManager",
    # 上报器
    "TraceReporter",
    "get_reporter",
    "set_reporter",
    "init_reporter",
    # 装饰器
    "traced",
    "traced_sync",
    # 工具函数
    "generate_trace_id",
    "generate_span_id",
    "generate_sub_job_id",
    "generate_content_id",
    "timestamp_to_ms",
    "ms_to_datetime",
    "calculate_duration_ms",
]

