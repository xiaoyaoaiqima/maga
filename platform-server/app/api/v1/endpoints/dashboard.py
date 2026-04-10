"""
Dashboard endpoints - 仪表盘统计 API
"""
import os
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_analytics_db
from app.core.redis import get_redis
from app.core.logger import logger
from app.models.plugin import Plugin
from app.models.expert_config import ExpertConfig
from app.models.job import Job
from app.models.expert_task import ExpertTask
from app.models.expert_debug_history import ExpertDebugHistory
from app.schemas.dashboard import (
    DashboardResponse,
    DashboardStats,
    DashboardSummaryResponse,
    DashboardSummary,
    SystemStatus,
    RecentExecution,
)
from app.schemas.base import ResponseData

router = APIRouter()

# ✅ 缓存开关：通过环境变量控制
DASHBOARD_CACHE_ENABLED = os.getenv("DASHBOARD_CACHE_ENABLED", "false").lower() == "true"


async def _get_dashboard_stats_impl(
    db: AsyncSession,
) -> DashboardResponse:
    """
    获取仪表盘统计数据的核心实现（内部函数）

    这是无缓存的原始实现，被 get_dashboard_stats 调用
    """
    # 1. 统计 Plugin 数量
    plugin_count_result = await db.execute(
        select(func.count()).select_from(Plugin).where(Plugin.is_deleted == 0)
    )
    total_plugins = plugin_count_result.scalar() or 0

    # 2. 统计 ExpertConfig 数量
    expert_config_count_result = await db.execute(
        select(func.count()).select_from(ExpertConfig).where(ExpertConfig.is_deleted == 0)
    )
    total_expert_configs = expert_config_count_result.scalar() or 0

    # 3. 统计 Job 数量
    job_count_result = await db.execute(
        select(func.count()).select_from(Job).where(Job.is_deleted == 0)
    )
    total_jobs = job_count_result.scalar() or 0

    # 4. 统计已部署 Job 数量 (status = 'deployed')
    deployed_jobs_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.is_deleted == 0,
            Job.status == "deployed"
        )
    )
    deployed_jobs = deployed_jobs_result.scalar() or 0

    # 5. 统计运行中 Job 数量 (status = 'running')
    running_jobs_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.is_deleted == 0,
            Job.status == "running"
        )
    )
    running_jobs = running_jobs_result.scalar() or 0

    # 6. 统计今日执行次数（ExpertTask 和 ExpertDebugHistory）
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # ExpertTask 今日执行
    today_tasks_result = await db.execute(
        select(func.count()).select_from(ExpertTask).where(
            ExpertTask.create_time >= today_start
        )
    )
    today_task_count = today_tasks_result.scalar() or 0

    # ExpertDebugHistory 今日执行
    today_debug_result = await db.execute(
        select(func.count()).select_from(ExpertDebugHistory).where(
            ExpertDebugHistory.create_time >= today_start
        )
    )
    today_debug_count = today_debug_result.scalar() or 0

    today_executions = today_task_count + today_debug_count

    # 7. 计算成功率（最近 7 天）
    week_ago = datetime.now() - timedelta(days=7)

    # 查询最近 7 天的调试记录（用于计算成功率）
    recent_debug_result = await db.execute(
        select(ExpertDebugHistory.success).where(
            ExpertDebugHistory.create_time >= week_ago
        )
    )
    recent_debug = recent_debug_result.scalars().all()

    # 计算成功率（基于调试记录）
    total_recent = len(recent_debug)
    if total_recent > 0:
        debug_success = sum(1 for d in recent_debug if d is True)
        success_rate = round(debug_success / total_recent * 100, 1)
    else:
        success_rate = 100.0  # 没有执行记录时默认 100%

    # 8. 检查系统状态
    system_status = SystemStatus(
        orchestrator=True,  # 能响应请求说明 orchestrator 正常
        database=True,  # 能执行上述查询说明数据库正常
        redis=False,
    )

    # 检查 Redis
    try:
        redis = await get_redis()
        await redis.ping()
        system_status.redis = True
    except Exception:
        system_status.redis = False

    # 9. 获取最近执行记录（ExpertDebugHistory）
    recent_executions: List[RecentExecution] = []

    # 获取最近 ExpertDebugHistory
    recent_debug_query = await db.execute(
        select(ExpertDebugHistory)
        .order_by(ExpertDebugHistory.create_time.desc())
        .limit(10)
    )
    recent_debug_records = recent_debug_query.scalars().all()

    for debug in recent_debug_records:
        recent_executions.append(RecentExecution(
            id=str(debug.id),
            job_name="Expert 调试",
            job_id=None,
            expert_config_code=debug.expert_config_code,
            status="success" if debug.success else "failed",
            created_at=debug.create_time or datetime.now(),
            execution_time_ms=debug.execution_time_ms,
            error=debug.error_message,
        ))

    # 构建响应
    stats = DashboardStats(
        total_plugins=total_plugins,
        total_expert_configs=total_expert_configs,
        total_jobs=total_jobs,
        deployed_jobs=deployed_jobs,
        running_jobs=running_jobs,
        today_executions=today_executions,
        success_rate=success_rate,
    )

    response = DashboardResponse(
        stats=stats,
        system_status=system_status,
        recent_executions=recent_executions,
    )

    return response


@router.get(
    "/stats",
    response_model=ResponseData[DashboardResponse],
    status_code=status.HTTP_200_OK,
    summary="获取仪表盘统计数据",
    description="获取系统概览统计数据，包括各类资源数量、系统状态和最近执行记录"
)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务数据查询（带自动降级）
) -> ResponseData[DashboardResponse]:
    """
    获取仪表盘统计数据

    ✅ v1.4: 支持缓存（通过环境变量 DASHBOARD_CACHE_ENABLED 控制）
    ✅ v1.5: 使用分析库进行业务数据查询，如果分析库不可用则自动降级到主库
    """
    # ✅ 如果启用缓存，先尝试从缓存获取
    logger.info(f"DEBUG: DASHBOARD_CACHE_ENABLED={DASHBOARD_CACHE_ENABLED}")
    if DASHBOARD_CACHE_ENABLED:
        from app.services.dashboard_data_cache_service import MySQLDashboardDataCacheService

        try:
            logger.info("DEBUG: 尝试获取缓存...")
            cache_service = MySQLDashboardDataCacheService(db)  # 缓存使用主库

            # 生成 cache_key
            cache_key = cache_service.generate_cache_key(
                endpoint="/api/v1/dashboard/stats",
                params={},
                tenant_id=None,
            )

            logger.info(f"DEBUG: cache_key={cache_key}")

            # 尝试获取缓存
            cached = await cache_service.get(
                cache_key=cache_key,
                cache_group="dashboard_stats",
                check_demo=True,  # ✅ 支持演示模式
            )

            logger.info(f"DEBUG: 缓存获取结果 cached={cached is not None}")
            if cached:
                logger.info("✅ Dashboard Stats 缓存命中")
                return ResponseData(
                    code=200,
                    message="success (cached)",
                    data=cached["data"],
                )

        except Exception as e:
            logger.warning(f"缓存获取失败，降级到直接查询: {e}")

    # ✅ 缓存未命中或未启用缓存，从分析库查询（带自动降级）
    logger.info("从数据库查询 Dashboard Stats（分析库，失败则降级到主库）")
    response = await _get_dashboard_stats_impl(analytics_db)  # 使用分析库查询

    # ✅ 如果启用了缓存，写入缓存
    if DASHBOARD_CACHE_ENABLED:
        try:
            logger.info("DEBUG: 写入缓存...")
            await cache_service.set(
                cache_key=cache_key,
                logical_key=cache_service._generate_logical_key("dashboard_stats", {}),
                cache_group="dashboard_stats",
                data=response.model_dump(mode='json'),  # ✅ 使用 model_dump 正确序列化 datetime
                ttl_seconds=300,
                request_params={},
                tenant_id=None,
                auto_refresh_enabled=False,
            )
            logger.info("✅ Dashboard Stats 缓存写入成功")
        except Exception as e:
            logger.warning(f"缓存写入失败（非致命）: {e}")

    return ResponseData(
        code=200,
        message="success",
        data=response,
    )


async def _get_dashboard_summary_impl(
    db: AsyncSession,
) -> DashboardSummaryResponse:
    """
    获取仪表盘摘要数据的核心实现（内部函数）

    这是轻量级的摘要实现，只返回核心指标
    """
    # 1. 统计 Job 总数
    job_count_result = await db.execute(
        select(func.count()).select_from(Job).where(Job.is_deleted == 0)
    )
    total_jobs = job_count_result.scalar() or 0

    # 2. 统计运行中 Job 数量 (status = 'running')
    running_jobs_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.is_deleted == 0,
            Job.status == "running"
        )
    )
    running_jobs = running_jobs_result.scalar() or 0

    # 3. 统计今日执行次数（ExpertTask 和 ExpertDebugHistory）
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # ExpertTask 今日执行
    today_tasks_result = await db.execute(
        select(func.count()).select_from(ExpertTask).where(
            ExpertTask.create_time >= today_start
        )
    )
    today_task_count = today_tasks_result.scalar() or 0

    # ExpertDebugHistory 今日执行
    today_debug_result = await db.execute(
        select(func.count()).select_from(ExpertDebugHistory).where(
            ExpertDebugHistory.create_time >= today_start
        )
    )
    today_debug_count = today_debug_result.scalar() or 0

    today_executions = today_task_count + today_debug_count

    # 4. 计算成功率（最近 7 天）
    week_ago = datetime.now() - timedelta(days=7)

    # 查询最近 7 天的调试记录（用于计算成功率）
    recent_debug_result = await db.execute(
        select(ExpertDebugHistory.success).where(
            ExpertDebugHistory.create_time >= week_ago
        )
    )
    recent_debug = recent_debug_result.scalars().all()

    # 计算成功率（基于调试记录）
    total_recent = len(recent_debug)
    if total_recent > 0:
        debug_success = sum(1 for d in recent_debug if d is True)
        success_rate = round(debug_success / total_recent * 100, 1)
    else:
        success_rate = 100.0  # 没有执行记录时默认 100%

    # 5. 检查系统状态
    system_status = SystemStatus(
        orchestrator=True,  # 能响应请求说明 orchestrator 正常
        database=True,  # 能执行上述查询说明数据库正常
        redis=False,
    )

    # 检查 Redis
    try:
        redis = await get_redis()
        await redis.ping()
        system_status.redis = True
    except Exception:
        system_status.redis = False

    # 构建摘要响应
    summary = DashboardSummary(
        total_jobs=total_jobs,
        running_jobs=running_jobs,
        today_executions=today_executions,
        success_rate=success_rate,
    )

    response = DashboardSummaryResponse(
        summary=summary,
        system_status=system_status,
        last_updated=datetime.now(),
    )

    return response


@router.get(
    "/summary",
    response_model=ResponseData[DashboardSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="获取仪表盘摘要数据",
    description="获取系统核心指标摘要，包括 Job 总数、运行中数量、今日执行次数、成功率和系统状态"
)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务数据查询（带自动降级）
) -> ResponseData[DashboardSummaryResponse]:
    """
    获取仪表盘摘要数据（轻量级）

    ✅ v1.4: 支持缓存（通过环境变量 DASHBOARD_CACHE_ENABLED 控制）
    ✅ v1.5: 使用分析库进行业务数据查询，如果分析库不可用则自动降级到主库
    """
    # ✅ 如果启用缓存，先尝试从缓存获取
    if DASHBOARD_CACHE_ENABLED:
        from app.services.dashboard_data_cache_service import MySQLDashboardDataCacheService

        try:
            cache_service = MySQLDashboardDataCacheService(db)  # 缓存使用主库

            # 生成 cache_key
            cache_key = cache_service.generate_cache_key(
                endpoint="/api/v1/dashboard/summary",
                params={},
                tenant_id=None,
            )

            # 尝试获取缓存
            cached = await cache_service.get(
                cache_key=cache_key,
                cache_group="dashboard_summary",
                check_demo=True,  # ✅ 支持演示模式
            )

            if cached:
                logger.info("✅ Dashboard Summary 缓存命中")
                return ResponseData(
                    code=200,
                    message="success (cached)",
                    data=cached["data"],
                )

        except Exception as e:
            logger.warning(f"缓存获取失败，降级到直接查询: {e}")

    # ✅ 缓存未命中或未启用缓存，从分析库查询（带自动降级）
    logger.info("从数据库查询 Dashboard Summary（分析库，失败则降级到主库）")
    response = await _get_dashboard_summary_impl(analytics_db)  # 使用分析库查询

    # ✅ 如果启用了缓存，写入缓存
    if DASHBOARD_CACHE_ENABLED:
        try:
            logger.info("DEBUG: 写入缓存...")
            await cache_service.set(
                cache_key=cache_key,
                logical_key=cache_service._generate_logical_key("dashboard_summary", {}),
                cache_group="dashboard_summary",
                data=response.model_dump(mode='json'),  # ✅ 使用 model_dump 正确序列化 datetime
                ttl_seconds=300,
                request_params={},
                tenant_id=None,
                auto_refresh_enabled=False,
            )
            logger.info("✅ Dashboard Summary 缓存写入成功")
        except Exception as e:
            logger.warning(f"缓存写入失败（非致命）: {e}")

    return ResponseData(
        code=200,
        message="success",
        data=response,
    )

