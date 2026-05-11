"""Tests for operator-facing content batch reports."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ContentAgentRun, ContentAgentStageCall, ContentBatchItem, ContentBatchItemVersion, ContentBatchJob
from app.services.content_batch_report_service import ContentBatchReportService


@pytest.mark.asyncio
async def test_batch_report_returns_operator_summary_items_and_runtime_artifacts():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ContentBatchJob.__table__,
                ContentBatchItem.__table__,
                ContentBatchItemVersion.__table__,
                ContentAgentStageCall.__table__,
                ContentAgentRun.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        job = ContentBatchJob(
            batch_code="batch_report_test",
            asset_key="yuanyue",
            product_topic="源悦小红书小批量",
            target_audience="新手妈妈",
            style="真实口语化",
            count=3,
            status="generated",
        )
        session.add(job)
        await session.flush()
        session.add_all(
            [
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=1,
                    status="generated",
                    plan_json={"product_topic": "宝宝便便不规律"},
                    run_id=101,
                    task_id=201,
                    title="宝宝便便乱？先别慌",
                    body="新手妈妈先别急着下结论，日常观察宝宝状态、吃奶和睡眠，再慢慢判断喂养节奏。",
                    quality_json={
                        "executor": "runtime_fast",
                        "hard_pass": True,
                        "review_report": {
                            "rewrite_required": False,
                            "rewrite_reason": "soft_suggestions",
                            "rewrite_rounds": 1,
                            "suggestions": [],
                            "replacement_needed": [],
                        },
                    },
                    diversity_json={"opening_type": "过来人提醒", "structure_type": "痛点-观察-建议"},
                ),
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=2,
                    status="generated",
                    plan_json={"product_topic": "转奶期肚肚敏感"},
                    run_id=102,
                    task_id=202,
                    title="转奶别硬来",
                    body="转奶期别急，先看宝宝喝奶状态和肚肚感受，慢慢调整节奏。",
                    quality_json={
                        "executor": "runtime_fast",
                        "hard_pass": True,
                        "review_report": {"rewrite_required": False, "suggestions": [], "replacement_needed": []},
                    },
                    diversity_json={"opening_type": "真实经历", "structure_type": "经历-观察-选择逻辑"},
                ),
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=3,
                    status="generated",
                    plan_json={"product_topic": "奶量上不去"},
                    title="不要自己判断",
                    body="如果状态不对，及时问医生。",
                    quality_json={
                        "hard_pass": False,
                        "review_report": {
                            "hard_results": [
                                {
                                    "pass": False,
                                    "ae_code": "compliance_redline",
                                    "evidence": ["医生"],
                                    "feedback": "fail",
                                    "risk_level": "high",
                                }
                            ]
                        },
                    },
                ),
            ]
        )
        started_at = datetime(2026, 5, 10, 12, 0, 0)
        session.add(
            ContentAgentRun(
                id=101,
                task_id=201,
                executor_code="hermes_maga_worker",
                status="succeeded",
                started_at=started_at,
                finished_at=started_at + timedelta(milliseconds=3200),
            )
        )
        session.add(
            ContentAgentStageCall(
                stage_call_id="stage-101-generate",
                run_id=101,
                sequence_no=3,
                capability="xhs.generate_draft",
                status="succeeded",
                stats_json={"total_latency_ms": 1200},
                output_snapshot={
                    "runtime_result": {
                        "mode": "runtime_fast",
                        "final_path": "/tmp/runtime-fast-101/final.md",
                        "debug_dir": "/tmp/runtime-fast-101",
                    }
                },
            )
        )
        await session.commit()

        report = await ContentBatchReportService(session).get_batch_report(job.id)

    assert report.batch_id == job.id
    assert report.batch_code == "batch_report_test"
    assert report.summary.total_count == 3
    assert report.summary.generated_count == 3
    assert report.summary.failed_count == 0
    assert report.summary.hard_pass_count == 2
    assert report.summary.rewrite_item_count == 1
    assert report.summary.remaining_rewrite_required_count == 0
    assert report.summary.avg_body_chars > 0
    assert 0 <= report.summary.max_pairwise_jaccard_2gram <= 1

    first = report.items[0]
    assert first.item_no == 1
    assert first.title == "宝宝便便乱？先别慌"
    assert first.body.startswith("新手妈妈")
    assert first.hard_pass is True
    assert first.rewrite_reason == "soft_suggestions"
    assert first.rewrite_rounds == 1
    assert first.suggestion_count == 0
    assert first.replacement_count == 0
    assert first.runtime_mode == "runtime_fast"
    assert first.generation_duration_ms == 1200
    assert first.total_duration_ms == 3200
    assert first.trace_run_id == 101
    assert first.trace_stage_calls[0].stage_call_id == "stage-101-generate"
    assert first.final_path == "/tmp/runtime-fast-101/final.md"
    assert first.debug_dir == "/tmp/runtime-fast-101"
    assert first.opening_type == "过来人提醒"

    rejected = report.items[2]
    assert rejected.status == "generated"
    assert rejected.hard_pass is False
    assert rejected.reject_reasons[0].source == "hard_review"
    assert rejected.reject_reasons[0].code == "compliance_redline"
    assert rejected.reject_reasons[0].message == "命中硬性审核红线：医生"
    assert rejected.reject_reasons[0].evidence == ["医生"]
