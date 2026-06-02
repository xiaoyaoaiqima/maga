"""Tests for MAGA worker generic model runtime provider configuration."""

from maga_worker import llm_runtime


def test_llm_runtime_prefers_maga_worker_provider_env(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_MODEL_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("MAGA_WORKER_MODEL_API_KEY", "runtime-key")
    monkeypatch.setenv("MAGA_WORKER_CONTENT_MODEL", "runtime-content")

    assert llm_runtime.default_content_model() == "runtime-content"
    assert llm_runtime.runtime_api_key() == "runtime-key"
    assert llm_runtime.runtime_base_url() == "https://provider.example/v1"


def test_llm_runtime_uses_openai_compatible_fallbacks(monkeypatch):
    monkeypatch.delenv("MAGA_WORKER_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MAGA_WORKER_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.lyston.qzz.io/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "custom-key")

    assert llm_runtime.runtime_api_key() == "custom-key"
    assert llm_runtime.runtime_base_url() == "https://api.lyston.qzz.io/v1"


def test_llm_runtime_adds_user_agent_for_lyston_proxy(monkeypatch):
    monkeypatch.delenv("MAGA_WORKER_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MAGA_WORKER_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.lyston.qzz.io/v1")

    kwargs = llm_runtime.openai_client_kwargs()

    assert kwargs["default_headers"] == {"User-Agent": "curl/8.7.1"}
