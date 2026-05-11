"""Tests for clean schema seed data."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.content_agent import ExecutorRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.models.base import Base
from scripts.create_clean_schema import seed_clean_schema


@pytest.mark.asyncio
async def test_seed_clean_schema_registers_hermes_maga_worker_executor():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await seed_clean_schema(conn, maga_worker_invoke_url="http://127.0.0.1:8765/invoke")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        executor = await session.scalar(
            select(ExecutorRegistry).where(ExecutorRegistry.executor_code == "hermes_maga_worker")
        )

    await engine.dispose()

    assert executor is not None
    assert executor.display_name == "Hermes MAGA worker"
    assert executor.executor_type == "hermes_profile"
    assert executor.profile_name == "maga-worker"
    assert executor.protocol_version == "0.1"
    assert executor.invoke_url == "http://127.0.0.1:8765/invoke"
    assert executor.config_json == {"executor_token": "test-token"}
    capabilities = {item["capability"] for item in executor.supported_capabilities_json}
    assert capabilities >= {
        "xhs.interpret_brief",
        "xhs.run_ae_analysis",
        "xhs.generate_draft",
        "xhs.run_ae_review",
        "xhs.rewrite_draft",
    }
    assert "asset.query" not in capabilities
    assert "feedback.collect" not in capabilities
