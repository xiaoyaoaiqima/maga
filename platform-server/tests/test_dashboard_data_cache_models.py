"""Tests for optional Dashboard data cache SQLAlchemy models."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.base import Base
from app.models.dashboard_data_cache import (
    DashboardDataCacheDemoConfig,
    DashboardDataCacheResponse,
)


@pytest.mark.asyncio
async def test_dashboard_cache_models_create_tables_used_by_cache_service():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[
                    DashboardDataCacheResponse.__table__,
                    DashboardDataCacheDemoConfig.__table__,
                ],
            )

        async with engine.connect() as conn:
            tables = set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))
            response_columns = {
                column["name"]
                for column in await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_columns("raap_dashboard_data_cache_response")
                )
            }
            demo_columns = {
                column["name"]
                for column in await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_columns("raap_dashboard_data_cache_demo_config")
                )
            }

        assert "raap_dashboard_data_cache_response" in tables
        assert "raap_dashboard_data_cache_demo_config" in tables
        assert {
            "cache_key",
            "logical_key",
            "cache_group",
            "response_data",
            "response_compressed",
            "request_params",
            "cache_watermark",
            "expires_at",
            "refresh_status",
        }.issubset(response_columns)
        assert {
            "demo_key",
            "demo_name",
            "demo_enabled",
            "demo_type",
            "global_enabled",
            "static_data",
            "dynamic_rule_type",
            "dynamic_rule_config",
            "valid_from",
            "valid_until",
        }.issubset(demo_columns)
    finally:
        await engine.dispose()
