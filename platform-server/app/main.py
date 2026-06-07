"""
FastAPI Application Entry Point
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.database import init_db, async_session_factory
from app.core.logger import setup_logging, get_logger
from app.api.v1.router import api_router
from app.middleware.logger import LoggerMiddleware
from app.middleware.metrics_middleware import MetricsMiddleware

# 初始化日志系统（在模块加载时执行）
setup_logging()
logger = get_logger()

from app.services.auth_service import AuthService
from app.services.sys_menu_service import SysMenuService
from datetime import datetime, timedelta

# 定义一个独立的任务函数（不依赖请求上下文）
async def run_daily_stats_aggregation():
    """执行每日统计聚合任务"""
    from app.core.logger import logger
    from app.services.trace_service import TraceService

    async with async_session_factory() as db:
        try:
            service = TraceService(db)
            # 1. 聚合今天的数据 (实时性)
            await service.aggregate_daily_stats()
            # 2. 修正昨天的数据 (防止跨天数据遗漏)
            yesterday = datetime.now().date() - timedelta(days=1)
            await service.aggregate_daily_stats(yesterday)
        except Exception as e:
            logger.error(f"Scheduled aggregation failed: {e}")


async def run_cache_refresh():
    """执行缓存刷新任务（仅 Master 节点）"""
    from app.core.logger import logger
    from app.services.cache_refresh_scheduler import CacheRefreshScheduler

    async with async_session_factory() as db:
        try:
            scheduler = CacheRefreshScheduler(db)
            await scheduler.refresh_all_pending()
        except Exception as e:
            logger.error(f"Cache refresh failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} service...")
    logger.info(f"Environment: {settings.APP_ENV}, Debug: {settings.APP_DEBUG}")
    logger.info(f"MAGA app mode: {settings.MAGA_APP_MODE}")
    logger.info(f"Log format: {settings.effective_log_format}, Level: {settings.LOG_LEVEL}")

    await init_db()
    logger.info("Database initialized")

    try:
        async with async_session_factory() as db:
            auth_service = AuthService(db)
            await auth_service.create_default_admin()
            menu_service = SysMenuService(db)
            await menu_service.init_default_menus()
    except Exception as e:
        logger.warning(f"Default bootstrap initialization failed: {e}")

    if settings.is_maga_clean_mode:
        logger.info("MAGA clean mode: legacy scheduler bootstrap skipped")
    else:
        # 初始化并启动旧 Job/ExpertTask 调度器；clean 模式不注册这些历史运行面。
        try:
            from app.scheduler import get_scheduler_manager
            from app.scheduler.expert_task_executor import set_main_event_loop

            # 保存主事件循环引用，供调度任务使用
            main_loop = asyncio.get_event_loop()
            set_main_event_loop(main_loop)

            scheduler_manager = get_scheduler_manager()
            scheduler_manager.init_scheduler()
            scheduler_manager.start()
            logger.info("Scheduler started")

            # 加载已部署的任务
            await _load_deployed_tasks(scheduler_manager)

            # 注册聚合任务：每小时执行一次 (分=0)
            scheduler_manager.add_cron_job(
                func=run_daily_stats_aggregation,
                job_id="trace_daily_aggregation",
                cron_expression="0 * * * *",  # 每小时第0分钟执行
                replace_existing=True,
            )

            # ✅ Phase 9: 注册缓存刷新任务：每分钟执行一次（仅 Master 节点执行）
            scheduler_manager.add_cron_job(
                func=run_cache_refresh,
                job_id="dashboard_cache_refresh",
                cron_expression="* * * * *",  # 每分钟执行
                replace_existing=True,
            )
            logger.info("✅ Dashboard cache refresh job registered (every minute, Master only)")

            # ✅ Phase 10: 启动时缓存预热（使用分布式锁协调）
            import os
            cache_warmup_enabled = os.getenv("CACHE_WARMUP_ON_STARTUP", "false").lower() == "true"
            if cache_warmup_enabled:
                try:
                    from app.services.cache_warmup_service import CacheWarmupService

                    async with async_session_factory() as db:
                        warmup_service = CacheWarmupService(db)

                        # 注册查询函数（示例：dashboard stats）
                        async def warmup_dashboard_stats():
                            from app.api.v1.endpoints.dashboard import _get_dashboard_stats_impl
                            return await _get_dashboard_stats_impl(db)

                        warmup_service.register_query_function("/api/v1/dashboard/stats", warmup_dashboard_stats)

                        # 执行预热
                        logger.info("🔥 Starting cache warmup...")
                        stats = await warmup_service.warmup_all()
                        logger.info(f"✅ Cache warmup completed: {stats}")
                except Exception as e:
                    logger.warning(f"Cache warmup failed (non-critical): {e}")
            else:
                logger.info("Cache warmup disabled (CACHE_WARMUP_ON_STARTUP=false)")

        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
    
    yield
    
    # Shutdown
    # 关闭调度器
    if settings.is_maga_clean_mode:
        logger.info("MAGA clean mode: no legacy scheduler shutdown required")
    else:
        try:
            from app.scheduler import get_scheduler_manager

            scheduler_manager = get_scheduler_manager()
            scheduler_manager.shutdown()
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Failed to stop scheduler: {e}")

    logger.info(f"Shutting down {settings.APP_NAME} service...")


async def _load_deployed_tasks(scheduler_manager) -> None:
    """加载已部署的任务到调度器"""
    from sqlalchemy import select
    from app.models.expert_task import ExpertTask
    from app.models.job import Job
    from app.scheduler.expert_task_executor import execute_expert_task_sync
    from app.services.expert_config_service import ExpertConfigService
    
    logger.info("[Scheduler] Loading deployed tasks...")
    
    async with async_session_factory() as db:
        try:
            # 查找所有已部署 Job 的 expert_task
            deployed_jobs_result = await db.execute(
                select(Job).where(
                    Job.status == "DEPLOYED",
                    Job.enabled == True,
                    Job.is_deleted == 0
                )
            )
            deployed_jobs = deployed_jobs_result.scalars().all()
            
            if not deployed_jobs:
                logger.info("[Scheduler] No deployed jobs found")
                return
            
            job_ids = [j.job_id for j in deployed_jobs]
            
            # 查找对应的 expert_tasks
            expert_tasks_result = await db.execute(
                select(ExpertTask).where(
                    ExpertTask.job_id.in_(job_ids),
                    ExpertTask.status.in_([0, 1]),  # 待执行或执行中
                    ExpertTask.is_deleted == 0
                )
            )
            expert_tasks = expert_tasks_result.scalars().all()
            
            logger.info(f"[Scheduler] Found {len(expert_tasks)} expert_tasks to load")
            
            expert_config_service = ExpertConfigService(db)
            
            for task in expert_tasks:
                try:
                    # 确定使用的执行器
                    expert_config = await expert_config_service.get_by_code(task.expert_config_code)
                    executor = 'generation' if expert_config and expert_config.expert_type.upper() == 'GENERATION' else 'critic'
                    
                    # 注册定时任务
                    job_id_for_scheduler = f"expert_task_{task.id}"
                    scheduler_manager.add_cron_job(
                        func=execute_expert_task_sync,
                        job_id=job_id_for_scheduler,
                        cron_expression=task.cron_expression,
                        args=(task.id,),
                        executor=executor,
                        replace_existing=True
                    )
                    logger.info(f"[Scheduler] Loaded task: {job_id_for_scheduler}, cron: {task.cron_expression}")
                except Exception as e:
                    logger.error(f"[Scheduler] Failed to load task {task.id}: {e}")
            
            logger.info(f"[Scheduler] Finished loading {len(expert_tasks)} tasks")
            
        except Exception as e:
            logger.error(f"[Scheduler] Error loading deployed tasks: {e}")


def create_app() -> FastAPI:
    """Create FastAPI application"""
    app = FastAPI(
        title="MAGA Platform Server",
        description="Marketing Agent Generation Platform",
        version="1.0.0",
        docs_url="/docs" if settings.APP_DEBUG else None,
        redoc_url="/redoc" if settings.APP_DEBUG else None,
        openapi_url="/openapi.json" if settings.APP_DEBUG else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该限制
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Metrics middleware (记录 HTTP 请求指标)
    app.add_middleware(MetricsMiddleware)

    # Custom logger middleware
    app.add_middleware(LoggerMiddleware)

    # Include routers
    app.include_router(api_router, prefix="/api/v1")

    # 全局异常处理：与成功响应同构 { code, message, data, detail }，便于前端统一解析
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from fastapi.exceptions import HTTPException

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": "error",
                "data": None,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Global exception: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "Internal Server Error",
                "data": None,
                "detail": "服务器内部错误",
            },
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
    )
