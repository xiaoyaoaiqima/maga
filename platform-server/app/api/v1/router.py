"""
API v1 router aggregation.

MAGA clean mode deliberately exposes only the content-production surface. The
legacy RAAP routes remain available in full mode so old local workflows can keep
running while production is narrowed around the MAGA workbench.
"""
from fastapi import APIRouter

from app.core.config import settings


def create_api_router(app_mode: str | None = None) -> APIRouter:
    """Build the API router for either the full legacy surface or clean MAGA mode."""
    router = APIRouter()
    mode = app_mode or settings.MAGA_APP_MODE
    if mode == "clean":
        _include_clean_routes(router)
    else:
        _include_full_routes(router)
    return router


def _include_clean_routes(api_router: APIRouter) -> None:
    """Register only the routes required by the MAGA production workbench."""
    from app.api.v1.endpoints import (
        assets,
        auth,
        chat,
        content_agent,
        content_generation_experts,
        files,
        health,
        llm_providers,
    )
    from app.api.v1.endpoints.system import info, roles, users as sys_users

    api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
    api_router.include_router(health.router, tags=["health"])
    api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
    api_router.include_router(content_agent.router, prefix="/content-agent", tags=["content-agent"])
    api_router.include_router(
        content_generation_experts.router,
        prefix="/content-agent",
        tags=["content-generation-experts"],
    )
    api_router.include_router(
        content_generation_experts.router,
        prefix="/content-generation",
        tags=["content-generation-experts"],
    )
    api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
    api_router.include_router(files.router, prefix="/files", tags=["files"])
    api_router.include_router(info.router, prefix="/system", tags=["system"])
    # clean 模式仍然暴露系统用户页；这些接口是该页面读取用户列表和角色下拉框的最小依赖。
    api_router.include_router(sys_users.router, prefix="/system", tags=["system"])
    api_router.include_router(roles.router, prefix="/system", tags=["system"])
    api_router.include_router(llm_providers.static_router, prefix="/llm-providers", tags=["llm-providers"])
    api_router.include_router(llm_providers.router, prefix="/llm-providers", tags=["llm-providers"])


def _include_full_routes(api_router: APIRouter) -> None:
    """Register the historical full API surface."""
    from app.api.v1.endpoints import (
        ab_tests,
        activities,
        agents,
        assets,
        auth,
        cache_monitor,
        calibration_records,
        calibration_tasks,
        chat,
        compat_invoke,
        content_agent,
        content_generation_experts,
        contents,
        critic_scores,
        dashboard,
        data_query,
        diversity_analysis,
        expert_configs,
        expert_evals,
        expert_tasks,
        files,
        health,
        job_create_drafts,
        job_execution,
        job_variants,
        jobs,
        llm_providers,
        messages,
        metric_definitions,
        metrics,
        plugin_contexts,
        plugins,
        publish,
        richness_analysis,
        rlhf,
        snapshots,
        tenants,
        test_cases,
        test_sets,
        traces,
        users,
    )
    from app.api.v1.endpoints.system import admin_tools, info, menus, roles, users as sys_users
    from app.modules.critic.router import external_router as critic_external_router
    from app.modules.critic.router import internal_router as critic_internal_router
    from app.modules.generation.router import internal_router as generation_internal_router

    # Authentication endpoints (public)
    api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
    api_router.include_router(compat_invoke.router, tags=["internal-compat"])

    # Include all endpoints
    api_router.include_router(health.router, tags=["health"])
    api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
    api_router.include_router(cache_monitor.router, tags=["cache-monitor"])
    api_router.include_router(users.router, prefix="/users", tags=["users"])
    api_router.include_router(metrics.router)

    # System management endpoints
    api_router.include_router(sys_users.router, prefix="/system", tags=["system"])
    api_router.include_router(roles.router, prefix="/system", tags=["system"])
    api_router.include_router(menus.router, prefix="/system", tags=["system"])
    api_router.include_router(info.router, prefix="/system", tags=["system"])
    api_router.include_router(admin_tools.router, prefix="/system", tags=["system"])

    # Orchestration endpoints
    api_router.include_router(plugins.router, prefix="/plugins", tags=["plugins"])
    api_router.include_router(plugin_contexts.router, prefix="/plugin-contexts", tags=["plugin-contexts"])
    api_router.include_router(expert_configs.router, prefix="/expert-configs", tags=["expert-configs"])
    api_router.include_router(test_sets.router, prefix="/test-sets", tags=["test-sets"])
    api_router.include_router(test_cases.router, prefix="/test-cases", tags=["test-cases"])
    api_router.include_router(expert_evals.router, prefix="/expert-evals", tags=["expert-evals"])
    api_router.include_router(job_create_drafts.router, prefix="/job-create/drafts", tags=["job-create-drafts"])
    api_router.include_router(job_variants.router, prefix="/job-variants", tags=["job-variants"])
    api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
    api_router.include_router(expert_tasks.router, prefix="/expert-tasks", tags=["expert-tasks"])
    api_router.include_router(content_agent.router, prefix="/content-agent", tags=["content-agent"])
    api_router.include_router(
        content_generation_experts.router,
        prefix="/content-agent",
        tags=["content-generation-experts"],
    )
    api_router.include_router(
        content_generation_experts.router,
        prefix="/content-generation",
        tags=["content-generation-experts"],
    )
    api_router.include_router(assets.router, prefix="/assets", tags=["assets"])

    # Snapshot management endpoints
    api_router.include_router(snapshots.router)

    # Dashboard endpoints
    api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])

    # Trace endpoints
    api_router.include_router(traces.router, prefix="/traces", tags=["traces"])

    # LLM Provider endpoints (static routes must be registered first)
    api_router.include_router(llm_providers.static_router, prefix="/llm-providers", tags=["llm-providers"])
    api_router.include_router(llm_providers.router, prefix="/llm-providers", tags=["llm-providers"])

    # RLHF endpoints
    api_router.include_router(rlhf.router)

    # Content matching endpoints
    api_router.include_router(contents.router)

    # Data Query endpoints (Redash unified data query)
    api_router.include_router(data_query.router)

    # Metric Definitions endpoints
    api_router.include_router(metric_definitions.router, prefix="/metric-definitions", tags=["metric-definitions"])

    # Business management endpoints (tenant/activity/agent)
    api_router.include_router(tenants.router)
    api_router.include_router(activities.router)
    api_router.include_router(agents.router)

    # Job Execution Tracking endpoints
    api_router.include_router(job_execution.router, prefix="/job-execution", tags=["job-execution"])

    # Diversity Analysis endpoints
    api_router.include_router(diversity_analysis.router, prefix="/diversity", tags=["diversity-analysis"])

    # Richness Analysis endpoints
    api_router.include_router(richness_analysis.router, prefix="/richness", tags=["richness-analysis"])

    # Critic Score endpoints
    api_router.include_router(critic_scores.router, prefix="/critic-scores", tags=["critic-scores"])

    # Message/Notification endpoints
    api_router.include_router(messages.router, tags=["messages"])

    # Critic and generation compatibility endpoints
    api_router.include_router(critic_external_router, tags=["critic"])
    api_router.include_router(critic_internal_router, prefix="/__internal/critic/api/v1", tags=["internal-critic"])
    api_router.include_router(generation_internal_router, prefix="/__internal/generation/api/v1", tags=["internal-generation"])

    # Files endpoints
    api_router.include_router(files.router, prefix="/files", tags=["files"])

    # Publish management endpoints
    api_router.include_router(publish.router)

    # AB Test endpoints
    api_router.include_router(ab_tests.router, prefix="/ab-tests", tags=["ab-tests"])

    api_router.include_router(calibration_records.router, prefix="/calibration-records", tags=["calibration-records"])
    api_router.include_router(calibration_tasks.router, prefix="/calibration-tasks", tags=["calibration-tasks"])


api_router = create_api_router()
