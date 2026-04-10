"""
测试工具函数
"""
import pytest
from datetime import datetime

from raap_trace_sdk.utils import (
    generate_trace_id,
    generate_span_id,
    generate_sub_job_id,
    generate_content_id,
    timestamp_to_ms,
    ms_to_datetime,
    calculate_duration_ms,
)


class TestIdGeneration:
    """ID 生成测试"""

    def test_generate_trace_id(self):
        """测试生成 Trace ID"""
        trace_id = generate_trace_id()
        assert trace_id.startswith("trace-")
        assert len(trace_id) == 14  # trace- + 8 chars

    def test_generate_span_id(self):
        """测试生成 Span ID"""
        span_id = generate_span_id()
        assert span_id.startswith("span-")
        assert len(span_id) == 13  # span- + 8 chars

    def test_generate_sub_job_id(self):
        """测试生成 Sub Job ID"""
        # 默认类型
        sub_job_id = generate_sub_job_id()
        assert sub_job_id.startswith("sub-test-")
        assert len(sub_job_id) == 25  # sub-test- + 16 chars

        # 指定类型
        sub_job_id = generate_sub_job_id("sched")
        assert sub_job_id.startswith("sub-sched-")

    def test_generate_content_id(self):
        """测试生成 Content ID"""
        content_id = generate_content_id()
        assert content_id.startswith("content-")
        assert len(content_id) == 24  # content- + 16 chars

    def test_id_uniqueness(self):
        """测试 ID 唯一性"""
        ids = [generate_trace_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestTimestampConversion:
    """时间戳转换测试"""

    def test_timestamp_to_ms(self):
        """测试 datetime 转毫秒"""
        dt = datetime(2025, 12, 7, 12, 0, 0)
        ms = timestamp_to_ms(dt)
        assert isinstance(ms, int)
        assert ms > 0

    def test_timestamp_to_ms_none(self):
        """测试 None 值处理"""
        assert timestamp_to_ms(None) is None

    def test_ms_to_datetime(self):
        """测试毫秒转 datetime"""
        dt = datetime(2025, 12, 7, 12, 0, 0)
        ms = timestamp_to_ms(dt)
        converted = ms_to_datetime(ms)
        # 比较到秒级别
        assert converted.year == dt.year
        assert converted.month == dt.month
        assert converted.day == dt.day
        assert converted.hour == dt.hour

    def test_ms_to_datetime_none(self):
        """测试 None 值处理"""
        assert ms_to_datetime(None) is None


class TestDurationCalculation:
    """耗时计算测试"""

    def test_calculate_duration_ms(self):
        """测试计算耗时"""
        start = datetime(2025, 12, 7, 12, 0, 0)
        end = datetime(2025, 12, 7, 12, 0, 1)  # 1 秒后
        duration = calculate_duration_ms(start, end)
        assert duration == 1000  # 1000 毫秒

