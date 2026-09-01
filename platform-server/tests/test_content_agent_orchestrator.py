"""Tests for the MAGA-side content-agent orchestrator."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ContentAgentRun, ContentAgentStageCall, ContentAgentTask, ExecutorRegistry
from app.models.llm_model_route import LLMModelRoute
from app.models.llm_provider_config import LLMProviderConfig
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
async def test_run_single_capability_invokes_content_generate_and_completes_run(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="maga_direct_llm_executor",
            executor_type="direct_llm",
            invoke_url="https://executor.example.com/invoke",
            supported_capabilities_json=[{"capability": "content.generate", "schema_version": "1"}],
        )
    )
    await db_session.flush()
    invocation_client = FakeInvocationClient(
        InvokeResult(
            mode="sync",
            stage_call_id="stage-fixed",
            output={"title": "标题", "body": "正文"},
            stats={"duration_ms": 50},
        )
    )
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=invocation_client,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.run_single_capability(
        ContentAgentTaskCreate(
            task_type="content_generate",
            executor_code="maga_direct_llm_executor",
            input_snapshot={"content_type": "article", "rendered_prompt": "生成内容"},
        ),
        capability="content.generate",
    )

    assert result.run.status == "succeeded"
    assert result.output == {"title": "标题", "body": "正文"}
    assert result.stage_calls[0].status == "succeeded"
    assert result.stage_calls[0].capability == "content.generate"
    assert invocation_client.calls[0]["invoke_url"] == "https://executor.example.com/invoke"
    assert invocation_client.calls[0]["envelope"]["capability"] == "content.generate"
    assert invocation_client.calls[0]["envelope"]["input"] == {
        "content_type": "article",
        "rendered_prompt": "生成内容",
    }


@pytest.mark.asyncio
async def test_run_single_capability_attaches_provider_config_only_to_invoke_envelope(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="maga_direct_llm_executor",
            executor_type="direct_llm",
            invoke_url="https://executor.example.com/invoke",
            supported_capabilities_json=[{"capability": "content.generate", "schema_version": "1"}],
        )
    )
    db_session.add(
        LLMProviderConfig(
            id=1,
            provider_code="aihubmix",
            provider_name="AIHubMix",
            provider_type="openai_compatible",
            base_url="https://aihubmix.example/v1",
            api_key="db-key",
            default_model="deepseek-v4-flash",
            priority=100,
            enabled=1,
        )
    )
    db_session.add(
        LLMModelRoute(
            id=1,
            model_code="deepseek-v4-flash",
            model_name="DeepSeek V4 Flash",
            provider_code="aihubmix",
            provider_model="deepseek-v4-flash",
            priority=100,
            enabled=1,
        )
    )
    await db_session.flush()
    invocation_client = FakeInvocationClient(
        InvokeResult(mode="sync", stage_call_id="stage-fixed", output={"title": "标题", "body": "正文"})
    )
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=invocation_client,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.run_single_capability(
        ContentAgentTaskCreate(
            task_type="content_generate",
            executor_code="maga_direct_llm_executor",
            input_snapshot={
                "content_type": "article",
                "rendered_prompt": "生成内容",
                "model_config": {"provider_code": "aihubmix", "model_code": "deepseek-v4-flash"},
            },
        ),
        capability="content.generate",
    )

    outbound_model_config = invocation_client.calls[0]["envelope"]["input"]["model_config"]
    assert outbound_model_config["base_url"] == "https://aihubmix.example/v1"
    assert outbound_model_config["api_key"] == "db-key"
    assert result.stage_calls[0].input_snapshot["model_config"] == {
        "provider_code": "aihubmix",
        "model_code": "deepseek-v4-flash",
    }


@pytest.mark.asyncio
async def test_run_content_rewrite_stage_falls_back_to_model_route_when_provider_code_is_stale(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="maga_direct_llm_executor",
            executor_type="direct_llm",
            invoke_url="https://executor.example.com/invoke",
            supported_capabilities_json=[
                {"capability": "content.generate", "schema_version": "1"},
                {"capability": "content.rewrite", "schema_version": "1"},
            ],
        )
    )
    db_session.add(
        LLMProviderConfig(
            id=1,
            provider_code="aihubmix",
            provider_name="AIHubMix",
            provider_type="openai_compatible",
            base_url="https://aihubmix.example/v1",
            api_key="db-key",
            default_model="deepseek-v4-flash",
            priority=100,
            enabled=1,
        )
    )
    db_session.add(
        LLMModelRoute(
            id=1,
            model_code="deepseek-v4-flash",
            model_name="DeepSeek V4 Flash",
            provider_code="aihubmix",
            provider_model="deepseek-v4-flash",
            priority=100,
            enabled=1,
        )
    )
    await db_session.flush()
    invocation_client = FakeInvocationClient(
        InvokeResult(mode="sync", stage_call_id="stage-fixed", output={"comment": "改写后的评论"})
    )
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=invocation_client,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )
    run_result = await orchestrator.run_single_capability(
        ContentAgentTaskCreate(
            task_type="content_generate",
            executor_code="maga_direct_llm_executor",
            input_snapshot={"content_type": "comment", "model_config": {"model_code": "deepseek-v4-flash"}},
        ),
        capability="content.generate",
    )

    rewrite_result = await orchestrator.run_content_rewrite_stage(
        run_id=run_result.run.id,
        executor_code="maga_direct_llm_executor",
        input_payload={
            "content_type": "comment",
            "previous_content": {"comment": "原评论"},
            "model_config": {"provider_code": "deepseek", "model_code": "deepseek-v4-flash"},
        },
    )

    outbound_model_config = invocation_client.calls[-1]["envelope"]["input"]["model_config"]
    assert outbound_model_config["provider_code"] == "aihubmix"
    assert outbound_model_config["base_url"] == "https://aihubmix.example/v1"
    assert outbound_model_config["api_key"] == "db-key"
    assert rewrite_result.stage_calls[0].input_snapshot["model_config"] == {
        "provider_code": "deepseek",
        "model_code": "deepseek-v4-flash",
    }


@pytest.mark.asyncio
async def test_run_single_capability_uses_direct_llm_executor_without_worker(db_session, monkeypatch):
    async def fake_call(**kwargs):
        return '{"title":"直连标题","body":"直连正文"}'

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    db_session.add(
        ExecutorRegistry(
            executor_code="maga_direct_llm_executor",
            executor_type="direct_llm",
            invoke_url="llm://direct/content",
            supported_capabilities_json=[{"capability": "content.generate", "schema_version": "1"}],
        )
    )
    await db_session.flush()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.run_single_capability(
        ContentAgentTaskCreate(
            task_type="content_generate",
            executor_code="maga_direct_llm_executor",
            input_snapshot={
                "content_type": "article",
                "output_fields": ["title", "body"],
                "rendered_prompt": "生成内容",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        ),
        capability="content.generate",
    )

    assert result.run.status == "succeeded"
    assert result.output["title"] == "直连标题"
    assert result.stage_calls[0].status == "succeeded"
    assert result.stage_calls[0].stats_json["adapter"] == "platform_server.direct_llm"


@pytest.mark.asyncio
async def test_run_single_capability_defaults_blank_executor_code_to_direct_llm(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="maga_direct_llm_executor",
            executor_type="direct_llm",
            invoke_url="https://executor.example.com/invoke",
            supported_capabilities_json=[{"capability": "content.generate", "schema_version": "1"}],
        )
    )
    await db_session.flush()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=FakeInvocationClient(
            InvokeResult(mode="sync", stage_call_id="stage-fixed", output={"comment": "评论"})
        ),
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.run_single_capability(
        ContentAgentTaskCreate(
            task_type="content_generate",
            executor_code="  ",
            input_snapshot={"content_type": "comment"},
        ),
        capability="content.generate",
    )

    assert result.run.executor_code == "maga_direct_llm_executor"
    assert result.stage_calls[0].status == "succeeded"


@pytest.mark.asyncio
async def test_run_single_capability_marks_failed_sync_stage_failed(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="maga_direct_llm_executor",
            executor_type="direct_llm",
            invoke_url="https://executor.example.com/invoke",
        )
    )
    await db_session.flush()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=FakeInvocationClient(
            InvokeResult(
                mode="sync",
                stage_call_id="stage-fixed",
                status="failed",
                error_code="model_error",
                error_message="provider 5xx",
            )
        ),
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    with pytest.raises(ValueError, match="provider 5xx"):
        await orchestrator.run_single_capability(
            ContentAgentTaskCreate(task_type="content_generate"),
            capability="content.generate",
        )

    stage = (await db_session.execute(select(ContentAgentStageCall))).scalar_one()
    assert stage.status == "failed"
    assert stage.error_code == "model_error"


@pytest.mark.asyncio
async def test_run_single_capability_marks_stage_and_run_failed_when_executor_call_raises(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="maga_direct_llm_executor",
            executor_type="direct_llm",
            invoke_url="https://executor.example.com/invoke",
        )
    )
    await db_session.flush()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=RaisingInvocationClient(),
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    with pytest.raises(ContentAgentInvokeError, match="content.generate"):
        await orchestrator.run_single_capability(
            ContentAgentTaskCreate(
                task_type="content_generate",
                executor_code="maga_direct_llm_executor",
                input_snapshot={"content_type": "article"},
            ),
            capability="content.generate",
        )

    task = (await db_session.execute(select(ContentAgentTask))).scalar_one()
    run = (await db_session.execute(select(ContentAgentRun))).scalar_one()
    stage = (await db_session.execute(select(ContentAgentStageCall))).scalar_one()

    assert task.status == "failed"
    assert task.error_message == "Executor invoke failed during content.generate: TimeoutError"
    assert run.status == "failed"
    assert run.error_message == task.error_message
    assert stage.status == "failed"
    assert stage.error_code == "executor_invoke_error"
    assert stage.error_message == task.error_message


@pytest.mark.asyncio
async def test_run_single_capability_requires_executor_invoke_url(db_session):
    db_session.add(ExecutorRegistry(executor_code="maga_direct_llm_executor", executor_type="direct_llm"))
    await db_session.flush()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=FakeInvocationClient(InvokeResult(mode="async", stage_call_id="unused")),
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    with pytest.raises(ValueError, match="invoke_url"):
        await orchestrator.run_single_capability(
            ContentAgentTaskCreate(task_type="content_generate"),
            capability="content.generate",
        )
