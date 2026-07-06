"""Tests for MAGA clean schema model registry and creation helpers."""
import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.maga_core import MAGA_CORE_MODELS, MAGA_CORE_TABLE_NAMES
from app.models.maga_core import MAGA_STARTUP_TABLE_NAMES
from app.models.sys_menu import SysMenu
from app.models.sys_user import SysUser
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
        "LLMProviderConfig",
        "LLMModelRoute",
    }.issubset(model_names)
    assert "Job" not in model_names
    assert "SubJob" not in model_names
    assert "Content" not in model_names


@pytest.mark.asyncio
async def test_startup_schema_creates_runtime_tables_without_legacy_shells():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Base.metadata.tables[name] for name in MAGA_STARTUP_TABLE_NAMES]

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(SysUser(id="admin-id", username="admin", password="hash", status=1))
        session.add(SysMenu(id="dashboard", menu_name="Dashboard", menu_type="M", parent_id="0"))
        await session.commit()
        admin = await session.scalar(select(SysUser).where(SysUser.username == "admin"))
        menu_count = await session.scalar(select(func.count()).select_from(SysMenu))

    async with engine.connect() as conn:
        table_names = set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))

    await engine.dispose()

    assert table_names == set(MAGA_STARTUP_TABLE_NAMES)
    assert {"sys_user", "sys_role", "sys_menu", "sys_user_role", "sys_role_menu"}.issubset(table_names)
    assert admin is not None
    assert menu_count and menu_count > 0
    assert "job" not in table_names
    assert "content" not in table_names
    assert "raap_dashboard_data_cache_response" not in table_names
