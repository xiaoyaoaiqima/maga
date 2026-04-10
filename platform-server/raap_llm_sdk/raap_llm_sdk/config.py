"""
配置获取模块

通过 Dapr HTTP 从 Orchestrator 获取 LLM 配置
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal
import httpx
from .models import ProviderConfig, ModelRoute
from .cache import LocalCache
from .exceptions import LLMConfigError

logger = logging.getLogger(__name__)

# 默认 Orchestrator App ID
DEFAULT_ORCHESTRATOR_APP_ID = "raap-service-orchestrator"

# 缓存 TTL（秒）
CONFIG_CACHE_TTL = 300  # 5 分钟


class ConfigProvider:
    """
    配置提供器
    
    从 Orchestrator 通过 Dapr HTTP Invocation 获取 LLM Provider 和 Model Route 配置
    """
    
    def __init__(
        self,
        orchestrator_app_id: str = None,
        cache_ttl: int = CONFIG_CACHE_TTL,
    ):
        """
        初始化配置提供器
        
        Args:
            orchestrator_app_id: Orchestrator 的 Dapr App ID
            cache_ttl: 缓存 TTL（秒）
        """
        self._orchestrator_app_id = orchestrator_app_id or os.getenv(
            "ORCHESTRATOR_APP_ID", DEFAULT_ORCHESTRATOR_APP_ID
        )
        self._cache = LocalCache(default_ttl=cache_ttl)
        self._dapr_http_port = int(os.getenv("DAPR_HTTP_PORT", "3500"))
    
    async def _invoke_http(self, path: str, method: str = "GET", params: Dict[str, Any] = None, json_body: Dict[str, Any] = None) -> Dict[str, Any]:
        url = f"http://localhost:{self._dapr_http_port}/v1.0/invoke/{self._orchestrator_app_id}/method{path}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                m = method.upper()
                headers = {}
                token = os.getenv("INTERNAL_API_TOKEN")
                if token:
                    headers["X-Internal-Token"] = token
                if m == "GET":
                    resp = await client.get(url, params=params, headers=headers)
                elif m == "POST":
                    resp = await client.post(url, params=params, json=json_body, headers=headers)
                elif m == "PUT":
                    resp = await client.put(url, params=params, json=json_body, headers=headers)
                else:
                    raise LLMConfigError(f"不支持的 HTTP 方法: {method}")
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            raise LLMConfigError(f"Dapr HTTP 调用失败: {e}")
    
    async def get_provider_config(self, provider_code: str) -> Optional[ProviderConfig]:
        """
        获取指定 Provider 配置
        
        Args:
            provider_code: Provider 编码
        
        Returns:
            ProviderConfig 或 None
        """
        cache_key = f"provider:{provider_code}"
        
        # 检查缓存
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        # 从 Orchestrator 获取（HTTP）
        try:
            config = await self._fetch_provider_config_http(provider_code)
            if config:
                self._cache.set(cache_key, config)
            return config
        except Exception as e:
            logger.error(f"获取 Provider 配置失败: {e}")
            raise LLMConfigError(f"获取 Provider 配置失败: {e}")
    
    async def _fetch_provider_config_http(self, provider_code: str) -> Optional[ProviderConfig]:
        try:
            result = await self._invoke_http(
                path=f"/api/v1/llm-providers/{provider_code}/internal-config",
                method="GET",
            )
            data = result.get("data", {}) if isinstance(result, dict) else {}
            if not data:
                return None
            default_params = None
            if data.get("default_params"):
                try:
                    default_params = json.loads(data["default_params"])
                except json.JSONDecodeError:
                    default_params = None
            return ProviderConfig(
                provider_code=data.get("provider_code"),
                provider_name=data.get("provider_name"),
                provider_type=data.get("provider_type", "openai_compatible"),
                base_url=data.get("base_url"),
                api_key=data.get("api_key"),
                default_model=data.get("default_model"),
                available_models=data.get("available_models"),
                default_params=default_params,
                timeout=data.get("timeout", 120),
                priority=data.get("priority", 0),
                enabled=data.get("enabled", True),
            )
        except Exception as e:
            raise LLMConfigError(f"HTTP 获取 Provider 配置失败: {e}")
    
    async def get_model_routes(self, model_code: str) -> List[ModelRoute]:
        """
        获取模型的所有路由（按优先级排序）
        
        Args:
            model_code: 统一模型编码
        
        Returns:
            ModelRoute 列表，按优先级降序
        """
        cache_key = f"routes:{model_code}"
        
        # 检查缓存
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        # 从 Orchestrator 获取（HTTP）
        try:
            routes = await self._fetch_model_routes_http(model_code)
            self._cache.set(cache_key, routes)
            return routes
        except Exception as e:
            logger.error(f"获取模型路由失败: {e}")
            raise LLMConfigError(f"获取模型路由失败: {e}")
    
    async def _fetch_model_routes_http(self, model_code: str) -> List[ModelRoute]:
        try:
            result = await self._invoke_http(
                path="/api/v1/llm-providers/routes",
                method="GET",
                # Orchestrator 端接口对 limit 做了校验（<=500）
                params={"model_code": model_code, "enabled": True, "limit": 500},
            )
            payload = result.get("data", {}) if isinstance(result, dict) else {}
            routes_data = payload.get("items", []) if isinstance(payload, dict) else []
            routes: List[ModelRoute] = []
            for r in routes_data:
                features = r.get("features")
                if isinstance(features, str):
                    try:
                        features = json.loads(features)
                    except json.JSONDecodeError:
                        features = None
                routes.append(ModelRoute(
                    model_code=r.get("model_code"),
                    model_name=r.get("model_name"),
                    provider_code=r.get("provider_code"),
                    provider_model=r.get("provider_model"),
                    priority=r.get("priority", 0),
                    enabled=r.get("enabled", True),
                    max_context_length=r.get("max_context_length"),
                    features=features,
                    cost_per_1k_input=Decimal(r.get("cost_per_1k_input", "0")) if r.get("cost_per_1k_input") else None,
                    cost_per_1k_output=Decimal(r.get("cost_per_1k_output", "0")) if r.get("cost_per_1k_output") else None,
                    timeout_seconds=r.get("timeout_seconds"),
                ))
            routes.sort(key=lambda x: x.priority, reverse=True)
            return routes
        except Exception as e:
            raise LLMConfigError(f"HTTP 获取模型路由失败: {e}")
    
    async def get_default_provider(self) -> Optional[ProviderConfig]:
        """
        获取默认（优先级最高）的 Provider 配置
        
        Returns:
            ProviderConfig 或 None
        """
        cache_key = "default_provider"
        
        # 检查缓存
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        try:
            result = await self._invoke_http(
                path="/api/v1/llm-providers",
                method="GET",
                params={"enabled": True, "limit": 1, "skip": 0},
            )
            payload = result.get("data", {}) if isinstance(result, dict) else {}
            providers = payload.get("items") if isinstance(payload, dict) else None
            if not providers:
                return None
            provider_code = providers[0].get("provider_code")
            config = await self.get_provider_config(provider_code)
            if config:
                self._cache.set(cache_key, config)
            return config
        except Exception as e:
            logger.error(f"获取默认 Provider 失败: {e}")
            raise LLMConfigError(f"获取默认 Provider 失败: {e}")
    
    async def report_circuit_breaker_state(
        self,
        provider_code: str,
        state: str,
        failure_count: int = 0,
        last_failure_reason: str = None,
    ):
        try:
            await self._invoke_http(
                path="/api/v1/llm-providers/circuit-breakers/report",
                method="POST",
                json_body={
                    "provider_code": provider_code,
                    "state": state,
                    "failure_count": failure_count,
                    "last_failure_reason": last_failure_reason or "",
                },
            )
        except Exception as e:
            logger.warning(f"熔断状态上报失败: {e}")
    
    def invalidate_cache(self, key: str = None):
        """
        清除缓存
        
        Args:
            key: 特定缓存键，None 清除所有
        """
        if key:
            self._cache.delete(key)
        else:
            self._cache.clear()
