"""Tests for operator-facing content batch reports."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import (
    ContentAgentRun,
    ContentAgentStageCall,
    ContentBatchItem,
    ContentBatchItemVersion,
    ContentBatchJob,
    ContentFeedback,
)
from app.models.maga_assets import AssetRegistry
from app.services.content_batch_report_service import ContentBatchReportService


@pytest.mark.asyncio
async def test_list_batch_reports_filters_by_asset_and_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ContentBatchJob.__table__,
                ContentBatchItem.__table__,
                ContentBatchItemVersion.__table__,
                ContentFeedback.__table__,
                ContentAgentStageCall.__table__,
                ContentAgentRun.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        job_a = ContentBatchJob(
            batch_code="comment_a_rule_1",
            asset_key="comment_asset_a",
            product_topic="评论测试 A",
            count=1,
            status="generated",
        )
        job_b = ContentBatchJob(
            batch_code="comment_a_rule_2",
            asset_key="comment_asset_a",
            product_topic="评论测试 A",
            count=1,
            status="generated",
        )
        job_c = ContentBatchJob(
            batch_code="comment_b_rule_1",
            asset_key="comment_asset_b",
            product_topic="评论测试 B",
            count=1,
            status="generated",
        )
        session.add_all([job_a, job_b, job_c])
        await session.flush()
        session.add_all(
            [
                ContentBatchItem(
                    batch_id=job_a.id,
                    item_no=1,
                    status="generated",
                    plan_json={"rule_id": "business_rule_001", "source_row_no": 5},
                    body="第一条规则的结果",
                    quality_json={"hard_pass": True},
                ),
                ContentBatchItem(
                    batch_id=job_b.id,
                    item_no=1,
                    status="generated",
                    plan_json={"rule_id": "business_rule_002", "source_row_no": "8"},
                    body="第二条规则的结果",
                    quality_json={"hard_pass": True},
                ),
                ContentBatchItem(
                    batch_id=job_c.id,
                    item_no=1,
                    status="generated",
                    plan_json={"rule_id": "business_rule_001", "source_row_no": 5},
                    body="另一个规则包的结果",
                    quality_json={"hard_pass": True},
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        service = ContentBatchReportService(session)
        asset_result = await service.list_batch_reports(asset_key="comment_asset_a", limit=10)
        rule_result = await service.list_batch_reports(
            asset_key="comment_asset_a",
            rule_id="business_rule_002",
            source_row_no=8,
            limit=10,
        )

    assert asset_result.total == 2
    assert {item.batch_code for item in asset_result.items} == {
        "comment_a_rule_1",
        "comment_a_rule_2",
    }
    assert rule_result.total == 1
    assert rule_result.items[0].batch_code == "comment_a_rule_2"

    await engine.dispose()


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
                ContentFeedback.__table__,
                ContentAgentStageCall.__table__,
                ContentAgentRun.__table__,
                AssetRegistry.__table__,
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
                    plan_json={
                        "rule_type": "business_rule",
                        "business_rule": "宝宝便便不规律",
                        "product_topic": "宝宝便便不规律",
                        "asset_combo_key": "pain:0|sell:0|example:0",
                        "unified_generation": {
                            "capability": "content.generate",
                            "selected_keywords": [
                                {
                                    "category_code": "persona",
                                    "category_name": "人设",
                                    "keyword_code": "real_mom",
                                    "keyword_name": "真实妈妈",
                                    "corpus": ["像真实妈妈一样说具体经历"],
                                }
                            ],
                            "keyword_asset": {
                                "asset_type": "content_generation_keywords",
                                "asset_key": "default_content_generation_keywords",
                                "version_no": 2,
                            },
                            "expert": {
                                "expert_config_code": "article_generator_v1",
                                "expert_config_name": "文章生成 Expert",
                                "model_config": {
                                    "provider_code": "aihubmix",
                                    "model_code": "deepseek-v4-flash",
                                    "temperature": 0.8,
                                },
                            },
                            "rendered_prompt": "业务=宝宝便便不规律\n关键词=真实妈妈",
                        },
                    },
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
                    diversity_json={
                        "opening_type": "过来人提醒",
                        "structure_type": "痛点-观察-建议",
                        "content_angle": "误区澄清",
                        "persona_lens": "新手妈妈",
                        "scene_type": "便便观察",
                        "evidence_type": "观察指标",
                    },
                ),
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=2,
                    status="generated",
                    plan_json={
                        "product_topic": "转奶期肚肚敏感",
                        "asset_combo_key": "pain:0|sell:0|example:0",
                        "asset_reuse_reason": "素材组合池已用完，按轮换策略复用",
                    },
                    run_id=102,
                    task_id=202,
                    title="转奶别硬来",
                    body="新手妈妈先别急着下结论，日常观察宝宝状态、吃奶和睡眠，再慢慢判断喂养节奏。",
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
                executor_code="maga_direct_llm_executor",
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
                capability="content.generate",
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
        session.add(
            ContentFeedback(
                batch_id=job.id,
                item_id=1,
                action="request_revision",
                review_status="needs_revision",
                comment="开头再具体一点",
                submitter="reviewer-a",
            )
        )
        session.add(
            AssetRegistry(
                asset_type="business_forbidden_terms",
                asset_key="yuanyue",
                display_name="源悦业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "schema_version": "1",
                    "terms": [{"term": "医生", "enabled": True}],
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
    assert report.summary.similarity_warning_count == 2

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
    assert first.feedback_count == 1
    assert first.similarity_warnings[0].item_no == 2
    assert first.similarity_warnings[0].score >= 0.42
    assert first.trace_stage_calls[0].stage_call_id == "stage-101-generate"
    assert first.final_path == "/tmp/runtime-fast-101/final.md"
    assert first.debug_dir == "/tmp/runtime-fast-101"
    assert first.opening_type == "过来人提醒"
    assert first.content_angle == "误区澄清"
    assert first.persona_lens == "新手妈妈"
    assert first.scene_type == "便便观察"
    assert first.evidence_type == "观察指标"
    assert first.asset_combo_key == "pain:0|sell:0|example:0"
    assert first.generation_snapshot is not None
    assert first.generation_snapshot["rule_type"] == "business_rule"
    assert first.generation_snapshot["business_rule"]["product_topic"] == "宝宝便便不规律"
    assert first.generation_snapshot["selected_keywords"][0]["keyword_name"] == "真实妈妈"
    assert first.generation_snapshot["expert"]["expert_config_code"] == "article_generator_v1"
    assert first.generation_snapshot["model_route"]["model_code"] == "deepseek-v4-flash"
    assert "宝宝便便不规律" in first.generation_snapshot["rendered_prompt"]
    assert first.generation_snapshot["execution_stages"][0]["stage_call_id"] == "stage-101-generate"
    assert report.items[1].asset_reuse_reason == "素材组合池已用完，按轮换策略复用"

    rejected = report.items[2]
    assert rejected.status == "generated"
    assert rejected.hard_pass is False
    assert rejected.reject_reasons[0].source == "hard_review"
    assert rejected.reject_reasons[0].code == "compliance_redline"
    assert rejected.reject_reasons[0].message == "命中硬性审核红线：医生"
    assert rejected.reject_reasons[0].evidence == ["医生"]
    assert rejected.forbidden_hits == ["医生"]
    assert rejected.reject_reasons[1].source == "forbidden_term"
    assert rejected.reject_reasons[1].message == "命中禁用词：医生"
