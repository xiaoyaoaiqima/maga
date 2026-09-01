"""Tests for clean schema seed data."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.agent import Agent
from app.models.content_agent import ContentFeedback, ExecutorRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES, MAGA_STARTUP_TABLE_NAMES
from app.models.base import Base
from app.models.sys_role_menu import SysRoleMenu
from app.models.sys_user_role import SysUserRole
from app.services.content_agent_bootstrap_service import (
    DEFAULT_REALTIME_CHAT_AGENT_CODE,
    seed_default_content_agent_executors,
    seed_default_realtime_chat_agent,
)
from scripts.create_clean_schema import seed_clean_schema


@pytest.mark.asyncio
async def test_seed_clean_schema_registers_direct_llm_executor():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await seed_clean_schema(conn, direct_llm_invoke_url="llm://direct/content")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        executor = await session.scalar(
            select(ExecutorRegistry).where(ExecutorRegistry.executor_code == "maga_direct_llm_executor")
        )

    await engine.dispose()

    assert executor is not None
    assert executor.display_name == "MAGA direct LLM executor"
    assert executor.executor_type == "direct_llm"
    assert executor.profile_name is None
    assert executor.protocol_version == "0.1"
    assert executor.invoke_url == "llm://direct/content"
    assert executor.config_json is None
    capabilities = {item["capability"] for item in executor.supported_capabilities_json}
    assert capabilities == {"content.generate", "content.rewrite"}
    assert "asset.query" not in capabilities
    assert "feedback.collect" not in capabilities


@pytest.mark.asyncio
async def test_seed_clean_schema_registers_default_realtime_chat_agent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await seed_clean_schema(conn, direct_llm_invoke_url="llm://direct/content")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        agent = await session.scalar(
            select(Agent).where(Agent.agent_code == DEFAULT_REALTIME_CHAT_AGENT_CODE)
        )

    await engine.dispose()

    assert agent is not None
    assert agent.agent_type == "REALTIME_CHAT"
    assert agent.enabled == 1
    assert agent.publish_status == "PUBLISHED"
    assert agent.default_model_code == "deepseek-v4-flash"
    assert agent.default_config["system_prompt"]


@pytest.mark.asyncio
async def test_sqlite_startup_association_tables_autoincrement_ids():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_STARTUP_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_role = SysUserRole(user_id="local-user", role_id="local-role")
        role_menu = SysRoleMenu(role_id="local-role", menu_id="local-menu")
        session.add_all([user_role, role_menu])
        await session.commit()

    await engine.dispose()

    assert user_role.id == 1
    assert role_menu.id == 1


@pytest.mark.asyncio
async def test_clean_schema_includes_content_feedback_table():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        feedback = ContentFeedback(
            batch_id=1,
            item_id=1,
            action="request_revision",
            review_status="needs_revision",
            comment="开头像真实妈妈一点",
            submitter="reviewer-a",
        )
        session.add(feedback)
        await session.commit()

        saved = await session.scalar(select(ContentFeedback).where(ContentFeedback.item_id == 1))

    await engine.dispose()

    assert saved is not None
    assert saved.comment == "开头像真实妈妈一点"
    assert saved.submitter == "reviewer-a"


@pytest.mark.asyncio
async def test_seed_clean_schema_updates_existing_executor_url():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await seed_clean_schema(conn, direct_llm_invoke_url="mock://direct-llm/content")
        await seed_clean_schema(conn, direct_llm_invoke_url="direct://provider/content")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        executors = (
            await session.execute(
                select(ExecutorRegistry).where(ExecutorRegistry.executor_code == "maga_direct_llm_executor")
            )
        ).scalars().all()

    await engine.dispose()

    assert len(executors) == 1
    assert executors[0].invoke_url == "direct://provider/content"


@pytest.mark.asyncio
async def test_startup_bootstrap_does_not_overwrite_existing_executor_url():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await seed_default_content_agent_executors(
            conn,
            direct_llm_invoke_url="direct://provider/content",
            overwrite=True,
        )
        await seed_default_content_agent_executors(
            conn,
            direct_llm_invoke_url="mock://direct-llm/content",
            overwrite=False,
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        executor = await session.scalar(
            select(ExecutorRegistry).where(ExecutorRegistry.executor_code == "maga_direct_llm_executor")
        )

    await engine.dispose()

    assert executor is not None
    assert executor.invoke_url == "direct://provider/content"
    assert executor.config_json is None


@pytest.mark.asyncio
async def test_startup_bootstrap_does_not_overwrite_existing_realtime_chat_agent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await seed_default_realtime_chat_agent(conn, overwrite=True)
        await conn.execute(
            Agent.__table__.update()
            .where(Agent.agent_code == DEFAULT_REALTIME_CHAT_AGENT_CODE)
            .values(default_model_code="custom-model", updated_by="operator")
        )
        await seed_default_realtime_chat_agent(conn, overwrite=False)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        agent = await session.scalar(
            select(Agent).where(Agent.agent_code == DEFAULT_REALTIME_CHAT_AGENT_CODE)
        )

    await engine.dispose()

    assert agent is not None
    assert agent.default_model_code == "custom-model"
    assert agent.updated_by == "operator"
