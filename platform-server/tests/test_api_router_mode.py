"""Tests for MAGA clean API routing mode."""

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_ROOT))

from app.api.v1.router import create_api_router


def _route_paths(app_mode: str) -> set[str]:
    return {getattr(route, "path", "") for route in create_api_router(app_mode).routes}


def _ordered_route_paths(app_mode: str) -> list[str]:
    return [
        getattr(route, "path", "")
        for route in create_api_router(app_mode).routes
        if "GET" in getattr(route, "methods", set())
    ]


def test_clean_mode_exposes_maga_workbench_routes_only():
    paths = _route_paths("clean")

    assert "/auth/login" in paths
    assert "/auth/userinfo" in paths
    assert "/health" in paths
    assert "/health/detailed" in paths
    assert "/content-agent/batches/start" in paths
    assert "/content-agent/comment-batches/start" in paths
    assert "/content-agent/ppl-runs/profiles" in paths
    assert "/content-agent/ppl-runs/start" in paths
    assert "/content-agent/prompt-debug/run" in paths
    assert "/content-agent/experts" in paths
    assert "/assets/generation-options" in paths
    assert "/assets/content-generation-keywords" in paths
    assert "/llm-providers" in paths
    assert "/llm-providers/routes" in paths
    assert "/system/users" in paths
    assert "/system/roles/list/all" in paths

    legacy_prefixes = (
        "/jobs",
        "/job-variants",
        "/job-create",
        "/expert-tasks",
        "/rlhf",
        "/ab-tests",
        "/plugins",
        "/plugin-contexts",
        "/dashboard",
        "/traces",
        "/critic-scores",
        "/calibration-records",
        "/calibration-tasks",
        "/__internal/critic",
        "/__internal/generation",
    )
    for path in paths:
        assert not path.startswith(legacy_prefixes), path


def test_clean_mode_system_static_routes_precede_dynamic_detail_routes():
    paths = _ordered_route_paths("clean")

    # FastAPI 按注册顺序匹配路由，list/all 必须排在 /{id} 前，避免被当成详情 ID。
    assert paths.index("/system/users/list/all") < paths.index("/system/users/{user_id}")
    assert paths.index("/system/roles/list/all") < paths.index("/system/roles/{role_id}")


def test_full_mode_keeps_legacy_routes_available():
    paths = _route_paths("full")

    assert "/content-agent/batches/start" in paths
    assert "/content-agent/ppl-runs/start" in paths
    assert "/content-agent/prompt-debug/run" in paths
    assert "/jobs" in paths
    assert "/plugins" in paths
    assert "/plugin-contexts" in paths
    assert "/ab-tests" in paths
    assert any(path.startswith("/rlhf") for path in paths)
    assert not any(path.startswith("/__internal/critic") for path in paths)
    assert not any(path.startswith("/__internal/generation") for path in paths)
    assert not any(path.startswith("/v1.0/invoke/") for path in paths)
