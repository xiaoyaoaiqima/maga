"""
RAAP 追踪 SDK - 追踪上报器

通过 Dapr HTTP Invocation 将追踪数据上报到 Orchestrator 服务
"""
import json
import logging
import asyncio
from typing import Optional, List
import os

import httpx

from .models import TraceContext, SpanData
from .utils import timestamp_to_ms

logger = logging.getLogger(__name__)

DEFAULT_DAPR_HTTP_PORT = 3500
DEFAULT_REPORT_PATH = "/api/v1/traces/report"
DEFAULT_BATCH_REPORT_PATH = "/api/v1/traces/report/batch"


class TraceReporter:
    """
    追踪上报器

    通过 Dapr HTTP Invocation 将追踪数据上报到 Orchestrator 服务。
    支持同步和异步上报，以及批量上报。
    """

    def __init__(
        self,
        orchestrator_app_id: str = "raap-service-orchestrator",
        method_name: str = DEFAULT_REPORT_PATH,
        batch_method_name: str = DEFAULT_BATCH_REPORT_PATH,
        enabled: bool = True,
        max_retry: int = 3,
        retry_delay: float = 0.5,
    ):
        """
        初始化上报器

        Args:
            orchestrator_app_id: Orchestrator 服务的 Dapr App ID
            method_name: 单条上报的 HTTP path（兼容旧值：ReportTraceSpan -> /api/v1/traces/report）
            batch_method_name: 批量上报的 HTTP path（兼容旧值：BatchReportTraceSpans -> /api/v1/traces/report/batch）
            enabled: 是否启用上报
            max_retry: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        self.orchestrator_app_id = orchestrator_app_id
        self.report_path = self._normalize_path(method_name, fallback=DEFAULT_REPORT_PATH)
        self.batch_report_path = self._normalize_path(batch_method_name, fallback=DEFAULT_BATCH_REPORT_PATH)
        self.enabled = enabled
        self.max_retry = max_retry
        self.retry_delay = retry_delay

        self._dapr_http_port = int(os.getenv("DAPR_HTTP_PORT", str(DEFAULT_DAPR_HTTP_PORT)))

    def _normalize_path(self, method_or_path: str, fallback: str) -> str:
        if not method_or_path:
            return fallback

        # 兼容旧的 gRPC method 名称（历史遗留），统一映射到 HTTP path
        if method_or_path == "ReportTraceSpan":
            return DEFAULT_REPORT_PATH
        if method_or_path == "BatchReportTraceSpans":
            return DEFAULT_BATCH_REPORT_PATH

        if method_or_path.startswith("/"):
            return method_or_path

        # 给一个“兜底”，避免把错误 method 当成 URL 拼接
        logger.warning(f"未知的 trace 上报 method: {method_or_path}，将使用默认 path: {fallback}")
        return fallback

    async def _post_via_dapr_http(self, path: str, json_body: dict) -> dict:
        url = f"http://localhost:{self._dapr_http_port}/v1.0/invoke/{self.orchestrator_app_id}/method{path}"
        headers: dict[str, str] = {}
        token = os.getenv("INTERNAL_API_TOKEN")
        if token:
            headers["X-Internal-Token"] = token

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=json_body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"raw": data}

    def _build_payload(self, context: TraceContext, span: SpanData) -> dict:
        """
        构建上报数据

        Args:
            context: 追踪上下文
            span: Span 数据

        Returns:
            上报数据字典
        """
        return {
            # 三层标识（第二层 sub_job_id 与 content_id 对等）
            "job_id": context.job_id,
            "sub_job_id": context.sub_job_id,
            "content_id": context.content_id,
            "trace_id": context.trace_id,
            # Span 信息
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "stage": span.stage,
            "status": span.status,
            "expert_config_code": span.expert_config_code,
            "service_app": span.service_app,
            "service_method": span.service_method,
            # 时间
            "start_time_ms": timestamp_to_ms(span.start_time),
            "end_time_ms": timestamp_to_ms(span.end_time),
            "duration_ms": span.duration_ms,
            # Token
            "model_code": span.model_code,
            "provider_code": span.provider_code,
            "input_tokens": span.input_tokens,
            "output_tokens": span.output_tokens,
            "total_tokens": span.total_tokens,
            # 成本
            "input_cost": span.input_cost,
            "output_cost": span.output_cost,
            "total_cost": span.total_cost,
            # 实验
            "experiment_id": context.experiment_id,
            "experiment_group": context.experiment_group,
            "experiment_variant": context.experiment_variant,
            # 结果
            "result_summary_json": json.dumps(span.result_summary) if span.result_summary else None,
            "error_type": span.error_type,
            "error_message": span.error_message,
            # 源数据
            "source_log_id": span.source_log_id,
            "source_log_table": span.source_log_table,
        }

    async def report_span(
        self,
        context: TraceContext,
        span: SpanData
    ) -> bool:
        """
        上报单个 Span
        
        Args:
            context: 追踪上下文
            span: Span 数据
            
        Returns:
            是否上报成功
        """
        if not self.enabled:
            return True

        payload = self._build_payload(context, span)

        for attempt in range(self.max_retry):
            try:
                result = await self._post_via_dapr_http(self.report_path, payload)
                # Orchestrator 返回：{success, message, trace_id?}
                if isinstance(result, dict) and "success" in result:
                    return bool(result.get("success"))
                return True
            except Exception as e:
                logger.warning(
                    f"追踪上报失败 (尝试 {attempt + 1}/{self.max_retry}): {e}"
                )
                if attempt < self.max_retry - 1:
                    await asyncio.sleep(self.retry_delay)
                    
        logger.error(f"追踪上报最终失败: span_id={span.span_id}")
        return False

    async def report_span_async(
        self,
        context: TraceContext,
        span: SpanData
    ) -> bool:
        """
        异步上报（后台执行，不阻塞主流程）

        Args:
            context: 追踪上下文
            span: Span 数据

        Returns:
            始终返回 True（实际结果在后台处理）
        """
        asyncio.create_task(self._report_span_background(context, span))
        return True

    async def _report_span_background(
        self,
        context: TraceContext,
        span: SpanData
    ):
        """后台上报任务"""
        try:
            await self.report_span(context, span)
        except Exception as e:
            logger.error(f"后台追踪上报失败: {e}")

    async def batch_report_spans(
        self,
        context: TraceContext,
        spans: List[SpanData]
    ) -> bool:
        """
        批量上报多个 Span
        
        Args:
            context: 追踪上下文
            spans: Span 数据列表
            
        Returns:
            是否上报成功
        """
        if not self.enabled or not spans:
            return True

        payloads = [self._build_payload(context, span) for span in spans]

        for attempt in range(self.max_retry):
            try:
                result = await self._post_via_dapr_http(self.batch_report_path, {"spans": payloads})
                if isinstance(result, dict) and "success" in result:
                    return bool(result.get("success"))
                return True
            except Exception as e:
                logger.warning(
                    f"批量追踪上报失败 (尝试 {attempt + 1}/{self.max_retry}): {e}"
                )
                if attempt < self.max_retry - 1:
                    await asyncio.sleep(self.retry_delay)
                    
        logger.error(f"批量追踪上报最终失败: count={len(spans)}")
        return False
        
    async def close(self):
        """兼容保留：HTTP 客户端为短连接，无需关闭"""
        return None


# 全局单例
_default_reporter: Optional[TraceReporter] = None


def get_reporter() -> TraceReporter:
    """
    获取默认上报器

    Returns:
        全局单例上报器
    """
    global _default_reporter
    if _default_reporter is None:
        _default_reporter = TraceReporter()
    return _default_reporter


def set_reporter(reporter: TraceReporter) -> None:
    """
    设置默认上报器

    Args:
        reporter: 上报器实例
    """
    global _default_reporter
    _default_reporter = reporter


def init_reporter(
    orchestrator_app_id: str = "raap-service-orchestrator",
    enabled: bool = True,
    **kwargs
) -> TraceReporter:
    """
    初始化并设置默认上报器

    Args:
        orchestrator_app_id: Orchestrator 服务的 Dapr App ID
        enabled: 是否启用上报
        **kwargs: 其他参数传递给 TraceReporter

    Returns:
        上报器实例
    """
    reporter = TraceReporter(
        orchestrator_app_id=orchestrator_app_id,
        enabled=enabled,
        **kwargs
    )
    set_reporter(reporter)
    return reporter

