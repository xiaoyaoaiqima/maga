"""Tests for MAGA batch content planner."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.maga_assets import AssetRegistry
from app.models.content_agent import ContentBatchJob, ContentBatchItem
from app.services.content_batch_planner import ContentBatchPlanner


def test_article_business_generation_limit_prefers_requested_count():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    asset = AssetRegistry(
        metadata_json={"default_generation_count": 10},
        content_json={"default_generation_count": 20},
    )
    rules = [
        {"business_rule": f"体验{i}", "corpus": "像真实妈妈分享业务规则。"}
        for i in range(1200)
    ]

    limit = service._product_experience_generation_limit(asset, rules, requested_count=1000)

    assert limit == 1000


def test_article_business_rule_plan_samples_three_examples_from_pool():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "奶量补充",
        "corpus": "围绕奶量补充写真实使用体验。",
        "examples": [f"参考示例{i}" for i in range(20)],
        "supplements": ["补充参考1"],
        "source_row_no": 1,
    }
    asset = AssetRegistry(
        asset_type="article_business_rule_set",
        asset_key="yuanyue_product_experience",
        content_json={"rule_type": "business_rule"},
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


def test_article_business_rule_plan_uses_asset_model_config_with_request_override():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "奶量补充",
        "corpus": "围绕奶量补充写真实使用体验。",
        "examples": ["参考示例1", "参考示例2", "参考示例3"],
        "source_row_no": 1,
    }
    asset = AssetRegistry(
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        content_json={
            "rule_type": "business_rule",
            "model_config": {"temperature": 0.9, "max_tokens": 2048},
        },
        metadata_json={},
    )

    default_plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
    )
    override_plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config={"temperature": 0.7},
    )

    assert default_plan["model_config"]["temperature"] == 0.9
    assert default_plan["model_config"]["max_tokens"] == 2048
    assert override_plan["model_config"]["temperature"] == 0.7
    assert override_plan["model_config"]["max_tokens"] == 2048


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
    assert job.diversity_plan_json == {}
    assert all("diversity_slot" not in item.plan_json for item in items)

    asset_combo_keys = [item.plan_json["asset_combo_key"] for item in items]
    plan_signatures = {
        (
            item.plan_json["painpoint_ref"]["item_index"],
            item.plan_json["selling_point_ref"]["item_index"],
            item.plan_json["reference_example_refs"][0]["item_index"],
        )
        for item in items
    }

    assert len(plan_signatures) == 27
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
    assert job.diversity_plan_json == {}
    assert all("diversity_slot" not in item.plan_json for item in items)
