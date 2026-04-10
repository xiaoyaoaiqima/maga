# RAAP LLM SDK

统一的 LLM 访问接口，提供模型路由、自动 Failover、熔断机制和成本计算。

## 安装

```bash
# 开发模式安装
cd raap_llm_sdk
pip install -e .
```

## 快速开始

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
    temperature=0.7,
    max_tokens=4096,
    context=LLMCallContext(
        trace_id="abc123",
        job_id="job-001",
        expert_config_code="content_generator"
    )
)

# 方式 2：指定具体端点（跳过路由，不自动 failover）
response = await client.invoke(
    provider_code="aihubmix",
    model="gpt-4o",
    messages=[...]
)

# 获取调用结果
print(response.content)              # 响应内容
print(response.usage.total_tokens)   # Token 使用量
print(response.cost.total_cost)      # 调用成本（美元）
print(response.failover_attempts)    # failover 次数（0 表示首选成功）
print(response.latency_ms)           # 耗时（毫秒）
```

## 功能特性

### 1. 模型路由

业务侧使用统一的 `model_code`（如 `gpt-4o`），SDK 自动根据配置路由到可用端点：

```python
# model_code 会自动路由到 aihubmix 或 openai 等端点
response = await client.invoke(model_code="gpt-4o", messages=[...])
```

### 2. 自动 Failover

当主端点故障时，自动切换到备用端点：

```
gpt-4o 路由配置：
  - aihubmix (priority=100, 主)
  - openai (priority=50, 备)

调用流程：
  aihubmix 调用失败 → 自动 failover → openai 调用成功
```

### 3. 熔断机制

防止故障端点持续被调用：

```
熔断状态机：
  CLOSED (正常) → 连续失败 3 次 → OPEN (熔断)
  OPEN → 60 秒后 → HALF_OPEN (半开探测)
  HALF_OPEN → 成功 → CLOSED
  HALF_OPEN → 失败 → OPEN
```

### 4. 成本计算

自动计算每次调用的成本：

```python
response = await client.invoke(model_code="gpt-4o", messages=[...])
print(f"输入成本: ${response.cost.input_cost}")
print(f"输出成本: ${response.cost.output_cost}")
print(f"总成本: ${response.cost.total_cost}")
```

### 5. 追踪上报

自动上报调用数据到 Orchestrator（需集成 raap_trace_sdk）：

```python
response = await client.invoke(
    model_code="gpt-4o",
    messages=[...],
    context=LLMCallContext(
        trace_id="abc123",
        job_id="job-001",
        sub_job_id="sub-001",
        content_id="content-001",
        expert_config_code="content_generator"
    )
)
```

## 配置

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ORCHESTRATOR_APP_ID` | Orchestrator Dapr App ID | `raap-service-orchestrator` |
| `ORCHESTRATOR_BASE_URL` | HTTP 回退地址（开发用） | `http://localhost:5100` |

### 初始化参数

```python
client = LLMClient(
    orchestrator_app_id="raap-service-orchestrator",  # Orchestrator App ID
    enable_failover=True,       # 启用自动 failover
    enable_circuit_breaker=True,# 启用熔断
    enable_trace_report=True,   # 启用追踪上报
    cache_ttl=300,              # 配置缓存 TTL（秒）
    circuit_breaker_threshold=3,# 熔断阈值
    circuit_breaker_timeout=60, # 熔断恢复时间（秒）
    redis_client=None,          # Redis 客户端（多实例共享熔断状态）
)
```

## 异常处理

```python
from raap_llm_sdk import (
    LLMClient,
    AllProvidersFailedError,
    NonRetryableError,
    CircuitBreakerOpenError,
)

try:
    response = await client.invoke(model_code="gpt-4o", messages=[...])
except AllProvidersFailedError as e:
    # 所有端点都失败
    print(f"所有端点不可用，尝试次数: {e.attempts}")
except NonRetryableError as e:
    # 不可重试错误（认证失败、参数错误等）
    print(f"不可重试错误: {e}")
except CircuitBreakerOpenError as e:
    # 端点被熔断
    print(f"端点 {e.provider_code} 已熔断")
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/
```

## 目录结构

```
raap_llm_sdk/
├── raap_llm_sdk/
│   ├── __init__.py           # 导出主要接口
│   ├── client.py             # LLMClient 主类
│   ├── config.py             # 配置获取（从 Orchestrator）
│   ├── cache.py              # 本地缓存（TTL 5分钟）
│   ├── circuit_breaker.py    # 熔断器
│   ├── router.py             # 模型路由器（支持优先级/轮询策略）
│   ├── models.py             # 数据模型
│   └── exceptions.py         # 异常定义
├── tests/
│   ├── test_cache.py         # 缓存测试
│   ├── test_circuit_breaker.py # 熔断器测试
│   ├── test_client.py        # 客户端测试
│   ├── test_config.py        # 配置测试
│   ├── test_exceptions.py    # 异常测试
│   ├── test_models.py        # 模型测试
│   └── test_router.py        # 路由器测试
├── setup.py
└── README.md
```

## 高级用法

### 自定义路由策略

```python
from raap_llm_sdk import ModelRouter, RoutingStrategy

# 使用轮询策略（负载均衡）
router = ModelRouter(
    circuit_breaker=client._circuit_breaker,
    strategy=RoutingStrategy.ROUND_ROBIN
)

# 获取可用路由
routes = router.get_available_routes(all_routes)

# 获取 failover 路由
backup = router.get_failover_route(
    routes,
    failed_provider="primary",
    previous_attempts=["primary"]
)
```

### 路由统计

```python
stats = router.get_route_stats(routes)
print(f"总路由数: {stats['total']}")
print(f"启用数: {stats['enabled']}")
print(f"熔断数: {stats['circuit_broken']}")
print(f"可用数: {stats['available']}")
```

