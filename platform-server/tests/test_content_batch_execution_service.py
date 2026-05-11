"""Tests for executing planned batch content items."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import (
    ContentAgentRun,
    ContentAgentStageCall,
    ContentAgentTask,
    ContentBatchItem,
    ContentBatchJob,
    ExecutorRegistry,
)
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.executor_invocation_service import InvokeResult, MockExecutorInvocationClient


@pytest.mark.asyncio
async def test_batch_execution_generates_first_n_items_and_links_runs():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ContentBatchJob.__table__,
                ContentBatchItem.__table__,
                ExecutorRegistry.__table__,
                ContentAgentTask.__table__,
                ContentAgentRun.__table__,
                ContentAgentStageCall.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="hermes_maga_worker",
                executor_type="hermes_profile",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_test",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=3,
            status="planned",
        )
        session.add(job)
        await session.flush()
        for item_no in range(1, 4):
            session.add(
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=item_no,
                    status="planned",
                    plan_json=_plan(item_no),
                )
            )
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=MockExecutorInvocationClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=2, created_by="test")
        await session.commit()

    assert result.batch_id == job.id
    assert result.requested_limit == 2
    assert result.generated_count == 2
    assert result.failed_count == 0

    async with session_factory() as session:
        items = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no))
        ).scalars().all()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert [item.status for item in items] == ["generated", "generated", "planned"]
    assert all(item.title and item.body for item in items[:2])
    assert items[0].title != items[1].title
    assert items[0].task_id is not None
    assert items[0].run_id is not None
    assert items[0].quality_json["executor"] == "mock_or_skeleton"
    review_report = items[0].quality_json["review_report"]
    assert review_report["rewrite_required"] is False
    assert review_report["hard_results"][0]["ae_code"] == "brand_product_guard"
    assert review_report["hard_results"][0]["pass"] is True
    assert items[0].quality_json["hard_pass"] is True
    assert items[0].quality_json["soft_score_avg"] == 87.0
    assert items[0].diversity_json["opening_type"] == "过来人提醒"
    assert len(stage_calls) == 8


class RuntimeFastDraftReviewClient:
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        capability = envelope.get("capability")
        if capability == "xhs.interpret_brief":
            input_payload = envelope.get("input") or {}
            output = {
                "structured_brief": {
                    "brief_type": input_payload.get("brief_type"),
                    "product_topic": input_payload.get("product_topic"),
                    "target_audience": input_payload.get("target_audience"),
                    "style": input_payload.get("style"),
                },
                "generation_snapshot": input_payload.get("generation_snapshot"),
            }
        elif capability == "xhs.run_ae_analysis":
            output = {"analyses": {}, "failed_aes": []}
        elif capability == "xhs.generate_draft":
            output = {
                "draft": {"title": "runtime fast 标题", "body": "runtime fast 正文"},
                "runtime_result": {"mode": "runtime_fast", "final_path": "/tmp/runtime-fast/final.md"},
                "review_report": {
                    "hard_results": [
                        {
                            "ae_code": "compliance_redline",
                            "pass": True,
                            "risk_level": "low",
                            "feedback": "pass",
                            "evidence": [],
                        }
                    ],
                    "soft_scores": [],
                    "rewrite_required": True,
                    "suggestions": ["把记录几天改成持续记录"],
                },
            }
        elif capability == "xhs.run_ae_review":
            output = {"review_report": {}, "hard_results": [], "soft_scores": [], "failed_aes": []}
        elif capability == "xhs.rewrite_draft":
            previous = (envelope.get("input") or {}).get("previous_draft") or {}
            output = {"final": previous}
        else:
            output = {}
        return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})


@pytest.mark.asyncio
async def test_batch_execution_preserves_review_report_returned_by_generate_draft_runtime_fast():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ContentBatchJob.__table__,
                ContentBatchItem.__table__,
                ExecutorRegistry.__table__,
                ContentAgentTask.__table__,
                ContentAgentRun.__table__,
                ContentAgentStageCall.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="hermes_maga_worker",
                executor_type="hermes_profile",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={"executor_token": "test-token"},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_runtime_fast",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=_plan(1)))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=RuntimeFastDraftReviewClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.status == "generated"
    assert item.title == "runtime fast 标题"
    assert item.body == "runtime fast 正文"
    review_report = item.quality_json["review_report"]
    assert review_report["hard_results"][0]["ae_code"] == "compliance_redline"
    assert review_report["rewrite_required"] is True
    assert review_report["suggestions"] == ["把记录几天改成持续记录"]
    assert item.quality_json["hard_pass"] is True
    assert item.quality_json["executor"] == "runtime_fast"
    assert item.quality_json["soft_score_avg"] is None
    assert {stage.capability for stage in stage_calls} >= {"xhs.generate_draft", "xhs.run_ae_review"}


def _plan(item_no: int) -> dict:
    opening = ["过来人提醒", "真实经历", "误区澄清"][item_no - 1]
    return {
        "item_no": item_no,
        "asset_key": "yuanyue",
        "product_topic": "宝宝便便不规律",
        "target_audience": "新手妈妈",
        "style": "经验老道型",
        "painpoint_ref": {
            "asset_type": "painpoint_model",
            "asset_key": "yuanyue",
            "item_index": 0,
            "item_id": f"pain_{item_no}",
            "snapshot": {"painpoint": "便便不规律", "description": "便便状态不稳定", "selling_point": "好消化易吸收"},
        },
        "selling_point_ref": {
            "asset_type": "product_selling_points",
            "asset_key": "yuanyue",
            "item_index": 0,
            "item_id": f"sell_{item_no}",
            "snapshot": {"selling_point": "好消化易吸收", "advantage": "软凝乳"},
        },
        "reference_example_refs": [
            {
                "asset_type": "reference_examples",
                "asset_key": "yuanyue",
                "item_index": item_no - 1,
                "item_id": f"yuanyue_ref_{item_no:03d}",
                "snapshot": {"title": f"参考例文{item_no}", "body": "先观察宝宝便便状态", "painpoint": "便便不规律"},
            }
        ],
        "compliance_rule_refs": [
            {
                "asset_type": "compliance_rules",
                "asset_key": "yuanyue",
                "item_index": 0,
                "item_id": "rule_001",
                "snapshot": {"dimension": "禁止治疗便秘", "risk_level": "high"},
            }
        ],
        "diversity_slot": {
            "opening_type": opening,
            "structure_type": "痛点-观察-建议",
            "emotion": "稳",
            "cta_type": "轻建议",
            "forbidden_overlap_group": f"G{item_no:02d}",
        },
    }
