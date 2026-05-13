"""Shared defaults for MAGA content-agent executor routing."""
from __future__ import annotations

DEFAULT_EXECUTOR_CODE = "hermes_maga_worker"
LEGACY_XHS_WRITER_EXECUTOR_CODE = "hermes_xhs_writer"
MAGA_WORKER_PROFILE_NAME = "maga-worker"
MAGA_WORKER_DISPLAY_NAME = "Hermes MAGA worker"
MAGA_WORKER_INVOKE_URL = "mock://maga-worker/invoke"
# MAGA only owns optional model overrides. Leave defaults empty so the worker
# or provider can choose an available model unless the operator explicitly sets one.
MAGA_WORKER_DEFAULT_GE_MODEL: str | None = None
MAGA_WORKER_DEFAULT_AE_MODEL: str | None = None
LEGACY_XHS_WRITER_DISPLAY_NAME = "Hermes xhs-writer (legacy alias)"
MAGA_WORKER_MODULE_CAPABILITIES = ["asset-steward", "xhs-writer", "feedback-trainer"]

XHS_CAPABILITY_SPECS = [
    {"capability": "xhs.interpret_brief", "schema_version": "1"},
    {"capability": "xhs.run_ae_analysis", "schema_version": "1"},
    {"capability": "xhs.generate_draft", "schema_version": "1"},
    {"capability": "xhs.run_ae_review", "schema_version": "1"},
    {"capability": "xhs.rewrite_draft", "schema_version": "1"},
]

ASSET_CAPABILITY_SPECS = [
    {"capability": "asset.query", "schema_version": "1"},
    {"capability": "asset.create_change_request", "schema_version": "1"},
    {"capability": "asset.create_change_proposal", "schema_version": "1"},
    {"capability": "asset.apply_change_proposal", "schema_version": "1"},
    {"capability": "asset.import", "schema_version": "1"},
    {"capability": "asset.smoke_generation", "schema_version": "1"},
]

FEEDBACK_CAPABILITY_SPECS = [
    {"capability": "feedback.collect", "schema_version": "1"},
    {"capability": "feedback.analyze", "schema_version": "1"},
    {"capability": "feedback.summarize_lessons", "schema_version": "1"},
    {"capability": "feedback.propose_asset_updates", "schema_version": "1"},
    {"capability": "feedback.create_calibration_records", "schema_version": "1"},
    {"capability": "feedback.compare_ai_human_scores", "schema_version": "1"},
    {"capability": "feedback.trigger_smoke_generation", "schema_version": "1"},
]

MAGA_WORKER_MANIFEST_CAPABILITY_SPECS = [
    *XHS_CAPABILITY_SPECS,
    *ASSET_CAPABILITY_SPECS,
    *FEEDBACK_CAPABILITY_SPECS,
]

# ExecutorRegistry.supported_capabilities_json describes the protocol calls this
# HTTP content-agent executor can receive today. The wider three-module
# capability map lives in the maga-worker profile manifest.
MAGA_WORKER_SUPPORTED_CAPABILITY_SPECS = [
    *XHS_CAPABILITY_SPECS,
    {"capability": "asset.import", "schema_version": "1"},
]


def normalize_executor_code(executor_code: str | None) -> str:
    """Treat empty/whitespace executor form input as the MAGA worker default."""
    normalized = (executor_code or "").strip()
    return normalized or DEFAULT_EXECUTOR_CODE
