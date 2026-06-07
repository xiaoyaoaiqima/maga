"""Tests for MAGA clean API routing mode."""

from app.api.v1.router import create_api_router


def _route_paths(app_mode: str) -> set[str]:
    return {getattr(route, "path", "") for route in create_api_router(app_mode).routes}


def test_clean_mode_exposes_maga_workbench_routes_only():
    paths = _route_paths("clean")

    assert "/auth/login" in paths
    assert "/auth/userinfo" in paths
    assert "/health" in paths
    assert "/health/detailed" in paths
    assert "/content-agent/batches/start" in paths
    assert "/content-agent/comment-batches/start" in paths
    assert "/content-agent/experts" in paths
    assert "/assets/generation-options" in paths
    assert "/assets/content-generation-keywords" in paths
    assert "/llm-providers" in paths
    assert "/llm-providers/routes" in paths

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


def test_full_mode_keeps_legacy_routes_available():
    paths = _route_paths("full")

    assert "/content-agent/batches/start" in paths
    assert "/jobs" in paths
    assert "/plugins" in paths
    assert "/plugin-contexts" in paths
    assert "/ab-tests" in paths
    assert any(path.startswith("/rlhf") for path in paths)
