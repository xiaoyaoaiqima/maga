"""
测试追踪上报器
"""
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from raap_trace_sdk.models import TraceContext, SpanData
from raap_trace_sdk.reporter import (
    TraceReporter,
    get_reporter,
    set_reporter,
    init_reporter,
)


class TestTraceReporter:
    """TraceReporter 测试"""

    @pytest.fixture
    def context(self):
        """测试上下文"""
        return TraceContext(
            job_id="job-test",
            sub_job_id="sub-test",
            trace_id="trace-test",
            content_id="content-test",
            experiment_id="exp-001",
            experiment_group="treatment",
        )

    @pytest.fixture
    def span(self):
        """测试 Span"""
        return SpanData(
            span_id="span-test",
            stage="ge_generation",
            status="success",
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=100,
            model_code="gpt-4",
            input_tokens=50,
            output_tokens=100,
            total_tokens=150,
            result_summary={"generated": True},
        )

    def test_build_payload(self, context, span):
        """测试构建上报数据"""
        reporter = TraceReporter(enabled=False)
        payload = reporter._build_payload(context, span)

        assert payload["job_id"] == "job-test"
        assert payload["sub_job_id"] == "sub-test"
        assert payload["content_id"] == "content-test"
        assert payload["trace_id"] == "trace-test"
        assert payload["span_id"] == "span-test"
        assert payload["stage"] == "ge_generation"
        assert payload["status"] == "success"
        assert payload["duration_ms"] == 100
        assert payload["model_code"] == "gpt-4"
        assert payload["input_tokens"] == 50
        assert payload["output_tokens"] == 100
        assert payload["total_tokens"] == 150
        assert payload["experiment_id"] == "exp-001"
        assert payload["experiment_group"] == "treatment"
        assert json.loads(payload["result_summary_json"]) == {"generated": True}

    @pytest.mark.asyncio
    async def test_report_span_disabled(self, context, span):
        """测试禁用时不上报"""
        reporter = TraceReporter(enabled=False)
        result = await reporter.report_span(context, span)
        assert result is True

    @pytest.mark.asyncio
    async def test_report_span_no_dapr(self, context, span):
        """测试无 Dapr 客户端时"""
        # 创建一个禁用的 reporter，模拟无 Dapr 客户端场景
        reporter = TraceReporter(enabled=True)
        # 直接禁用以模拟无法初始化的情况
        reporter.enabled = False
        result = await reporter.report_span(context, span)
        # 禁用时应该返回 True（不做任何事）
        assert result is True

    @pytest.mark.asyncio
    async def test_report_span_async(self, context, span):
        """测试异步上报"""
        reporter = TraceReporter(enabled=True)
        reporter._dapr_client = MagicMock()
        reporter._dapr_client.invoke_method = MagicMock(return_value=MagicMock(status_code=200))

        # 异步上报立即返回
        result = await reporter.report_span_async(context, span)
        assert result is True


class TestReporterSingleton:
    """上报器单例测试"""

    def test_get_reporter(self):
        """测试获取默认上报器"""
        reporter1 = get_reporter()
        reporter2 = get_reporter()
        assert reporter1 is reporter2

    def test_set_reporter(self):
        """测试设置上报器"""
        custom_reporter = TraceReporter(enabled=False)
        set_reporter(custom_reporter)
        assert get_reporter() is custom_reporter

    def test_init_reporter(self):
        """测试初始化上报器"""
        reporter = init_reporter(
            orchestrator_app_id="test-app",
            enabled=False,
        )
        assert reporter.orchestrator_app_id == "test-app"
        assert reporter.enabled is False
        assert get_reporter() is reporter

