from typing import Any, Dict, Optional
import httpx
from app.core.config import settings

_dapr_http_client: Optional[httpx.AsyncClient] = None


def get_dapr_http_client() -> httpx.AsyncClient:
    """Get a shared AsyncClient for Dapr service invocation."""
    global _dapr_http_client
    if _dapr_http_client is None:
        limits = httpx.Limits(
            max_connections=settings.DAPR_HTTP_MAX_CONNECTIONS,
            max_keepalive_connections=settings.DAPR_HTTP_MAX_KEEPALIVE_CONNECTIONS,
            keepalive_expiry=settings.DAPR_HTTP_KEEPALIVE_EXPIRY,
        )
        _dapr_http_client = httpx.AsyncClient(
            follow_redirects=True,
            limits=limits,
        )
    return _dapr_http_client


async def close_dapr_http_client() -> None:
    """Close the shared Dapr AsyncClient on shutdown."""
    global _dapr_http_client
    if _dapr_http_client is not None:
        await _dapr_http_client.aclose()
        _dapr_http_client = None


async def invoke_method(
    app_id: str,
    method_name: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    method: str = "POST",
) -> Dict[str, Any]:
    """
    通过 Dapr 调用其他服务的方法

    Args:
        app_id: 目标服务 ID，如 "maga-backend"
        method_name: API 方法路径，如 "api/v1/content-strategies/123/combinations"
        payload: POST 请求的 JSON body
        timeout: 超时时间（秒）
        headers: 请求头
        params: GET 请求的查询参数
        method: HTTP 方法，"POST" 或 "GET"

    Returns:
        解析后的 JSON 响应
    """
    url = f"http://localhost:{settings.DAPR_HTTP_PORT}/v1.0/invoke/{app_id}/method/{method_name}"
    client = get_dapr_http_client()
    request_kwargs = {"headers": headers, "params": params, "timeout": timeout}

    if method.upper() == "GET":
        resp = await client.get(url, **request_kwargs)
    else:
        resp = await client.post(url, json=payload, **request_kwargs)

    resp.raise_for_status()
    t = resp.text
    try:
        i = t.find("{")
        j = t.rfind("}")
        raw = t[i:j+1] if (i >= 0 and j >= i) else t
        return __import__("json").loads(raw)
    except Exception:
        return {"raw": t}
