"""
Health check schemas
"""
from datetime import datetime

from app.schemas.base import BaseSchema


class HealthResponse(BaseSchema):
    """Health check response"""
    status: str = "healthy"
    timestamp: datetime
    service: str
    version: str
    dependencies: dict[str, str] = {}

