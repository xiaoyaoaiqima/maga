"""OpenAI-compatible model client used by MAGA worker content capabilities."""
from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

DEFAULT_CONTENT_MODEL = "deepseek-v3.2"
DEFAULT_BASE_URL = "https://aihubmix.com/v1"


def normalize_content_model(model: str | None) -> str:
    value = str(model or "").strip()
    if not value:
        return DEFAULT_CONTENT_MODEL
    compact = value.lower().replace("_", "-").replace(" ", "-")
    # worker 生成链路禁止继续使用历史 GPT 配置，统一回落 DeepSeek。
    if compact.startswith("gpt"):
        return DEFAULT_CONTENT_MODEL
    return value


def runtime_base_url() -> str:
    return (
        os.environ.get("MAGA_WORKER_MODEL_BASE_URL")
        or os.environ.get("HERMES_MODEL_BASE_URL")
        or os.environ.get("AIHUBMIX_BASE_URL")
        or os.environ.get("AIHUBMIX_API_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("ARK_BASE_URL")
        or DEFAULT_BASE_URL
    )


def runtime_api_key() -> str | None:
    return (
        os.environ.get("MAGA_WORKER_MODEL_API_KEY")
        or os.environ.get("HERMES_MODEL_API_KEY")
        or os.environ.get("AIHUBMIX_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ARK_API_KEY")
    )


def default_content_model() -> str:
    return normalize_content_model(os.environ.get("MAGA_WORKER_CONTENT_MODEL"))


def openai_client_kwargs(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float | int | str | None = None,
) -> dict[str, Any]:
    resolved_base_url = base_url or runtime_base_url()
    kwargs: dict[str, Any] = {
        "api_key": api_key or runtime_api_key(),
        "base_url": resolved_base_url,
    }
    timeout_raw = timeout if timeout is not None else os.environ.get("MAGA_WORKER_MODEL_TIMEOUT", "90")
    try:
        kwargs["timeout"] = float(timeout_raw)
    except (TypeError, ValueError):
        kwargs["timeout"] = 90.0
    if "api.lyston.qzz.io" in resolved_base_url.lower():
        kwargs["default_headers"] = {"User-Agent": "curl/8.7.1"}
    return kwargs


def _client(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float | int | str | None = None,
) -> OpenAI:
    return OpenAI(**openai_client_kwargs(api_key=api_key, base_url=base_url, timeout=timeout))


def call_model(
    model: str,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float | int | str | None = None,
    max_retries: int | str | None = None,
) -> str:
    model = normalize_content_model(model)
    last_err: Exception | None = None
    try:
        retry_count = int(max_retries) if max_retries is not None else 3
    except (TypeError, ValueError):
        retry_count = 3
    retry_count = max(1, min(retry_count, 3))
    for _ in range(retry_count):
        try:
            request: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            }
            if max_tokens:
                request["max_tokens"] = max_tokens
            resp = _client(api_key=api_key, base_url=base_url, timeout=timeout).chat.completions.create(**request)
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - provider clients raise heterogeneous exceptions
            last_err = exc
    raise RuntimeError(f"call_model failed after {retry_count} retries: {last_err}") from last_err
