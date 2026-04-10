"""
Prometheus Metrics 端点
提供应用级别的监控指标
"""
from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Histogram, Gauge
import time

router = APIRouter(prefix="/metrics", tags=["metrics"])

# 定义指标
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

dapr_grpc_requests_total = Counter(
    'dapr_grpc_requests_total',
    'Legacy metric name (actual: Dapr HTTP invocation)',
    ['target_service', 'method', 'status']
)

dapr_grpc_request_duration_seconds = Histogram(
    'dapr_grpc_request_duration_seconds',
    'Legacy metric name (actual: Dapr HTTP invocation duration in seconds)',
    ['target_service', 'method'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# 兼容：历史指标名带 grpc，但当前实际为 Dapr HTTP Invocation
# 新代码请使用 dapr_http_*；旧看板可继续用 dapr_grpc_*（建议后续统一迁移）
dapr_http_requests_total = Counter(
    'dapr_http_requests_total',
    'Total Dapr HTTP invocation requests',
    ['target_service', 'method', 'status']
)

dapr_http_request_duration_seconds = Histogram(
    'dapr_http_request_duration_seconds',
    'Dapr HTTP invocation request duration in seconds',
    ['target_service', 'method'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

active_connections = Gauge(
    'active_connections',
    'Number of active connections',
    ['type']
)

@router.get("")
async def metrics():
    """
    Prometheus metrics 端点
    返回所有应用指标
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

