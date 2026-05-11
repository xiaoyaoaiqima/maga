import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.dashboard_data_cache_service import MySQLDashboardDataCacheService


@pytest.mark.asyncio
async def test_cache_get_treats_missing_optional_cache_tables_as_cache_miss():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            service = MySQLDashboardDataCacheService(session)

            cached = await service.get(
                cache_key="missing-cache-key",
                cache_group="metric_query_paginated",
                check_demo=True,
            )

        assert cached is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cache_set_ignores_missing_optional_cache_table():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            service = MySQLDashboardDataCacheService(session)

            await service.set(
                cache_key="missing-cache-key",
                logical_key="metric_query_paginated:missing-cache-key",
                cache_group="metric_query_paginated",
                data={"data": [], "pagination": {"total": 0}},
                ttl_seconds=60,
                request_params={"metric_key": "job_task_list"},
            )
    finally:
        await engine.dispose()

class _CaptureSession:
    def __init__(self):
        self.statement = None
        self.params = None
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement, params=None):
        self.statement = str(statement)
        self.params = params or {}

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_cache_set_explicitly_initializes_hit_count_for_tables_without_default():
    session = _CaptureSession()
    service = MySQLDashboardDataCacheService(session)

    await service.set(
        cache_key="cache-key",
        logical_key="metric_query_paginated:cache-key",
        cache_group="metric_query_paginated",
        data={"data": [], "pagination": {"total": 0}},
        ttl_seconds=60,
        request_params={"metric_key": "job_task_list"},
    )

    assert session.committed is True
    assert session.rolled_back is False
    assert "hit_count" in session.statement
    assert session.params["hit_count"] == 0

