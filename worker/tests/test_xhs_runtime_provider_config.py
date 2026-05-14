"""Tests for xhs_runtime provider configuration."""
from __future__ import annotations

from maga_worker import xhs_runtime


def test_runtime_provider_config_prefers_explicit_openai_compatible_env(monkeypatch):
    monkeypatch.setenv("XHS_RUNTIME_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("XHS_RUNTIME_API_KEY", "runtime-key")
    monkeypatch.setenv("XHS_RUNTIME_MODEL_GE", "runtime-ge")
    monkeypatch.setenv("XHS_RUNTIME_MODEL_AE", "runtime-ae")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_API_KEY", raising=False)

    assert xhs_runtime.model_ge() == "runtime-ge"
    assert xhs_runtime.model_ae() == "runtime-ae"
    assert xhs_runtime.runtime_api_key() == "runtime-key"
    assert xhs_runtime.runtime_base_url() == "https://provider.example/v1"


def test_runtime_provider_config_can_use_hermes_model_base_url_with_custom_key(monkeypatch):
    monkeypatch.delenv("XHS_RUNTIME_BASE_URL", raising=False)
    monkeypatch.delenv("XHS_RUNTIME_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("CUSTOM_API_KEY", "custom-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("HERMES_MODEL_BASE_URL", "https://api.lyston.qzz.io/v1")

    assert xhs_runtime.runtime_api_key() == "custom-key"
    assert xhs_runtime.runtime_base_url() == "https://api.lyston.qzz.io/v1"


def test_openai_client_kwargs_include_lyston_gateway_header(monkeypatch):
    monkeypatch.setenv("HERMES_MODEL_BASE_URL", "https://api.lyston.qzz.io/v1")
    monkeypatch.setenv("CUSTOM_API_KEY", "custom-key")
    monkeypatch.delenv("XHS_RUNTIME_BASE_URL", raising=False)
    monkeypatch.delenv("XHS_RUNTIME_API_KEY", raising=False)

    kwargs = xhs_runtime.openai_client_kwargs()

    assert kwargs["api_key"] == "custom-key"
    assert kwargs["base_url"] == "https://api.lyston.qzz.io/v1"
    assert kwargs["timeout"] == 90.0
    assert kwargs["default_headers"] == {"User-Agent": "curl/8.7.1"}
