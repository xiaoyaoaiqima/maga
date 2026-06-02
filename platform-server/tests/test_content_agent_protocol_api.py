"""API tests for MVP-aligned MAGA ↔ Executor protocol callback endpoints."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.content_agent import router
from app.core.database import get_db
from app.models.base import Base
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.schemas.content_agent import ContentAgentStageCallCreate, ContentAgentTaskCreate
from app.services.content_agent_service import ContentAgentService
from fastapi import FastAPI


@pytest_asyncio.fixture
async def api_context():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/content-agent")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with session_factory() as session:
        service = ContentAgentService(session)
        task = await service.create_task(ContentAgentTaskCreate(task_type="content_generate"))
        run, stage = await service.start_run_with_stage(
            task.id,
            executor_code="hermes_maga_worker",
            stage=ContentAgentStageCallCreate(
                stage_call_id="stage-api-001",
                capability="content.generate",
                input_snapshot={"content_type": "article", "rendered_prompt": "生成内容"},
            ),
        )
        await session.commit()
        run_id = run.id
        stage_call_id = stage.stage_call_id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, run_id, stage_call_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_mvp_transition_endpoints_are_not_public_protocol(api_context):
    client, run_id, stage_call_id = api_context

    complete = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/stage-calls/{stage_call_id}/complete",
        json={"output": {"title": "标题", "body": "正文"}},
    )
    fail = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/stage-calls/{stage_call_id}/fail",
        json={"error_code": "model_error", "error_message": "provider 5xx"},
    )
    heartbeat = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/heartbeat",
        json={"stage_call_id": stage_call_id, "progress_hint": "ge_generating"},
    )

    assert complete.status_code == 404
    assert fail.status_code == 404
    assert heartbeat.status_code == 404


@pytest.mark.asyncio
async def test_human_review_endpoint_uses_stage_header_and_no_run_token_or_schema(api_context):
    client, run_id, stage_call_id = api_context

    response = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/human-review",
        headers={"X-Stage-Call-Id": stage_call_id, "X-Maga-Protocol-Version": "0.1"},
        json={
            "stage_call_id": stage_call_id,
            "reason": "operator_review",
            "payload": {"title": "标题", "body": "正文"},
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reason"] == "operator_review"
    assert data["status"] == "pending"
    assert data["payload_json"] == {"title": "标题", "body": "正文"}
    assert data["response_schema_json"] is None


@pytest.mark.asyncio
async def test_human_review_rejects_stale_stage_header(api_context):
    client, run_id, stage_call_id = api_context

    response = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/human-review",
        headers={"X-Stage-Call-Id": "stale-stage", "X-Maga-Protocol-Version": "0.1"},
        json={"stage_call_id": stage_call_id, "reason": "hard_ae_failed", "payload": {}},
    )

    assert response.status_code == 409
