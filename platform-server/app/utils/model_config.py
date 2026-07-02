"""
Model config utilities shared across services.
"""
import os
from typing import Any, Dict, Optional

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1500
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")


def normalize_default_model(model_code: Optional[str]) -> str:
    value = str(model_code or "").strip()
    if not value:
        return DEFAULT_MODEL
    compact = value.lower().replace("_", "-").replace(" ", "-")
    # 生成链路统一走 DeepSeek，避免残留 GPT 路由从历史配置或环境变量穿透。
    if compact.startswith("gpt"):
        return DEFAULT_MODEL
    return value


def normalize_model_config(
    model_config: Any,
    default_temperature: float = DEFAULT_TEMPERATURE,
    default_max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Dict[str, Any]:
    """
    Normalize model_config into a dict with temperature and max_tokens.
    Accepts dict, proto-like objects, or other mapping-like inputs.
    """
    def _extract(cfg: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "temperature": cfg.get("temperature", default_temperature),
            "max_tokens": cfg.get("max_tokens", default_max_tokens),
        }
    
    # 优先处理字典类型
    if isinstance(model_config, dict):
        return _extract(model_config)
    
    # 处理 None 或空值
    if not model_config:
        return {
            "temperature": default_temperature,
            "max_tokens": default_max_tokens,
        }
    
    # 处理有属性的对象（如 proto 对象）
    if hasattr(model_config, "temperature") and not isinstance(model_config, dict):
        return {
            "temperature": getattr(model_config, "temperature", default_temperature),
            "max_tokens": getattr(model_config, "max_tokens", default_max_tokens),
        }
    
    # 尝试转换为字典
    try:
        if hasattr(model_config, "__dict__"):
            return _extract(model_config.__dict__)
        elif hasattr(model_config, "items"):
            return _extract(dict(model_config))
    except (TypeError, ValueError, AttributeError):
        pass
    
    return {
        "temperature": default_temperature,
        "max_tokens": default_max_tokens,
    }


def ensure_chat_completions_endpoint(base_url: Optional[str]) -> Optional[str]:
    """
    Normalize OpenAI-compatible endpoint to end with /v1/chat/completions.
    Avoids double-appending if already present.
    """
    if not base_url:
        return None
    
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1/chat/completions") or normalized.endswith("/chat/completions"):
        return normalized
    # OpenAI-compatible providers usually configure base_url as ".../v1".
    # Keep that form and append only the resource path, not another /v1.
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    
    return f"{normalized}/v1/chat/completions"


def build_llm_config(
    model_code: str,
    model_config: Dict[str, Any],
    provider_env: Optional[str] = None,
    api_key_env: Optional[str] = None,
    base_url_env: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a unified LLM config using request overrides and environment defaults.
    """
    # 生成链路统一走 DeepSeek 默认模型，避免历史环境变量覆盖到 GPT 路由。
    model = normalize_default_model(model_code or os.getenv("DEEPSEEK_MODEL"))
    temperature = model_config.get("temperature", DEFAULT_TEMPERATURE)
    max_tokens = model_config.get("max_tokens", DEFAULT_MAX_TOKENS)
    provider = provider_env or os.getenv("LLM_PROVIDER", "deepseek")
    api_key = api_key_env or os.getenv("OPENAI_API_KEY")
    base_url_raw = base_url_env or os.getenv("OPENAI_BASE_URL") or os.getenv("AIHUBMIX_API_URL")
    base_url = ensure_chat_completions_endpoint(base_url_raw) if base_url_raw else None
    
    config: Dict[str, Any] = {
        "model": model,
        "provider": provider,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if api_key:
        config["api_key"] = api_key
    if base_url:
        config["base_url"] = base_url
        config["endpoint"] = base_url
    
    return config
