"""
代理层下游错误解析：统一从 httpx 响应中提取 detail 并 raise HTTPException。
便于前端与全局异常处理器得到一致的错误体。
"""
import json
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from loguru import logger


def _detail_to_str(detail: Any) -> str:
    """将 detail（可能为 list/dict，如 422 校验错误）转为字符串"""
    if isinstance(detail, str):
        return detail
    if detail is None:
        return ""
    try:
        return json.dumps(detail, ensure_ascii=False)
    except Exception:
        return str(detail)


def parse_downstream_error(
    resp: httpx.Response,
    log_prefix: str = "",
    max_detail_len: int = 500,
) -> None:
    """
    若 resp.status_code >= 400，则解析下游错误、打日志并抛出 HTTPException。
    否则不抛异常，由调用方继续处理。

    - 优先从 JSON 中取 detail 或 message，避免把整段 JSON 当文案展示
    - 日志统一带上 path/status_code 与截断的 detail，便于排查
    """
    if resp.status_code < 400:
        return

    raw = resp.text
    detail: Any = None
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("message") or body.get("error")
        if detail is None:
            detail = raw
    except Exception:
        detail = raw

    detail_str = _detail_to_str(detail) if detail is not None else raw or f"HTTP {resp.status_code}"

    log_msg = f"{log_prefix}下游返回错误 status={resp.status_code} detail={detail_str[:max_detail_len]!r}"
    if len(detail_str) > max_detail_len:
        log_msg += "..."
    logger.warning(log_msg)

    raise HTTPException(status_code=resp.status_code, detail=detail_str)
