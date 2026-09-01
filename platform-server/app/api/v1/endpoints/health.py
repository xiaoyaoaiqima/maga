"""
Health check endpoints
"""
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check() -> HealthResponse:
    """Basic health check"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        service=settings.APP_NAME,
        version="1.0.0",
    )


@router.get("/health/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def readiness_check() -> HealthResponse:
    """
    Readiness check - verify service is ready to receive traffic

    轻量级检查：只验证服务进程是否存活，不检查外部依赖

    设计理由：
    1. K8s readiness probe 应该快速响应（< 100ms）
    2. 避免因数据库/Redis 暂时不可用导致容器被重启
    3. 如果依赖服务不可用，业务请求会自然失败，无需 readiness check 判断
    4. 详细的依赖状态检查请使用 /health/detailed 端点
    """
    return HealthResponse(
        status="ready",
        timestamp=datetime.utcnow(),
        service=settings.APP_NAME,
        version="1.0.0",
    )


@router.get("/health/detailed", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def detailed_health_check(
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """
    详细健康检查 - 包含所有依赖服务的状态

    用于：
    - 监控系统定期检查服务健康状态
    - 人工排查问题时查看依赖状态
    - 不建议用作 K8s readiness/liveness probe
    """
    dependencies = {}

    # Check the configured primary database (SQLite locally, MySQL in production).
    try:
        await db.execute(text("SELECT 1"))
        dependencies["database"] = "healthy"
    except Exception as e:
        dependencies["database"] = f"unhealthy: {str(e)}"

    if settings.REDIS_ENABLED:
        try:
            redis = await get_redis()
            await redis.ping()
            dependencies["redis"] = "healthy"
        except Exception as e:
            dependencies["redis"] = f"unhealthy: {str(e)}"

    # Determine overall status
    overall_status = "healthy" if all(
        v == "healthy" for v in dependencies.values()
    ) else "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        service=settings.APP_NAME,
        version="1.0.0",
        dependencies=dependencies,
    )


@router.get("/health/live", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def liveness_check() -> HealthResponse:
    """Liveness check - verify service is running"""
    return HealthResponse(
        status="alive",
        timestamp=datetime.utcnow(),
        service=settings.APP_NAME,
        version="1.0.0",
    )
