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
from app.models.expert_config import ExpertConfig
from app.models.llm_model_route import LLMModelRoute
from app.models.llm_provider_config import LLMProviderConfig
from app.models.maga_assets import AssetRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
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
                    {"capability": "xhs.review_and_rewrite", "schema_version": "1"},
                    {"capability": "xhs.run_ae_review", "schema_version": "1"},
                    {"capability": "xhs.rewrite_draft", "schema_version": "1"},
                    {"capability": "content.generate", "schema_version": "1"},
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

    assert task.task_type == "content_generate"
    assert task.input_snapshot["capability"] == "content.generate"
    assert task.input_snapshot["model_config"] == {}


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

    assert task.input_snapshot["model_config"] == {
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

    assert task.input_snapshot["model_config"] == {
        "ge_model": "maga-ge",
        "ae_model": "maga-ae",
    }


@pytest.mark.asyncio
async def test_start_generation_endpoint_persists_unified_prompt_snapshot(start_generation_client):
    client, session_factory = start_generation_client
    response = await client.post(
        "/api/v1/content-agent/generation/start",
        json={"product_topic": "美素佳儿源悦", "target_audience": "新手妈妈"},
    )

    assert response.status_code == 200
    async with session_factory() as session:
        task = (await session.execute(select(ContentAgentTask))).scalars().first()

    assert task.input_snapshot["expert"]["expert_config_code"] == "article_generator_v1"
    assert "美素佳儿源悦" in task.input_snapshot["rendered_prompt"]
    assert "新手妈妈" in task.input_snapshot["rendered_prompt"]
    assert task.input_snapshot["selected_keywords"]


@pytest.mark.asyncio
async def test_preflight_check_blocks_missing_worker_rewrite_capability(start_generation_client):
    client, session_factory = start_generation_client
    await _seed_preflight_dependencies(session_factory)

    response = await client.post(
        "/api/v1/content-agent/preflight-check",
        json={
            "asset_key": "yuanyue_comment_activity",
            "asset_type": "comment_angle_rule_set",
            "executor_code": "hermes_maga_worker",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["passed"] is False
    assert data["blocking_codes"] == ["worker_capabilities"]


@pytest.mark.asyncio
async def test_preflight_check_passes_when_generation_flow_is_ready(start_generation_client):
    client, session_factory = start_generation_client
    await _seed_preflight_dependencies(session_factory, include_rewrite_capability=True)

    response = await client.post(
        "/api/v1/content-agent/preflight-check",
        json={
            "asset_key": "yuanyue_comment_activity",
            "asset_type": "comment_angle_rule_set",
            "executor_code": "hermes_maga_worker",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["passed"] is True
    assert data["content_type"] == "comment"
    assert "worker_capabilities" not in data["blocking_codes"]


async def _seed_preflight_dependencies(session_factory, *, include_rewrite_capability: bool = False):
    async with session_factory() as session:
        executor = (
            await session.execute(
                select(ExecutorRegistry).where(ExecutorRegistry.executor_code == "hermes_maga_worker")
            )
        ).scalar_one()
        if include_rewrite_capability:
            executor.supported_capabilities_json = [
                *(executor.supported_capabilities_json or []),
                {"capability": "content.rewrite", "schema_version": "1"},
            ]
        session.add(
            AssetRegistry(
                asset_type="comment_angle_rule_set",
                asset_key="yuanyue_comment_activity",
                display_name="源悦-评论（评论切角）",
                version_no=1,
                status="active",
                asset_stage="production",
                source_name="test.csv",
                content_json={
                    "items": [
                        {
                            "comment_angle": "真实体验",
                            "corpus": "围绕源悦活动写一条自然评论。",
                        }
                    ]
                },
                metadata_json={"rule_count": 1},
            )
        )
        session.add(
            LLMModelRoute(
                id=1,
                model_code="deepseek-v4-flash",
                model_name="deepseek-v4-flash",
                provider_code="deepseek",
                provider_model="deepseek-v4-flash",
                priority=50,
                enabled=1,
                currency="USD",
                is_deleted=0,
            )
        )
        for expert_id, code, name, expert_type, capability in [
            (1, "comment_generator_v1", "评论生成 Expert", "GENERATION", "content.generate"),
            (2, "content_rewrite_v1", "审核改写 Expert", "REWRITE", "content.rewrite"),
        ]:
            session.add(
                ExpertConfig(
                    id=expert_id,
                    expert_config_code=code,
                    expert_config_name=name,
                    expert_type=expert_type,
                    expert_app="maga-worker",
                    expert_service="content-generation-flow",
                    expert_func=capability,
                    model_code="deepseek-v4-flash",
                    model_config={"provider_code": "deepseek"},
                    prompt_template="请根据 {{ business_rule }} 生成内容。",
                    enabled=True,
                    publish_status="PUBLISHED",
                    is_deleted=0,
                )
            )
        await session.commit()
