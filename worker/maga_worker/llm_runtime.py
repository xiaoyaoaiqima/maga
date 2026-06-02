"""OpenAI-compatible model client used by MAGA worker content capabilities."""
from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

DEFAULT_CONTENT_MODEL = "deepseek-v3-2-251201"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"


def runtime_base_url() -> str:
    return (
        os.environ.get("MAGA_WORKER_MODEL_BASE_URL")
        or os.environ.get("HERMES_MODEL_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("ARK_BASE_URL")
        or DEFAULT_BASE_URL
    )


def runtime_api_key() -> str | None:
    return (
        os.environ.get("MAGA_WORKER_MODEL_API_KEY")
        or os.environ.get("HERMES_MODEL_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ARK_API_KEY")
    )


def default_content_model() -> str:
    return os.environ.get("MAGA_WORKER_CONTENT_MODEL") or DEFAULT_CONTENT_MODEL


def openai_client_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "api_key": runtime_api_key(),
        "base_url": runtime_base_url(),
    }
    timeout_raw = os.environ.get("MAGA_WORKER_MODEL_TIMEOUT", "90")
    try:
        kwargs["timeout"] = float(timeout_raw)
    except ValueError:
        kwargs["timeout"] = 90.0
    if "api.lyston.qzz.io" in runtime_base_url().lower():
        kwargs["default_headers"] = {"User-Agent": "curl/8.7.1"}
    return kwargs


def _client() -> OpenAI:
    return OpenAI(**openai_client_kwargs())


def call_model(model: str, system: str, user: str, temperature: float = 0.7, max_tokens: int | None = None) -> str:
    last_err: Exception | None = None
    for _ in range(3):
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
            resp = _client().chat.completions.create(**request)
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - provider clients raise heterogeneous exceptions
            last_err = exc
    raise RuntimeError(f"call_model failed after 3 retries: {last_err}") from last_err
