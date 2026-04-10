"""
RAAP 追踪 SDK - 工具函数

提供 ID 生成、时间处理等工具函数
"""
import uuid
from datetime import datetime
from typing import Optional


def generate_trace_id() -> str:
    """
    生成 Trace ID

    格式：trace-{uuid8}
    示例：trace-abc12345
    """
    return f"trace-{uuid.uuid4().hex[:8]}"


def generate_span_id() -> str:
    """
    生成 Span ID

    格式：span-{uuid8}
    示例：span-xyz78901
    """
    return f"span-{uuid.uuid4().hex[:8]}"


def generate_sub_job_id(job_type: str = "test") -> str:
    """
    生成 Sub Job ID

    Args:
        job_type: 执行类型（test/sched）

    格式：sub-{type}-{uuid16}
    示例：sub-test-abc123def456ghij
    """
    return f"sub-{job_type}-{uuid.uuid4().hex[:16]}"


def generate_content_id() -> str:
    """
    生成 Content ID

    格式：content-{uuid16}
    示例：content-abc123xyz789mnop
    """
    return f"content-{uuid.uuid4().hex[:16]}"


def timestamp_to_ms(dt: Optional[datetime]) -> Optional[int]:
    """
    将 datetime 转换为毫秒时间戳

    Args:
        dt: datetime 对象

    Returns:
        毫秒时间戳，如果 dt 为 None 则返回 None
    """
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def ms_to_datetime(ms: Optional[int]) -> Optional[datetime]:
    """
    将毫秒时间戳转换为 datetime

    Args:
        ms: 毫秒时间戳

    Returns:
        datetime 对象，如果 ms 为 None 则返回 None
    """
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000)


def calculate_duration_ms(start: datetime, end: datetime) -> int:
    """
    计算两个时间点之间的毫秒数

    Args:
        start: 开始时间
        end: 结束时间

    Returns:
        毫秒数
    """
    return int((end - start).total_seconds() * 1000)

