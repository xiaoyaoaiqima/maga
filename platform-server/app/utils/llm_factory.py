"""
LLM Factory
LLM 工厂类，负责创建和管理不同的 LLM 实例

已改造为使用 raap_llm_sdk：
- 通过 Dapr gRPC 从 Orchestrator 动态获取 Provider 配置
- 支持自动 Failover
- 支持熔断机制
- 移除硬编码的 API Key
- 添加 Provider 配置缓存（TTL 5 分钟）
"""
import os
import time
from typing import Optional, Dict, Any, List
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.logger import get_logger
from app.utils.model_config import normalize_default_model

logger = get_logger()

# Provider 配置缓存 TTL（秒）
PROVIDER_CONFIG_CACHE_TTL = 300

# LLM SDK 客户端（延迟初始化）
_llm_client = None
_sdk_available = None


def _check_sdk_available() -> bool:
    global _sdk_available
    if _sdk_available is None:
        try:
            import importlib
            importlib.import_module("raap_llm_sdk")
            _sdk_available = True
        except Exception:
            _sdk_available = False
    return _sdk_available


def get_llm_client():
    global _llm_client
    if _llm_client is None:
        if not _check_sdk_available():
            return None
        from raap_llm_sdk import LLMClient  # type: ignore
        _llm_client = LLMClient(
            orchestrator_app_id=os.getenv("ORCHESTRATOR_APP_ID", "raap-service-orchestrator"),
            enable_failover=True,
            enable_circuit_breaker=True,
            enable_trace_report=False,  # 统一由 Orchestrator 记录专家级 Trace，隐藏底层 llm_call
        )
    return _llm_client


class LLMFactory:
    """LLM 工厂类"""

    _instances: Dict[str, BaseChatModel] = {}
    _config_cache: Dict[str, Dict[str, Any]] = {}  # 格式: {cache_key: {"config": {...}, "timestamp": ...}}

    @classmethod
    def _get_config_from_cache(cls, cache_key: str) -> Optional[Dict[str, Any]]:
        """从缓存获取配置，如果未过期"""
        if cache_key not in cls._config_cache:
            return None

        cached_data = cls._config_cache[cache_key]
        timestamp = cached_data.get("timestamp", 0)
        config = cached_data.get("config")

        # 检查缓存是否过期
        if time.time() - timestamp > PROVIDER_CONFIG_CACHE_TTL:
            logger.debug(f"Provider 配置缓存已过期: {cache_key}")
            del cls._config_cache[cache_key]
            return None

        logger.debug(f"使用缓存的 Provider 配置: {cache_key}")
        return config

    @classmethod
    def _save_config_to_cache(cls, cache_key: str, config: Dict[str, Any]) -> None:
        """保存配置到缓存"""
        cls._config_cache[cache_key] = {
            "config": config,
            "timestamp": time.time()
        }
        logger.debug(f"Provider 配置已缓存: {cache_key}, TTL={PROVIDER_CONFIG_CACHE_TTL}s")

    @classmethod
    async def get_provider_config(cls, provider_code: str = None) -> Optional[Dict[str, Any]]:
        orchestrator_app_id = os.getenv("ORCHESTRATOR_APP_ID", "raap-service-orchestrator")
        dapr_http_port = int(os.getenv("DAPR_HTTP_PORT", "3500"))

        # 确定缓存键
        cache_key = f"provider:{provider_code}" if provider_code else "provider:auto_routing"

        # 尝试从缓存获取
        cached_config = cls._get_config_from_cache(cache_key)
        if cached_config is not None:
            return cached_config

        try:
            async def invoke_orchestrator(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
                import httpx  # type: ignore
                url = f"http://localhost:{dapr_http_port}/v1.0/invoke/{orchestrator_app_id}/method{path}"
                headers: Dict[str, str] = {}
                token = os.getenv("INTERNAL_API_TOKEN")
                if token:
                    headers["X-Internal-Token"] = token
                # 增加超时时间到 30 秒，以应对高并发场景
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url, params=params, headers=headers)
                    resp.raise_for_status()
                    return resp.json()
            def _fallback(provider_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
                prov = (provider_hint or "").lower() if provider_hint else None
                api_key = (
                    os.getenv("AIHUBMIX_API_KEY")
                    or os.getenv("OPENAI_API_KEY")
                    or os.getenv("DEEPSEEK_API_KEY")
                    or os.getenv("VOLCENGINE_API_KEY")
                )
                if not api_key:
                    return None
                if prov in (None, "", "aihubmix", "openai"):
                    base_url = os.getenv("AIHUBMIX_BASE_URL") or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1"
                    default_model = normalize_default_model(os.getenv("DEEPSEEK_MODEL"))
                    return {
                        "provider_code": prov or "aihubmix",
                        "base_url": base_url,
                        "api_key": api_key,
                        "default_model": default_model,
                        "timeout": 120,
                        "default_params": {},
                    }
                if prov == "deepseek":
                    base_url = os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com/v1"
                    default_model = normalize_default_model(os.getenv("DEEPSEEK_MODEL"))
                    return {
                        "provider_code": "deepseek",
                        "base_url": base_url,
                        "api_key": api_key,
                        "default_model": default_model,
                        "timeout": 120,
                        "default_params": {},
                    }
                if prov in ("volcengine", "doubao"):
                    base_url = os.getenv("VOLCENGINE_API_BASE") or "https://api.volcengine.com"
                    default_model = os.getenv("VOLCENGINE_MODEL") or "doubao-pro-32k"
                    return {
                        "provider_code": "volcengine",
                        "base_url": base_url,
                        "api_key": api_key,
                        "default_model": default_model,
                        "timeout": 120,
                        "default_params": {},
                    }
                return {
                    "provider_code": prov or "aihubmix",
                    "base_url": os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1",
                    "api_key": api_key,
                    "default_model": normalize_default_model(os.getenv("DEEPSEEK_MODEL")),
                    "timeout": 120,
                    "default_params": {},
                }
            if provider_code:
                data = await invoke_orchestrator(f"/api/v1/llm-providers/{provider_code}/internal-config")
                rd = data.get("data") or {}
                api_key = rd.get("api_key") or os.getenv("OPENAI_API_KEY") or os.getenv("AIHUBMIX_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("VOLCENGINE_API_KEY")
                cfg = {
                    "provider_code": rd.get("provider_code") or provider_code,
                    "base_url": rd.get("base_url"),
                    "api_key": api_key,
                    "default_model": rd.get("default_model"),
                    "timeout": rd.get("timeout") or 120,
                    "default_params": rd.get("default_params") or {},
                }
                if not cfg.get("base_url") or not cfg.get("default_model"):
                    fb = _fallback(provider_code)
                    if fb:
                        cls._save_config_to_cache(cache_key, fb)
                        return fb
                # 保存到缓存
                cls._save_config_to_cache(cache_key, cfg)
                return cfg
            else:
                lst = await invoke_orchestrator("/api/v1/llm-providers", {"enabled": True, "limit": 100})
                items = (lst.get("data", {}).get("items") or [])
                if not items:
                    fb = _fallback(None)
                    if fb:
                        cls._save_config_to_cache(cache_key, fb)
                        return fb
                    return None
                items.sort(key=lambda x: x.get("priority", 0), reverse=True)
                best = items[0]
                internal = await invoke_orchestrator(f"/api/v1/llm-providers/{best.get('provider_code')}/internal-config")
                rd = internal.get("data") or {}
                api_key = rd.get("api_key") or os.getenv("OPENAI_API_KEY") or os.getenv("AIHUBMIX_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("VOLCENGINE_API_KEY")
                cfg = {
                    "provider_code": rd.get("provider_code") or best.get("provider_code"),
                    "base_url": rd.get("base_url") or best.get("base_url"),
                    "api_key": api_key,
                    "default_model": rd.get("default_model") or best.get("default_model"),
                    "timeout": (rd.get("timeout") or best.get("timeout")) or 120,
                    "default_params": rd.get("default_params") or best.get("default_params") or {},
                }
                if not cfg.get("base_url") or not cfg.get("default_model"):
                    fb = _fallback(cfg.get("provider_code"))
                    if fb:
                        cls._save_config_to_cache(cache_key, fb)
                        return fb
                # 保存到缓存
                cls._save_config_to_cache(cache_key, cfg)
                return cfg
        except Exception as e:
            logger.error(f"获取 Provider 配置失败（HTTP）: {e}")
            fb = None
            try:
                fb = _fallback(None)
            except Exception:
                fb = None
            return fb
    
    @classmethod
    async def create_llm_async(
        cls,
        provider_code: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: Optional[float] = None,
        timeout: int = 120,
        **kwargs
    ) -> BaseChatModel:
        config = await cls.get_provider_config(provider_code)
        if not config:
            raise ValueError("无法获取 LLM Provider 配置")
        
        return cls._create_llm_from_config(
            config=config,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            timeout=timeout,
            **kwargs
        )
    
    @classmethod
    def create_llm(
        cls,
        provider: str = "aihubmix",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: Optional[float] = None,
        base_url: Optional[str] = None,
        use_cache: bool = True,
        **kwargs
    ) -> BaseChatModel:
        """
        同步创建 LLM 实例（兼容旧接口）
        
        注意：此方法为兼容旧代码保留，新代码建议使用 create_llm_async
        
        由于 gRPC 调用需要异步，此方法会抛出警告并使用传入的参数
        """
        logger.warning(
            "create_llm() 是同步方法，无法通过 gRPC 获取配置，"
            "请使用 create_llm_async() 或传入完整配置"
        )
        
        cache_key = f"{provider}_{model}_{temperature}_{max_tokens}_{base_url}"
        
        # 如果禁用缓存，则清空缓存并跳过复用
        if not use_cache:
            cls.clear_cache()
        elif cache_key in cls._instances:
            logger.debug(f"使用缓存的 LLM 实例: {cache_key}")
            return cls._instances[cache_key]
        
        # 必须提供 api_key 和 base_url
        if not api_key:
            api_key = os.getenv("AIHUBMIX_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "同步模式下必须提供 api_key 或设置 AIHUBMIX_API_KEY/OPENAI_API_KEY 环境变量，"
                    "建议使用 create_llm_async() 通过 gRPC 获取配置"
                )
        
        if not base_url:
            base_url = os.getenv("AIHUBMIX_BASE_URL", "https://aihubmix.com/v1")
        
        config = {
            "provider_code": provider,
            "base_url": base_url,
            "api_key": api_key,
            "default_model": normalize_default_model(model or os.getenv("DEEPSEEK_MODEL")),
        }
        
        llm = cls._create_llm_from_config(
            config=config,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            **kwargs
        )
        
        # 缓存实例（仅当允许缓存时）
        if use_cache:
            cls._instances[cache_key] = llm
        logger.info(f"创建新的 LLM 实例: {provider}/{model}")
        
        return llm
    
    @classmethod
    def _create_llm_from_config(
        cls,
        config: Dict[str, Any],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: Optional[float] = None,
        timeout: int = 120,
        **kwargs
    ) -> BaseChatModel:
        """从配置创建 LangChain ChatOpenAI 实例"""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError("请安装 langchain-openai: pip install langchain-openai")
        
        model_name = normalize_default_model(model or config.get("default_model"))
        api_key = config.get("api_key")
        base_url = config.get("base_url")
        
        if not api_key:
            raise ValueError("API Key 未配置")
        
        llm_kwargs = {
            "model": model_name,
            "openai_api_key": api_key,
            "openai_api_base": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        
        if top_p is not None:
            llm_kwargs["top_p"] = top_p
        
        # 添加其他参数
        llm_kwargs.update(kwargs)
        
        logger.debug(
            f"LLM 配置: provider={config.get('provider_code')}, "
            f"model={model_name}, base_url={base_url}, timeout={timeout}s"
        )
        
        return ChatOpenAI(**llm_kwargs)
    
    @classmethod
    def clear_cache(cls):
        """清除缓存的 LLM 实例"""
        cls._instances.clear()
        cls._config_cache.clear()
        logger.info("已清除所有缓存的 LLM 实例")


async def get_llm(
    provider: str = "aihubmix",
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 实例（便捷函数，异步版本）
    
    Args:
        provider: LLM 提供商（可映射到 provider_code）
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大 token 数
        **kwargs: 其他参数
        
    Returns:
        LangChain ChatOpenAI 实例
    """
    # 尝试映射 provider 到 provider_code
    provider_mapping = {
        "gemini": "aihubmix",  # Gemini 通过 aihubmix 代理
        "openai": "aihubmix",
        "aihubmix": "aihubmix",
        "deepseek": "deepseek",
        "doubao": "volcengine",
    }
    provider_code = provider_mapping.get(provider, provider)
    
    return await LLMFactory.create_llm_async(
        provider_code=provider_code,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )


# ==================== 直接调用接口（集成 raap_llm_sdk，使用 gRPC 获取配置） ====================

def _normalize_messages(messages: List[Any]) -> List[Dict[str, str]]:
    """将 LangChain Message 或原始字典统一为 role/content 结构"""
    normalized: List[Dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role") or "user"
            content = msg.get("content") or ""
        else:
            role = getattr(msg, "role", None) or getattr(msg, "type", None) or "user"
            content = getattr(msg, "content", "") or ""
        normalized.append({"role": role, "content": content})
    return normalized


async def invoke_llm(
    model_code: str,
    messages: List[Dict[str, str]],
    context: Optional[Dict[str, Any]] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs
) -> Dict[str, Any]:
    """
    直接调用 LLM（使用 raap_llm_sdk，支持 Failover）
    
    配置通过 Dapr gRPC 从 Orchestrator 获取
    """
    client = get_llm_client()
    if not client:
        raise RuntimeError("raap_llm_sdk 未安装或初始化失败")
    
    from raap_llm_sdk import LLMCallContext
    
    llm_context = None
    if context:
        llm_context = LLMCallContext(
            trace_id=context.get("trace_id", "") or "",
            job_id=context.get("job_id", "") or "",
            sub_job_id=context.get("sub_job_id"),
            content_id=context.get("content_id"),
            expert_config_code=context.get("expert_config_code"),
            experiment_id=context.get("experiment_id"),
            experiment_group=context.get("experiment_group"),
        )
    
    normalized_messages = _normalize_messages(messages)
    
    model_code = normalize_default_model(model_code)

    response = await client.invoke(
        model_code=model_code,
        messages=normalized_messages,
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
        "cost": {
            "input_cost": float(response.cost.input_cost),
            "output_cost": float(response.cost.output_cost),
            "total_cost": float(response.cost.total_cost),
        },
        "latency_ms": response.latency_ms,
        "failover_attempts": response.failover_attempts,
        "raw_response": response.raw_response,
    }


async def invoke_llm_messages(
    model_code: str,
    messages: List[Any],
    context: Optional[Dict[str, Any]] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs
) -> Dict[str, Any]:
    """
    便捷方法：接受 LangChain Message 或字典消息列表，统一走 raap_llm_sdk 调用。
    """
    normalized_messages = _normalize_messages(messages)
    return await invoke_llm(
        model_code=model_code,
        messages=normalized_messages,
        context=context,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
