"""API tests for starting protocol v0.1 generation runs."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.content_agent import router
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import ContentAgentTask, ExecutorRegistry
from app.models.llm_provider_config import LLMProviderConfig
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.models.maga_assets import AssetRegistry
from app.models.prompt_optimizer import PromptAsset, PromptVersion
from app.services.asset_import_service import WORKER_STATIC_ASSET_SOURCE_NAME
from fastapi import FastAPI


@pytest_asyncio.fixture
async def start_generation_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="hermes_maga_worker",
                executor_type="hermes_profile",
                profile_name="maga-worker",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                supported_capabilities_json=[
                    {"capability": "xhs.interpret_brief", "schema_version": "1"},
                    {"capability": "xhs.run_ae_analysis", "schema_version": "1"},
                    {"capability": "xhs.generate_draft", "schema_version": "1"},
                    {"capability": "xhs.run_ae_review", "schema_version": "1"},
                    {"capability": "xhs.rewrite_draft", "schema_version": "1"},
                ],
            )
        )
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/content-agent")

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_start_generation_endpoint_returns_publishable_title_and_body(start_generation_client):
    client, _session_factory = start_generation_client
    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={
            "product_topic": "美素佳儿源悦",
            "target_audience": "新手妈妈",
            "style": "情绪共情",
            "executor_code": "hermes_maga_worker",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task_id"]
    assert data["run_id"]
    assert data["title"]
    assert data["body"]
    assert "美素佳儿源悦" in data["title"]
    assert "新手妈妈" in data["body"]
    assert "output" not in data
    assert "stage_call_id" not in data
    assert "capability" not in data


@pytest.mark.asyncio
async def test_start_generation_endpoint_does_not_send_default_model_override(start_generation_client):
    client, session_factory = start_generation_client
    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={
            "product_topic": "美素佳儿源悦",
            "target_audience": "新手妈妈",
            "style": "情绪共情",
        },
    )

    assert response.status_code == 200
    async with session_factory() as session:
        task = (await session.execute(select(ContentAgentTask))).scalars().first()

    assert task.input_snapshot["generation_snapshot"]["model_config"] == {}


@pytest.mark.asyncio
async def test_start_generation_endpoint_uses_maga_default_provider_model(start_generation_client):
    client, session_factory = start_generation_client
    async with session_factory() as session:
        session.add(
            LLMProviderConfig(
                id=1,
                provider_code="aihubmix",
                provider_name="AIHubMix",
                provider_type="openai_compatible",
                base_url="https://api.example.test/v1",
                api_key="test-key",
                default_model="deepseek-v4-flash",
                priority=100,
                enabled=1,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={
            "product_topic": "美素佳儿源悦",
            "target_audience": "新手妈妈",
            "style": "情绪共情",
        },
    )

    assert response.status_code == 200
    async with session_factory() as session:
        task = (await session.execute(select(ContentAgentTask))).scalars().first()

    assert task.input_snapshot["generation_snapshot"]["model_config"] == {
        "ge_model": "deepseek-v4-flash",
        "ae_model": "deepseek-v4-flash",
    }


@pytest.mark.asyncio
async def test_start_generation_endpoint_uses_default_executor_when_form_sends_blank_code(start_generation_client):
    client, _session_factory = start_generation_client
    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={"product_topic": "美素佳儿源悦", "executor_code": "  "},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"]
    assert data["body"]


@pytest.mark.asyncio
async def test_start_generation_endpoint_returns_404_when_executor_missing(start_generation_client):
    client, _session_factory = start_generation_client
    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={"product_topic": "美素佳儿源悦", "executor_code": "missing_executor"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_start_generation_endpoint_persists_maga_model_config(start_generation_client):
    client, session_factory = start_generation_client
    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={
            "product_topic": "美素佳儿源悦",
            "model_config": {"ge_model": "maga-ge", "ae_model": "maga-ae"},
        },
    )

    assert response.status_code == 200
    async with session_factory() as session:
        task = (await session.execute(select(ContentAgentTask))).scalars().first()

    assert task.input_snapshot["generation_snapshot"]["model_config"] == {
        "ge_model": "maga-ge",
        "ae_model": "maga-ae",
    }


@pytest.mark.asyncio
async def test_start_generation_endpoint_persists_prompt_bundle_snapshot(start_generation_client):
    client, session_factory = start_generation_client
    async with session_factory() as session:
        prompt = PromptAsset(name="xhs_writer.ge.soul", prompt_type="generation", tags=["ge"])
        session.add(prompt)
        await session.flush()
        version = PromptVersion(prompt_id=prompt.id, version_no=1, content="你是 GE 主写手。")
        session.add(version)
        await session.flush()
        prompt.current_version_id = version.id
        session.add(
            AssetRegistry(
                asset_type="expert_corpus",
                asset_key="compliance_redline",
                version_no=1,
                status="active",
                source_name=WORKER_STATIC_ASSET_SOURCE_NAME,
                source_hash="corpus-hash",
                content_json={"content": {"expert": "compliance_redline"}},
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={"product_topic": "美素佳儿源悦"},
    )

    assert response.status_code == 200
    async with session_factory() as session:
        task = (await session.execute(select(ContentAgentTask))).scalars().first()

    bundle = task.input_snapshot["generation_snapshot"]["prompt_bundle_snapshot"]
    assert bundle["prompts"]["xhs_writer.ge.soul"]["version_id"] == version.id
    assert bundle["prompts"]["xhs_writer.ge.soul"]["content"] == "你是 GE 主写手。"
    assert bundle["assets"]["expert_corpus:compliance_redline"]["source_hash"] == "corpus-hash"
