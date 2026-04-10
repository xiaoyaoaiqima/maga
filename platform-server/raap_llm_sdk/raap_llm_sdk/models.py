"""
LLM SDK 数据模型
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any


@dataclass
class ProviderConfig:
    """LLM Provider 配置"""
    provider_code: str
    provider_name: str
    provider_type: str  # openai_compatible / gemini_native / azure
    base_url: str
    api_key: str
    default_model: Optional[str] = None
    available_models: Optional[List[str]] = None
    default_params: Optional[Dict[str, Any]] = None
    timeout: int = 120
    priority: int = 0
    enabled: bool = True


@dataclass
class ModelRoute:
    """模型路由配置"""
    model_code: str
    model_name: str
    provider_code: str
    provider_model: str
    priority: int = 0
    enabled: bool = True
    max_context_length: Optional[int] = None
    features: Optional[Dict[str, bool]] = None
    cost_per_1k_input: Optional[Decimal] = None
    cost_per_1k_output: Optional[Decimal] = None
    timeout_seconds: Optional[int] = None
    
@dataclass
class LLMCallContext:
    """LLM 调用上下文（用于追踪）"""
    trace_id: str
    job_id: str
    sub_job_id: Optional[str] = None
    content_id: Optional[str] = None
    expert_config_code: Optional[str] = None
    experiment_id: Optional[str] = None
    experiment_group: Optional[str] = None
    parent_span_id: Optional[str] = None  # 新增：父级 Span ID


@dataclass
class LLMUsage:
    """Token 使用统计"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMCost:
    """成本统计"""
    input_cost: Decimal = field(default_factory=lambda: Decimal("0"))
    output_cost: Decimal = field(default_factory=lambda: Decimal("0"))
    total_cost: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class LLMResponse:
    """LLM 调用响应"""
    content: str
    model_code: str
    provider_code: str
    provider_model: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    cost: LLMCost = field(default_factory=LLMCost)
    latency_ms: int = 0
    failover_attempts: int = 0
    success: bool = True
    error_message: Optional[str] = None
    
    # 原始响应（可选）
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class CircuitBreakerState:
    """熔断器状态"""
    provider_code: str
    state: str  # closed / open / half_open
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_failure_reason: Optional[str] = None
    open_until: Optional[datetime] = None

