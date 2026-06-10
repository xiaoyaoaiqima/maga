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


def test_llm_runtime_prefers_aihubmix_before_openai_fallback(monkeypatch):
    monkeypatch.delenv("MAGA_WORKER_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MAGA_WORKER_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("AIHUBMIX_BASE_URL", "https://aihubmix.example/v1")
    monkeypatch.setenv("AIHUBMIX_API_KEY", "aihubmix-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    assert llm_runtime.runtime_api_key() == "aihubmix-key"
    assert llm_runtime.runtime_base_url() == "https://aihubmix.example/v1"


def test_llm_runtime_defaults_to_aihubmix(monkeypatch):
    for key in [
        "MAGA_WORKER_MODEL_BASE_URL",
        "HERMES_MODEL_BASE_URL",
        "AIHUBMIX_BASE_URL",
        "AIHUBMIX_API_URL",
        "OPENAI_BASE_URL",
        "ARK_BASE_URL",
    ]:
        monkeypatch.delenv(key, raising=False)

    assert llm_runtime.runtime_base_url() == "https://aihubmix.com/v1"


def test_llm_runtime_adds_user_agent_for_lyston_proxy(monkeypatch):
    monkeypatch.delenv("MAGA_WORKER_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MAGA_WORKER_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.lyston.qzz.io/v1")

    kwargs = llm_runtime.openai_client_kwargs()

    assert kwargs["default_headers"] == {"User-Agent": "curl/8.7.1"}


def test_llm_runtime_accepts_explicit_provider_config(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_MODEL_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("MAGA_WORKER_MODEL_API_KEY", "env-key")

    kwargs = llm_runtime.openai_client_kwargs(
        base_url="https://db-provider.example/v1",
        api_key="db-key",
    )

    assert kwargs["base_url"] == "https://db-provider.example/v1"
    assert kwargs["api_key"] == "db-key"


def test_llm_runtime_accepts_explicit_timeout(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_MODEL_TIMEOUT", "90")

    kwargs = llm_runtime.openai_client_kwargs(timeout=12)

    assert kwargs["timeout"] == 12.0
