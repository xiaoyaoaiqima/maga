"""
System Information API
"""
import asyncio
from typing import Dict
import httpx
from fastapi import APIRouter, Depends
from app.core.config import settings
from app.schemas.system_info import SystemInfoResponse, K8sInfo, DatabaseInfo, RedisInfo, ServiceHealth
from app.schemas.base import ResponseData

router = APIRouter(prefix="/info", tags=["系统信息"])


async def check_service_health(app_id: str) -> ServiceHealth:
    """
    Check health of a service via Dapr sidecar
    """
    url = f"http://localhost:{settings.DAPR_HTTP_PORT}/v1.0/invoke/{app_id}/method/api/v1/health"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                # 适配 ResponseModel 结构或直接返回 status
                status = data.get("status") or data.get("data", {}).get("status") or "healthy"
                version = data.get("version") or data.get("data", {}).get("version")
                return ServiceHealth(status=status, version=version)
            return ServiceHealth(status=f"error: {resp.status_code}")
    except Exception as e:
        return ServiceHealth(status=f"unreachable: {str(e)}")


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

    # 3. 异步并行检查各微服务状态
    services_to_check = {
        "critic": "raap-service-ag",
        "generation": "raap-service-generation-experts",
        "keyword": "raap-service-keyword-corpus",
    }

    # 添加 orchestrator 自身状态
    health_results: Dict[str, ServiceHealth] = {
        "orchestrator": ServiceHealth(status="healthy", version="1.0.0")
    }

    tasks = []
    service_names = []
    for key, app_id in services_to_check.items():
        service_names.append(key)
        tasks.append(check_service_health(app_id))

    results = await asyncio.gather(*tasks)
    for name, result in zip(service_names, results):
        health_results[name] = result

    system_info = SystemInfoResponse(
        app_env=settings.APP_ENV,
        k8s=k8s,
        database=database,
        redis=redis,
        services=health_results
    )

    return ResponseData(code=200, message="success", data=system_info)
