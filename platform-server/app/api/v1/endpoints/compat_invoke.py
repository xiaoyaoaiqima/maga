"""
Internal compatibility routes.

These routes preserve the old Dapr invoke shape while forwarding requests
to in-process module routers mounted under /__internal.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter()

APP_ID_PATH_PREFIX = {
    "raap-service-ag": "/__internal/critic",
    "raap-service-generation-experts": "/__internal/generation",
}


def _resolve_internal_path(app_id: str, method_path: str) -> str:
    if app_id not in APP_ID_PATH_PREFIX:
        raise HTTPException(status_code=404, detail=f"未知内部服务: {app_id}")
    if not method_path.startswith("/"):
        method_path = f"/{method_path}"
    return f"{APP_ID_PATH_PREFIX[app_id]}{method_path}"


@router.api_route(
    "/v1.0/invoke/{app_id}/method/{method_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def compat_invoke(request: Request, app_id: str, method_path: str) -> Any:
    target_path = _resolve_internal_path(app_id, f"/{method_path}")
    url = f"{settings.internal_service_base_url}{target_path}"
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.request(
                request.method,
                url,
                params=list(request.query_params.multi_items()),
                content=body if body else None,
                headers=headers or None,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"内部模块调用失败: {exc}") from exc

    try:
        payload = resp.json()
    except json.JSONDecodeError:
        payload = {"code": resp.status_code, "message": resp.text, "data": None}

    return JSONResponse(status_code=resp.status_code, content=payload)
