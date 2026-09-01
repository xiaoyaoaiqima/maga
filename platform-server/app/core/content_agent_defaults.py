"""Shared defaults for MAGA content-agent executor routing."""
from __future__ import annotations

DEFAULT_EXECUTOR_CODE = "maga_direct_llm_executor"
DEFAULT_CONTENT_GENERATION_SYSTEM_PROMPT = "你是中文小红书内容生成器，严格按用户提示输出，不解释过程。"
DIRECT_LLM_EXECUTOR_DISPLAY_NAME = "MAGA direct LLM executor"
DIRECT_LLM_EXECUTOR_INVOKE_URL = "llm://direct/content"
# Leave optional model overrides empty so the configured provider can choose an
# available model unless the operator explicitly sets one.
DIRECT_LLM_DEFAULT_GE_MODEL: str | None = None
DIRECT_LLM_DEFAULT_AE_MODEL: str | None = None

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

CONTENT_AGENT_CAPABILITY_SPECS = [
    *ASSET_CAPABILITY_SPECS,
    *CONTENT_CAPABILITY_SPECS,
]

# The in-process direct LLM executor only performs content generation and rewrite.
DIRECT_LLM_SUPPORTED_CAPABILITY_SPECS = [
    *CONTENT_CAPABILITY_SPECS,
]


def normalize_executor_code(executor_code: str | None) -> str:
    """Treat empty/whitespace executor form input as the direct LLM default."""
    normalized = (executor_code or "").strip()
    return normalized or DEFAULT_EXECUTOR_CODE
