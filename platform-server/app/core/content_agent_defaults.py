"""Shared defaults for MAGA content-agent executor routing."""
from __future__ import annotations

DEFAULT_EXECUTOR_CODE = "maga_direct_llm_executor"
MAGA_WORKER_PROFILE_NAME = "maga-worker"
MAGA_WORKER_DISPLAY_NAME = "MAGA direct LLM executor"
MAGA_WORKER_INVOKE_URL = "llm://direct/content"
# MAGA only owns optional model overrides. Leave defaults empty so the worker
# or provider can choose an available model unless the operator explicitly sets one.
MAGA_WORKER_DEFAULT_GE_MODEL: str | None = None
MAGA_WORKER_DEFAULT_AE_MODEL: str | None = None
MAGA_WORKER_MODULE_CAPABILITIES = ["asset-steward", "content-generator"]

ASSET_CAPABILITY_SPECS = [
    {"capability": "asset.query", "schema_version": "1"},
    {"capability": "asset.create_change_request", "schema_version": "1"},
    {"capability": "asset.create_change_proposal", "schema_version": "1"},
    {"capability": "asset.apply_change_proposal", "schema_version": "1"},
    {"capability": "asset.import", "schema_version": "1"},
    {"capability": "asset.smoke_generation", "schema_version": "1"},
]

CONTENT_CAPABILITY_SPECS = [
    {"capability": "content.generate", "schema_version": "1"},
    {"capability": "content.rewrite", "schema_version": "1"},
]

MAGA_WORKER_MANIFEST_CAPABILITY_SPECS = [
    *ASSET_CAPABILITY_SPECS,
    *CONTENT_CAPABILITY_SPECS,
]

# ExecutorRegistry.supported_capabilities_json describes the protocol calls this
# HTTP content-agent executor can receive today.
MAGA_WORKER_SUPPORTED_CAPABILITY_SPECS = [
    {"capability": "asset.import", "schema_version": "1"},
    *CONTENT_CAPABILITY_SPECS,
]


def normalize_executor_code(executor_code: str | None) -> str:
    """Treat empty/whitespace executor form input as the MAGA worker default."""
    normalized = (executor_code or "").strip()
    return normalized or DEFAULT_EXECUTOR_CODE
