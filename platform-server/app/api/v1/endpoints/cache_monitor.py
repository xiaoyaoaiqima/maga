"""
缓存监控端点
提供缓存性能指标的可视化接口
"""
from fastapi import APIRouter
from loguru import logger

from app.core.redis import get_cache_metrics, reset_cache_metrics

router = APIRouter(prefix="/cache-monitor", tags=["cache-monitor"])


@router.get("/metrics")
async def get_metrics():
    """
    获取缓存性能指标

    Returns:
        {
            "hits": 1234,
            "misses": 567,
            "hit_rate": "68.52%",
            "sets": 890,
            "deletes": 45,
            "errors": 2,
            "total_requests": 1801,
            "avg_latency_ms": "2.35",
            "p95_latency_ms": "5.20",
            "p99_latency_ms": "8.90"
        }
    """
    try:
        metrics = get_cache_metrics()
        logger.info("缓存指标查询成功")
        return {
            "success": True,
            "data": metrics
        }
    except Exception as e:
        logger.error(f"获取缓存指标失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/metrics/reset")
async def reset_metrics():
    """
    重置缓存指标统计

    用于定期重置计数器，避免数值溢出
    """
    try:
        reset_cache_metrics()
        logger.info("缓存指标已重置")
        return {
            "success": True,
            "message": "缓存指标已重置"
        }
    except Exception as e:
        logger.error(f"重置缓存指标失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/health")
async def health_check():
    """
    缓存健康检查

    Returns:
        {
            "status": "healthy",
            "metrics": {...}
        }
    """
    metrics = get_cache_metrics()

    # 判断缓存是否健康
    total_requests = metrics["total_requests"]
    hit_rate = float(metrics["hit_rate"].replace("%", ""))
    error_rate = metrics["errors"] / total_requests if total_requests > 0 else 0

    # 健康标准
    is_healthy = (
        hit_rate >= 50 and  # 命中率至少 50%
        error_rate < 0.01  # 错误率小于 1%
    )

    status = "healthy" if is_healthy else "degraded"

    return {
        "status": status,
        "metrics": metrics,
        "recommendations": _get_recommendations(metrics)
    }


def _get_recommendations(metrics: dict) -> list[str]:
    """根据缓存指标生成优化建议"""
    recommendations = []

    hit_rate = float(metrics["hit_rate"].replace("%", ""))
    total_requests = metrics["total_requests"]
    error_rate = metrics["errors"] / total_requests if total_requests > 0 else 0

    if hit_rate < 50:
        recommendations.append("⚠️ 缓存命中率较低，建议检查 TTL 设置或缓存键设计")

    if error_rate > 0.01:
        recommendations.append("⚠️ 缓存错误率较高，请检查 Redis 连接状态")

    if total_requests < 100:
        recommendations.append("ℹ️ 样本量较少，指标可能不够准确")

    if not recommendations:
        recommendations.append("✅ 缓存运行状态良好")

    return recommendations
