"""Tests for MAGA clean schema model registry and creation helpers."""
import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.maga_core import MAGA_CORE_MODELS, MAGA_CORE_TABLE_NAMES
from scripts.create_clean_schema import create_clean_schema


@pytest.mark.asyncio
async def test_clean_schema_creates_only_new_maga_core_tables():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    await create_clean_schema(engine)

    async with engine.connect() as conn:
        table_names = set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))

    assert table_names == set(MAGA_CORE_TABLE_NAMES)
    assert "job" not in table_names
    assert "sub_job" not in table_names
    assert "content" not in table_names
    assert "expert_business_result" not in table_names
    await engine.dispose()


def test_clean_registry_contains_phase1_core_models_and_not_legacy_models():
    model_names = {model.__name__ for model in MAGA_CORE_MODELS}

    assert {
        "ExecutorRegistry",
        "ContentBrief",
        "BriefSnapshot",
        "ContentAgentTask",
        "ContentAgentRun",
        "ContentAgentEvent",
        "ContentAgentArtifact",
    }.issubset(model_names)
    assert "Job" not in model_names
    assert "SubJob" not in model_names
    assert "Content" not in model_names
