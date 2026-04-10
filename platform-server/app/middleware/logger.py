"""
HTTP 日志中间件

功能：
1. 结构化 HTTP 请求日志
2. 每个请求只打 1 条完整日志
3. 自动生成和传递 trace_id / request_id
4. 可选记录 request/response body
5. 自动脱敏敏感数据
"""
import time
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message

from app.core.config import settings
from app.core.logger import log_http_request
from app.core.trace import (
    init_request_context,
    clear_request_context,
    get_trace_context,
)
from app.utils.sensitive import mask_sensitive_data, mask_headers


# 不记录日志的路径（健康检查、metrics 等）
SKIP_LOG_PATHS = {
    "/health",
    "/health/live",
    "/health/ready",
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/metrics",
    "/api/v1/metrics",
    "/favicon.ico",
    "/docs",
    "/redoc",
    "/openapi.json",
}

# Request ID 请求头名称
REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"


class LoggerMiddleware(BaseHTTPMiddleware):
    """
    HTTP 请求日志中间件
    
    每个请求完成时记录一条完整的结构化日志
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求并记录日志"""
        # 跳过不需要记录的路径
        if request.url.path in SKIP_LOG_PATHS:
            return await call_next(request)
        
        # 从请求头获取 trace_id 和 request_id（用于链路追踪）
        incoming_request_id = request.headers.get(REQUEST_ID_HEADER)
        incoming_trace_id = request.headers.get(TRACE_ID_HEADER)
        
        # 初始化请求上下文
        context = init_request_context(
            request_id=incoming_request_id,
            trace_id=incoming_trace_id,
        )
        
        # 记录开始时间
        start_time = time.perf_counter()
        
        # 提取请求信息
        method = request.method
        path = request.url.path
        query_string = str(request.url.query) if request.url.query else ""
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        # 可选：读取请求体
        request_body = None
        if settings.LOG_INCLUDE_REQUEST_BODY and method in ("POST", "PUT", "PATCH"):
            request_body = await self._get_request_body(request)
        
        # 执行请求
        response: Optional[Response] = None
        error_message: Optional[str] = None
        status_code = 500  # 默认错误状态码
        
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            error_message = str(e)
            raise
        finally:
            # 计算耗时
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # 可选：读取响应体（仅在需要时）
            response_body = None
            # 注意：读取响应体比较复杂，需要重新构造响应，这里暂不实现
            # if settings.LOG_INCLUDE_RESPONSE_BODY and response:
            #     response_body = await self._get_response_body(response)
            
            # 脱敏处理
            if request_body and settings.effective_sensitive_mask:
                request_body = mask_sensitive_data(request_body)
            if response_body and settings.effective_sensitive_mask:
                response_body = mask_sensitive_data(response_body)
            
            # 从 request.state 获取用户 ID（如果认证中间件设置了）
            user_id = getattr(request.state, "user_id", None)
            
            # 记录日志
            log_http_request(
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=user_agent,
                query_string=query_string,
                request_body=request_body,
                response_body=response_body,
                user_id=user_id,
                error=error_message,
            )
            
            # 清理请求上下文
            clear_request_context()
        
        # 在响应头中添加 request_id 和 trace_id（便于客户端追踪）
        if response:
            response.headers[REQUEST_ID_HEADER] = context["request_id"]
            response.headers[TRACE_ID_HEADER] = context["trace_id"]
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """
        获取客户端真实 IP
        
        优先从代理头获取，支持：
        - X-Forwarded-For
        - X-Real-IP
        - CF-Connecting-IP (Cloudflare)
        """
        # 按优先级尝试获取真实 IP
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # X-Forwarded-For 可能包含多个 IP，取第一个
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip
        
        # 兜底：使用直连 IP
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def _get_request_body(self, request: Request) -> Optional[dict]:
        """
        读取请求体
        
        注意：这会消费请求体，需要重新设置
        """
        try:
            # 检查 Content-Type
            content_type = request.headers.get("content-type", "")
            
            if "application/json" in content_type:
                body = await request.body()
                if body:
                    import json
                    # 重新设置请求体（因为 body() 会消费流）
                    async def receive() -> Message:
                        return {"type": "http.request", "body": body}
                    request._receive = receive
                    return json.loads(body)
            
            elif "application/x-www-form-urlencoded" in content_type:
                form_data = await request.form()
                # 重建请求
                body = await request.body()
                async def receive() -> Message:
                    return {"type": "http.request", "body": body}
                request._receive = receive
                return dict(form_data)
            
        except Exception:
            pass
        
        return None
