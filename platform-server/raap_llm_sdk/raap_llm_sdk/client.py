"""
LLM Client - 主客户端类

提供统一的 LLM 访问接口，支持：
- 模型路由（自动选择端点）
- 自动 Failover（端点故障切换）
- 熔断机制（防止雪崩）
- 自动追踪上报（集成 raap_trace_sdk）
"""
import os
import time
import logging
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal

from .models import (
    ProviderConfig, ModelRoute, LLMCallContext,
    LLMResponse, LLMUsage, LLMCost
)
from .config import ConfigProvider
from .cache import LocalCache
from .circuit_breaker import CircuitBreaker
from .exceptions import (
    LLMError, LLMConfigError, RetryableError, NonRetryableError,
    AllProvidersFailedError, CircuitBreakerOpenError, classify_error
)

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM 统一客户端
    
    使用示例：
    ```python
    from raap_llm_sdk import LLMClient, LLMCallContext
    
    # 初始化
    client = LLMClient(orchestrator_app_id="raap-service-orchestrator")
    
    # 使用统一 model_code（推荐，自动 failover）
    response = await client.invoke(
        model_code="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
        context=LLMCallContext(trace_id="xxx", job_id="xxx")
    )
    
    # 指定端点（跳过路由）
    response = await client.invoke(
        provider_code="aihubmix",
        model="gpt-4o",
        messages=[...]
    )
    ```
    """
    
    def __init__(
        self,
        orchestrator_app_id: str = None,
        enable_failover: bool = True,
        enable_circuit_breaker: bool = True,
        enable_trace_report: bool = True,
        cache_ttl: int = 300,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_timeout: int = 60,
        redis_client = None,
    ):
        """
        初始化 LLM 客户端
        
        Args:
            orchestrator_app_id: Orchestrator 的 Dapr App ID
            enable_failover: 是否启用自动 failover
            enable_circuit_breaker: 是否启用熔断
            enable_trace_report: 是否启用追踪上报
            cache_ttl: 配置缓存 TTL（秒）
            circuit_breaker_threshold: 熔断触发阈值
            circuit_breaker_timeout: 熔断恢复时间（秒）
            redis_client: Redis 客户端（用于多实例共享熔断状态）
        """
        self._config_provider = ConfigProvider(
            orchestrator_app_id=orchestrator_app_id,
            cache_ttl=cache_ttl,
        )
        self._provider_cache = LocalCache(default_ttl=cache_ttl)
        
        self._enable_failover = enable_failover
        self._enable_circuit_breaker = enable_circuit_breaker
        self._enable_trace_report = enable_trace_report
        
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold,
            recovery_timeout=circuit_breaker_timeout,
            redis_client=redis_client,
        ) if enable_circuit_breaker else None
        
        self._trace_reporter = None
    
    async def invoke(
        self,
        messages: List[Dict[str, str]],
        model_code: str = None,
        provider_code: str = None,
        model: str = None,
        context: LLMCallContext = None,
        temperature: float = None,
        max_tokens: int = None,
        **kwargs
    ) -> LLMResponse:
        """
        调用 LLM
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model_code: 统一模型编码（使用路由，自动 failover）
            provider_code: 指定端点编码（跳过路由）
            model: 指定端点的模型名（与 provider_code 配合使用）
            context: 调用上下文（用于追踪）
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他模型参数
        
        Returns:
            LLMResponse 对象
        
        Raises:
            AllProvidersFailedError: 所有端点都失败
            NonRetryableError: 不可重试的错误
        """
        start_time = time.time()
        
        if model_code:
            # 模式 1：使用 model_code，自动路由 + failover
            return await self._invoke_with_routing(
                model_code=model_code,
                messages=messages,
                context=context,
                temperature=temperature,
                max_tokens=max_tokens,
                start_time=start_time,
                **kwargs
            )
        elif provider_code:
            # 模式 2：指定端点，跳过路由
            return await self._invoke_direct(
                provider_code=provider_code,
                model=model,
                messages=messages,
                context=context,
                temperature=temperature,
                max_tokens=max_tokens,
                start_time=start_time,
                **kwargs
            )
        else:
            raise LLMError("必须指定 model_code 或 provider_code")
    
    async def _invoke_with_routing(
        self,
        model_code: str,
        messages: List[Dict[str, str]],
        context: LLMCallContext,
        start_time: float,
        **kwargs
    ) -> LLMResponse:
        """带路由和 failover 的调用"""
        # 获取模型路由
        routes = await self._config_provider.get_model_routes(model_code)
        if not routes:
            raise LLMConfigError(f"模型 '{model_code}' 没有可用的路由配置")
        
        # 按优先级排序（已在获取时排序）
        last_error = None
        failover_attempts = 0
        
        for route in routes:
            # 检查熔断
            if self._circuit_breaker and self._circuit_breaker.is_open(route.provider_code):
                logger.debug(f"端点 {route.provider_code} 已熔断，跳过")
                continue
            
            try:
                # 获取端点配置
                provider = await self._get_provider_config(route.provider_code)
                if not provider:
                    logger.warning(f"端点 {route.provider_code} 配置不存在，跳过")
                    continue
                
                # 调用 LLM
                response = await self._call_llm(
                    provider=provider,
                    model=route.provider_model,
                    messages=messages,
                    route=route,
                    **kwargs
                )
                
                # 成功：记录熔断状态
                if self._circuit_breaker:
                    self._circuit_breaker.record_success(route.provider_code)
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                result = LLMResponse(
                    content=response.content,
                    model_code=model_code,
                    provider_code=route.provider_code,
                    provider_model=route.provider_model,
                    usage=response.usage,
                    latency_ms=latency_ms,
                    failover_attempts=failover_attempts,
                    success=True,
                    raw_response=response.raw_response,
                )
                
                # 上报追踪
                if self._enable_trace_report and context:
                    await self._report_trace(context, result)
                
                return result
                
            except RetryableError as e:
                # 可重试错误：记录失败，尝试下一个端点
                last_error = e
                failover_attempts += 1
                
                if self._circuit_breaker:
                    self._circuit_breaker.record_failure(route.provider_code, str(e))
                
                logger.warning(
                    f"端点 {route.provider_code} 调用失败: {e}，"
                    f"尝试 failover（{failover_attempts}/{len(routes)}）"
                )
                
                if not self._enable_failover:
                    raise
                
                continue
                
            except NonRetryableError as e:
                # 不可重试错误：直接抛出
                logger.error(f"端点 {route.provider_code} 不可重试错误: {e}")
                raise
        
        # 所有端点都失败
        raise AllProvidersFailedError(
            f"模型 '{model_code}' 所有端点均不可用",
            last_error=last_error,
            attempts=failover_attempts
        )
    
    async def _invoke_direct(
        self,
        provider_code: str,
        model: str,
        messages: List[Dict[str, str]],
        context: LLMCallContext,
        start_time: float,
        **kwargs
    ) -> LLMResponse:
        """直接调用指定端点"""
        # 检查熔断
        if self._circuit_breaker and self._circuit_breaker.is_open(provider_code):
            raise CircuitBreakerOpenError(provider_code)
        
        # 获取端点配置
        provider = await self._get_provider_config(provider_code)
        if not provider:
            raise LLMConfigError(f"Provider '{provider_code}' not found")
        
        try:
            response = await self._call_llm(
                provider=provider,
                model=model or provider.default_model,
                messages=messages,
                **kwargs
            )
            
            if self._circuit_breaker:
                self._circuit_breaker.record_success(provider_code)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            result = LLMResponse(
                content=response.content,
                model_code=model or provider.default_model,
                provider_code=provider_code,
                provider_model=model or provider.default_model,
                usage=response.usage,
                latency_ms=latency_ms,
                failover_attempts=0,
                success=True,
                raw_response=response.raw_response,
            )
            
            if self._enable_trace_report and context:
                await self._report_trace(context, result)
            
            return result
            
        except (RetryableError, NonRetryableError) as e:
            if self._circuit_breaker:
                self._circuit_breaker.record_failure(provider_code, str(e))
            raise
    
    async def _get_provider_config(self, provider_code: str) -> Optional[ProviderConfig]:
        """获取 Provider 配置（带缓存）"""
        cache_key = f"provider:{provider_code}"
        
        cached = self._provider_cache.get(cache_key)
        if cached:
            return cached
        
        config = await self._config_provider.get_provider_config(provider_code)
        if config:
            self._provider_cache.set(cache_key, config)
        
        return config
    
    async def _call_llm(
        self,
        provider: ProviderConfig,
        model: str,
        messages: List[Dict[str, str]],
        route: ModelRoute = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        实际调用 LLM API
        
        默认走 OpenAI 兼容接口，可选择流式
        """
        import httpx
        import json
        
        # 构建请求参数
        params = {
            "model": model,
            "messages": messages,
        }
        
        # 合并默认参数
        if provider.default_params:
            params.update(provider.default_params)
        
        # 覆盖用户指定的参数
        if kwargs.get("temperature") is not None:
            params["temperature"] = kwargs["temperature"]
        if kwargs.get("max_tokens") is not None:
            params["max_tokens"] = kwargs["max_tokens"]
        
        # 其他参数（含工具调用）
        for key in [
            "top_p",
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "tools",
            "tool_choice",
        ]:
            if kwargs.get(key) is not None:
                params[key] = kwargs[key]
        
        if stream:
            params["stream"] = True
        
        timeout = route.timeout_seconds if route and route.timeout_seconds else provider.timeout
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if stream:
                    chunks: List[Dict[str, Any]] = []
                    async with client.stream(
                        "POST",
                        f"{provider.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {provider.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=params,
                    ) as resp:
                        if resp.status_code != 200:
                            text = await resp.aread()
                            error = classify_error(resp.status_code, text[:500].decode() if isinstance(text, (bytes, bytearray)) else str(text))
                            raise error
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            if line.startswith("data:"):
                                data = line[5:].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    chunks.append(chunk)
                                except json.JSONDecodeError:
                                    logger.debug(f"忽略无法解析的流式数据: {data[:200]}")
                                    continue
                    # 聚合内容与 usage
                    full_content_parts: List[str] = []
                    usage_data: Dict[str, Any] = {}
                    for chunk in chunks:
                        choice = (chunk.get("choices") or [{}])[0] or {}
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            full_content_parts.append(delta["content"])
                        if choice.get("message", {}).get("content"):
                            full_content_parts.append(choice["message"]["content"])
                        if chunk.get("usage"):
                            usage_data = chunk["usage"]
                    content = "".join(full_content_parts)
                    return LLMResponse(
                        content=content,
                        model_code=model,
                        provider_code=provider.provider_code,
                        provider_model=model,
                        usage=LLMUsage(
                            input_tokens=usage_data.get("prompt_tokens", 0),
                            output_tokens=usage_data.get("completion_tokens", 0),
                            total_tokens=usage_data.get("total_tokens", 0),
                        ),
                        raw_response={"chunks": chunks},
                    )
                else:
                    response = await client.post(
                        f"{provider.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {provider.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=params,
                    )
                
                if response.status_code != 200:
                    error = classify_error(response.status_code, response.text[:500])
                    raise error
                
                result = response.json()
                
                # 解析响应
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage_data = result.get("usage", {})
                
                return LLMResponse(
                    content=content,
                    model_code=model,
                    provider_code=provider.provider_code,
                    provider_model=model,
                    usage=LLMUsage(
                        input_tokens=usage_data.get("prompt_tokens", 0),
                        output_tokens=usage_data.get("completion_tokens", 0),
                        total_tokens=usage_data.get("total_tokens", 0),
                    ),
                    raw_response=result,
                )
            
        except httpx.TimeoutException:
            raise RetryableError(f"请求超时 ({timeout}s)", status_code=408)
        except httpx.ConnectError as e:
            raise RetryableError(f"连接失败: {e}", status_code=503)
        except httpx.RemoteProtocolError as e:
            # 远程协议错误：服务器在发送响应前断开连接，应该触发 failover
            raise RetryableError(f"远程协议错误: {e}", status_code=503)
        except httpx.ReadError as e:
            # 读取错误：网络传输过程中断，应该触发 failover
            raise RetryableError(f"读取错误: {e}", status_code=503)
        except httpx.WriteError as e:
            # 写入错误：发送请求时网络中断，应该触发 failover
            raise RetryableError(f"写入错误: {e}", status_code=503)
        except httpx.HTTPStatusError as e:
            error = classify_error(e.response.status_code, str(e))
            raise error
    
    async def _report_trace(self, context: LLMCallContext, response: LLMResponse):
        """上报追踪数据"""
        if not self._enable_trace_report:
            return
        
        try:
            # 延迟导入 trace_sdk
            if self._trace_reporter is None:
                try:
                    from raap_trace_sdk import TraceReporter, TraceContext, SpanData, generate_span_id
                    self._trace_reporter = TraceReporter()
                except ImportError:
                    logger.debug("raap_trace_sdk not found, trace reporting disabled")
                    self._enable_trace_report = False
                    return

            # 再次导入以确保类型可用（如果 _trace_reporter 已经初始化）
            from raap_trace_sdk import TraceContext, SpanData, generate_span_id

            # 构建追踪上下文
            trace_ctx = TraceContext(
                job_id=context.job_id or "",
                sub_job_id=context.sub_job_id or "",
                content_id=context.content_id,
                trace_id=context.trace_id or "",
                experiment_id=context.experiment_id,
                experiment_group=context.experiment_group,
            )

            # 构建 Span 数据
            span = SpanData(
                span_id=generate_span_id(),
                parent_span_id=context.parent_span_id,  # 设置父级 Span ID
                stage="llm_call",
                status="success" if response.success else "failed",
                expert_config_code=context.expert_config_code,
                service_app="raap-llm-sdk",
                service_method="invoke",
                model_code=response.model_code,
                provider_code=response.provider_code,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
                # 成本计算由 Orchestrator 服务端统一处理
                input_cost=0.0,
                output_cost=0.0,
                total_cost=0.0,
                duration_ms=response.latency_ms,
                result_summary={
                    "failover_count": response.failover_attempts
                }
            )
            
            await self._trace_reporter.report_span(trace_ctx, span)
            
        except Exception as e:
            logger.warning(f"追踪上报失败: {e}")
    
    def get_circuit_breaker_status(self, provider_code: str = None):
        """获取熔断状态"""
        if not self._circuit_breaker:
            return None
        return self._circuit_breaker.get_status(provider_code)
    
    def reset_circuit_breaker(self, provider_code: str):
        """重置熔断状态"""
        if self._circuit_breaker:
            self._circuit_breaker.reset(provider_code)
    
    def invalidate_cache(self, key: str = None):
        """清除配置缓存"""
        if key:
            self._provider_cache.delete(key)
        else:
            self._provider_cache.clear()
        self._config_provider.invalidate_cache(key)

