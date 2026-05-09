"""Tests for the minimal MAGA-side content-agent orchestrator."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ExecutorRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.schemas.content_agent import ContentAgentTaskCreate
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.executor_invocation_service import InvokeResult


class FakeInvocationClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def invoke(self, *, invoke_url, envelope):
        self.calls.append({"invoke_url": invoke_url, "envelope": envelope})
        return self.result


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
async def test_start_generation_run_invokes_first_capability_and_completes_sync_stage(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="hermes_xhs_writer",
            executor_type="hermes_profile",
            invoke_url="https://executor.example.com/invoke",
            supported_capabilities_json=[{"capability": "xhs.interpret_brief", "schema_version": "1"}],
        )
    )
    await db_session.flush()
    invocation_client = FakeInvocationClient(
        InvokeResult(
            mode="sync",
            stage_call_id="stage-fixed",
            output={"structured_brief": {"topic": "A2 奶粉"}},
            stats={"duration_ms": 50},
        )
    )
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=invocation_client,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.start_generation_run(
        ContentAgentTaskCreate(
            task_type="xhs_generate",
            executor_code="hermes_xhs_writer",
            input_snapshot={"brief": {"topic": "A2 奶粉"}},
        )
    )

    assert result.run.status == "running"
    assert result.stage_call.status == "succeeded"
    assert result.stage_call.capability == "xhs.interpret_brief"
    assert result.stage_call.output_snapshot == {"structured_brief": {"topic": "A2 奶粉"}}
    assert invocation_client.calls[0]["invoke_url"] == "https://executor.example.com/invoke"
    assert invocation_client.calls[0]["envelope"]["capability"] == "xhs.interpret_brief"
    assert invocation_client.calls[0]["envelope"]["input"] == {"brief": {"topic": "A2 奶粉"}}


@pytest.mark.asyncio
async def test_start_generation_run_leaves_async_stage_running(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="hermes_xhs_writer",
            executor_type="hermes_profile",
            invoke_url="https://executor.example.com/invoke",
        )
    )
    await db_session.flush()
    invocation_client = FakeInvocationClient(InvokeResult(mode="async", stage_call_id="stage-fixed", ack_at="2026-05-08T12:00:00Z"))
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=invocation_client,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.start_generation_run(ContentAgentTaskCreate(task_type="xhs_generate"))

    assert result.stage_call.status == "running"
    assert result.invoke_result.mode == "async"
    assert result.invoke_result.ack_at == "2026-05-08T12:00:00Z"


@pytest.mark.asyncio
async def test_start_generation_run_requires_executor_invoke_url(db_session):
    db_session.add(ExecutorRegistry(executor_code="hermes_xhs_writer", executor_type="hermes_profile"))
    await db_session.flush()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=FakeInvocationClient(InvokeResult(mode="async", stage_call_id="unused")),
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    with pytest.raises(ValueError, match="invoke_url"):
        await orchestrator.start_generation_run(ContentAgentTaskCreate(task_type="xhs_generate"))
