from fastapi import APIRouter

from app.modules.critic.endpoints import ban_terms, dapr_http_invoke

external_router = APIRouter()
external_router.include_router(ban_terms.router)

internal_router = APIRouter()
internal_router.include_router(ban_terms.router)
internal_router.include_router(dapr_http_invoke.router)
