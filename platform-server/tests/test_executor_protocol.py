"""Tests for MAGA ↔ Executor protocol v0.1 core behavior."""
import pytest
import pytest_asyncio
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ContentAgentArtifact, ContentAgentEvent, ContentAgentRun, ContentAgentStageCall
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.schemas.content_agent import (
    ContentAgentArtifactCreate,
    ContentAgentEventCreate,
    ContentAgentStageCallCompleteRequest,
    ContentAgentStageCallCreate,
    ContentAgentStageCallFailRequest,
    ContentAgentTaskCreate,
)
from app.services.content_agent_service import ContentAgentService


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_clean_schema_includes_stage_call_and_human_review_tables(db_session):
    table_names = set(await db_session.run_sync(lambda sync_session: inspect(sync_session.bind).get_table_names()))

    assert "content_agent_stage_call" in table_names
    assert "content_agent_human_review" in table_names


@pytest.mark.asyncio
async def test_start_run_creates_run_token_and_current_stage_call(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(
        ContentAgentTaskCreate(task_type="xhs_generate", input_snapshot={"product_topic": "A2 奶粉"})
    )

    run, stage_call = await service.start_run_with_stage(
        task.id,
        executor_code="hermes_xhs_writer",
        stage=ContentAgentStageCallCreate(
            stage_call_id="stage-interpret-001",
            capability="xhs.interpret_brief",
            input_snapshot={"brief": {"version_id": "brief-v1"}},
            deadline_at=None,
        ),
    )

    assert run.run_token
    assert run.status == "running"
    assert run.current_stage_call_id == "stage-interpret-001"
    assert stage_call.run_id == run.id
    assert stage_call.status == "running"
    assert stage_call.sequence_no == 1


@pytest.mark.asyncio
async def test_stage_complete_requires_current_stage_and_run_token(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(ContentAgentTaskCreate(task_type="xhs_generate"))
    run, _ = await service.start_run_with_stage(
        task.id,
        executor_code="hermes_xhs_writer",
        stage=ContentAgentStageCallCreate(
            stage_call_id="stage-generate-001",
            capability="xhs.generate_draft",
            input_snapshot={},
        ),
    )

    with pytest.raises(ValueError, match="run token"):
        await service.complete_stage_call(
            run.id,
            "stage-generate-001",
            ContentAgentStageCallCompleteRequest(
                run_token="bad-token",
                output={"draft_artifact_id": "art-001"},
                stats={"total_latency_ms": 100},
            ),
        )

    completed = await service.complete_stage_call(
        run.id,
        "stage-generate-001",
        ContentAgentStageCallCompleteRequest(
            run_token=run.run_token,
            output={"draft_artifact_id": "art-001"},
            stats={"total_latency_ms": 100},
        ),
    )

    assert completed.status == "succeeded"
    assert completed.output_snapshot == {"draft_artifact_id": "art-001"}
    assert completed.stats_json == {"total_latency_ms": 100}


@pytest.mark.asyncio
async def test_stage_fail_marks_stage_failed_but_leaves_run_for_maga_decision(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(ContentAgentTaskCreate(task_type="xhs_generate"))
    run, _ = await service.start_run_with_stage(
        task.id,
        executor_code="hermes_xhs_writer",
        stage=ContentAgentStageCallCreate(stage_call_id="stage-review-001", capability="xhs.run_ae_review"),
    )

    failed = await service.fail_stage_call(
        run.id,
        "stage-review-001",
        ContentAgentStageCallFailRequest(
            run_token=run.run_token,
            error_code="model_error",
            error_message="provider 5xx",
            retryable=True,
        ),
    )

    refreshed_run = await db_session.get(ContentAgentRun, run.id)
    assert failed.status == "failed"
    assert failed.error_code == "model_error"
    assert failed.error_message == "provider 5xx"
    assert refreshed_run.status == "running"


@pytest.mark.asyncio
async def test_event_and_artifact_are_idempotent_per_run_key_and_grouped_by_stage(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(ContentAgentTaskCreate(task_type="xhs_generate"))
    run, _ = await service.start_run_with_stage(
        task.id,
        executor_code="hermes_xhs_writer",
        stage=ContentAgentStageCallCreate(stage_call_id="stage-ae-001", capability="xhs.run_ae_analysis"),
    )

    event_request = ContentAgentEventCreate(
        stage_call_id="stage-ae-001",
        step="ae_analysis",
        event_type="llm_call",
        idempotency_key="evt-001",
        otel_attributes={"gen_ai.request.model": "doubao-seed"},
        output_snapshot={"analysis": "ok"},
    )
    first_event = await service.create_event(run.id, event_request)
    second_event = await service.create_event(run.id, event_request)

    artifact_request = ContentAgentArtifactCreate(
        stage_call_id="stage-ae-001",
        artifact_code="art-001",
        artifact_type="score_report",
        idempotency_key="art-key-001",
        content_json={"score": 88},
    )
    first_artifact = await service.create_artifact(run.id, artifact_request)
    second_artifact = await service.create_artifact(run.id, artifact_request)

    event_count = await db_session.scalar(select(func.count()).select_from(ContentAgentEvent).where(ContentAgentEvent.run_id == run.id))
    artifact_count = await db_session.scalar(select(func.count()).select_from(ContentAgentArtifact).where(ContentAgentArtifact.run_id == run.id))

    assert first_event.id == second_event.id
    assert first_event.stage_call_id == "stage-ae-001"
    assert first_event.otel_attributes_json == {"gen_ai.request.model": "doubao-seed"}
    assert first_artifact.id == second_artifact.id
    assert first_artifact.stage_call_id == "stage-ae-001"
    assert first_artifact.artifact_code == "art-001"
    assert event_count == 1
    assert artifact_count == 1
