"""Tests for content agent execution-layer service."""
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ContentAgentRun, ContentAgentTask
from app.schemas.content_agent import (
    ContentAgentArtifactCreate,
    ContentAgentClaimRequest,
    ContentAgentEventCreate,
    ContentAgentRunCompleteRequest,
    ContentAgentRunFailRequest,
    ContentAgentTaskCreate,
)
from app.services.content_agent_service import ContentAgentService


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_claim_task_creates_run_and_marks_task_running(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(
        ContentAgentTaskCreate(
            task_code="task-001",
            task_type="xhs_generate",
            executor_code="hermes_maga_worker",
            input_snapshot={"product_topic": "美素佳儿源悦", "style": "情绪共情"},
            asset_refs={"brief_id": 10},
        )
    )

    claim = await service.claim_task(
        ContentAgentClaimRequest(
            executor_code="hermes_maga_worker",
            capabilities=["xhs_generate"],
            external_run_id="local-run-001",
        )
    )

    assert claim is not None
    assert claim.task_id == task.id
    assert claim.run_id is not None
    assert claim.task_type == "xhs_generate"
    assert claim.input == {"product_topic": "美素佳儿源悦", "style": "情绪共情"}
    assert claim.asset_refs == {"brief_id": 10}

    refreshed = await db_session.get(ContentAgentTask, task.id)
    assert refreshed.status == "running"
    assert refreshed.retry_count == 0


@pytest.mark.asyncio
async def test_claim_task_returns_none_when_no_pending_task_matches_capability(db_session):
    service = ContentAgentService(db_session)
    await service.create_task(
        ContentAgentTaskCreate(
            task_type="xhs_rewrite",
            executor_code="hermes_maga_worker",
            input_snapshot={"product_topic": "美素佳儿源悦"},
        )
    )

    claim = await service.claim_task(
        ContentAgentClaimRequest(
            executor_code="hermes_maga_worker",
            capabilities=["xhs_generate"],
        )
    )

    assert claim is None


@pytest.mark.asyncio
async def test_claim_task_can_claim_task_without_pinned_executor(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(
        ContentAgentTaskCreate(
            task_code="task-shared-001",
            task_type="xhs_generate",
            executor_code=None,
            input_snapshot={"product_topic": "美素佳儿源悦"},
        )
    )

    claim = await service.claim_task(
        ContentAgentClaimRequest(executor_code="hermes_maga_worker", capabilities=["xhs_generate"])
    )

    assert claim is not None
    assert claim.task_id == task.id


@pytest.mark.asyncio
async def test_claim_task_does_not_create_duplicate_runs_when_called_twice(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(
        ContentAgentTaskCreate(
            task_code="task-atomic-001",
            task_type="xhs_generate",
            executor_code="hermes_maga_worker",
            input_snapshot={"product_topic": "美素佳儿源悦"},
        )
    )

    first_claim = await service.claim_task(
        ContentAgentClaimRequest(executor_code="hermes_maga_worker", capabilities=["xhs_generate"])
    )
    second_claim = await service.claim_task(
        ContentAgentClaimRequest(executor_code="hermes_maga_worker", capabilities=["xhs_generate"])
    )

    run_count = await db_session.scalar(select(func.count()).select_from(ContentAgentRun))
    refreshed = await db_session.get(ContentAgentTask, task.id)

    assert first_claim is not None
    assert second_claim is None
    assert run_count == 1
    assert refreshed.status == "running"


@pytest.mark.asyncio
async def test_event_artifact_and_complete_update_run_and_task(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(
        ContentAgentTaskCreate(
            task_type="xhs_generate",
            executor_code="hermes_maga_worker",
            input_snapshot={"product_topic": "美素佳儿源悦"},
        )
    )
    claim = await service.claim_task(
        ContentAgentClaimRequest(executor_code="hermes_maga_worker", capabilities=["xhs_generate"])
    )

    event = await service.create_event(
        claim.run_id,
        ContentAgentEventCreate(
            step="ae_score",
            event_type="llm_call",
            expert_code="naturalness_ai_smell",
            output_snapshot={"score": 88},
            message="AI 味评分完成",
        ),
    )
    artifact = await service.create_artifact(
        claim.run_id,
        ContentAgentArtifactCreate(
            artifact_type="final_content",
            name="final",
            content_text="标题\n正文",
            content_json={"title": "标题", "body": "正文"},
        ),
    )
    run = await service.complete_run(
        claim.run_id,
        ContentAgentRunCompleteRequest(
            output_summary={"title": "标题", "final_artifact_id": artifact.id},
        ),
    )

    assert event.run_id == claim.run_id
    assert artifact.run_id == claim.run_id
    assert run.status == "succeeded"

    refreshed = await db_session.get(ContentAgentTask, task.id)
    assert refreshed.status == "succeeded"
    assert refreshed.output_summary == {"title": "标题", "final_artifact_id": artifact.id}


@pytest.mark.asyncio
async def test_fail_run_marks_run_and_task_failed(db_session):
    service = ContentAgentService(db_session)
    task = await service.create_task(
        ContentAgentTaskCreate(
            task_type="xhs_generate",
            executor_code="hermes_maga_worker",
            input_snapshot={"product_topic": "美素佳儿源悦"},
        )
    )
    claim = await service.claim_task(
        ContentAgentClaimRequest(executor_code="hermes_maga_worker", capabilities=["xhs_generate"])
    )

    run = await service.fail_run(
        claim.run_id,
        ContentAgentRunFailRequest(error_message="runtime failed"),
    )

    assert run.status == "failed"
    assert run.error_message == "runtime failed"
    refreshed = await db_session.get(ContentAgentTask, task.id)
    assert refreshed.status == "failed"
    assert refreshed.error_message == "runtime failed"
