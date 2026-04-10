"""
RAAP LLM SDK

统一的 LLM 访问接口，提供：
- 模型路由（自动选择端点）
- 自动 Failover（端点故障切换）
- 熔断机制（防止雪崩）
- 成本计算
- 自动追踪上报

使用示例：
```python
from raap_llm_sdk import LLMClient, LLMCallContext

# 初始化客户端
client = LLMClient(orchestrator_app_id="raap-service-orchestrator")

# 方式 1：使用统一 model_code（推荐，自动 failover）
response = await client.invoke(
    model_code="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ],
    context=LLMCallContext(
        trace_id="abc123",
        job_id="job-001",
        expert_config_code="content_generator"
    )
)

# 方式 2：指定具体端点
response = await client.invoke(
    provider_code="aihubmix",
    model="gpt-4o",
    messages=[...]
)

# 获取调用结果
print(response.content)              # 响应内容
print(response.usage.total_tokens)   # Token 使用量
print(response.cost.total_cost)      # 调用成本
print(response.failover_attempts)    # failover 次数
```
"""

from .client import LLMClient
from .langchain_llm import LangChainLLM
from .models import (
    ProviderConfig,
    ModelRoute,
    LLMCallContext,
    LLMResponse,
    LLMUsage,
    LLMCost,
    CircuitBreakerState,
)
from .config import ConfigProvider
from .cache import LocalCache
from .circuit_breaker import CircuitBreaker
from .router import ModelRouter, RoutingStrategy
from .exceptions import (
    LLMError,
    LLMConfigError,
    RetryableError,
    NonRetryableError,
    AllProvidersFailedError,
    CircuitBreakerOpenError,
    classify_error,
)

__version__ = "0.1.0"

__all__ = [
    # 主类
    "LLMClient",
    "LangChainLLM",
    # 数据模型
    "ProviderConfig",
    "ModelRoute",
    "LLMCallContext",
    "LLMResponse",
    "LLMUsage",
    "LLMCost",
    "CircuitBreakerState",
    # 配置与路由
    "ConfigProvider",
    "LocalCache",
    "CircuitBreaker",
    "ModelRouter",
    "RoutingStrategy",
    # 异常
    "LLMError",
    "LLMConfigError",
    "RetryableError",
    "NonRetryableError",
    "AllProvidersFailedError",
    "CircuitBreakerOpenError",
    "classify_error",
]

