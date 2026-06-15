"""Tests for MAGA batch content planner."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.maga_assets import AssetRegistry
from app.models.content_agent import ContentBatchJob, ContentBatchItem
from app.services.content_batch_planner import ContentBatchPlanner


def test_product_experience_generation_limit_prefers_requested_count():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    asset = AssetRegistry(
        metadata_json={"default_generation_count": 10},
        content_json={"default_generation_count": 20},
    )
    rules = [
        {"product_experience": f"体验{i}", "corpus": "像真实妈妈分享产品使用体验。"}
        for i in range(1200)
    ]

    limit = service._product_experience_generation_limit(asset, rules, requested_count=1000)

    assert limit == 1000


def test_article_business_rule_plan_samples_three_examples_from_pool():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "product_experience_001",
        "product_experience": "0-6个月，3个月内，奶量补充",
        "corpus": "围绕奶量补充写真实使用体验。",
        "examples": [f"参考示例{i}" for i in range(20)],
        "supplements": ["补充参考1"],
        "source_row_no": 1,
    }
    asset = AssetRegistry(
        asset_type="article_business_rule_set",
        asset_key="yuanyue_product_experience",
        content_json={"rule_type": "product_experience"},
        metadata_json={},
    )

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="default_system_prompt_keywords",
        quality_guard_profile_key=None,
        model_config=None,
    )

    assert len(plan["examples"]) == 3
    assert set(plan["examples"]).issubset(set(rule["examples"]))
    assert plan["supplements"] == []
    assert plan["example_pool_count"] == 20
    assert plan["supplement_pool_count"] == 1
    assert plan["example_sample_count"] == 3
    assert plan["selected_example_source"] == "examples"
    assert len(plan["selected_example_indices"]) == 3


@pytest.mark.asyncio
async def test_content_batch_planner_creates_100_diverse_yuanyue_plans():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, ContentBatchJob.__table__, ContentBatchItem.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add_all(
            [
                AssetRegistry(
                    asset_type="painpoint_model",
                    asset_key="yuanyue",
                    display_name="源悦痛点模型",
                    version_no=1,
                    status="active",
                    content_json={
                        "items": [
                            {"painpoint": "便便不规律", "symptom": "拉臭费劲", "description": "便便状态不稳定", "selling_point": "好消化易吸收"},
                            {"painpoint": "肚肚不舒服", "symptom": "胀气", "description": "喝奶后肚肚闹腾", "selling_point": "温和"},
                            {"painpoint": "换奶适应", "symptom": "适应慢", "description": "换奶期担心不适应", "selling_point": "软分子蛋白"},
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="product_selling_points",
                    asset_key="yuanyue",
                    display_name="源悦产品卖点",
                    version_no=1,
                    status="active",
                    content_json={
                        "items": [
                            {"selling_point": "好消化易吸收", "advantage": "软凝乳"},
                            {"selling_point": "温和", "advantage": "亲和宝宝肚肚"},
                            {"selling_point": "软分子蛋白", "advantage": "结构松散"},
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="reference_examples",
                    asset_key="yuanyue",
                    display_name="源悦参考例文",
                    version_no=1,
                    status="active",
                    content_json={
                        "items": [
                            {"example_id": "ex1", "title": "过来人经验", "body": "先观察宝宝便便状态", "style_tags": ["经验笔记"]},
                            {"example_id": "ex2", "title": "场景共鸣", "body": "新手妈妈别焦虑", "style_tags": ["场景共鸣"]},
                            {"example_id": "ex3", "title": "选择清单", "body": "看消化和适应", "style_tags": ["清单型"]},
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="reference_writing_patterns",
                    asset_key="yuanyue",
                    display_name="源悦写法资产",
                    version_no=1,
                    status="active",
                    asset_stage="candidate",
                    content_json={
                        "items": [
                            {
                                "pattern_id": "wp1",
                                "topic_fit": ["便便不规律"],
                                "audience_fit": ["新手妈妈"],
                                "style_fit": ["经验老道型"],
                                "opening_pattern": "先共情便便焦虑",
                                "story_arc": "痛点场景 -> 观察判断 -> 轻建议",
                                "proof_style": "日常观察记录",
                            },
                            {
                                "pattern_id": "wp2",
                                "topic_fit": ["换奶适应"],
                                "audience_fit": ["转奶期宝宝家长"],
                                "style_fit": ["清单型"],
                                "opening_pattern": "先列换奶清单",
                                "story_arc": "清单 -> 对比 -> 收束",
                                "proof_style": "清单建议",
                            },
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="compliance_rules",
                    asset_key="yuanyue",
                    display_name="源悦审核规则",
                    version_no=1,
                    status="active",
                    content_json={"items": [{"dimension": "禁止治疗便秘", "risk_level": "high"}]},
                ),
            ]
        )
        await session.commit()

        planner = ContentBatchPlanner(session)
        job = await planner.create_batch_plan(
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=100,
            created_by="test",
        )
        await session.commit()

    async with session_factory() as session:
        items = (
            await session.execute(
                select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no)
            )
        ).scalars().all()

    assert job.count == 100
    assert len(items) == 100
    assert all(item.status == "planned" for item in items)
    assert all(item.plan_json["asset_key"] == "yuanyue" for item in items)
    assert all(item.plan_json["painpoint_ref"] for item in items)
    assert all(item.plan_json["reference_example_refs"] for item in items)
    assert all(item.plan_json["writing_pattern_ref"] for item in items)
    assert all(item.plan_json["compliance_rule_refs"] for item in items)
    assert all(item.plan_json["brief_constraints"]["word_count"] == "150-250" for item in items)
    assert all(item.plan_json["brief_constraints"]["emoji"] == "少量" for item in items)

    opening_types = {item.plan_json["diversity_slot"]["opening_type"] for item in items}
    structure_types = {item.plan_json["diversity_slot"]["structure_type"] for item in items}
    narrative_focuses = {item.plan_json["diversity_slot"]["narrative_focus"] for item in items}
    cta_types = {item.plan_json["diversity_slot"]["cta_type"] for item in items}
    content_angles = {item.plan_json["diversity_slot"]["content_angle"] for item in items}
    scene_types = {item.plan_json["diversity_slot"]["scene_type"] for item in items}
    evidence_types = {item.plan_json["diversity_slot"]["evidence_type"] for item in items}
    asset_combo_keys = [item.plan_json["asset_combo_key"] for item in items]
    plan_signatures = {
        (
            item.plan_json["painpoint_ref"]["item_index"],
            item.plan_json["selling_point_ref"]["item_index"],
            item.plan_json["reference_example_refs"][0]["item_index"],
            item.plan_json["diversity_slot"]["opening_type"],
            item.plan_json["diversity_slot"]["structure_type"],
            item.plan_json["diversity_slot"]["narrative_focus"],
        )
        for item in items
    }

    assert len(opening_types) >= 6
    assert len(structure_types) >= 5
    assert len(narrative_focuses) >= 6
    assert len(cta_types) >= 4
    assert len(content_angles) >= 6
    assert len(scene_types) >= 4
    assert len(evidence_types) >= 4
    assert len(plan_signatures) >= 90
    assert len(set(asset_combo_keys[:27])) == 27
    assert items[27].plan_json["asset_reuse_reason"] == "素材组合池已用完，按轮换策略复用"
    assert items[0].plan_json["writing_pattern_ref"]["item_id"] == "wp1"


@pytest.mark.asyncio
async def test_content_batch_planner_accepts_topic_based_painpoint_model():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, ContentBatchJob.__table__, ContentBatchItem.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add_all(
            [
                AssetRegistry(
                    asset_type="painpoint_model",
                    asset_key="yuanyue",
                    display_name="源悦主题/痛点模型",
                    version_no=1,
                    status="active",
                    content_json={
                        "topics": [
                            {
                                "topic": "便便不规律",
                                "descriptions": ["羊屎蛋/干硬", "便便又干又硬"],
                                "selling_points": [{"selling_point": "好消化易吸收"}],
                            }
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="product_selling_points",
                    asset_key="yuanyue",
                    display_name="源悦产品卖点",
                    version_no=1,
                    status="active",
                    content_json={"items": [{"selling_point": "好消化易吸收", "advantage": "软凝乳"}]},
                ),
                AssetRegistry(
                    asset_type="reference_examples",
                    asset_key="yuanyue",
                    display_name="源悦参考例文",
                    version_no=1,
                    status="active",
                    content_json={"items": [{"example_id": "ex1", "title": "过来人经验", "body": "新手妈妈别焦虑"}]},
                ),
                AssetRegistry(
                    asset_type="reference_writing_patterns",
                    asset_key="yuanyue",
                    display_name="源悦写法资产",
                    version_no=1,
                    status="active",
                    asset_stage="candidate",
                    content_json={
                        "items": [
                            {
                                "pattern_id": "wp_topic",
                                "topic_fit": ["便便不规律"],
                                "audience_fit": ["新手妈妈"],
                                "style_fit": ["经验老道型"],
                                "opening_pattern": "先共情便便焦虑",
                            }
                        ]
                    },
                ),
            ]
        )
        await session.commit()

        job = await ContentBatchPlanner(session).create_batch_plan(
            asset_key="yuanyue",
            product_topic="便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=1,
            created_by="test",
        )
        await session.commit()
        item = await session.scalar(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id))

    assert item is not None
    painpoint = item.plan_json["painpoint_ref"]["snapshot"]
    assert painpoint["painpoint"] == "便便不规律"
    assert painpoint["description"] == "羊屎蛋/干硬；便便又干又硬"
    assert painpoint["selling_point"] == "好消化易吸收"
    assert item.plan_json["writing_pattern_ref"]["item_id"] == "wp_topic"


@pytest.mark.asyncio
async def test_content_batch_planner_accepts_article_business_rule_set_focus_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, ContentBatchJob.__table__, ContentBatchItem.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="article_business_rule_set",
                asset_key="a2_sentiment_post_activity",
                display_name="A2舆情相关帖子业务规则",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "rule_type": "article_business",
                    "activity_name": "A2舆情相关帖子",
                    "quality_guard_profile_key": "a2_sentiment_post_202606",
                    "generation_requirements": "输出 JSON 对象，字段为 title 和 body。",
                    "items": [
                        {
                            "rule_id": "post_rule_001",
                            "business_rule": "门店到货",
                            "corpus": "写a2到货后的真实短帖。",
                            "source_row_no": 1,
                        },
                        {
                            "rule_id": "post_rule_002",
                            "business_rule": "线上有货",
                            "corpus": "写线上看到a2有货后的真实短帖。",
                            "source_row_no": 2,
                        },
                    ],
                },
            )
        )
        await session.commit()

        job = await ContentBatchPlanner(session).create_batch_plan(
            asset_key="a2_sentiment_post_activity",
            rule_id="post_rule_002",
            product_topic=None,
            target_audience=None,
            style=None,
            count=10,
            created_by="test",
        )
        await session.commit()
        items = (
            await session.execute(
                select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no)
            )
        ).scalars().all()

    assert job.product_topic == "A2舆情相关帖子"
    assert job.strategy_json["source"] == "article_business_rule_set"
    assert job.strategy_json["quality_guard_profile_key"] == "a2_sentiment_post_202606"
    assert len(items) == 10
    assert {item.plan_json["rule_id"] for item in items} == {"post_rule_002"}
    assert all(item.plan_json["output_fields"] == ["title", "body"] for item in items)
    assert all(item.plan_json["quality_guard_profile_key"] == "a2_sentiment_post_202606" for item in items)
    sixth_slot = items[5].plan_json["diversity_slot"]
    assert sixth_slot["opening_type"] != "反焦虑安抚"
    assert sixth_slot["persona_lens"] != "容易焦虑的妈妈"
    assert sixth_slot["evidence_type"] != "清单建议"
    assert sixth_slot["cta_type"] != "轻建议"
    slots = [item.plan_json["diversity_slot"] for item in items]
    business_terms = ("报告", "罐底", "蜡样", "批次", "看不懂", "不太懂", "不会看")
    assert all("report_reaction" not in slot for slot in slots)
    assert not any(
        term in str(slot_value)
        for slot in slots
        for slot_value in slot.values()
        for term in business_terms
    )
