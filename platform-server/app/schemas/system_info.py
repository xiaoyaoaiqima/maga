"""
System Information Schemas
"""
from typing import Dict, Optional
from app.schemas.base import BaseSchema


class K8sInfo(BaseSchema):
    """Kubernetes environment information"""
    pod_name: str
    node_name: str
    namespace: str


class DatabaseInfo(BaseSchema):
    """Desensitized database connection information"""
    host: str
    port: int
    user: str
    database: str
    adminer_url: Optional[str] = None


class RedisInfo(BaseSchema):
    """Desensitized redis connection information"""
    host: str
    port: int
    db: int
    insight_url: Optional[str] = None


class ServiceHealth(BaseSchema):
    """Service health status"""
    status: str
    version: Optional[str] = None
    last_check: Optional[str] = None


class SystemInfoResponse(BaseSchema):
    """System information response"""
    app_env: str
    k8s: K8sInfo
    database: DatabaseInfo
    redis: RedisInfo
    services: Dict[str, ServiceHealth]
