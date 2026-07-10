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
from app.services.content_batch_report_service import (
    ContentBatchReportService,
    _article_pool_item_exportable,
)
from app.schemas.content_batch_report import ContentBatchReportItem


def test_summary_reports_repeated_closure_clusters_only_near_body_end():
    service = ContentBatchReportService(db=None)
    items = [
        ContentBatchReportItem(
            item_id=1,
            item_no=1,
            status="generated",
            body="开头说省心，后面都是普通观察，继续写饭点、接娃、作业和出门安排，最后只落在普通记录。",
            body_chars=42,
        ),
        ContentBatchReportItem(
            item_id=2,
            item_no=2,
            status="generated",
            body="这段主要写孩子日常状态，最后妈妈心里有底。",
            body_chars=22,
        ),
        ContentBatchReportItem(
            item_id=3,
            item_no=3,
            status="generated",
            body="没有写成什么神奇变化，就是这杯奶放在家里确实省心。",
            body_chars=26,
        ),
        ContentBatchReportItem(
            item_id=4,
            item_no=4,
            status="generated",
            body="孩子愿意喝，家里也能坚持，贵也认了。",
            body_chars=18,
        ),
        ContentBatchReportItem(
            item_id=5,
            item_no=5,
            status="generated",
            body="先这么观察着，后面应该还会继续喝。",
            body_chars=18,
        ),
        ContentBatchReportItem(
            item_id=6,
            item_no=6,
            status="generated",
            body="队友说当初选得还行，我也觉得判断没错。",
            body_chars=20,
        ),
    ]

    stats = service._summary(items).closure_cluster_stats
    clusters = {cluster["cluster_code"]: cluster for cluster in stats["clusters"]}

    assert stats["total_checked"] == 6
    assert stats["closing_hit_count"] == 5
    assert clusters["peace_of_mind"]["count"] == 2
    assert clusters["peace_of_mind"]["watch"] is True
    assert clusters["peace_of_mind"]["warning"] is False
    assert [hit["item_no"] for hit in clusters["peace_of_mind"]["hits"]] == [2, 3]
    assert clusters["worth_it"]["count"] == 1
    assert clusters["keep_drinking"]["count"] == 1
    assert clusters["right_choice"]["count"] == 1
    assert clusters["right_choice"]["hits"][0]["phrases"] == ["判断没错", "选得还行"]


def test_report_surfaces_history_similarity_watch_without_rewrite():
    service = ContentBatchReportService(db=None)
    items = [
        ContentBatchReportItem(
            item_id=1,
            item_no=1,
            status="generated",
            body="第一段相同。第二段也相同。第三段继续相同。",
            quality={
                "similarity_watch": [
                    {
                        "similar_item_no": 8,
                        "similar_batch_id": 99,
                        "similar_batch_code": "batch_history",
                        "similarity_score": 0.53,
                        "scope": "history",
                        "watch": True,
                        "rewrite_required": False,
                    }
                ]
            },
        )
    ]

    service._attach_similarity_warnings(items)

    assert items[0].similarity_warnings[0].scope == "history"
    assert items[0].similarity_warnings[0].batch_id == 99
    assert items[0].similarity_warnings[0].score == 0.53


def test_article_pool_export_uses_final_postprocess_state():
    item = ContentBatchReportItem(
        item_id=1,
        item_no=1,
        status="generated",
        title="日常记录",
        body="正文",
        hard_pass=True,
        rewrite_required=False,
        quality={
            "hard_pass": True,
            "review_report": {"rewrite_required": False},
            "product_experience_llm_quality_failures": [
                {"error_message": "LLM review did not return a JSON object"}
            ],
        },
    )

    assert _article_pool_item_exportable(item) is False


def test_article_pool_export_allows_wangyue_v2_llm_review_unavailable_mark_only():
    item = ContentBatchReportItem(
        item_id=1,
        item_no=1,
        status="generated",
        title="日常记录",
        body="正文",
        hard_pass=True,
        rewrite_required=False,
        quality={
            "hard_pass": True,
            "review_report": {"rewrite_required": False},
            "product_experience_llm_quality_review_unavailable_mark_only": True,
            "product_experience_llm_quality_failures": [
                {"error_message": "LLM review did not return a JSON object"}
            ],
        },
    )

    assert _article_pool_item_exportable(item) is True


def test_article_pool_export_allows_mark_only_phrase_review():
    item = ContentBatchReportItem(
        item_id=1,
        item_no=1,
        status="generated",
        title="日常记录",
        body="正文",
        hard_pass=True,
        rewrite_required=False,
        quality={
            "hard_pass": True,
            "review_report": {"rewrite_required": False},
            "product_experience_phrase_guard": {
                "pass": False,
                "rewrite_required": True,
                "mark_rewrite_required": False,
                "reasons": ["wangyue_article_logic_drift_context"],
            },
            "product_experience_llm_quality_review": {
                "pass": True,
                "rewrite_required": False,
            },
        },
    )

    assert _article_pool_item_exportable(item) is True


def test_summary_reports_complete_content_path_skeleton():
    service = ContentBatchReportService(db=None)
    items = [
        ContentBatchReportItem(
            item_id=1,
            item_no=1,
            status="generated",
            body="选奶粉时对比了几款，最后看中旺玥。孩子每天喝完一杯，最近小脸圆润了点，我也放心些。",
            body_chars=45,
        ),
        ContentBatchReportItem(
            item_id=2,
            item_no=2,
            status="generated",
            body="给娃挑奶时看了成分，旺玥这罐他喝得挺顺，小腿摸着结实，准备继续喝。",
            body_chars=38,
        ),
        ContentBatchReportItem(
            item_id=3,
            item_no=3,
            status="generated",
            body="今天只是记录一下账单，旺玥不便宜，娃喝得还行。",
            body_chars=24,
        ),
    ]

    stats = service._summary(items).content_path_skeleton_stats

    assert stats["total_checked"] == 3
    assert stats["complete_skeleton_count"] == 2
    assert stats["complete_skeleton_ratio"] == 0.6667
    assert [hit["item_no"] for hit in stats["hits"]] == [1, 2]
    assert stats["part_counts"]["selection"] == 2
    assert stats["part_counts"]["drinking_acceptance"] == 3
    assert stats["part_counts"]["state_observation"] == 2
    assert stats["part_counts"]["mom_closure"] == 2


def test_summary_reports_real_user_pool_stats():
    service = ContentBatchReportService(db=None)
    items = [
        ContentBatchReportItem(
            item_id=1,
            item_no=1,
            status="generated",
            body="正文1",
            body_chars=3,
            generation_snapshot={
                "business_rule": {
                    "real_user_pool": {
                        "asset_key": "maternal_infant_xhs_real_user_pool",
                        "source_type_counts": {"note": 5, "comment": 2},
                        "layer_counts": {"route": 1, "texture": 3},
                        "route_family_counts": {"school_collective": 1},
                        "tag_counts": {"营养": 3, "价格": 1},
                        "risk_tag_counts": {"评论口吻": 2},
                        "dedupe_hashes": ["a", "b", "c"],
                        "title_reference": {"selected_titles": ["当妈后才懂"]},
                        "prompt_text_by_layer": {
                            "title_shape": ["选奶看花眼"],
                            "route": ["上幼儿园后接触人多"],
                            "texture": ["除了贵点没毛病"],
                            "opening_texture": ["说实话，选奶这事会纠结"],
                        },
                    }
                }
            },
        ),
        ContentBatchReportItem(
            item_id=2,
            item_no=2,
            status="generated",
            body="正文2",
            body_chars=3,
            generation_snapshot={
                "business_rule": {
                    "real_user_pool": {
                        "asset_key": "maternal_infant_xhs_real_user_pool",
                        "source_type_counts": {"note": 5, "comment": 2},
                        "layer_counts": {"route": 1, "texture": 3},
                        "route_family_counts": {"outdoor_activity": 1},
                        "tag_counts": {"营养": 2},
                        "risk_tag_counts": {"强功效": 1},
                        "dedupe_hashes": ["a", "d"],
                        "title_reference": {"selected_titles": ["当妈后才懂"]},
                        "prompt_text_by_layer": {
                            "title_shape": ["选奶看花眼"],
                            "route": ["户外活动多以后"],
                            "texture": ["除了贵点没毛病"],
                            "ending": ["先喝着记录一下"],
                        },
                    }
                }
            },
        ),
    ]

    stats = service._summary(items).real_user_pool_stats

    assert stats["enabled_item_count"] == 2
    assert stats["pool_assets"] == {"maternal_infant_xhs_real_user_pool": 2}
    assert stats["source_type_counts"] == {"note": 10, "comment": 4}
    assert stats["layer_counts"] == {"route": 2, "texture": 6}
    assert stats["route_family_counts"] == {"school_collective": 1, "outdoor_activity": 1}
    assert stats["tag_counts"]["营养"] == 5
    assert stats["risk_tag_counts"] == {"评论口吻": 2, "强功效": 1}
    assert stats["repeated_dedupe_hashes"] == [{"dedupe_hash": "a", "count": 2}]
    assert stats["title_reference_repeat_top"] == [
        {"text": "当妈后才懂", "count": 2},
        {"text": "选奶看花眼", "count": 2},
    ]
    assert stats["texture_repeat_top"] == [{"text": "除了贵点没毛病", "count": 2}]
    assert stats["route_repeat_top"] == []
    assert stats["opening_phrase_repeat_top"] == []


def test_summary_reports_mouth_phrase_budget_stats():
    service = ContentBatchReportService(db=None)
    budget = {
        "enabled": True,
        "allowed_terms": ["最近"],
        "avoid_terms": ["省心", "踏实"],
        "groups": [
            {
                "code": "time_recent",
                "name": "万能时间词",
                "terms": ["最近"],
                "max_count": 1,
            },
            {
                "code": "peace_closure",
                "name": "安心收口",
                "terms": ["省心", "踏实"],
                "max_count": 1,
            },
        ],
        "batch_item_count": 3,
    }
    items = [
        ContentBatchReportItem(
            item_id=1,
            item_no=1,
            status="generated",
            title="最近选奶记录",
            body="这段没有口癖。",
            body_chars=7,
            generation_snapshot={"business_rule": {"mouth_phrase_budget": budget}},
        ),
        ContentBatchReportItem(
            item_id=2,
            item_no=2,
            status="generated",
            title="普通标题",
            body="孩子愿意喝，当妈的省心一点。",
            body_chars=15,
            generation_snapshot={"business_rule": {"mouth_phrase_budget": {**budget, "allowed_terms": []}}},
        ),
        ContentBatchReportItem(
            item_id=3,
            item_no=3,
            status="generated",
            title="普通标题",
            body="这杯奶固定下来确实省心，晚上看着也踏实。",
            body_chars=22,
            generation_snapshot={"business_rule": {"mouth_phrase_budget": {**budget, "allowed_terms": []}}},
        ),
    ]

    stats = service._summary(items).mouth_phrase_budget_stats

    assert stats["enabled_item_count"] == 3
    term_stats = {item["term"]: item for item in stats["term_stats"]}
    assert term_stats["最近"]["count"] == 1
    assert term_stats["最近"]["hits"][0]["title_count"] == 1
    assert term_stats["省心"]["count"] == 2
    over_budget = {item["group_code"]: item for item in stats["over_budget_groups"]}
    assert "time_recent" not in over_budget
    assert over_budget["peace_closure"]["count"] == 3


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
async def test_report_marks_rewrite_required_item_as_not_hard_pass():
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
        job = ContentBatchJob(
            batch_code="batch_rewrite_required_hard_pass",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="generated",
        )
        session.add(job)
        await session.flush()
        session.add(
            ContentBatchItem(
                batch_id=job.id,
                item_no=1,
                status="generated",
                plan_json={},
                title="短了",
                body="给娃开始喝旺玥，心里顺了",
                quality_json={
                    "hard_pass": True,
                    "review_report": {
                        "rewrite_required": True,
                        "rewrite_reason": "业务规则口癖骨架或长度仍需人工处理",
                    },
                },
            )
        )
        await session.commit()

    async with session_factory() as session:
        report = await ContentBatchReportService(session).get_batch_report(job.id, include_details=True)

    assert report.items[0].hard_pass is False
    assert report.items[0].rewrite_required is True
    assert report.summary.hard_pass_count == 0
    assert report.summary.remaining_rewrite_required_count == 1

    await engine.dispose()


def test_report_surfaces_business_usability_tier_from_llm_quality_review():
    service = ContentBatchReportService(db=None)
    item = ContentBatchItem(
        id=1,
        batch_id=1,
        item_no=1,
        status="generated",
        title="最近喝奶这事",
        body="家里旺玥一直在喝，孩子这阵状态挺稳。",
        quality_json={
            "hard_pass": True,
            "review_report": {"rewrite_required": False},
            "product_experience_llm_quality_review": {
                "business_usability_tier": "light_fix_usable",
                "business_usability_reason": "标题一般但种草内核成立",
            },
        },
    )

    report_item = service._report_item(item, [], include_details=False)
    summary = service._summary([report_item])

    assert report_item.business_usability_tier == "light_fix_usable"
    assert report_item.business_usability_reason == "标题一般但种草内核成立"
    assert summary.business_usability_stats == {
        "counts": {"direct_pool": 0, "light_fix_usable": 1, "hold_out": 0},
        "item_nos_by_tier": {"light_fix_usable": [1]},
    }
    assert report_item.quality["product_experience_llm_quality_review"]["business_usability_tier"] == "light_fix_usable"


def test_business_usability_stats_excludes_final_postprocess_failures():
    service = ContentBatchReportService(db=None)
    items = [
        ContentBatchReportItem(
            item_id=1,
            item_no=1,
            status="generated",
            title="可用",
            body="家里旺玥一直在喝，孩子状态挺稳。",
            hard_pass=True,
            rewrite_required=False,
            business_usability_tier="direct_pool",
            quality={
                "hard_pass": True,
                "review_report": {"rewrite_required": False},
                "product_experience_llm_quality_review": {
                    "pass": True,
                    "rewrite_required": False,
                    "business_usability_tier": "direct_pool",
                },
            },
        ),
        ContentBatchReportItem(
            item_id=2,
            item_no=2,
            status="generated",
            title="禁词未清",
            body="担心体质跟不上，后来选了旺玥。",
            hard_pass=False,
            rewrite_required=True,
            rewrite_reason="业务规则口癖骨架或长度仍需人工处理",
            business_usability_tier="direct_pool",
            quality={
                "hard_pass": True,
                "review_report": {
                    "rewrite_required": True,
                    "rewrite_reason": "业务规则口癖骨架或长度仍需人工处理",
                },
                "product_experience_llm_quality_review": {
                    "pass": True,
                    "rewrite_required": False,
                    "business_usability_tier": "direct_pool",
                },
            },
        ),
    ]

    stats = service._summary(items).business_usability_stats

    assert stats["counts"]["direct_pool"] == 1
    assert stats["item_nos_by_tier"]["direct_pool"] == [1]
    assert stats["excluded_by_final_postprocess"] == [
        {
            "item_no": 2,
            "business_usability_tier": "direct_pool",
            "rewrite_reason": "业务规则口癖骨架或长度仍需人工处理",
            "reasons": ["业务规则口癖骨架或长度仍需人工处理"],
        }
    ]


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

        report = await ContentBatchReportService(session).get_batch_report(job.id, include_details=True)

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
