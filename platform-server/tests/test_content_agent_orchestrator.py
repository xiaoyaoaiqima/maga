"""Tests for the minimal MAGA-side content-agent orchestrator."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ContentAgentRun, ContentAgentStageCall, ContentAgentTask, ExecutorRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.schemas.content_agent import ContentAgentTaskCreate
from app.services.content_agent_orchestrator import ContentAgentInvokeError, ContentAgentOrchestrator
from app.services.executor_invocation_service import InvokeResult


class FakeInvocationClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def invoke(self, *, invoke_url, envelope, executor_token=None):
        self.calls.append({"invoke_url": invoke_url, "envelope": envelope, "executor_token": executor_token})
        return self.result


class RaisingInvocationClient:
    async def invoke(self, *, invoke_url, envelope, executor_token=None):
        raise TimeoutError()


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
            executor_code="hermes_maga_worker",
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
            output={"structured_brief": {"topic": "美素佳儿源悦"}},
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
            executor_code="hermes_maga_worker",
            input_snapshot={"brief": {"topic": "美素佳儿源悦"}},
        )
    )

    assert result.run.status == "running"
    assert result.stage_call.status == "succeeded"
    assert result.stage_call.capability == "xhs.interpret_brief"
    assert result.stage_call.output_snapshot == {"structured_brief": {"topic": "美素佳儿源悦"}}
    assert invocation_client.calls[0]["invoke_url"] == "https://executor.example.com/invoke"
    assert invocation_client.calls[0]["envelope"]["capability"] == "xhs.interpret_brief"
    assert invocation_client.calls[0]["envelope"]["input"] == {"brief": {"topic": "美素佳儿源悦"}}


@pytest.mark.asyncio
async def test_start_generation_run_defaults_blank_executor_code_to_maga_worker(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="hermes_maga_worker",
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
            output={"structured_brief": {"topic": "美素佳儿源悦"}},
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
            executor_code="  ",
            input_snapshot={"brief": {"topic": "美素佳儿源悦"}},
        )
    )

    assert result.run.executor_code == "hermes_maga_worker"
    assert result.stage_call.status == "succeeded"
    assert invocation_client.calls[0]["invoke_url"] == "https://executor.example.com/invoke"


@pytest.mark.asyncio
async def test_start_generation_run_marks_failed_sync_stage_failed(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="hermes_maga_worker",
            executor_type="hermes_profile",
            invoke_url="https://executor.example.com/invoke",
        )
    )
    await db_session.flush()
    invocation_client = FakeInvocationClient(
        InvokeResult(
            mode="sync",
            stage_call_id="stage-fixed",
            status="failed",
            error_code="model_error",
            error_message="provider 5xx",
        )
    )
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=invocation_client,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.start_generation_run(ContentAgentTaskCreate(task_type="xhs_generate"))

    assert result.stage_call.status == "failed"
    assert result.invoke_result.status == "failed"
    assert result.stage_call.error_code == "model_error"


@pytest.mark.asyncio
async def test_run_mvp_generation_chain_marks_stage_and_run_failed_when_executor_call_raises(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="hermes_maga_worker",
            executor_type="hermes_profile",
            invoke_url="https://executor.example.com/invoke",
        )
    )
    await db_session.flush()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=RaisingInvocationClient(),
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    with pytest.raises(ContentAgentInvokeError, match="xhs.interpret_brief"):
        await orchestrator.run_mvp_generation_chain(
            ContentAgentTaskCreate(
                task_type="xhs_generate",
                executor_code="hermes_maga_worker",
                input_snapshot={"product_topic": "美素佳儿源悦"},
            )
        )

    task = (await db_session.execute(select(ContentAgentTask))).scalar_one()
    run = (await db_session.execute(select(ContentAgentRun))).scalar_one()
    stage = (await db_session.execute(select(ContentAgentStageCall))).scalar_one()

    assert task.status == "failed"
    assert task.error_message == "Executor invoke failed during xhs.interpret_brief: TimeoutError"
    assert run.status == "failed"
    assert run.error_message == task.error_message
    assert stage.status == "failed"
    assert stage.error_code == "executor_invoke_error"
    assert stage.error_message == task.error_message


@pytest.mark.asyncio
async def test_start_generation_run_requires_executor_invoke_url(db_session):
    db_session.add(ExecutorRegistry(executor_code="hermes_maga_worker", executor_type="hermes_profile"))
    await db_session.flush()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=FakeInvocationClient(InvokeResult(mode="async", stage_call_id="unused")),
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    with pytest.raises(ValueError, match="invoke_url"):
        await orchestrator.start_generation_run(ContentAgentTaskCreate(task_type="xhs_generate"))
