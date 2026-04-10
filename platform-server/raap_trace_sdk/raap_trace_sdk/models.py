"""
RAAP 追踪 SDK - 数据模型

定义追踪系统的核心数据结构：
- TraceContext: 三层标识上下文
- SpanData: 单次调用的详细信息
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class TraceContext:
    """
    三层标识上下文

    在服务间传递时，需要完整传递这三层标识：
    - 第一层: job_id（任务级）
    - 第二层: sub_job_id ≈ content_id（内容级，1:1 对等）
    - 第三层: trace_id（请求级）
    """

    # 第一层：任务标识
    job_id: str

    # 第二层：内容标识（sub_job_id 与 content_id 对等）
    sub_job_id: str  # 执行侧视角
    content_id: Optional[str] = None  # 内容侧视角（GE 成功后才有，与 sub_job_id 1:1 对等）

    # 第三层：请求追踪标识
    trace_id: str = ""

    # A/B 实验信息
    experiment_id: Optional[str] = None
    experiment_group: Optional[str] = None
    experiment_variant: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "job_id": self.job_id,
            "sub_job_id": self.sub_job_id,
            "content_id": self.content_id,
            "trace_id": self.trace_id,
            "experiment_id": self.experiment_id,
            "experiment_group": self.experiment_group,
            "experiment_variant": self.experiment_variant,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceContext":
        """从字典创建实例"""
        return cls(
            job_id=data.get("job_id", ""),
            sub_job_id=data.get("sub_job_id", ""),
            content_id=data.get("content_id"),
            trace_id=data.get("trace_id", ""),
            experiment_id=data.get("experiment_id"),
            experiment_group=data.get("experiment_group"),
            experiment_variant=data.get("experiment_variant"),
        )

    def copy(self) -> "TraceContext":
        """创建副本"""
        return TraceContext(
            job_id=self.job_id,
            sub_job_id=self.sub_job_id,
            content_id=self.content_id,
            trace_id=self.trace_id,
            experiment_id=self.experiment_id,
            experiment_group=self.experiment_group,
            experiment_variant=self.experiment_variant,
        )


@dataclass
class SpanData:
    """
    Span 数据

    记录单次调用的详细信息，包括：
    - 调用标识（span_id, parent_span_id）
    - 阶段信息（stage, expert_config_code）
    - 执行状态（status, error_type, error_message）
    - 性能指标（start_time, end_time, duration_ms）
    - Token 统计（model_code, input_tokens, output_tokens）
    - 结果摘要（result_summary）
    """

    # 调用标识
    span_id: str
    parent_span_id: Optional[str] = None

    # 阶段信息
    stage: str = ""  # plugin_render/prompt_render/ge_generation/ag_ban/ag_critic
    expert_config_code: Optional[str] = None
    service_app: Optional[str] = None
    service_method: Optional[str] = None

    # 执行状态
    status: str = "pending"  # pending/running/success/failed/timeout
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    # 时间信息
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None

    # Token 统计
    model_code: Optional[str] = None
    provider_code: Optional[str] = None  # LLM Provider 编码
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # 成本信息
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0

    # 结果摘要
    result_summary: Optional[Dict[str, Any]] = None

    # 源数据引用（关联到原服务的日志表）
    source_log_id: Optional[str] = None
    source_log_table: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "stage": self.stage,
            "expert_config_code": self.expert_config_code,
            "service_app": self.service_app,
            "service_method": self.service_method,
            "status": self.status,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "model_code": self.model_code,
            "provider_code": self.provider_code,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "result_summary": self.result_summary,
            "source_log_id": self.source_log_id,
            "source_log_table": self.source_log_table,
        }

