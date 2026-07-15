"""System Information API."""
from typing import Dict
from fastapi import APIRouter
from app.core.config import settings
from app.schemas.system_info import SystemInfoResponse, K8sInfo, DatabaseInfo, RedisInfo, ServiceHealth
from app.schemas.base import ResponseData

router = APIRouter(prefix="/info", tags=["系统信息"])


@router.get("", response_model=ResponseData[SystemInfoResponse], summary="获取系统信息")
async def get_system_info():
    """
    获取系统环境、K8s 集群、数据库、Redis 以及各服务的健康状态
    """
    # 1. 获取基础环境信息
    k8s = K8sInfo(
        pod_name=settings.POD_NAME or "local-dev",
        node_name=settings.NODE_NAME or "local-node",
        namespace=settings.NAMESPACE or "raap-dev"
    )

    # 2. 获取数据库和 Redis 信息 (脱敏)
    # 生成 Adminer 跳转链接 (支持自动登录)
    adminer_url = settings.ADMINER_URL
    if adminer_url:
        # 由于我们配置了 Adminer 自动登录脚本，直接跳转即可
        # 如果需要跳转到特定库，可以带上 ?username=...&db=...
        pass

    database = DatabaseInfo(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        database=settings.MYSQL_DATABASE,
        adminer_url=adminer_url
    )

    redis = RedisInfo(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        insight_url=settings.REDIS_INSIGHT_URL
    )

    # 3. 当前 MAGA 服务状态
    health_results: Dict[str, ServiceHealth] = {
        "orchestrator": ServiceHealth(status="healthy", version="1.0.0")
    }

    system_info = SystemInfoResponse(
        app_env=settings.APP_ENV,
        k8s=k8s,
        database=database,
        redis=redis,
        services=health_results
    )

    return ResponseData(code=200, message="success", data=system_info)
