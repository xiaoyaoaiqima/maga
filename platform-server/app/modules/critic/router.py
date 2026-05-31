from fastapi import APIRouter

from app.modules.critic.endpoints import dapr_http_invoke

external_router = APIRouter()

internal_router = APIRouter()
internal_router.include_router(dapr_http_invoke.router)
