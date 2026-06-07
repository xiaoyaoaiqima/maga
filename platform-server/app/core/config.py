"""
Application Configuration
"""

import os
from functools import lru_cache
from typing import Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Application
    APP_NAME: str = "maga_platform_server"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    MAGA_APP_MODE: Literal["full", "clean"] = "full"
    APP_DEBUG: bool = True
    APP_PORT: int = 5100

    # MySQL
    DATABASE_URL: str = ""  # 可选：覆盖主库连接，便于本地 SQLite smoke test
    MYSQL_HOST: str = "mysql"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "maga"
    MYSQL_PASSWORD: str = "maga123456"
    MYSQL_DATABASE: str = "maga"
    MYSQL_ECHO: bool = False
    MYSQL_POOL_SIZE: int = 20  # 增加连接池大小以支持更多并发任务
    MYSQL_MAX_OVERFLOW: int = 40  # 增加最大溢出连接数


    # MySQL - 分析库（Dashboard 专用，pre/prod 共用）
    # 注意：此配置为硬编码默认值，用于 pre/生产环境快速上线
    MYSQL_ANALYTICS_ENABLED: str = ""  # 分析库开关（空值=自动判断，true/false=强制开关）
    MYSQL_ANALYTICS_HOST: str = "mysql"
    MYSQL_ANALYTICS_PORT: int = 3306
    MYSQL_ANALYTICS_USER: str = "maga"
    MYSQL_ANALYTICS_PASSWORD: str = "maga123456"
    MYSQL_ANALYTICS_DATABASE: str = "maga"
    MYSQL_ANALYTICS_POOL_SIZE: int = 10
    MYSQL_ANALYTICS_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_TIMEOUT: int = 5

    # Rate Limiting - 限流配置
    RATE_LIMIT_ENABLED: bool = True  # 是否启用限流
    RATE_LIMIT_DEFAULT_REQUESTS: int = 10  # 默认请求数/秒
    RATE_LIMIT_DEFAULT_WINDOW: int = 1  # 默认时间窗口（秒）
    RATE_LIMIT_AG_REQUESTS: int = 5  # AG 服务限制（AI 调用成本高）
    RATE_LIMIT_GENERATION_EXPERTS_REQUESTS: int = 5  # 生成专家服务

    # JWT
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天

    # Internal invoke compatibility
    DAPR_HTTP_PORT: int = 5100
    DAPR_GRPC_PORT: int = 50001
    DAPR_HTTP_MAX_CONNECTIONS: int = 100
    DAPR_HTTP_MAX_KEEPALIVE_CONNECTIONS: int = 20
    DAPR_HTTP_KEEPALIVE_EXPIRY: int = 30

    # Job execution tuning
    JOB_GENERATION_BATCH_SIZE: int = 6
    JOB_CRITIC_BATCH_SIZE: int = 5
    JOB_MAX_ACTIVE_GENERATION_SUBTASKS: int = 12
    JOB_MAX_ACTIVE_CRITIC_SUBTASKS: int = 16

    # OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    # Redash 配置
    REDASH_ENABLED: bool = True
    REDASH_BASE_URL: str = "http://redash-service:5000"
    REDASH_API_KEY: str = ""  # 需要从 Redash 获取 User API Key
    REDASH_REQUEST_TIMEOUT: int = 30  # API 请求超时（秒）

    # Adminer 配置
    ADMINER_URL: Optional[str] = None
    # Redis Insight 配置
    REDIS_INSIGHT_URL: Optional[str] = None

    # ✅ v1.4: Dashboard 缓存系统配置
    DASHBOARD_CACHE_ENABLED: bool = True  # 缓存开关
    RAAP_ORCHESTRATOR_MASTER: bool = False  # Master 节点标识
    CACHE_WARMUP_ON_STARTUP: bool = False  # 缓存预热

    # Logging - 日志配置
    LOG_FORMAT: Literal["json", "text"] = "json"  # 默认 JSON 格式，所有环境统一
    LOG_LEVEL: str = "INFO"
    LOG_INCLUDE_REQUEST_BODY: bool = False  # 是否记录请求 body
    LOG_INCLUDE_RESPONSE_BODY: bool = False  # 是否记录响应 body
    LOG_SENSITIVE_MASK_ENABLED: bool = False  # 敏感数据脱敏开关（开发环境默认关闭）
    LOG_SENSITIVE_FIELDS: list[str] = [
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "secret_key",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "phone",
        "mobile",
        "telephone",
        "id_card",
        "idcard",
        "identity",
        "credit_card",
        "card_number",
        "email",
    ]

    # Runtime metadata
    POD_NAME: str = ""
    NODE_NAME: str = ""
    NAMESPACE: str = ""

    # 腾讯云 COS 配置
    COS_SECRET_ID: str = ""
    COS_SECRET_KEY: str = ""
    COS_REGION: str = "ap-shanghai"
    COS_BUCKET_NAME: str = ""
    COS_DOMAIN: str = ""

    INTERNAL_SERVICE_BASE_URL: str = ""

    @property
    def MYSQL_DATABASE_URL(self) -> str:
        """Generate MySQL database URL (主库)"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def MYSQL_ANALYTICS_DATABASE_URL(self) -> str:
        """Generate MySQL analytics database URL (分析库)"""
        return (
            f"mysql+aiomysql://{self.MYSQL_ANALYTICS_USER}:{self.MYSQL_ANALYTICS_PASSWORD}"
            f"@{self.MYSQL_ANALYTICS_HOST}:{self.MYSQL_ANALYTICS_PORT}/{self.MYSQL_ANALYTICS_DATABASE}"
        )

    @field_validator(
        "APP_DEBUG",
        "LOG_SENSITIVE_MASK_ENABLED",
        "LOG_INCLUDE_REQUEST_BODY",
        "LOG_INCLUDE_RESPONSE_BODY",
        mode="before",
    )
    @classmethod
    def parse_bool(cls, v):
        """Parse boolean value"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.APP_ENV == "production"

    @property
    def is_maga_clean_mode(self) -> bool:
        """Whether the server should expose only the MAGA content-production surface."""
        return self.MAGA_APP_MODE == "clean"

    @property
    def effective_log_format(self) -> str:
        """Get effective log format based on environment"""
        # 生产环境强制使用 JSON 格式
        if self.is_production:
            return "json"
        return self.LOG_FORMAT

    @property
    def effective_sensitive_mask(self) -> bool:
        """Get effective sensitive mask setting"""
        # 生产环境强制开启脱敏
        if self.is_production:
            return True
        return self.LOG_SENSITIVE_MASK_ENABLED

    @property
    def analytics_enabled(self) -> bool:
        """
        分析库是否启用（优先级：显式配置 > 环境自动判断）

        规则：
        - 如果 MYSQL_ANALYTICS_ENABLED 为空字符串：pre/prod 自动启用，dev 不启用
        - 如果 MYSQL_ANALYTICS_ENABLED 为 "true"/"1"/"yes"：强制启用
        - 如果 MYSQL_ANALYTICS_ENABLED 为 "false"/"0"/"no"：强制禁用

        Returns:
            bool: True 表示启用分析库，False 表示使用主库
        """
        # 优先检查显式配置
        if self.MYSQL_ANALYTICS_ENABLED:
            if isinstance(self.MYSQL_ANALYTICS_ENABLED, str):
                return self.MYSQL_ANALYTICS_ENABLED.lower() in ("true", "1", "yes")
            return bool(self.MYSQL_ANALYTICS_ENABLED)

        # 未显式配置时，pre/prod 自动启用
        return self.APP_ENV in ("staging", "production")

    @property
    def internal_service_base_url(self) -> str:
        if self.INTERNAL_SERVICE_BASE_URL:
            return self.INTERNAL_SERVICE_BASE_URL.rstrip("/")
        host = os.getenv("INTERNAL_SERVICE_HOST", "127.0.0.1")
        port = int(os.getenv("INTERNAL_SERVICE_PORT", str(self.APP_PORT)))
        return f"http://{host}:{port}"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
