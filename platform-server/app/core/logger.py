"""
统一日志配置模块

支持：
1. JSON/Text 格式自动切换（生产环境 JSON，开发环境彩色文本）
2. 腾讯云 CLS 友好的 JSON 格式
3. OpenTelemetry trace_id 集成
4. 服务元信息注入
5. 拦截所有日志（包括 uvicorn、sqlalchemy 等）统一输出
"""
import inspect
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

# 东八区时区（统一使用 +08:00）
CN_TZ = timezone(timedelta(hours=8))

from loguru import logger

from app.core.config import settings


class InterceptHandler(logging.Handler):
    """
    日志拦截处理器
    
    将 Python 标准库 logging 的日志重定向到 loguru
    这样 uvicorn、sqlalchemy 等库的日志也会被统一处理
    """
    
    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的 loguru 级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        
        # 查找实际的调用者（跳过 logging 模块的调用栈）
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        
        # 使用 loguru 记录日志
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _get_service_info() -> dict:
    """获取服务元信息"""
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",  # 可以从 __version__ 获取
        "env": settings.APP_ENV,
        "pod_name": settings.POD_NAME or os.getenv("HOSTNAME", ""),
        "node_name": settings.NODE_NAME or os.getenv("NODE_NAME", ""),
        "namespace": settings.NAMESPACE or os.getenv("NAMESPACE", ""),
    }


def _get_trace_info() -> dict:
    """获取追踪信息"""
    # 延迟导入避免循环依赖
    from app.core.trace import get_request_id, get_trace_id, get_span_id
    
    return {
        "trace_id": get_trace_id(),
        "span_id": get_span_id(),
        "request_id": get_request_id(),
    }


def create_json_sink(service_info: dict):
    """
    创建 JSON 日志 sink
    
    直接写入 stdout，绕过 loguru 的格式化处理
    """
    def json_sink(message):
        record = message.record
        
        # 获取追踪信息
        trace_info = _get_trace_info()
        
        # 构建日志对象
        log_record = {
            # 时间戳 - ISO 8601 格式，统一使用 +08:00 时区
            "timestamp": datetime.now(CN_TZ).isoformat(),
            # 日志级别
            "level": record["level"].name,
            # 日志消息
            "message": record["message"],
            # 服务信息
            **service_info,
            # 追踪信息
            **trace_info,
            # 代码位置
            "caller": {
                "file": record["file"].path,
                "line": record["line"],
                "function": record["function"],
            },
        }
        
        # 添加额外数据（如果有）
        if record["extra"]:
            # 过滤掉内部使用的字段
            extra = {
                k: v for k, v in record["extra"].items() 
                if not k.startswith("_")
            }
            if extra:
                log_record["extra"] = extra
        
        # 添加异常信息（如果有）
        if record["exception"]:
            exc = record["exception"]
            traceback_str = ""
            if exc.traceback:
                try:
                    traceback_list = list(exc.traceback) if hasattr(exc.traceback, '__iter__') else []
                    traceback_str = "".join(traceback_list) if traceback_list else ""
                except (TypeError, AttributeError):
                    traceback_str = str(exc.traceback) if exc.traceback else ""
            
            log_record["error"] = {
                "type": exc.type.__name__ if exc.type else "Exception",
                "message": str(exc.value) if exc.value else "",
                "stack_trace": traceback_str,
            }
        
        # 直接写入 stdout
        sys.stdout.write(json.dumps(log_record, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()
    
    return json_sink


class TextFormatter:
    """
    文本日志格式化器
    
    开发环境使用，带颜色和简洁格式
    """
    
    def __call__(self, record: dict) -> str:
        """格式化日志记录为文本"""
        # 获取追踪信息
        trace_info = _get_trace_info()
        request_id = trace_info["request_id"]
        
        # 截取 request_id 前 8 位便于阅读
        short_request_id = request_id[:8] if request_id and request_id != "-" else "-"
        
        # 构建基础格式字符串（不包含可能导致解析错误的 extra 数据）
        format_str = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            f"<cyan>{short_request_id}</cyan> | "
            "<level>{message}</level>"
        )
        
        # 如果有额外数据，转换为安全的字符串格式添加
        # 注意：不直接嵌入字典，避免 format_map 解析错误
        if record["extra"]:
            extra = {k: v for k, v in record["extra"].items() if not k.startswith("_")}
            if extra:
                # 使用 json 序列化确保安全，并用 repr 的方式显示
                extra_str = json.dumps(extra, ensure_ascii=False, default=str)
                # 转义花括号，避免被 format_map 解析
                extra_str = extra_str.replace("{", "{{").replace("}", "}}")
                format_str += f" | <dim>{extra_str}</dim>"
        
        format_str += "\n"
        
        # 如果有异常，添加堆栈跟踪
        if record["exception"]:
            format_str += "{exception}\n"
        
        return format_str


def setup_logging() -> None:
    """
    配置日志系统
    
    根据环境自动选择 JSON 或文本格式
    拦截所有标准库日志（uvicorn、sqlalchemy 等）统一处理
    """
    # 移除默认 handler
    logger.remove()
    
    # 获取服务信息
    service_info = _get_service_info()
    
    # 根据配置选择格式
    if settings.effective_log_format == "json":
        # 生产环境：JSON 格式到 stdout
        json_sink = create_json_sink(service_info)
        logger.add(
            json_sink,
            level=settings.LOG_LEVEL,
            colorize=False,
        )
    else:
        # 开发环境：彩色文本格式
        formatter = TextFormatter()
        logger.add(
            sys.stdout,
            format=formatter,
            level=settings.LOG_LEVEL,
            colorize=True,
        )
        
        # 开发环境额外写入文件（便于调试）
        log_path = Path("logs")
        log_path.mkdir(exist_ok=True)
        
        # 普通日志文件
        logger.add(
            log_path / "{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            level="DEBUG",
            rotation="00:00",
            retention="7 days",
            compression="zip",
            encoding="utf-8",
        )
        
        # 错误日志文件
        logger.add(
            log_path / "error_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}\n{exception}",
            level="ERROR",
            rotation="00:00",
            retention="30 days",
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
        )
    
    # === 拦截标准库日志 ===
    # 配置根日志处理器，将所有标准库日志转发到 loguru
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(settings.LOG_LEVEL)
    
    # 配置各个库的日志级别和传播规则
    for name in logging.root.manager.loggerDict.keys():
        # 清空所有默认处理器
        logging.getLogger(name).handlers = []
        
        # 配置特定库的行为
        if name.startswith("uvicorn"):
            # uvicorn 日志：传播到 root，由我们的 handler 处理
            logging.getLogger(name).propagate = True
        elif name.startswith("sqlalchemy"):
            # sqlalchemy 日志：传播到 root
            logging.getLogger(name).propagate = True
        elif name.startswith("watchfiles"):
            # watchfiles 日志：不传播（避免开发模式下的噪音）
            logging.getLogger(name).propagate = False
        else:
            # 其他日志：传播到 root
            logging.getLogger(name).propagate = True


def get_logger():
    """
    获取 logger 实例
    
    Returns:
        loguru logger 实例
    """
    return logger


# === 便捷日志函数 ===

def log_info(message: str, **kwargs: Any) -> None:
    """记录 INFO 级别日志"""
    logger.info(message, **kwargs)


def log_debug(message: str, **kwargs: Any) -> None:
    """记录 DEBUG 级别日志"""
    logger.debug(message, **kwargs)


def log_warning(message: str, **kwargs: Any) -> None:
    """记录 WARNING 级别日志"""
    logger.warning(message, **kwargs)


def log_error(message: str, exc_info: Optional[Exception] = None, **kwargs: Any) -> None:
    """记录 ERROR 级别日志"""
    if exc_info:
        logger.opt(exception=exc_info).error(message, **kwargs)
    else:
        logger.error(message, **kwargs)


def log_critical(message: str, exc_info: Optional[Exception] = None, **kwargs: Any) -> None:
    """记录 CRITICAL 级别日志"""
    if exc_info:
        logger.opt(exception=exc_info).critical(message, **kwargs)
    else:
        logger.critical(message, **kwargs)


# === 结构化日志函数（用于 HTTP 请求等）===

def log_http_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: str = "",
    user_agent: str = "",
    query_string: str = "",
    request_body: Optional[dict] = None,
    response_body: Optional[dict] = None,
    user_id: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """
    记录 HTTP 请求日志
    
    Args:
        method: HTTP 方法
        path: 请求路径
        status_code: 响应状态码
        duration_ms: 请求耗时（毫秒）
        client_ip: 客户端 IP
        user_agent: User-Agent
        query_string: 查询字符串
        request_body: 请求体（可选）
        response_body: 响应体（可选）
        user_id: 用户 ID（可选）
        error: 错误信息（可选）
    """
    # 构建 HTTP 信息
    http_info = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "client_ip": client_ip,
    }
    
    if query_string:
        http_info["query_string"] = query_string
    if user_agent:
        http_info["user_agent"] = user_agent
    
    # 构建日志消息
    message = f"HTTP {status_code} {method} {path} {duration_ms:.2f}ms"
    
    # 根据状态码选择日志级别
    if status_code >= 500:
        level = "ERROR"
    elif status_code >= 400:
        level = "WARNING"
    else:
        level = "INFO"
    
    # 记录日志（使用 bind 添加额外字段）
    log_entry = logger.bind(
        http=http_info,
        user_id=user_id,
    )
    
    if request_body:
        log_entry = log_entry.bind(request_body=request_body)
    if response_body:
        log_entry = log_entry.bind(response_body=response_body)
    if error:
        log_entry = log_entry.bind(error=error)
    
    log_entry.log(level, message)


def log_service_call(
    target_service: str,
    method: str,
    duration_ms: float,
    success: bool,
    error: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    记录服务间调用日志
    
    Args:
        target_service: 目标服务名
        method: 调用方法
        duration_ms: 调用耗时
        success: 是否成功
        error: 错误信息
        **kwargs: 其他信息
    """
    message = f"Service call to {target_service}/{method} {'succeeded' if success else 'failed'} in {duration_ms:.2f}ms"
    
    log_entry = logger.bind(
        service_call={
            "target_service": target_service,
            "method": method,
            "duration_ms": round(duration_ms, 2),
            "success": success,
        },
        **kwargs,
    )
    
    if success:
        log_entry.info(message)
    else:
        log_entry.bind(error=error).error(message)
