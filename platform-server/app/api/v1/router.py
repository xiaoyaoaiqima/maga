"""
API v1 router aggregation
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    activities,
    agents,
    assets,
    auth,
    compat_invoke,
    content_agent,
    cache_monitor,
    calibration_records,
    calibration_tasks,
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
    prompt_optimizer,
    publish,
    richness_analysis,
    test_cases,
    test_sets,
    traces,
    users,
    rlhf,
    snapshots,
    tenants,
)
from app.api.v1.endpoints.system import roles, menus, info, users as sys_users, admin_tools
from app.api.v1.endpoints import ab_tests
from app.modules.critic.router import external_router as critic_external_router
from app.modules.critic.router import internal_router as critic_internal_router
from app.modules.generation.router import internal_router as generation_internal_router
from app.modules.keyword_corpus.router import external_router as keyword_corpus_external_router
from app.modules.keyword_corpus.router import internal_router as keyword_corpus_internal_router
from app.modules.keyword_corpus.router import knowledge_router as keyword_corpus_knowledge_router

api_router = APIRouter()

# Authentication endpoints (public)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(compat_invoke.router, tags=["internal-compat"])

# Include all endpoints
api_router.include_router(health.router, tags=["health"])
api_router.include_router(cache_monitor.router, tags=["cache-monitor"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(metrics.router)  # Metrics endpoint

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
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(prompt_optimizer.router, prefix="/prompt-optimizer", tags=["prompt-optimizer"])

# Snapshot management endpoints
api_router.include_router(snapshots.router)

# Dashboard endpoints
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])

# Trace endpoints
api_router.include_router(traces.router, prefix="/traces", tags=["traces"])

# LLM Provider endpoints (静态路由必须先注册)
api_router.include_router(llm_providers.static_router, prefix="/llm-providers", tags=["llm-providers"])
api_router.include_router(llm_providers.router, prefix="/llm-providers", tags=["llm-providers"])

# RLHF endpoints
api_router.include_router(rlhf.router)

# Content matching endpoints
api_router.include_router(contents.router)

# Data Query endpoints (Redash 统一数据查询)
api_router.include_router(data_query.router)

# Metric Definitions endpoints (指标定义)
api_router.include_router(metric_definitions.router, prefix="/metric-definitions", tags=["metric-definitions"])

# Business management endpoints (多租户/活动/Agent)
api_router.include_router(tenants.router)
api_router.include_router(activities.router)
api_router.include_router(agents.router)

# Job Execution Tracking endpoints
api_router.include_router(job_execution.router, prefix="/job-execution", tags=["job-execution"])

# Diversity Analysis endpoints (内容多样性/人设分布分析)
api_router.include_router(diversity_analysis.router, prefix="/diversity", tags=["diversity-analysis"])

# Richness Analysis endpoints (内容丰富度分析)
api_router.include_router(richness_analysis.router, prefix="/richness", tags=["richness-analysis"])

# Critic Score endpoints (评分记录与统计)
api_router.include_router(critic_scores.router, prefix="/critic-scores", tags=["critic-scores"])

# Message/Notification endpoints
api_router.include_router(messages.router, tags=["messages"])

# Keyword corpus / critic endpoints
api_router.include_router(keyword_corpus_external_router, prefix="/keyword-corpus", tags=["keyword-corpus"])
api_router.include_router(keyword_corpus_knowledge_router, tags=["knowledge-bases"])
api_router.include_router(critic_external_router, tags=["keyword-corpus"])
api_router.include_router(keyword_corpus_internal_router, prefix="/__internal/keyword-corpus/api/v1", tags=["internal-keyword-corpus"])
api_router.include_router(critic_internal_router, prefix="/__internal/critic/api/v1", tags=["internal-critic"])
api_router.include_router(generation_internal_router, prefix="/__internal/generation/api/v1", tags=["internal-generation"])

# Files endpoints (文件上传)
api_router.include_router(files.router, prefix="/files", tags=["files"])

# Publish management endpoints (上线管理)
api_router.include_router(publish.router)

# AB Test endpoints (AB测试)
api_router.include_router(ab_tests.router, prefix="/ab-tests", tags=["ab-tests"])

api_router.include_router(calibration_records.router, prefix="/calibration-records", tags=["calibration-records"])
api_router.include_router(calibration_tasks.router, prefix="/calibration-tasks", tags=["calibration-tasks"])
