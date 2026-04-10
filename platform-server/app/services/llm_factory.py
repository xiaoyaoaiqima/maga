"""
LLM 工厂类

已改造为使用 raap_llm_sdk：
- 通过 Dapr 从 Orchestrator 动态获取 Provider 配置
- 支持自动 Failover
- 支持熔断机制
- 移除硬编码的 API Key
"""
import os
from typing import Dict, Any, Optional, List, Union

from app.utils.model_config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    ensure_chat_completions_endpoint,
)
from loguru import logger

# LLM SDK 客户端（延迟初始化）
_llm_client = None
_sdk_available = None


def _check_sdk_available() -> bool:
    """检查 SDK 是否可用"""
    global _sdk_available
    if _sdk_available is None:
        try:
            from raap_llm_sdk import LLMClient  # noqa: F401
            _sdk_available = True
        except ImportError:
            _sdk_available = False
            logger.warning("raap_llm_sdk 未安装")
    return _sdk_available


def get_llm_client():
    """获取 LLM SDK 客户端（单例）"""
    global _llm_client
    if _llm_client is None:
        if not _check_sdk_available():
            raise RuntimeError("raap_llm_sdk 未安装，无法初始化 LLM 客户端")
        
        from raap_llm_sdk import LLMClient
        _llm_client = LLMClient(
            orchestrator_app_id=os.getenv("ORCHESTRATOR_APP_ID", "raap-service-orchestrator"),
            enable_failover=True,
            enable_circuit_breaker=True,
            enable_trace_report=False,  # 统一由 Orchestrator 记录专家级 Trace，隐藏底层 llm_call
        )
        logger.info("LLM SDK 客户端初始化成功（使用 Dapr）")
    return _llm_client


class LLMFactory:
    """LangChain 多模型工厂"""
    
    # 默认兜底 key 置空，避免将真实密钥提交到代码库
    DEFAULT_FALLBACK_API_KEY = ""
    # 默认兜底 base_url（无环境变量时使用）
    DEFAULT_FALLBACK_BASE_URL = "https://aihubmix.com/v1/chat/completions"
    
    @staticmethod
    def get_llm_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取 LLM 配置信息（同步，兼容旧接口）
        
        注意：此方法仅使用环境变量，无法从 Orchestrator 动态获取配置
        新代码建议使用 call_llm() 获取动态配置
        
        Args:
            config: Agent 配置字典，包含 provider, model, endpoint 等
            
        Returns:
            LLM 配置字典，包含 api_key, base_url, model 等信息
        """
        provider = config.get("provider", "openai")
        
        # 兼容 Main 分支的 AIModelService 逻辑，但也保留旧逻辑作为兜底
        if provider == "openai" or provider == "aihubmix":
            # 使用 OpenAI 或 AIHUBMIX
            # 优先使用配置中的 api_key，然后尝试 OPENAI_API_KEY，最后尝试 AIHUBMIX_API_KEY
            api_key = (
                config.get("api_key") or 
                os.getenv("OPENAI_API_KEY") or 
                os.getenv("AIHUBMIX_API_KEY") or
                LLMFactory.DEFAULT_FALLBACK_API_KEY
            )
            # 优先使用配置中的 base_url，然后尝试 OPENAI_BASE_URL，AIHUBMIX_API_URL，最后兜底默认值
            base_url_candidate = (
                config.get("endpoint")
                or config.get("base_url")
                or os.getenv("OPENAI_BASE_URL")
                or os.getenv("AIHUBMIX_API_URL")
                or LLMFactory.DEFAULT_FALLBACK_BASE_URL
            )
            base_url = ensure_chat_completions_endpoint(base_url_candidate)
            model = config.get("model") or DEFAULT_MODEL
            temperature = config.get("temperature", DEFAULT_TEMPERATURE)
            max_tokens = config.get("max_tokens", DEFAULT_MAX_TOKENS)
            
            return {
                "provider": provider,
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        elif provider == "deepseek":
            # DeepSeek 配置
            api_key = config.get("api_key") or os.getenv("DEEPSEEK_API_KEY")
            base_url = config.get("endpoint") or config.get("base_url") or "https://api.deepseek.com/v1/chat/completions"
            model = config.get("model", "deepseek-chat")
            
            return {
                "provider": "deepseek",
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
                "temperature": config.get("temperature", 0.7),
                "max_tokens": config.get("max_tokens", 1500),
            }
        elif provider == "doubao":
            # 豆包配置
            api_key = config.get("api_key") or os.getenv("DOUBAO_API_KEY")
            base_url = config.get("endpoint") or config.get("base_url") or "https://ark.cn-beijing.volces.com/api/v3"
            model = config.get("model", "doubao-pro-32k")
            
            return {
                "provider": "doubao",
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
                "temperature": config.get("temperature", 0.7),
                "max_tokens": config.get("max_tokens", 2000),
            }
        else:
            # 默认回退逻辑
            api_key = (
                config.get("api_key") or 
                os.getenv("OPENAI_API_KEY") or 
                os.getenv("AIHUBMIX_API_KEY")
            )
            base_url = (
                config.get("endpoint") or 
                config.get("base_url") or 
                os.getenv("OPENAI_BASE_URL") or 
                os.getenv("AIHUBMIX_API_URL") or
                "https://aihubmix.com/v1"
            )
            return {
                "provider": provider,
                "api_key": api_key,
                "base_url": base_url,
                "model": config.get("model", os.getenv("OPENAI_MODEL", "gpt-4o")),
                "temperature": config.get("temperature", 0.7),
                "max_tokens": config.get("max_tokens", 1500),
            }
    
    @staticmethod
    async def call_llm(
        config: Dict[str, Any],
        system_prompt: str,
        user_prompt: str,
        functions: Optional[list] = None,
        context: Optional[Dict[str, Any]] = None,
        return_full_response: bool = False,
    ) -> Union[str, Dict[str, Any]]:
        """
        调用 LLM 模型（使用 raap_llm_sdk，通过 Dapr 获取配置）
        
        Args:
            config: LLM 配置
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            functions: Function calling 定义列表（可选，暂不支持）
            context: 追踪上下文（可选）
            return_full_response: 是否返回完整响应对象（包含 usage, model, provider 等）
            
        Returns:
            LLM 返回的文本，或完整的响应字典
        """
        # 兼容：如果 raap_llm_sdk 不存在，则走 OpenAI 兼容 HTTP 直连（不依赖 build context）
        if not _check_sdk_available():
            import httpx

            llm_config = LLMFactory.get_llm_config(config)
            api_key = llm_config.get("api_key")
            base_url = ensure_chat_completions_endpoint(llm_config.get("base_url") or llm_config.get("endpoint") or "")
            model = llm_config.get("model") or config.get("model") or DEFAULT_MODEL
            temperature = config.get("temperature", llm_config.get("temperature", DEFAULT_TEMPERATURE))
            max_tokens = config.get("max_tokens", llm_config.get("max_tokens", DEFAULT_MAX_TOKENS))

            if not api_key:
                raise RuntimeError("未配置 API Key，无法调用模型")
            if not base_url:
                raise RuntimeError("未配置 base_url，无法调用模型")

            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt or ""},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if functions:
                payload["functions"] = functions

            # 模型执行超时（秒）：默认 30s，可通过环境变量覆盖
            timeout_s = float(os.getenv("LLM_HTTP_TIMEOUT", "30"))
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    resp = await client.post(base_url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.TimeoutException as e:
                # 让上层能稳定识别并展示“超时”，避免 str(e) 为空导致日志不直观
                raise TimeoutError(f"LLM HTTP 调用超时 (timeout={timeout_s}s)") from e
            
            content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            
            if not return_full_response:
                return content
            
            # 组装完整响应
            usage = data.get("usage", {})
            # 直连模式：从配置或环境变量获取 provider，避免返回 "unknown" 导致后续查询失败
            provider_code = llm_config.get("provider") or os.getenv("LLM_PROVIDER", "openai")
            return {
                "content": content,
                "model_code": model,
                "provider_code": provider_code,
                "usage": {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
            }
        
        client = get_llm_client()
        
        # 兼容处理
        llm_config = LLMFactory.get_llm_config(config)
        logger.info(f"[LLMFactory] 调用 LLM，模型: {llm_config['model']}, provider: {llm_config['provider']}")
        
        model_code = config.get("model", os.getenv("OPENAI_MODEL", "gpt-4o"))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        logger.info(f"[LLMFactory] 使用 raap_llm_sdk 调用 LLM，模型: {model_code}")
        
        from raap_llm_sdk import LLMCallContext
        
        llm_context = None
        if context:
            llm_context = LLMCallContext(
                trace_id=context.get("trace_id", ""),
                job_id=context.get("job_id", ""),
                sub_job_id=context.get("sub_job_id"),
                content_id=context.get("content_id"),
                expert_config_code=context.get("expert_config_code"),
            )
        
        response = await client.invoke(
            model_code=model_code,
            messages=messages,
            context=llm_context,
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 1500),
        )
        
        logger.info(
            f"[LLMFactory] LLM 调用成功: "
            f"provider={response.provider_code}, "
            f"tokens={response.usage.total_tokens}, "
            f"latency={response.latency_ms}ms, "
            f"failover={response.failover_attempts}"
        )
        
        if not return_full_response:
            return response.content.strip()
            
        return {
            "content": response.content.strip(),
            "model_code": response.model_code,
            "provider_code": response.provider_code,
            "provider_model": response.provider_model,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "cost": response.cost,
            "currency": "USD",  # SDK 暂未返回 currency，默认使用 USD
        }


# ==================== 直接调用接口（推荐新代码使用） ====================

async def invoke_llm(
    model_code: str,
    messages: List[Dict[str, str]],
    context: Optional[Dict[str, Any]] = None,
    temperature: float = 0.7,
    max_tokens: int = 1500,
    **kwargs
) -> Dict[str, Any]:
    """
    直接调用 LLM（使用 raap_llm_sdk，支持 Failover）
    
    配置通过 Dapr 从 Orchestrator 获取
    
    Args:
        model_code: 统一模型编码（如 gpt-4o, claude-3.5-sonnet）
        messages: 消息列表 [{"role": "user", "content": "..."}]
        context: 追踪上下文（trace_id, job_id, expert_config_code 等）
        temperature: 温度参数
        max_tokens: 最大 token 数
        **kwargs: 其他参数
        
    Returns:
        响应字典，包含 content, usage, cost, latency_ms 等
    """
    if not _check_sdk_available():
        raise RuntimeError("raap_llm_sdk 未安装，invoke_llm 暂不支持（请改用 call_llm 兼容模式）")

    client = get_llm_client()
    
    from raap_llm_sdk import LLMCallContext
    
    llm_context = None
    if context:
        llm_context = LLMCallContext(
            trace_id=context.get("trace_id", ""),
            job_id=context.get("job_id", ""),
            sub_job_id=context.get("sub_job_id"),
            content_id=context.get("content_id"),
            expert_config_code=context.get("expert_config_code"),
            experiment_id=context.get("experiment_id"),
            experiment_group=context.get("experiment_group"),
        )
    
    response = await client.invoke(
        model_code=model_code,
        messages=messages,
        context=llm_context,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )
    
    return {
        "content": response.content,
        "model_code": response.model_code,
        "provider_code": response.provider_code,
        "provider_model": response.provider_model,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
        },
        "latency_ms": response.latency_ms,
        "failover_attempts": response.failover_attempts,
    }
