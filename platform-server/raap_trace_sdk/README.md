# RAAP Trace SDK

RAAP 微服务统一追踪 SDK，为 GE（Generation Experts）和 AG（Alignment Governance）服务提供统一的调用追踪能力。

## 特性

- **三层标识体系**：job_id（任务级）→ sub_job_id/content_id（内容级）→ trace_id/span_id（调用级）
- **自动追踪装饰器**：`@traced` 自动捕获执行时间、状态、Token 消耗等
- **上下文管理**：基于 `contextvars`，支持异步环境
- **gRPC 上报**：通过 Dapr 将追踪数据上报到 Orchestrator

## 安装

```bash
# 开发模式安装
pip install -e ./raap_trace_sdk

# 或者添加到 requirements.txt
-e ./raap_trace_sdk
```

## 快速开始

### 1. 初始化上报器

```python
from raap_trace_sdk import init_reporter

# 在服务启动时初始化
init_reporter(orchestrator_app_id="raap-service-orchestrator")
```

### 2. 设置追踪上下文

```python
from raap_trace_sdk import TraceContext, set_context, TraceContextManager

# 方式1：直接设置
context = TraceContext(
    job_id="job-abc123",
    sub_job_id="sub-test-xyz789",
    trace_id="trace-123456",
)
set_context(context)

# 方式2：使用上下文管理器
async with TraceContextManager(context):
    await do_something()
```

### 3. 使用装饰器自动追踪

```python
from raap_trace_sdk import traced

@traced(stage="ge_generation")
async def generate_content(prompt: str, model_code: str):
    """内容生成"""
    result = await llm_service.generate(prompt, model_code)
    return {
        "generated": True,
        "content_id": result.content_id,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
        "model_code": model_code,
    }
```

装饰器会自动：
- 生成 `span_id`
- 记录执行时间
- 捕获返回结果中的 Token 信息
- 上报追踪数据到 Orchestrator

### 4. 带上下文参数的函数

```python
from raap_trace_sdk import traced, TraceContext

@traced(stage="ag_ban_illegal")
async def check_illegal(context: TraceContext, content: str):
    """违规检测"""
    result = await ban_expert.check(content)
    return {
        "passed": result.passed,
        "reason": result.reason,
    }
```

如果函数参数中包含 `TraceContext`，装饰器会自动使用它。

## 三层标识说明

| 层级 | 标识 | 说明 |
|------|------|------|
| 第一层 | `job_id` | 任务级标识，来自 Job 表 |
| 第二层 | `sub_job_id` ≈ `content_id` | 内容级标识，1:1 对等关系 |
| 第三层 | `trace_id` + `span_id` | 调用级标识，形成调用链路 |

## API 参考

### TraceContext

```python
@dataclass
class TraceContext:
    job_id: str                    # 任务 ID
    sub_job_id: str                # 执行 ID（与 content_id 对等）
    content_id: Optional[str]      # 内容 ID（GE 成功后才有）
    trace_id: str                  # 请求追踪 ID
    experiment_id: Optional[str]   # A/B 实验 ID
    experiment_group: Optional[str] # 实验分组
```

### SpanData

```python
@dataclass
class SpanData:
    span_id: str                   # 调用 ID
    parent_span_id: Optional[str]  # 父调用 ID
    stage: str                     # 阶段名称
    status: str                    # 状态：success/failed/timeout
    duration_ms: Optional[int]     # 耗时（毫秒）
    input_tokens: int              # 输入 Token 数
    output_tokens: int             # 输出 Token 数
    # ... 更多字段见源码
```

### @traced 装饰器

```python
@traced(
    stage="ge_generation",         # 阶段名称
    reporter=None,                 # 上报器（默认使用全局单例）
    async_report=True,             # 是否异步上报
    expert_config_code="xxx",      # Expert 配置编码
)
async def my_function(...):
    ...
```

## 工具函数

```python
from raap_trace_sdk import (
    generate_trace_id,      # 生成 trace-{uuid8}
    generate_span_id,       # 生成 span-{uuid8}
    generate_sub_job_id,    # 生成 sub-{type}-{uuid16}
    generate_content_id,    # 生成 content-{uuid16}
)
```

## 设计文档

详细设计请参考：`readme/TRACE_SYSTEM_DESIGN.md`

