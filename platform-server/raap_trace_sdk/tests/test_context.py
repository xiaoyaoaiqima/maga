"""
测试上下文管理
"""
import pytest
import asyncio

from raap_trace_sdk.models import TraceContext
from raap_trace_sdk.context import (
    set_context,
    get_current_context,
    clear_context,
    set_current_span_id,
    get_current_span_id,
    TraceContextManager,
    SpanContextManager,
)


class TestContextVars:
    """上下文变量测试"""

    def test_set_and_get_context(self):
        """测试设置和获取上下文"""
        context = TraceContext(
            job_id="job-123",
            sub_job_id="sub-456",
            trace_id="trace-789",
        )
        set_context(context)
        retrieved = get_current_context()
        assert retrieved is context
        clear_context()

    def test_clear_context(self):
        """测试清除上下文"""
        context = TraceContext(
            job_id="job-123",
            sub_job_id="sub-456",
            trace_id="trace-789",
        )
        set_context(context)
        clear_context()
        assert get_current_context() is None

    def test_span_id_context(self):
        """测试 Span ID 上下文"""
        set_current_span_id("span-001")
        assert get_current_span_id() == "span-001"
        clear_context()
        assert get_current_span_id() is None


class TestTraceContextManager:
    """TraceContextManager 测试"""

    def test_sync_context_manager(self):
        """测试同步上下文管理器"""
        context = TraceContext(
            job_id="job-123",
            sub_job_id="sub-456",
            trace_id="trace-789",
        )

        assert get_current_context() is None

        with TraceContextManager(context):
            assert get_current_context() is context

        assert get_current_context() is None

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """测试异步上下文管理器"""
        context = TraceContext(
            job_id="job-123",
            sub_job_id="sub-456",
            trace_id="trace-789",
        )

        assert get_current_context() is None

        async with TraceContextManager(context):
            assert get_current_context() is context

        assert get_current_context() is None


class TestSpanContextManager:
    """SpanContextManager 测试"""

    def test_span_context_nesting(self):
        """测试 Span 上下文嵌套"""
        with SpanContextManager("span-001"):
            assert get_current_span_id() == "span-001"

            with SpanContextManager("span-002"):
                assert get_current_span_id() == "span-002"

            # 退出内层后恢复外层
            assert get_current_span_id() == "span-001"

        assert get_current_span_id() is None

    @pytest.mark.asyncio
    async def test_async_span_context(self):
        """测试异步 Span 上下文"""
        async with SpanContextManager("span-001"):
            assert get_current_span_id() == "span-001"

        assert get_current_span_id() is None

