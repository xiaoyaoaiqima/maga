"""Tests for MAGA batch content planner."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.maga_assets import AssetRegistry
from app.models.content_agent import ContentBatchJob, ContentBatchItem
from app.services.content_batch_planner import ContentBatchPlanner


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
    assert all(item.plan_json["compliance_rule_refs"] for item in items)

    opening_types = {item.plan_json["diversity_slot"]["opening_type"] for item in items}
    structure_types = {item.plan_json["diversity_slot"]["structure_type"] for item in items}
    plan_signatures = {
        (
            item.plan_json["painpoint_ref"]["item_index"],
            item.plan_json["selling_point_ref"]["item_index"],
            item.plan_json["reference_example_refs"][0]["item_index"],
            item.plan_json["diversity_slot"]["opening_type"],
            item.plan_json["diversity_slot"]["structure_type"],
        )
        for item in items
    }

    assert len(opening_types) >= 6
    assert len(structure_types) >= 5
    assert len(plan_signatures) >= 90
