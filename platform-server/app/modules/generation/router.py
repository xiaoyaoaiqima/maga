from fastapi import APIRouter

from app.modules.generation.endpoints import dapr_http_invoke

internal_router = APIRouter()
internal_router.include_router(dapr_http_invoke.router)
