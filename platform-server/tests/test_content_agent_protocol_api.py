"""API tests for MAGA ↔ Executor protocol v0.1 callback endpoints."""

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
        task = await service.create_task(ContentAgentTaskCreate(task_type="xhs_generate"))
        run, stage = await service.start_run_with_stage(
            task.id,
            executor_code="hermes_xhs_writer",
            stage=ContentAgentStageCallCreate(
                stage_call_id="stage-api-001",
                capability="xhs.generate_draft",
                input_snapshot={"structured_brief": {"topic": "A2 奶粉"}},
            ),
        )
        await session.commit()
        run_id = run.id
        run_token = run.run_token
        stage_call_id = stage.stage_call_id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, run_id, stage_call_id, run_token

    await engine.dispose()


@pytest.mark.asyncio
async def test_stage_complete_endpoint_validates_token_and_returns_stage(api_context):
    client, run_id, stage_call_id, run_token = api_context

    bad = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/stage-calls/{stage_call_id}/complete",
        json={"run_token": "bad-token", "output": {"draft_artifact_id": "art-001"}},
    )
    assert bad.status_code == 409

    response = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/stage-calls/{stage_call_id}/complete",
        json={"run_token": run_token, "output": {"draft_artifact_id": "art-001"}, "stats": {"duration_ms": 123}},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stage_call_id"] == stage_call_id
    assert data["status"] == "succeeded"
    assert data["output_snapshot"] == {"draft_artifact_id": "art-001"}


@pytest.mark.asyncio
async def test_stage_fail_endpoint_returns_failed_stage(api_context):
    client, run_id, stage_call_id, run_token = api_context

    response = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/stage-calls/{stage_call_id}/fail",
        json={
            "run_token": run_token,
            "error_code": "model_error",
            "error_message": "provider 5xx",
            "retryable": True,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "model_error"
    assert data["retryable"] == 1


@pytest.mark.asyncio
async def test_heartbeat_endpoint_updates_current_stage_progress(api_context):
    client, run_id, stage_call_id, run_token = api_context

    response = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/heartbeat",
        json={"run_token": run_token, "stage_call_id": stage_call_id, "progress_hint": "ge_generating"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status_substate"] == "running.ge_generating"


@pytest.mark.asyncio
async def test_human_review_endpoint_creates_review_gate(api_context):
    client, run_id, stage_call_id, run_token = api_context

    response = await client.post(
        f"/api/v1/content-agent/runs/{run_id}/human-review",
        json={
            "run_token": run_token,
            "stage_call_id": stage_call_id,
            "reason": "hard_ae_failed",
            "payload": {"draft_artifact_id": "art-001"},
            "response_schema": {"type": "object"},
            "ui_hint": "review_form",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reason"] == "hard_ae_failed"
    assert data["status"] == "pending"
    assert data["payload_json"] == {"draft_artifact_id": "art-001"}
