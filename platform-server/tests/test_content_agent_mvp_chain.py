"""Tests for MVP five-stage sync generation orchestration."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ContentAgentStageCall, ContentAgentTask, ExecutorRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.schemas.content_agent import ContentAgentTaskCreate
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.executor_invocation_service import InvokeResult


class CapabilityAwareFakeInvocationClient:
    def __init__(self, *, review_output=None, rewrite_output=None):
        self.calls = []
        self.review_output = review_output or {
            "hard_results": [{"ae_code": "compliance_redline", "pass": True}],
            "soft_scores": [{"ae_code": "business_logic", "score": 88}],
            "failed_aes": [],
        }
        self.rewrite_output = rewrite_output or {
            "final": {"title": "美素佳儿源悦放心选", "body": "先看适合度，再看喂养反馈。", "hashtags": ["母婴"]}
        }

    async def invoke(self, *, invoke_url, envelope, executor_token=None):
        self.calls.append({"invoke_url": invoke_url, "envelope": envelope, "executor_token": executor_token})
        capability = envelope["capability"]
        stage_call_id = envelope["stage_call_id"]
        if capability == "xhs.interpret_brief":
            return InvokeResult(
                mode="sync",
                stage_call_id=stage_call_id,
                output={
                    "structured_brief": {
                        "product_topic": envelope["input"]["product_topic"],
                        "style": envelope["input"].get("style"),
                    },
                    "runtime_brief": {
                        "brief_id": "compiled-test-001",
                        "product_topic": envelope["input"]["product_topic"],
                    },
                    "brief_warnings": [],
                },
            )
        if capability == "xhs.run_ae_analysis":
            return InvokeResult(
                mode="sync",
                stage_call_id=stage_call_id,
                output={"analyses": {"business_logic": {"analysis": "新手妈妈怕选错奶粉"}}, "failed_aes": []},
            )
        if capability == "xhs.generate_draft":
            return InvokeResult(
                mode="sync",
                stage_call_id=stage_call_id,
                output={"draft": {"title": "美素佳儿源悦怎么选", "body": "新手妈妈选奶粉别只看热度，要看适合度。", "hashtags": ["奶粉"]}},
            )
        if capability == "xhs.run_ae_review":
            return InvokeResult(
                mode="sync",
                stage_call_id=stage_call_id,
                output=self.review_output,
            )
        if capability == "xhs.review_and_rewrite":
            draft = envelope["input"].get("draft") or {}
            if self.review_output.get("rewrite_required") or any(
                item.get("pass") is False for item in self.review_output.get("hard_results", [])
            ):
                return InvokeResult(
                    mode="sync",
                    stage_call_id=stage_call_id,
                    output={
                        "final": self.rewrite_output["final"],
                        "draft": self.rewrite_output["final"],
                        "review_report": self.review_output,
                        "hard_results": self.review_output["hard_results"],
                        "soft_scores": self.review_output["soft_scores"],
                        "failed_aes": self.review_output["failed_aes"],
                    },
                )
            return InvokeResult(
                mode="sync",
                stage_call_id=stage_call_id,
                output={
                    "final": {"title": draft.get("title"), "body": draft.get("body")},
                    "draft": {"title": draft.get("title"), "body": draft.get("body")},
                    "review_report": self.review_output,
                    "hard_results": self.review_output["hard_results"],
                    "soft_scores": self.review_output["soft_scores"],
                    "failed_aes": self.review_output["failed_aes"],
                },
            )
        if capability == "xhs.rewrite_draft":
            return InvokeResult(
                mode="sync",
                stage_call_id=stage_call_id,
                output=self.rewrite_output,
            )
        raise AssertionError(f"unexpected capability {capability}")


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
async def test_run_mvp_generation_chain_returns_title_body_only_when_review_passes(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="hermes_maga_worker",
            executor_type="hermes_profile",
            invoke_url="https://executor.example.com/invoke",
            supported_capabilities_json=[
                {"capability": "xhs.interpret_brief", "schema_version": "1"},
                {"capability": "xhs.run_ae_analysis", "schema_version": "1"},
                {"capability": "xhs.generate_draft", "schema_version": "1"},
                {"capability": "xhs.review_and_rewrite", "schema_version": "1"},
                {"capability": "xhs.run_ae_review", "schema_version": "1"},
                {"capability": "xhs.rewrite_draft", "schema_version": "1"},
            ],
        )
    )
    await db_session.flush()
    invocation_client = CapabilityAwareFakeInvocationClient()
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=invocation_client,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.run_mvp_generation_chain(
        ContentAgentTaskCreate(
            task_type="xhs_generate",
            executor_code="hermes_maga_worker",
            input_snapshot={"product_topic": "美素佳儿源悦", "target_audience": "新手妈妈", "style": "情绪共情"},
        )
    )

    assert result.final_content == {"title": "美素佳儿源悦怎么选", "body": "新手妈妈选奶粉别只看热度，要看适合度。"}
    assert "hashtags" not in result.final_content
    assert result.run.status == "succeeded"
    assert [call["envelope"]["capability"] for call in invocation_client.calls] == [
        "xhs.interpret_brief",
        "xhs.run_ae_analysis",
        "xhs.generate_draft",
        "xhs.review_and_rewrite",
    ]
    assert invocation_client.calls[2]["envelope"]["input"]["runtime_brief"]["brief_id"] == "compiled-test-001"
    assert invocation_client.calls[3]["envelope"]["input"]["runtime_brief"]["brief_id"] == "compiled-test-001"
    stage_rows = (await db_session.execute(select(ContentAgentStageCall).order_by(ContentAgentStageCall.sequence_no))).scalars().all()
    assert [stage.sequence_no for stage in stage_rows] == [1, 2, 3, 4]
    assert all(stage.status == "succeeded" for stage in stage_rows)
    task = await db_session.get(ContentAgentTask, result.run.task_id)
    assert task.status == "succeeded"
    assert task.output_summary == {"title": "美素佳儿源悦怎么选", "body": "新手妈妈选奶粉别只看热度，要看适合度。"}


@pytest.mark.asyncio
async def test_run_mvp_generation_chain_rewrites_once_when_hard_review_fails(db_session):
    db_session.add(
        ExecutorRegistry(
            executor_code="hermes_maga_worker",
            executor_type="hermes_profile",
            invoke_url="https://executor.example.com/invoke",
            supported_capabilities_json=[
                {"capability": "xhs.interpret_brief", "schema_version": "1"},
                {"capability": "xhs.run_ae_analysis", "schema_version": "1"},
                {"capability": "xhs.generate_draft", "schema_version": "1"},
                {"capability": "xhs.review_and_rewrite", "schema_version": "1"},
                {"capability": "xhs.run_ae_review", "schema_version": "1"},
                {"capability": "xhs.rewrite_draft", "schema_version": "1"},
            ],
        )
    )
    await db_session.flush()
    invocation_client = CapabilityAwareFakeInvocationClient(
        review_output={
            "hard_results": [{"ae_code": "compliance_redline", "pass": False, "feedback": "标题有绝对化表达"}],
            "soft_scores": [{"ae_code": "business_logic", "score": 82}],
            "failed_aes": ["compliance_redline"],
        },
        rewrite_output={"final": {"title": "美素佳儿源悦安心看", "body": "把适合度讲清楚，比堆卖点更重要。", "hashtags": ["母婴"]}},
    )
    orchestrator = ContentAgentOrchestrator(
        db_session,
        invocation_client=invocation_client,
        callback_base_url="https://maga.example.com/api/v1/content-agent",
    )

    result = await orchestrator.run_mvp_generation_chain(
        ContentAgentTaskCreate(
            task_type="xhs_generate",
            executor_code="hermes_maga_worker",
            input_snapshot={"product_topic": "美素佳儿源悦", "target_audience": "新手妈妈", "style": "情绪共情"},
        )
    )

    assert result.final_content == {"title": "美素佳儿源悦安心看", "body": "把适合度讲清楚，比堆卖点更重要。"}
    assert "hashtags" not in result.final_content
    assert result.run.rewrite_round == 0
    assert [call["envelope"]["capability"] for call in invocation_client.calls] == [
        "xhs.interpret_brief",
        "xhs.run_ae_analysis",
        "xhs.generate_draft",
        "xhs.review_and_rewrite",
    ]
    review_input = invocation_client.calls[-1]["envelope"]["input"]
    assert review_input["draft"]["title"] == "美素佳儿源悦怎么选"
    assert review_input["runtime_brief"]["brief_id"] == "compiled-test-001"
    stage_rows = (await db_session.execute(select(ContentAgentStageCall).order_by(ContentAgentStageCall.sequence_no))).scalars().all()
    assert [stage.sequence_no for stage in stage_rows] == [1, 2, 3, 4]
    assert stage_rows[-1].capability == "xhs.review_and_rewrite"
