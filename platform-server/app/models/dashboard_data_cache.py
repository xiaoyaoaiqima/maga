"""Dashboard data cache models.

These optional tables support the legacy AI dashboard cache/demo-data layer.
They should be present in local/dev schemas when `Base.metadata.create_all()`
runs, but the service still degrades gracefully if a historical DB is missing
these tables.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.content_agent import BIGINT_PK


class DashboardDataCacheResponse(Base):
    """Cached dashboard API response."""

    __tablename__ = "raap_dashboard_data_cache_response"
    __table_args__ = (
        UniqueConstraint("cache_key", "cache_group", name="uk_dashboard_cache_key_group"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键 ID")
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="Physical key")
    logical_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True, comment="Logical key")
    cache_group: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="Cache group")
    response_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="未压缩响应 JSON")
    response_compressed: Mapped[Optional[bytes]] = mapped_column(LargeBinary(length=16 * 1024 * 1024), nullable=True, comment="gzip 响应")
    response_data_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="响应大小")
    request_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="请求参数")
    tenant_id: Mapped[Optional[int]] = mapped_column(BIGINT_PK, nullable=True, index=True, comment="租户 ID")
    cache_watermark: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="缓存生成时间")
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="300", comment="TTL 秒")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment="过期时间")
    is_expired: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", index=True, comment="是否过期")
    hit_count: Mapped[int] = mapped_column(BIGINT_PK, nullable=False, server_default="0", index=True, comment="命中次数")
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后命中时间")
    auto_refresh_enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", index=True, comment="是否自动刷新")
    auto_refresh_interval: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="自动刷新间隔")
    next_refresh_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True, comment="下次刷新时间")
    refresh_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="idle", index=True, comment="刷新状态")
    last_refresh_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后刷新时间")
    last_refresh_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="最后刷新结果")
    last_refresh_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="最后刷新错误")
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="领取时间")
    claimed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="领取节点")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class DashboardDataCacheRefreshConfig(Base):
    """Dashboard cache refresh configuration."""

    __tablename__ = "raap_dashboard_data_cache_refresh_config"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键 ID")
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True, comment="Physical key")
    logical_key: Mapped[str] = mapped_column(String(500), nullable=False, comment="Logical key")
    cache_group: Mapped[str] = mapped_column(String(100), nullable=False, comment="Cache group")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否启用")
    refresh_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=300, comment="刷新间隔")
    backoff_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否退避")
    max_backoff_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=3600, comment="最大退避间隔")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class DashboardDataCacheRefreshHistory(Base):
    """Dashboard cache refresh history."""

    __tablename__ = "raap_dashboard_data_cache_refresh_history"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键 ID")
    logical_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True, comment="Logical key")
    refresh_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, comment="刷新状态")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="开始时间")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="完成时间")
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="耗时秒")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class DashboardDataCacheDemoConfig(Base):
    """Dashboard demo data configuration."""

    __tablename__ = "raap_dashboard_data_cache_demo_config"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键 ID")
    demo_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True, comment="演示数据键")
    demo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="演示数据名称")
    demo_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True, comment="是否启用")
    demo_type: Mapped[str] = mapped_column(String(32), nullable=False, default="static", index=True, comment="演示类型")
    global_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="全局演示开关")
    static_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="静态演示数据")
    dynamic_rule_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="动态规则类型")
    dynamic_rule_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="动态规则配置")
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="有效期开始")
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="有效期结束")
    hit_count: Mapped[int] = mapped_column(BIGINT_PK, nullable=False, default=0, comment="命中次数")
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后命中时间")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)


class DashboardDataCacheDistributedLock(Base):
    """Distributed lock for dashboard cache warmup."""

    __tablename__ = "raap_dashboard_data_cache_distributed_lock"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键 ID")
    lock_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True, comment="锁键")
    lock_holder: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="锁持有者")
    lock_token: Mapped[str] = mapped_column(String(36), nullable=False, comment="锁令牌")
    acquired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="获取时间")
    expire_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment="过期时间")
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="兼容历史字段")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="兼容历史字段")
    locked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="兼容历史字段")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class DashboardDataCacheWarmupConfig(Base):
    """Dashboard cache warmup configuration."""

    __tablename__ = "raap_dashboard_data_cache_warmup_config"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True, comment="主键 ID")
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True, comment="Physical key")
    logical_key: Mapped[str] = mapped_column(String(500), nullable=False, comment="Logical key")
    cache_group: Mapped[str] = mapped_column(String(100), nullable=False, comment="Cache group")
    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Endpoint")
    request_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="请求参数")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True, comment="预热优先级")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否启用")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
