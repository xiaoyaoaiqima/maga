"""
RAAP 追踪 SDK - 装饰器

提供 @traced 装饰器，自动追踪函数执行
"""
from functools import wraps
from datetime import datetime
from typing import Optional, Callable, Any

from .models import TraceContext, SpanData
from .context import get_current_context, get_current_span_id, SpanContextManager
from .utils import generate_span_id
from .reporter import TraceReporter, get_reporter


def traced(
    stage: str,
    reporter: Optional[TraceReporter] = None,
    async_report: bool = True,
    expert_config_code: Optional[str] = None,
    service_app: Optional[str] = None,
    service_method: Optional[str] = None,
):
    """
    自动追踪装饰器

    自动捕获：
    - 执行时间（start_time, end_time, duration_ms）
    - 执行状态（success/failed/timeout）
    - 返回结果中的 Token 信息（如果返回 dict 且包含 input_tokens 等字段）
    - 返回结果作为 result_summary
    - 错误信息（如果执行失败）
    - parent_span_id（从上下文自动获取）

    Args:
        stage: 阶段名称（如 ge_generation, ag_ban, ag_critic, plugin_render, prompt_render）
        reporter: 追踪上报器（默认使用全局单例）
        async_report: 是否异步上报（不阻塞主流程）
        expert_config_code: Expert 配置编码（可选）
        service_app: 目标服务 App ID（可选）
        service_method: 调用方法名（可选）

    Usage:
        @traced(stage="ge_generation")
        async def generate_content(context: TraceContext, prompt: str, model_code: str):
            result = await llm_call(prompt, model_code)
            return {
                "generated": True,
                "content_id": result.content_id,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "model_code": result.model_code,
            }

        # 也可以不传 context，自动从上下文获取
        @traced(stage="ag_ban_illegal")
        async def check_content(content: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            _reporter = reporter or get_reporter()

            # 尝试从参数中获取 context
            context = kwargs.get("context")
            if context is None and args:
                # 检查第一个参数是否是 TraceContext
                if isinstance(args[0], TraceContext):
                    context = args[0]

            # 如果参数中没有，从上下文变量获取
            if context is None:
                context = get_current_context()

            # 无上下文时直接执行，不追踪
            if context is None:
                return await func(*args, **kwargs)

            # 生成 Span ID
            span_id = generate_span_id()
            parent_span_id = get_current_span_id()

            start_time = datetime.now()
            status = "running"
            error_type = None
            error_message = None
            result_summary = None

            # Token 信息（从返回结果中提取）
            model_code = None
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0

            try:
                # 使用 SpanContextManager 传递 parent_span_id
                async with SpanContextManager(span_id):
                    result = await func(*args, **kwargs)

                status = "success"

                # 如果返回值是 dict，自动提取信息
                if isinstance(result, dict):
                    result_summary = result.copy()
                    # 提取 Token 信息
                    model_code = result.get("model_code")
                    input_tokens = result.get("input_tokens", 0)
                    output_tokens = result.get("output_tokens", 0)
                    total_tokens = result.get("total_tokens", 0)
                    # 更新 context 的 content_id（如果有）
                    if "content_id" in result and result["content_id"]:
                        context.content_id = result["content_id"]

                return result

            except TimeoutError as e:
                status = "timeout"
                error_type = "timeout"
                error_message = str(e)
                raise

            except Exception as e:
                status = "failed"
                error_type = type(e).__name__
                error_message = str(e)
                raise

            finally:
                end_time = datetime.now()
                duration_ms = int((end_time - start_time).total_seconds() * 1000)

                span = SpanData(
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    stage=stage,
                    expert_config_code=expert_config_code,
                    service_app=service_app,
                    service_method=service_method or func.__name__,
                    status=status,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    # Token 信息
                    model_code=model_code,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    # 结果和错误
                    result_summary=result_summary,
                    error_type=error_type,
                    error_message=error_message,
                )

                # 上报
                if async_report:
                    await _reporter.report_span_async(context, span)
                else:
                    await _reporter.report_span(context, span)

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            """同步函数包装器（不进行追踪，仅记录警告）"""
            import warnings
            warnings.warn(
                f"@traced 装饰器仅支持异步函数，同步函数 {func.__name__} 将不会被追踪",
                RuntimeWarning
            )
            return func(*args, **kwargs)

        # 判断是否为异步函数
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def traced_sync(
    stage: str,
    reporter: Optional[TraceReporter] = None,
    expert_config_code: Optional[str] = None,
):
    """
    同步函数追踪装饰器（简化版，仅记录日志，不上报）

    注意：此装饰器仅用于开发调试，生产环境应使用异步版本

    Args:
        stage: 阶段名称
        reporter: 追踪上报器（未使用，保留接口一致性）
        expert_config_code: Expert 配置编码

    Usage:
        @traced_sync(stage="plugin_render")
        def render_plugin(template: str, variables: dict):
            ...
    """
    import logging
    _logger = logging.getLogger(__name__)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = datetime.now()
            span_id = generate_span_id()

            _logger.debug(
                f"[TRACE] 开始执行: stage={stage}, span_id={span_id}, "
                f"func={func.__name__}"
            )

            try:
                result = func(*args, **kwargs)

                end_time = datetime.now()
                duration_ms = int((end_time - start_time).total_seconds() * 1000)

                _logger.debug(
                    f"[TRACE] 执行成功: stage={stage}, span_id={span_id}, "
                    f"duration_ms={duration_ms}"
                )

                return result

            except Exception as e:
                end_time = datetime.now()
                duration_ms = int((end_time - start_time).total_seconds() * 1000)

                _logger.warning(
                    f"[TRACE] 执行失败: stage={stage}, span_id={span_id}, "
                    f"duration_ms={duration_ms}, error={type(e).__name__}: {e}"
                )
                raise

        return wrapper
    return decorator

