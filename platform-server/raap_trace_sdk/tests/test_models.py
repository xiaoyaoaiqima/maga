"""
测试数据模型
"""
import pytest
from datetime import datetime

from raap_trace_sdk.models import TraceContext, SpanData


class TestTraceContext:
    """TraceContext 测试"""

    def test_create_context(self):
        """测试创建上下文"""
        context = TraceContext(
            job_id="job-test123",
            sub_job_id="sub-test-abc",
            trace_id="trace-xyz",
        )
        assert context.job_id == "job-test123"
        assert context.sub_job_id == "sub-test-abc"
        assert context.trace_id == "trace-xyz"
        assert context.content_id is None
        assert context.experiment_id is None

    def test_to_dict(self):
        """测试转换为字典"""
        context = TraceContext(
            job_id="job-123",
            sub_job_id="sub-456",
            trace_id="trace-789",
            content_id="content-abc",
            experiment_id="exp-001",
            experiment_group="treatment",
        )
        data = context.to_dict()
        assert data["job_id"] == "job-123"
        assert data["sub_job_id"] == "sub-456"
        assert data["content_id"] == "content-abc"
        assert data["experiment_id"] == "exp-001"
        assert data["experiment_group"] == "treatment"

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "job_id": "job-123",
            "sub_job_id": "sub-456",
            "trace_id": "trace-789",
            "content_id": "content-abc",
        }
        context = TraceContext.from_dict(data)
        assert context.job_id == "job-123"
        assert context.sub_job_id == "sub-456"
        assert context.content_id == "content-abc"

    def test_copy(self):
        """测试复制上下文"""
        context = TraceContext(
            job_id="job-123",
            sub_job_id="sub-456",
            trace_id="trace-789",
        )
        copied = context.copy()
        assert copied.job_id == context.job_id
        assert copied is not context


class TestSpanData:
    """SpanData 测试"""

    def test_create_span(self):
        """测试创建 Span"""
        span = SpanData(
            span_id="span-001",
            stage="ge_generation",
            status="success",
        )
        assert span.span_id == "span-001"
        assert span.stage == "ge_generation"
        assert span.status == "success"
        assert span.input_tokens == 0
        assert span.output_tokens == 0

    def test_span_with_tokens(self):
        """测试带 Token 信息的 Span"""
        span = SpanData(
            span_id="span-002",
            stage="ge_generation",
            status="success",
            model_code="gpt-4",
            input_tokens=100,
            output_tokens=200,
            total_tokens=300,
        )
        assert span.model_code == "gpt-4"
        assert span.input_tokens == 100
        assert span.output_tokens == 200
        assert span.total_tokens == 300

    def test_span_to_dict(self):
        """测试转换为字典"""
        now = datetime.now()
        span = SpanData(
            span_id="span-003",
            stage="ag_ban",
            status="success",
            start_time=now,
            end_time=now,
            duration_ms=100,
            result_summary={"passed": True},
        )
        data = span.to_dict()
        assert data["span_id"] == "span-003"
        assert data["stage"] == "ag_ban"
        assert data["duration_ms"] == 100
        assert data["result_summary"] == {"passed": True}

