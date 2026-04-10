"""
Metrics Middleware
记录 HTTP 请求的 metrics
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time
from app.api.v1.endpoints.metrics import (
    http_requests_total,
    http_request_duration_seconds
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """记录 HTTP 请求指标"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # 执行请求
        response = await call_next(request)
        
        # 计算耗时
        duration = time.time() - start_time
        
        # 获取路径（排除查询参数）
        path = request.url.path
        
        # 记录指标
        http_requests_total.labels(
            method=request.method,
            endpoint=path,
            status=response.status_code
        ).inc()
        
        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=path
        ).observe(duration)
        
        return response

