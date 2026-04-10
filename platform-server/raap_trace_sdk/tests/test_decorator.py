"""
测试装饰器
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from raap_trace_sdk.models import TraceContext
from raap_trace_sdk.decorator import traced, traced_sync
from raap_trace_sdk.context import set_context, clear_context, TraceContextManager
from raap_trace_sdk.reporter import TraceReporter


class TestTracedDecorator:
    """@traced 装饰器测试"""

    @pytest.fixture
    def mock_reporter(self):
        """模拟上报器"""
        reporter = MagicMock(spec=TraceReporter)
        reporter.report_span_async = AsyncMock(return_value=True)
        reporter.report_span = AsyncMock(return_value=True)
        return reporter

    @pytest.fixture
    def context(self):
        """测试上下文"""
        return TraceContext(
            job_id="job-test",
            sub_job_id="sub-test",
            trace_id="trace-test",
        )

    @pytest.mark.asyncio
    async def test_traced_success(self, mock_reporter, context):
        """测试成功执行时的追踪"""
        @traced(stage="test_stage", reporter=mock_reporter)
        async def test_func(context: TraceContext):
            return {"result": "ok", "input_tokens": 10, "output_tokens": 20}

        result = await test_func(context)
        assert result["result"] == "ok"

        # 验证上报被调用
        mock_reporter.report_span_async.assert_called_once()
        call_args = mock_reporter.report_span_async.call_args
        span = call_args[0][1]  # 第二个参数是 SpanData
        assert span.stage == "test_stage"
        assert span.status == "success"
        assert span.input_tokens == 10
        assert span.output_tokens == 20

    @pytest.mark.asyncio
    async def test_traced_failure(self, mock_reporter, context):
        """测试失败执行时的追踪"""
        @traced(stage="test_stage", reporter=mock_reporter)
        async def test_func(context: TraceContext):
            raise ValueError("测试错误")

        with pytest.raises(ValueError):
            await test_func(context)

        # 验证上报被调用
        mock_reporter.report_span_async.assert_called_once()
        call_args = mock_reporter.report_span_async.call_args
        span = call_args[0][1]
        assert span.status == "failed"
        assert span.error_type == "ValueError"
        assert span.error_message == "测试错误"

    @pytest.mark.asyncio
    async def test_traced_with_context_var(self, mock_reporter, context):
        """测试从上下文变量获取 context"""
        @traced(stage="test_stage", reporter=mock_reporter)
        async def test_func():
            return {"result": "ok"}

        async with TraceContextManager(context):
            result = await test_func()
            assert result["result"] == "ok"

        mock_reporter.report_span_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_traced_no_context(self, mock_reporter):
        """测试无上下文时不追踪"""
        @traced(stage="test_stage", reporter=mock_reporter)
        async def test_func():
            return {"result": "ok"}

        clear_context()
        result = await test_func()
        assert result["result"] == "ok"

        # 无上下文时不应该上报
        mock_reporter.report_span_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_traced_updates_content_id(self, mock_reporter, context):
        """测试自动更新 content_id"""
        @traced(stage="ge_generation", reporter=mock_reporter)
        async def test_func(ctx: TraceContext):
            return {"content_id": "content-new-123"}

        assert context.content_id is None
        await test_func(context)
        assert context.content_id == "content-new-123"


class TestTracedSyncDecorator:
    """@traced_sync 装饰器测试"""

    def test_traced_sync_success(self):
        """测试同步函数成功执行"""
        @traced_sync(stage="test_stage")
        def test_func():
            return "ok"

        result = test_func()
        assert result == "ok"

    def test_traced_sync_failure(self):
        """测试同步函数失败执行"""
        @traced_sync(stage="test_stage")
        def test_func():
            raise ValueError("错误")

        with pytest.raises(ValueError):
            test_func()

