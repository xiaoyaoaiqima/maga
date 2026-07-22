"""API tests for MAGA Asset Steward surfaces."""

import json

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.assets import router
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import ExecutorRegistry
from app.models.expert_config import ExpertConfig
from app.models.maga_assets import AssetChangeProposal, AssetChangeRequest, AssetImportRun, AssetRegistry
from app.services.comment_business_rule_service import _row_to_rule_item as _comment_row_to_rule_item
from app.services.product_experience_rule_service import _row_to_rule_item, _warnings_for_items


def test_comment_rule_item_parses_content_direction_and_generation_material():
    item = _comment_row_to_rule_item(
        {
            "rule_id": "a2_direct_35",
            "业务规则名称": "批批检-检测透明中立认可",
            "内容方向": "围绕看到一项品牌信息后的普通用户反应自然接话。",
            "内容素材": "a2公开每批检测信息\n对应批次报告可以查询",
            "示例": "现在能看报告挺好，我会再观察一阵",
        },
        1,
    )

    assert item is not None
    assert item["corpus"] == "围绕看到一项品牌信息后的普通用户反应自然接话。"
    assert item["content_direction"] == item["corpus"]
    assert item["activity_material"] == ["a2公开每批检测信息", "对应批次报告可以查询"]


def test_comment_rule_item_builds_one_prompt_bundle_from_operator_columns():
    item = _comment_row_to_rule_item(
        {
            "rule_id": "a2_direct_01",
            "业务规则名称": "有货-直给简单报喜",
            "生文指令": "生成一条小红书母婴社区真实用户评论，口语化，有活人感。",
            "内容方向": "写看到有货了的即时反应，像在评论区简单报喜。",
            "内容素材": "a2已经到货、来货，或重新能买到。||品牌或产品名可写a2或a2至初。",
            "写法": "字数在20字以内",
            "生成要求": "不要说缺货、断粮等消极词。",
        },
        1,
    )

    assert item is not None
    assert item["prompt_mode"] == "comment_prompt_bundle"
    assert item["comment_prompt_bundle"] == {
        "generation_instruction": "生成一条小红书母婴社区真实用户评论，口语化，有活人感。",
        "content_direction": "写看到有货了的即时反应，像在评论区简单报喜。",
        "activity_material": [
            "a2已经到货、来货，或重新能买到。",
            "品牌或产品名可写a2或a2至初。",
        ],
        "writing_requirements": ["字数在20字以内"],
        "notes": ["不要说缺货、断粮等消极词。"],
    }


def test_row_to_rule_item_does_not_infer_product_mode_when_post_type_is_explicit():
    item = _row_to_rule_item(
        {
            "业务规则名称": "V2M-01｜进阶保护力｜使用反馈｜容易中招",
            "规则语料": "任务：写小红书妈妈UGC正向种草笔记。",
            "帖子类型": "使用反馈",
            "痛点": "容易中招",
            "卖点方向": "进阶保护力",
        },
        1,
    )

    assert item is not None
    assert item["post_type"] == "使用反馈"
    assert item["painpoint"] == "容易中招"
    assert item["selling_point"] == "进阶保护力"
    assert "product_appearance_mode" not in item
    assert "product_relation" not in item


def test_row_to_rule_item_parses_five_layer_article_fields_and_legacy_activity_pools():
    item = _row_to_rule_item(
        {
            "业务规则名称": "妈妈班｜老师讲解",
            "生文指令": "写一篇真实待产妈妈参加a2妈妈班后的分享。",
            "内容方向": "写老师讲完后，妈妈理清新生儿奶粉选择标准。",
            "灵感线索": "和课后记下的一句话有关。",
            "生文素材": "活动信息：活动发生在妈妈班。",
            "奖品素材": "现场看到待产包。||现场看到新客礼盒。",
            "批批检素材": "扫罐底码能看检测报告。||每批检测报告可对应查询。",
            "卖点表达": "a2至初含A2型蛋白质。",
            "卖点表达说明": "不要写成保证吸收。",
            "卖点痛点组合": "A2蛋白质+第一口奶选择",
            "硬边界": "宝宝尚未出生。||不写宝宝已经喝过。",
            "写法": "标题少于20字。||正文130-200字。",
            "生成要求": "只输出 title 和 body。",
        },
        1,
    )

    assert item is not None
    assert item["prompt_mode"] == "layered_article"
    assert item["corpus"] == item["content_direction"]
    assert item["inspiration_material"] == "和课后记下的一句话有关。"
    assert item["activity_material"] == ["活动信息：活动发生在妈妈班。"]
    assert item["hard_boundaries"] == ["宝宝尚未出生。", "不写宝宝已经喝过。"]
    assert item["writing_requirements"] == ["标题少于20字。", "正文130-200字。"]
    assert item["generation_requirements"] == ["只输出 title 和 body。"]
    assert item["selling_painpoint_group"] == "A2蛋白质+第一口奶选择"
    assert item["variation_slots"] == [
        {
            "slot_code": "activity_prize",
            "slot_name": "活动奖品素材",
            "options": ["现场看到待产包。", "现场看到新客礼盒。"],
        },
        {
            "slot_code": "batch_detection",
            "slot_name": "批批检素材",
            "options": ["扫罐底码能看检测报告。", "每批检测报告可对应查询。"],
        },
    ]


def test_row_to_rule_item_extracts_info_source_options_from_generation_material():
    item = _row_to_rule_item(
        {
            "业务规则名称": "莼悦｜有机品质",
            "内容方向": "写妈妈选奶时确认莼悦。",
            "生文素材": (
                "活动信息：普通选奶记录。\n"
                "【信息来源素材】\n"
                "- 正文不写来源\n"
                "- 母婴店导购\n"
                "- 日常接触中了解到（抽象来源）"
            ),
        },
        1,
    )

    assert item is not None
    assert item["activity_material"] == ["活动信息：普通选奶记录。"]
    assert item["variation_slots"] == [
        {
            "slot_code": "info_source",
            "slot_name": "信息来源线索",
            "options": [
                "正文不写来源",
                "母婴店导购",
                "日常接触中了解到（抽象来源）",
            ],
        }
    ]


def test_row_to_rule_item_parses_layered_article_operator_variation_columns():
    item = _row_to_rule_item(
        {
            "业务规则名称": "a2礼遇｜集罐12罐换奶粉",
            "内容方向": "静态兜底方向。",
            "内容方向素材": "直给参加活动，再写活动内容。||先写生活来源，再写活动内容。",
            "活动了解途径素材": "门店导购说起。||宝妈群里有人提。",
            "参加活动原因素材": "长期在喝，觉得福利实在。",
            "活动内容素材": "集12罐兑换1罐奶粉。",
            "批批检素材": "a2至初现在每批都有检测。",
            "产品体验素材": "a2至初粉质细腻，好冲开。",
            "消费者认可素材": "觉得a2做得认真，愿意推荐。",
            "正向表达素材": "品质在线。||细节到位。",
        },
        1,
    )

    assert item is not None
    assert item["variation_slots"] == [
        {
            "slot_code": "content_direction",
            "slot_name": "内容方向",
            "options": ["直给参加活动，再写活动内容。", "先写生活来源，再写活动内容。"],
            "offset": 0,
        },
        {
            "slot_code": "info_source",
            "slot_name": "活动了解途径",
            "options": ["门店导购说起。", "宝妈群里有人提。"],
            "offset": 0,
        },
        {
            "slot_code": "participation_motive",
            "slot_name": "参加活动原因",
            "options": ["长期在喝，觉得福利实在。"],
            "offset": 0,
        },
        {
            "slot_code": "activity_content",
            "slot_name": "活动内容",
            "options": ["集12罐兑换1罐奶粉。"],
            "offset": 0,
        },
        {
            "slot_code": "batch_detection",
            "slot_name": "批批检素材",
            "options": ["a2至初现在每批都有检测。"],
        },
        {
            "slot_code": "product_experience",
            "slot_name": "活动后的产品体验",
            "options": ["a2至初粉质细腻，好冲开。"],
            "offset": 0,
        },
        {
            "slot_code": "consumer_praise",
            "slot_name": "活动后的消费者认可",
            "options": ["觉得a2做得认真，愿意推荐。"],
            "offset": 0,
        },
        {
            "slot_code": "positive_expression",
            "slot_name": "活动分享正向表达",
            "options": ["品质在线。", "细节到位。"],
            "offset": 0,
        },
    ]


def test_row_to_rule_item_preserves_multiline_json_variation_options():
    original_direction = (
        "先说自己怎么了解到活动和参加活动的原因，再讲下活动内容。\n"
        "再另起一段，讲你又看到了检测升级的信息。\n"
        "最后结合起来再夸夸a2品牌。"
    )
    item = _row_to_rule_item(
        {
            "业务规则名称": "a2礼遇｜多重福利叠加",
            "内容方向": original_direction,
            "内容方向素材": json.dumps(
                [original_direction, "直给点说自己参加了活动。"],
                ensure_ascii=False,
            ),
        },
        1,
    )

    assert item is not None
    assert item["variation_slots"] == [
        {
            "slot_code": "content_direction",
            "slot_name": "内容方向",
            "options": [original_direction, "直给点说自己参加了活动。"],
            "offset": 0,
        }
    ]


def test_row_to_rule_item_parses_merged_consumer_recognition_slot():
    item = _row_to_rule_item(
        {
            "业务规则名称": "a2礼遇｜多重福利叠加",
            "内容方向": "活动后写检测，再写认可。",
            "活动内容素材": "积分、集罐、抽奖、回馈礼都有。",
            "批批检素材": "a2至初现在每批都有检测。",
            "认可表达素材": (
                "消费者有被重视到，品质也更透明。"
                "而且a2至初奶香自然，宝宝每次都咕咚咕咚喝光。"
            ),
            "正向表达素材": "a2品质在线。",
        },
        1,
    )

    assert item is not None
    assert [slot["slot_code"] for slot in item["variation_slots"]] == [
        "activity_content",
        "batch_detection",
        "consumer_recognition",
        "positive_expression",
    ]
    assert item["variation_slots"][2] == {
        "slot_code": "consumer_recognition",
        "slot_name": "认可表达",
        "options": [
            "消费者有被重视到，品质也更透明。而且a2至初奶香自然，宝宝每次都咕咚咕咚喝光。"
        ],
        "offset": 0,
    }


def test_layered_article_rules_do_not_require_examples():
    assert _warnings_for_items(
        [
            {
                "business_rule": "妈妈班｜老师讲解",
                "prompt_mode": "layered_article",
                "examples": [],
                "supplements": [],
            }
        ]
    ) == []


@pytest_asyncio.fixture
async def asset_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                AssetRegistry.__table__,
                AssetImportRun.__table__,
                AssetChangeRequest.__table__,
                AssetChangeProposal.__table__,
                ExecutorRegistry.__table__,
                ExpertConfig.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="compliance_rules",
                asset_key="yuanyue",
                display_name="源悦审核规则",
                version_no=1,
                status="active",
                content_json={"items": [{"dimension": "不得宣称治疗便秘"}]},
                created_by="test",
            )
        )
        session.add(
            AssetImportRun(
                source_name="源悦种草活动-ai训练规则.xlsx",
                source_hash="abc",
                status="succeeded",
                imported_assets=3,
                summary_json={"asset_key": "yuanyue"},
                created_by="test",
            )
        )
        session.add_all(
            [
                ExecutorRegistry(
                    executor_code="maga_direct_llm_executor",
                    executor_type="direct_llm",
                    profile_name="maga-worker",
                    invoke_url="mock://maga-worker/invoke",
                    supported_capabilities_json=[{"capability": "asset.import", "schema_version": "1"}],
                    config_json={"executor_token": "test-token"},
                    enabled=1,
                ),
                AssetRegistry(
                    asset_type="painpoint_model",
                    asset_key="yuanyue",
                    display_name="源悦旧痛点模型",
                    version_no=1,
                    status="active",
                    content_json={"items": [{"painpoint": "历史错误痛点"}]},
                    created_by="test",
                ),
                AssetRegistry(
                    asset_type="painpoint_model",
                    asset_key="yuanyue",
                    display_name="源悦痛点模型",
                    version_no=2,
                    status="active",
                    content_json={
                        "topics": [
                            {
                                "baby_stage": "转奶期宝宝",
                                "topic": "肠胃弱/奶量上不去",
                                "descriptions": ["便便不规律"],
                            }
                        ]
                    },
                    created_by="test",
                ),
                AssetRegistry(
                    asset_type="brand_profile",
                    asset_key="yuanyue",
                    display_name="源悦品牌资料",
                    version_no=1,
                    status="active",
                    content_json={"content_style": "高质量真实用户ugc"},
                    created_by="test",
                ),
                AssetRegistry(
                    asset_type="reference_examples",
                    asset_key="yuanyue",
                    display_name="源悦参考例文",
                    version_no=1,
                    status="active",
                    content_json={
                        "items": [
                            {
                                "direction": "吃",
                                "painpoint": "转奶/消化吸收",
                                "post_format": "用后分享",
                                "style_tags": ["用后分享", "吃"],
                                "body": "新手妈妈别急着焦虑，先看宝宝喝奶和便便状态。",
                            }
                        ]
                    },
                    created_by="test",
                ),
                AssetRegistry(
                    asset_type="brand_profile",
                    asset_key="other-brand",
                    display_name="其他品牌资料",
                    version_no=1,
                    status="active",
                    content_json={"content_style": "其他品牌风格"},
                    created_by="test",
                ),
                AssetRegistry(
                    asset_type="painpoint_model",
                    asset_key="topic-brand",
                    display_name="主题结构资产",
                    version_no=1,
                    status="active",
                    content_json={"topics": [{"topic": "睡眠倒退", "descriptions": ["夜醒频繁"]}]},
                    created_by="test",
                ),
                AssetRegistry(
                    asset_type="comment_business_rule_set",
                    asset_key="hidden_probe_rule",
                    display_name="隐藏调试评论规则",
                    version_no=1,
                    status="active",
                    content_json={"items": [{"business_rule": "调试业务规则", "corpus": "仅用于调试"}]},
                    metadata_json={"hidden": True, "visibility_reason": "probe"},
                    created_by="test",
                ),
                AssetRegistry(
                    asset_type="painpoint_model",
                    asset_key="yuanyue",
                    display_name="源悦候选扩展主题",
                    version_no=3,
                    status="active",
                    asset_stage="candidate",
                    content_json={"topics": [{"topic": "AI扩展候选痛点", "descriptions": ["候选表达"]}]},
                    created_by="test",
                ),
                AssetRegistry(
                    asset_type="painpoint_expression_candidates",
                    asset_key="yuanyue",
                    display_name="源悦候选痛点描述",
                    version_no=1,
                    status="active",
                    asset_stage="candidate",
                    content_json={
                        "items": [
                            {
                                "topic": "便便不规律",
                                "symptom": "羊屎蛋/干硬",
                                "expression": "便便又干又硬，一粒粒的像羊屎",
                                "expression_source": "xlsx_seed",
                            },
                            {
                                "topic": "便便不规律",
                                "symptom": None,
                                "expression": "每天换尿不湿都会忍不住看便便状态，怕又是一粒粒、硬硬的那种。",
                                "expression_source": "ai_expanded",
                            },
                        ]
                    },
                    created_by="test",
                ),
            ]
        )
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/assets")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_selling_painpoint_expression_creates_new_production_version(asset_client):
    request_response = await asset_client.post(
        "/api/v1/assets/change-requests",
        json={"source_text": "测试更新单条旺玥卖点表达", "created_by": "test"},
    )
    request_id = request_response.json()["data"]["id"]
    proposal_response = await asset_client.post(
        "/api/v1/assets/change-proposals",
        json={
            "request_id": request_id,
            "proposed_changes_json": {
                "assets": [
                    {
                        "asset_type": "article_business_rule_set",
                        "asset_key": "wangyue_v3_core_storyline_article_rules",
                        "asset_stage": "production",
                        "display_name": "旺玥 V3",
                        "content_json": {
                            "items": [{"rule_id": "business_rule_019", "source_row_no": 19}],
                            "selling_painpoint_expressions": [
                                {
                                    "selling_painpoint_group": "营养丰富+营养不足",
                                    "expression": "这个很不错  我做了好久的功课  也打算给孩子准备这款",
                                    "source_row_no": 163,
                                }
                            ],
                        },
                    }
                ]
            },
            "created_by": "test",
        },
    )
    proposal_id = proposal_response.json()["data"]["id"]
    apply_response = await asset_client.post(f"/api/v1/assets/change-proposals/{proposal_id}/apply")
    assert apply_response.status_code == 200

    response = await asset_client.patch(
        "/api/v1/assets/article-business-rule-sets/wangyue_v3_core_storyline_article_rules/"
        "selling-painpoint-expressions/163",
        json={
            "expected_expression": "这个很不错  我做了好久的功课  也打算给孩子准备这款",
            "expression": "这个很不错，我当时也做了好久功课，最后给孩子选了这款",
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    asset = response.json()["data"]
    assert asset["version_no"] == 2
    assert asset["source_name"] == "selling_painpoint_expression:163"
    expression = asset["content_json"]["selling_painpoint_expressions"][0]
    assert expression["expression"] == "这个很不错，我当时也做了好久功课，最后给孩子选了这款"
    assert asset["metadata_json"]["last_selling_painpoint_expression_source_row_no"] == 163



@pytest.mark.asyncio
async def test_import_selling_painpoint_expressions_replaces_pool_and_preserves_groups(asset_client):
    request_response = await asset_client.post(
        "/api/v1/assets/change-requests",
        json={"source_text": "测试全量导入旺玥卖点表达", "created_by": "test"},
    )
    request_id = request_response.json()["data"]["id"]
    proposal_response = await asset_client.post(
        "/api/v1/assets/change-proposals",
        json={
            "request_id": request_id,
            "proposed_changes_json": {
                "assets": [
                    {
                        "asset_type": "article_business_rule_set",
                        "asset_key": "wangyue_v3_import_probe",
                        "asset_stage": "production",
                        "content_json": {
                            "items": [{"rule_id": "business_rule_001", "source_row_no": 1}],
                            "selling_painpoint_expressions": [
                                {
                                    "selling_painpoint_group": "旧分组",
                                    "expression": "旧表达",
                                    "source_row_no": 1,
                                }
                            ],
                        },
                    }
                ]
            },
            "created_by": "test",
        },
    )
    proposal_id = proposal_response.json()["data"]["id"]
    await asset_client.post(f"/api/v1/assets/change-proposals/{proposal_id}/apply")

    csv_content = (
        "# 导出自：旺玥\n"
        "卖点表达,语料\n"
        "进阶保护力+精力不足,官方卖点表达\n"
        "进阶保护力+精力不足-ugc,孩子活动起来更有劲儿\n"
    )
    response = await asset_client.post(
        "/api/v1/assets/imports/article-selling-painpoint-expressions",
        data={"asset_key": "wangyue_v3_import_probe", "created_by": "test"},
        files={"file": ("卖点表达.csv", csv_content.encode("utf-8"), "text/csv")},
    )

    assert response.status_code == 200
    asset = response.json()["data"]
    assert asset["version_no"] == 2
    expressions = asset["content_json"]["selling_painpoint_expressions"]
    assert [item["selling_painpoint_group"] for item in expressions] == [
        "进阶保护力+精力不足",
        "进阶保护力+精力不足-ugc",
    ]
    assert asset["metadata_json"]["selling_painpoint_expression_count"] == 2
    assert asset["metadata_json"]["selling_painpoint_group_counts"] == {
        "进阶保护力+精力不足": 1,
        "进阶保护力+精力不足-ugc": 1,
    }


@pytest.mark.asyncio
async def test_update_article_business_rule_fields_versions_corpus_and_group_together(asset_client):
    request_response = await asset_client.post(
        "/api/v1/assets/change-requests",
        json={"source_text": "测试更新旺玥内容方向与卖点路由", "created_by": "test"},
    )
    request_id = request_response.json()["data"]["id"]
    old_corpus = "内容方向：\n写放学回来容易喊累。"
    proposal_response = await asset_client.post(
        "/api/v1/assets/change-proposals",
        json={
            "request_id": request_id,
            "proposed_changes_json": {
                "assets": [
                    {
                        "asset_type": "article_business_rule_set",
                        "asset_key": "wangyue_v3_rule_update_probe",
                        "asset_stage": "production",
                        "content_json": {
                            "items": [
                                {
                                    "rule_id": "business_rule_017",
                                    "source_row_no": 17,
                                    "corpus": old_corpus,
                                    "content_direction": old_corpus,
                                    "selling_painpoint_group": "进阶保护力+精力不足",
                                    "writing_requirements": ["旧的单条写法覆盖"],
                                    "generation_requirements": ["旧的单条生成覆盖"],
                                }
                            ],
                            "selling_painpoint_expressions": [],
                        },
                    }
                ]
            },
            "created_by": "test",
        },
    )
    proposal_id = proposal_response.json()["data"]["id"]
    await asset_client.post(f"/api/v1/assets/change-proposals/{proposal_id}/apply")

    new_corpus = "内容方向：\n妈妈记录下最近日常，具体怎么写由你自行构思。"
    response = await asset_client.patch(
        "/api/v1/assets/article-business-rule-sets/wangyue_v3_rule_update_probe/rules/business_rule_017",
        json={
            "expected_corpus": old_corpus,
            "expected_selling_painpoint_group": "进阶保护力+精力不足",
            "expected_inspiration_none_source_row_nos": [],
            "expected_inspiration_clue_by_source_row_no": {},
            "expected_writing_requirements": ["旧的单条写法覆盖"],
            "expected_generation_requirements": ["旧的单条生成覆盖"],
            "corpus": new_corpus,
            "selling_painpoint_group": "进阶保护力+精力不足-ugc",
            "inspiration_none_source_row_nos": [68, 63, 68],
            "inspiration_clue_by_source_row_no": {
                "64": "和一次户外活动相关",
                "67": "和放学后的一件小事相关",
            },
            "writing_requirements": None,
            "generation_requirements": None,
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    asset = response.json()["data"]
    assert asset["version_no"] == 2
    item = asset["content_json"]["items"][0]
    assert item["corpus"] == new_corpus
    assert item["content_direction"] == new_corpus
    assert item["selling_painpoint_group"] == "进阶保护力+精力不足-ugc"
    assert item["inspiration_none_source_row_nos"] == [63, 68]
    assert item["inspiration_clue_by_source_row_no"] == {
        "64": "和一次户外活动相关",
        "67": "和放学后的一件小事相关",
    }
    assert "writing_requirements" not in item
    assert "generation_requirements" not in item
    assert asset["metadata_json"]["last_article_business_rule_id"] == "business_rule_017"
    assert asset["metadata_json"]["last_article_business_rule_inspiration_none_source_row_nos_before"] == []
    assert asset["metadata_json"]["last_article_business_rule_inspiration_none_source_row_nos_after"] == [63, 68]
    assert asset["metadata_json"]["last_article_business_rule_inspiration_clue_by_source_row_no_before"] == {}
    assert asset["metadata_json"]["last_article_business_rule_inspiration_clue_by_source_row_no_after"] == {
        "64": "和一次户外活动相关",
        "67": "和放学后的一件小事相关",
    }
    assert asset["metadata_json"]["last_article_business_rule_writing_requirements_before"] == [
        "旧的单条写法覆盖"
    ]
    assert asset["metadata_json"]["last_article_business_rule_writing_requirements_after"] is None
    assert asset["metadata_json"]["last_article_business_rule_generation_requirements_before"] == [
        "旧的单条生成覆盖"
    ]
    assert asset["metadata_json"]["last_article_business_rule_generation_requirements_after"] is None


def test_product_experience_rule_import_preserves_structure_and_scene_constraint_fields():
    item = _row_to_rule_item(
        {
            "业务规则": "V3M-01｜进阶保护力｜使用反馈",
            "语料": "写一篇旺玥妈妈UGC。",
            "帖子类型": "使用反馈",
            "structure_slot": "先反馈后补产品",
            "scene_motive_bucket": "保护力反馈关系",
            "scene_constraint": "围绕身边反馈或集体活动后的自家状态观察",
            "正文场景": "旧正文场景长文本",
        },
        1,
    )

    assert item is not None
    assert item["structure_slot"] == "先反馈后补产品"
    assert item["scene_motive_bucket"] == "保护力反馈关系"
    assert item["scene_constraint"] == "围绕身边反馈或集体活动后的自家状态观察"


def test_product_experience_rule_import_preserves_selling_surface_fields():
    item = _row_to_rule_item(
        {
            "业务规则": "V163-01｜保护力关注种草",
            "语料": "写一篇旺玥妈妈UGC。",
            "卖点表达口吻": "像妈妈说看中保护力支持，喝下来这段时间状态稳。",
            "成分承接": "乳铁蛋白、HMO只承接保护力相关观察。",
            "好处表达": "少请假、少中招、精神头在线里选一个方向。",
            "表达机制": "从自家状态或一直留下来的理由进入。",
        },
        1,
    )

    assert item is not None
    assert item["selling_point_surface"] == "像妈妈说看中保护力支持，喝下来这段时间状态稳。"
    assert item["ingredient_surface"] == "乳铁蛋白、HMO只承接保护力相关观察。"
    assert item["benefit_surface"] == "少请假、少中招、精神头在线里选一个方向。"
    assert (
        item["selling_kernel"]
        == "卖点表达：像妈妈说看中保护力支持，喝下来这段时间状态稳；"
        "成分承接：乳铁蛋白、HMO只承接保护力相关观察；"
        "好处表达：少请假、少中招、精神头在线里选一个方向"
    )
    assert item["expression_mechanism"] == "从自家状态或一直留下来的理由进入。"


def test_product_experience_rule_import_preserves_selling_description_field():
    item = _row_to_rule_item(
        {
            "业务规则": "V236-01｜卖点描述池",
            "语料": "写一篇旺玥妈妈UGC。",
            "痛点": "营养不足",
            "卖点方向": "营养丰富",
            "卖点描述": "饭菜有波动时，旺玥的价值落在基础营养更好接住，钙铁锌可以自然提一嘴。",
        },
        1,
    )

    assert item is not None
    assert item["selling_description"] == "饭菜有波动时，旺玥的价值落在基础营养更好接住，钙铁锌可以自然提一嘴。"
    assert (
        item["selling_kernel"]
        == "痛点：营养不足；卖点：营养丰富；"
        "卖点描述：饭菜有波动时，旺玥的价值落在基础营养更好接住，钙铁锌可以自然提一嘴"
    )


@pytest.mark.asyncio
async def test_list_assets_and_get_latest_asset(asset_client):
    list_response = await asset_client.get("/api/v1/assets", params={"asset_key": "yuanyue"})
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["code"] == 200
    listed = list_payload["data"]
    compliance_asset = next(item for item in listed if item["asset_type"] == "compliance_rules")
    assert compliance_asset["asset_key"] == "yuanyue"

    get_response = await asset_client.get("/api/v1/assets/compliance_rules/yuanyue")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["code"] == 200
    asset = get_payload["data"]
    assert asset["version_no"] == 1
    assert asset["content_json"]["items"][0]["dimension"] == "不得宣称治疗便秘"


@pytest.mark.asyncio
async def test_asset_summary_and_import_runs(asset_client):
    summary_response = await asset_client.get("/api/v1/assets/summary", params={"asset_key": "yuanyue"})
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["code"] == 200
    data = summary_payload["data"]
    compliance = next(item for item in data if item["asset_type"] == "compliance_rules")
    assert compliance["item_count"] == 1
    assert compliance["version_no"] == 1

    runs_response = await asset_client.get("/api/v1/assets/import-runs")
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert runs_payload["code"] == 200
    runs = runs_payload["data"]
    assert runs[0]["source_name"] == "源悦种草活动-ai训练规则.xlsx"
    assert runs[0]["imported_assets"] == 3


@pytest.mark.asyncio
async def test_asset_summary_filters_latest_versions_by_asset_type(asset_client):
    response = await asset_client.get(
        "/api/v1/assets/summary",
        params={"asset_type": "painpoint_model"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data
    assert {item["asset_type"] for item in data} == {"painpoint_model"}
    yuanyue = next(item for item in data if item["asset_key"] == "yuanyue")
    assert yuanyue["version_no"] == 2
    assert all(item["asset_stage"] == "production" for item in data)


@pytest.mark.asyncio
async def test_asset_summary_hides_debug_rules_by_default(asset_client):
    default_response = await asset_client.get(
        "/api/v1/assets/summary",
        params={"asset_type": "comment_business_rule_set"},
    )
    assert default_response.status_code == 200
    default_data = default_response.json()["data"]
    assert all(item["asset_key"] != "hidden_probe_rule" for item in default_data)

    hidden_response = await asset_client.get(
        "/api/v1/assets/summary",
        params={"asset_type": "comment_business_rule_set", "include_hidden": True},
    )
    assert hidden_response.status_code == 200
    hidden_data = hidden_response.json()["data"]
    hidden_rule = next(item for item in hidden_data if item["asset_key"] == "hidden_probe_rule")
    assert hidden_rule["hidden"] is True


@pytest.mark.asyncio
async def test_asset_visibility_can_be_updated(asset_client):
    update_response = await asset_client.patch(
        "/api/v1/assets/brand_profile/other-brand/visibility",
        json={"hidden": True, "reason": "debug", "updated_by": "ops"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["metadata_json"]["hidden"] is True
    assert updated["metadata_json"]["visibility_reason"] == "debug"

    default_response = await asset_client.get(
        "/api/v1/assets/summary",
        params={"asset_type": "brand_profile"},
    )
    default_keys = {item["asset_key"] for item in default_response.json()["data"]}
    assert "other-brand" not in default_keys

    hidden_response = await asset_client.get(
        "/api/v1/assets/summary",
        params={"asset_type": "brand_profile", "include_hidden": True},
    )
    hidden_keys = {item["asset_key"] for item in hidden_response.json()["data"]}
    assert "other-brand" in hidden_keys


@pytest.mark.asyncio
async def test_generation_options_are_extracted_from_uploaded_assets(asset_client):
    response = await asset_client.get("/api/v1/assets/generation-options", params={"asset_key": "yuanyue"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    data = payload["data"]
    assert data["asset_keys"] == ["other-brand", "topic-brand", "yuanyue"]
    assert "肠胃弱/奶量上不去" in data["product_topics"]
    assert "AI扩展候选痛点" not in data["product_topics"]
    assert "历史错误痛点" not in data["product_topics"]
    assert "奶量上不去" not in data["product_topics"]
    assert "便便不规律" not in data["product_topics"]
    assert "吃" not in data["product_topics"]
    assert "转奶期宝宝" in data["target_audiences"]
    assert "新手妈妈别急着焦虑" not in data["target_audiences"]
    assert "新手妈妈" not in data["target_audiences"]
    assert "高质量真实用户ugc" not in data["styles"]
    assert "其他品牌风格" not in data["styles"]
    assert "用后分享" not in data["styles"]
    assert "吃" not in data["styles"]
    assert "长" not in data["styles"]
    assert "经验复盘" in data["styles"]
    assert "情绪共情" in data["styles"]
    assert data["persona_profiles"] == []

    topic_response = await asset_client.get("/api/v1/assets/generation-options", params={"asset_key": "topic-brand"})
    assert topic_response.status_code == 200
    topic_payload = topic_response.json()
    assert topic_payload["code"] == 200
    assert topic_payload["data"]["product_topics"] == ["睡眠倒退"]
    assert topic_payload["data"]["target_audiences"] == ["新手妈妈"]


@pytest.mark.asyncio
async def test_content_generation_keywords_get_fallback_and_save_versions(asset_client):
    fallback_response = await asset_client.get("/api/v1/assets/content-generation-keywords")
    assert fallback_response.status_code == 200
    fallback_payload = fallback_response.json()
    assert fallback_payload["code"] == 200
    fallback = fallback_payload["data"]
    assert fallback["source"] == "fallback"
    assert fallback["asset_type"] == "content_generation_keywords"
    assert fallback["content_json"]["schema_version"] == "2"
    fallback_categories = fallback["content_json"]["categories"]
    assert len(fallback_categories) >= 6
    fallback_by_code = {item["category_code"]: item for item in fallback_categories}
    assert [item["category_name"] for item in fallback_categories[:3]] == ["人设", "生文指令", "生文指令"]
    assert "comment_generation_requirement" not in fallback_by_code
    assert fallback_by_code["comment_writing_instruction"]["applicable_content_types"] == ["comment"]
    assert fallback_by_code["comment_writing_instruction"]["selection_mode"] == "fixed"
    comment_instruction = fallback_by_code["comment_writing_instruction"]["sub_keywords"][0]
    assert comment_instruction["keyword_code"] == "natural_comment"
    assert "只输出评论正文" in comment_instruction["corpus"][0]
    assert "先看" not in comment_instruction["corpus"][0]
    assert "参考示例" not in comment_instruction["corpus"][0]
    persona_keywords = fallback_by_code["persona"]["sub_keywords"]
    persona_by_code = {item["keyword_code"]: item for item in persona_keywords}
    assert "babytree_short_confirm_mom" in persona_by_code
    assert "babytree_teeth_care_mom" in persona_by_code
    assert "babytree_dad_checkup_mom" in persona_by_code
    assert "只围绕一个具体宝宝状态问一句" in persona_by_code["babytree_short_confirm_mom"]["corpus"][0]
    assert "仅在业务覆盖孕期或检查场景时圈选" in persona_by_code["babytree_dad_checkup_mom"]["corpus"][0]
    assert fallback_by_code["comment_speaking_style"]["category_name"] == "说话方式"
    assert fallback_by_code["comment_speaking_style"]["applicable_content_types"] == ["comment"]
    assert [item["keyword_name"] for item in fallback_by_code["comment_speaking_style"]["sub_keywords"]] == [
        "接楼主一句",
        "接姐妹评论",
        "顺手报信",
        "老客稳场",
        "自己刚补到",
        "短句附和",
        "轻提醒一句",
        "个人处理方式",
        "同城/附近更新",
        "小声补充",
        "半句式回复",
        "问答感回复",
        "松口气反应",
        "务实妈妈口吻",
        "评论串跟进",
        "给个参考",
    ]
    old_customer_style = next(
        item
        for item in fallback_by_code["comment_speaking_style"]["sub_keywords"]
        if item["keyword_code"] == "old_customer_stabilize"
    )
    assert "不要把“老客”这个词写进正文" in old_customer_style["corpus"][0]
    sister_reply_style = next(
        item
        for item in fallback_by_code["comment_speaking_style"]["sub_keywords"]
        if item["keyword_code"] == "reply_to_sister_comment"
    )
    assert "姐妹哪买的" in sister_reply_style["corpus"][0]
    report_reference_style = next(
        item
        for item in fallback_by_code["comment_speaking_style"]["sub_keywords"]
        if item["keyword_code"] == "soft_reference"
    )
    assert "Not Detected就是未检出" in report_reference_style["corpus"][0]
    assert fallback_by_code["writing_instruction"]["applicable_content_types"] == ["article"]
    assert fallback_by_code["comment_writing_instruction"]["applicable_content_types"] == ["comment"]
    assert fallback_by_code["article_format_control"]["category_name"] == "帖子格式控制"
    assert fallback_by_code["article_format_control"]["applicable_content_types"] == ["article"]
    assert fallback_by_code["article_format_control"]["sub_keywords"][0]["keyword_name"] == "短帖干净"
    assert fallback_by_code["comment_format_control"]["category_name"] == "评论格式控制"
    assert fallback_by_code["comment_format_control"]["applicable_content_types"] == ["comment"]
    assert [item["keyword_name"] for item in fallback_by_code["comment_format_control"]["sub_keywords"]] == [
        "5-8字短接话",
        "评论串短接楼",
        "8-16字",
        "10-20字",
        "21-30字少量",
        "21-35字",
        "21-50字",
    ]
    assert fallback_by_code["perturbation_rule"]["sub_keywords"][0]["keyword_name"] == "随机发散"
    assert "离散运动" in fallback_by_code["perturbation_rule"]["sub_keywords"][0]["corpus"][0]
    assert [item["keyword_code"] for item in fallback_by_code["perturbation_rule"]["sub_keywords"]] == [
        "random_thinking_shift"
    ]
    assert "纸尿裤" not in fallback_by_code["writing_method"]["sub_keywords"][0]["corpus"][0]
    assert "5到8字" in fallback_by_code["comment_format_control"]["sub_keywords"][0]["corpus"][0]
    assert "3到12字" in fallback_by_code["comment_format_control"]["sub_keywords"][1]["corpus"][0]
    assert "21到30字" in fallback_by_code["comment_format_control"]["sub_keywords"][4]["corpus"][0]
    assert "21到35字" in fallback_by_code["comment_format_control"]["sub_keywords"][5]["corpus"][0]
    assert "21到50字" in fallback_by_code["comment_format_control"]["sub_keywords"][6]["corpus"][0]
    format_corpus = "\n".join(
        line
        for item in fallback_by_code["comment_format_control"]["sub_keywords"]
        for line in item["corpus"]
    )
    for business_term in ("批批检", "扫码", "罐底码", "未检出", "到货", "门店", "转奶", "会员权益"):
        assert business_term not in format_corpus

    payload = {
        "asset_key": "default_content_generation_keywords",
        "display_name": "表达扩散语料",
        "created_by": "ops",
        "selection_policy": {"default_mode": "one_per_enabled_category"},
        "categories": [
            {
                "category_code": "persona",
                "category_name": "人设",
                "enabled": True,
                "required": False,
                "sort_order": 10,
                "selection_mode": "one",
                "applicable_content_types": ["article", "comment"],
                "sub_keywords": [
                    {
                        "keyword_code": "experienced_mom",
                        "keyword_name": "经验型妈妈",
                        "enabled": True,
                        "weight": 1,
                        "corpus": ["像真实妈妈在评论区交流。"],
                    }
                ],
            },
            {
                "category_code": "rhythm",
                "category_name": "句式节奏",
                "enabled": True,
                "required": False,
                "sort_order": 20,
                "selection_mode": "one",
                "applicable_content_types": ["comment"],
                "sub_keywords": [
                    {
                        "keyword_code": "short_sentence",
                        "keyword_name": "短句",
                        "enabled": True,
                        "weight": 1,
                        "corpus": ["短句表达，不写成说明书。"],
                    }
                ],
            },
        ],
    }

    invalid_fixed_payload = {
        **payload,
        "categories": [
            {
                **payload["categories"][0],
                "selection_mode": "fixed",
                "selected_keyword_code": "",
            }
        ],
    }
    invalid_fixed_response = await asset_client.put(
        "/api/v1/assets/content-generation-keywords",
        json=invalid_fixed_payload,
    )
    assert invalid_fixed_response.status_code == 400
    assert "固定选择时必须指定子关键词" in invalid_fixed_response.json()["detail"]

    first_save = await asset_client.put("/api/v1/assets/content-generation-keywords", json=payload)
    assert first_save.status_code == 200
    first_asset = first_save.json()["data"]
    assert first_asset["version_no"] == 1
    assert first_asset["metadata_json"]["category_count"] == 2
    assert first_asset["metadata_json"]["corpus_count"] == 2

    second_payload = {
        **payload,
        "categories": [
            {
                **payload["categories"][0],
                "sub_keywords": [
                    {
                        **payload["categories"][0]["sub_keywords"][0],
                        "corpus": ["像真实妈妈在评论区交流。", "别端着讲课。"],
                    }
                ],
            }
        ],
    }
    second_save = await asset_client.put("/api/v1/assets/content-generation-keywords", json=second_payload)
    assert second_save.status_code == 200
    second_asset = second_save.json()["data"]
    assert second_asset["version_no"] == 2

    latest_response = await asset_client.get("/api/v1/assets/content-generation-keywords")
    latest = latest_response.json()["data"]
    assert latest["source"] == "asset_registry"
    assert latest["version_no"] == 2
    assert latest["content_json"]["categories"][0]["sub_keywords"][0]["corpus"] == [
        "像真实妈妈在评论区交流。",
        "别端着讲课。",
    ]

    versions_response = await asset_client.get("/api/v1/assets/content-generation-keywords/versions")
    versions = versions_response.json()["data"]
    assert [item["version_no"] for item in versions] == [2, 1]
    assert versions[0]["status"] == "active"
    assert versions[1]["status"] == "archived"

    rollback_response = await asset_client.post(
        "/api/v1/assets/content-generation-keywords/rollback",
        json={"asset_key": "default_content_generation_keywords", "version_no": 1, "created_by": "ops"},
    )
    assert rollback_response.status_code == 200
    rolled_back = rollback_response.json()["data"]
    assert rolled_back["version_no"] == 3
    assert rolled_back["metadata_json"]["rollback_from_version_no"] == 1

    export_response = await asset_client.get("/api/v1/assets/exports/content-generation-keywords")
    export_data = export_response.json()["data"]
    assert export_data["version_no"] == 3
    assert "类别Code" in export_data["csv_text"]
    assert "像真实妈妈在评论区交流。" in export_data["csv_text"]


@pytest.mark.asyncio
async def test_import_and_preview_content_generation_keywords(asset_client):
    csv_content = "\n".join(
        [
            "类别Code,类别名称,类别说明,类别启用,必选,类别顺序,选择模式,固定子关键词Code,适用内容,子关键词Code,子关键词名称,子关键词启用,权重,语料",
            "persona,人设,表达身份,是,否,10,fixed,experienced_mom,\"article,comment\",experienced_mom,经验型妈妈,是,1,像真实妈妈在评论区说话。",
            "persona,人设,表达身份,是,否,10,fixed,experienced_mom,\"article,comment\",experienced_mom,经验型妈妈,是,1,不要端着讲课。",
            "rhythm,句式节奏,控制节奏,是,否,20,one,,comment,short_sentence,短句,是,1,短句表达，像顺手评论。",
        ]
    )

    import_response = await asset_client.post(
        "/api/v1/assets/imports/content-generation-keywords",
        data={"created_by": "ops"},
        files={"file": ("表达扩散语料.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )
    assert import_response.status_code == 200
    imported = import_response.json()["data"]
    assert imported["imported_assets"] == 1
    assert ["content_generation_keywords", "default_content_generation_keywords"] in imported["asset_keys"]
    assert imported["summary_json"]["category_count"] == 2
    assert imported["summary_json"]["corpus_count"] == 3
    detail_response = await asset_client.get("/api/v1/assets/content-generation-keywords")
    persona_category = detail_response.json()["data"]["content_json"]["categories"][0]
    assert persona_category["selection_mode"] == "fixed"
    assert persona_category["selected_keyword_code"] == "experienced_mom"

    preview_response = await asset_client.post(
        "/api/v1/assets/content-generation-keywords/preview",
        json={
            "asset_key": "default_content_generation_keywords",
            "content_type": "comment",
            "item_no": 1,
            "business_rule": {
                "rule_type": "business_rule",
                "business_rule": "互动提问",
                "corpus": "像妈妈在评论区问源悦真实反馈。",
            },
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["data"]
    assert [item["category_code"] for item in preview["selected_keywords"]] == ["persona", "rhythm"]
    assert "像妈妈在评论区问源悦真实反馈" in preview["rendered_prompt"]
    assert "短句表达，像顺手评论" not in preview["rendered_prompt"]


@pytest.mark.asyncio
async def test_asset_stage_can_list_candidate_assets_without_polluting_production(asset_client):
    production_response = await asset_client.get("/api/v1/assets/summary", params={"asset_key": "yuanyue"})
    production_payload = production_response.json()
    assert production_payload["code"] == 200
    assert all(item["asset_stage"] == "production" for item in production_payload["data"])

    all_stage_response = await asset_client.get(
        "/api/v1/assets/summary",
        params={"asset_key": "yuanyue", "asset_stage": ""},
    )
    all_stage_payload = all_stage_response.json()
    assert all_stage_payload["code"] == 200
    assert {"production", "candidate"}.issubset({item["asset_stage"] for item in all_stage_payload["data"]})

    candidate_response = await asset_client.get(
        "/api/v1/assets/summary",
        params={"asset_key": "yuanyue", "asset_stage": "candidate"},
    )
    candidate_payload = candidate_response.json()
    assert candidate_payload["code"] == 200
    candidates = candidate_payload["data"]
    assert all(item["asset_stage"] == "candidate" for item in candidates)
    assert any(item["asset_type"] == "painpoint_model" for item in candidates)

    candidate_detail_response = await asset_client.get(
        "/api/v1/assets/painpoint_model/yuanyue",
        params={"asset_stage": "candidate"},
    )
    candidate_detail = candidate_detail_response.json()["data"]
    assert candidate_detail["asset_stage"] == "candidate"
    assert candidate_detail["content_json"]["topics"][0]["topic"] == "AI扩展候选痛点"


@pytest.mark.asyncio
async def test_painpoint_expression_candidate_detail_auto_classifies_missing_symptom(asset_client):
    response = await asset_client.get(
        "/api/v1/assets/painpoint_expression_candidates/yuanyue",
        params={"asset_stage": "candidate"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    items = payload["data"]["content_json"]["items"]
    ai_item = next(item for item in items if item["expression_source"] == "ai_expanded")
    assert ai_item["symptom"] == "羊屎蛋/干硬"
    assert ai_item["symptom_source"] == "auto_inferred"


@pytest.mark.asyncio
async def test_create_candidate_asset_api_keeps_generation_options_production_only(asset_client):
    response = await asset_client.post(
        "/api/v1/assets/candidates",
        json={
            "asset_type": "painpoint_model",
            "asset_key": "yuanyue",
            "display_name": "源悦候选痛点描述",
            "source_name": "seed-expansion",
            "source_uri": "file:///tmp/source.xlsx",
            "source_hash": "hash-1",
            "content_json": {
                "items": [
                    {
                        "candidate_id": "c1",
                        "topic": "AI候选新主题",
                        "expression": "宝宝状态忽高忽低，妈妈只能每天细看变化。",
                    }
                ]
            },
            "metadata_json": {"source_kind": "ai_seed_expansion"},
            "created_by": "codex",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    created = payload["data"]
    assert created["asset_stage"] == "candidate"
    assert created["version_no"] == 4

    candidate_response = await asset_client.get(
        "/api/v1/assets/summary",
        params={"asset_key": "yuanyue", "asset_stage": "candidate"},
    )
    candidates = candidate_response.json()["data"]
    painpoint_candidates = [item for item in candidates if item["asset_type"] == "painpoint_model"]
    assert len(painpoint_candidates) == 1
    assert painpoint_candidates[0]["version_no"] == 4

    options_response = await asset_client.get("/api/v1/assets/generation-options", params={"asset_key": "yuanyue"})
    options = options_response.json()["data"]
    assert "AI候选新主题" not in options["product_topics"]


@pytest.mark.asyncio
async def test_asset_steward_creates_request_proposal_and_applies_new_asset_version(asset_client):
    request_response = await asset_client.post(
        "/api/v1/assets/change-requests",
        json={
            "source_text": "新增宝宝便便不规律方向，避免治疗便秘",
            "requester": "运营A",
            "context_json": {"asset_key": "yuanyue"},
        },
    )
    assert request_response.status_code == 200
    request_payload = request_response.json()
    assert request_payload["code"] == 200
    request_data = request_payload["data"]
    assert request_data["status"] == "pending"

    proposal_response = await asset_client.post(
        "/api/v1/assets/change-proposals",
        json={
            "request_id": request_data["id"],
            "risk_level": "high",
            "summary": "补充便便不规律表达规则",
            "affected_assets_json": [{"asset_type": "compliance_rules", "asset_key": "yuanyue"}],
            "proposed_changes_json": {
                "assets": [
                    {
                        "asset_type": "compliance_rules",
                        "asset_key": "yuanyue",
                        "display_name": "源悦审核规则",
                        "content_json": {"items": [{"dimension": "禁止治疗便秘、改善便秘等医疗化表述"}]},
                    }
                ]
            },
            "risk_notes_json": ["母婴消化相关默认高风险，需要人工确认"],
            "smoke_test_json": {
                "product_topic": "宝宝便便不规律",
                "target_audience": "新手妈妈",
                "style": "经验老道型",
            },
        },
    )
    assert proposal_response.status_code == 200
    proposal_payload = proposal_response.json()
    assert proposal_payload["code"] == 200
    proposal_data = proposal_payload["data"]
    assert proposal_data["status"] == "proposed"

    apply_response = await asset_client.post(f"/api/v1/assets/change-proposals/{proposal_data['id']}/apply")
    assert apply_response.status_code == 200
    apply_payload = apply_response.json()
    assert apply_payload["code"] == 200
    applied = apply_payload["data"]
    assert applied["status"] == "applied"
    assert applied["created_asset_ids"]

    latest_response = await asset_client.get("/api/v1/assets/compliance_rules/yuanyue")
    latest_payload = latest_response.json()
    assert latest_payload["code"] == 200
    latest = latest_payload["data"]
    assert latest["version_no"] == 2
    assert latest["content_json"]["items"][0]["dimension"] == "禁止治疗便秘、改善便秘等医疗化表述"


@pytest.mark.asyncio
async def test_change_request_can_generate_and_apply_candidate_compliance_rule(asset_client):
    request_response = await asset_client.post(
        "/api/v1/assets/change-requests",
        json={
            "source_text": "运营反馈：源悦和 a2 蛋白、a2 公司没有关系。禁止提及 a2 蛋白。",
            "requester": "ops",
            "context_json": {
                "asset_key": "yuanyue",
                "detected_terms": ["a2", "蛋白", "公司没有关系"],
                "item_no": 1,
            },
        },
    )
    request_data = request_response.json()["data"]

    list_response = await asset_client.get("/api/v1/assets/change-requests", params={"limit": 5})
    list_data = list_response.json()["data"]
    assert list_data[0]["id"] == request_data["id"]
    assert list_data[0]["status"] == "pending"

    proposal_response = await asset_client.post(
        f"/api/v1/assets/change-requests/{request_data['id']}/propose-compliance-rule"
    )
    assert proposal_response.status_code == 200
    proposal = proposal_response.json()["data"]
    assert proposal["status"] == "proposed"
    assert proposal["risk_level"] == "high"
    proposed_asset = proposal["proposed_changes_json"]["assets"][0]
    assert proposed_asset["asset_type"] == "compliance_rules"
    assert proposed_asset["asset_stage"] == "candidate"
    assert proposed_asset["content_json"]["items"][-1]["forbidden_terms"] == ["a2", "a2蛋白", "a2公司"]

    proposals_response = await asset_client.get("/api/v1/assets/change-proposals", params={"limit": 5})
    proposals = proposals_response.json()["data"]
    assert proposals[0]["id"] == proposal["id"]

    updated_requests_response = await asset_client.get("/api/v1/assets/change-requests", params={"limit": 5})
    assert updated_requests_response.json()["data"][0]["status"] == "proposed"

    apply_response = await asset_client.post(f"/api/v1/assets/change-proposals/{proposal['id']}/apply")
    assert apply_response.status_code == 200
    applied = apply_response.json()["data"]
    assert applied["status"] == "applied"

    candidate_response = await asset_client.get(
        "/api/v1/assets/compliance_rules/yuanyue",
        params={"asset_stage": "candidate"},
    )
    candidate = candidate_response.json()["data"]
    assert candidate["asset_stage"] == "candidate"
    assert candidate["content_json"]["items"][-1]["rule_type"] == "forbidden_product_fact"
    assert "a2蛋白" in candidate["content_json"]["items"][-1]["forbidden_terms"]


@pytest.mark.asyncio
async def test_upload_comment_business_rule_set_imports_rule_asset(asset_client):
    csv_content = "\n".join(
        [
            "# 运营本地说明行会被导入器忽略",
            "业务规则,语料",
            '"整体适应","整体适应：',
            '关键词方向是有货+真实反馈。',
            '整体适应：',
            '像妈妈在评论区聊刚开始喝源悦的观察，语气自然一点。',
            '',
            '示例：',
            '- 我家刚开始也在看源悦，想蹲蹲真实反馈',
            '- 0.03这个数我记住了，单位别问我哈哈',
            '- 1. 这种编号前缀要清理',
            '- 有同款宝宝吗，喝着接受度咋样',
            '',
            '注意：示例只作为语气参考，不要照抄"',
            '"成分讨论","成分讨论：',
            '像在确认信息，别写成科普长文。',
            '',
            '示例：',
            '- 软分子蛋白这个点我也想了解下"',
            "",
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/comment-business-rule-set",
        data={
            "created_by": "ops",
            "keyword_asset_key": "a2_plot_discussion_comment_keywords",
            "quality_guard_profile_key": "a2_sentiment_comment_202606",
            "keyword_selection": '{"persona":["family_mom","experienced_mom"]}',
        },
        files={"file": ("业务规则_子关键词导出.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    data = payload["data"]
    assert data["imported_assets"] == 1
    assert ["comment_business_rule_set", "yuanyue_comment_activity"] in data["asset_keys"]
    assert data["summary_json"]["rule_count"] == 2
    assert data["summary_json"]["example_count"] == 5
    assert data["summary_json"]["default_generation_count"] == 10
    assert data["summary_json"]["keyword_asset_key"] == "a2_plot_discussion_comment_keywords"
    assert data["summary_json"]["quality_guard_profile_key"] == "a2_sentiment_comment_202606"
    assert data["summary_json"]["keyword_selection"] == {"persona": ["family_mom", "experienced_mom"]}

    detail_response = await asset_client.get(
        "/api/v1/assets/comment_business_rule_set/yuanyue_comment_activity"
    )
    assert detail_response.status_code == 200
    asset = detail_response.json()["data"]
    assert asset["asset_type"] == "comment_business_rule_set"
    assert asset["content_json"]["keyword_asset_key"] == "a2_plot_discussion_comment_keywords"
    assert asset["content_json"]["quality_guard_profile_key"] == "a2_sentiment_comment_202606"
    assert asset["content_json"]["keyword_selection"] == {"persona": ["family_mom", "experienced_mom"]}
    assert asset["metadata_json"]["keyword_asset_key"] == "a2_plot_discussion_comment_keywords"
    assert asset["metadata_json"]["quality_guard_profile_key"] == "a2_sentiment_comment_202606"
    assert asset["metadata_json"]["keyword_selection"] == {"persona": ["family_mom", "experienced_mom"]}
    assert asset["content_json"]["rule_type"] == "business_rule"
    assert asset["content_json"]["items"][0]["business_rule"] == "整体适应"
    assert asset["content_json"]["items"][0]["examples"][0] == "我家刚开始也在看源悦，想蹲蹲真实反馈"
    assert any("0.03这个数我记住了" in item for item in asset["content_json"]["items"][0]["examples"])
    assert "这种编号前缀要清理" in asset["content_json"]["items"][0]["examples"]
    assert "注意：示例只作为语气参考，不要照抄" in asset["content_json"]["items"][0]["corpus"]
    assert "示例：" not in asset["content_json"]["items"][0]["corpus"]
    assert "关键词方向" not in asset["content_json"]["items"][0]["corpus"]
    assert asset["content_json"]["items"][0]["corpus"].count("整体适应：") == 1
    assert "我家刚开始也在看源悦" not in asset["content_json"]["items"][0]["corpus"]


@pytest.mark.asyncio
async def test_upload_comment_business_rule_set_accepts_three_column_rule_then_updates_examples(asset_client):
    csv_content = "\n".join(
        [
            "业务规则名称,规则语料,示例",
            '"有货后先不急着转奶","写什么：妈妈说自己问到或买到 a2 了，所以先继续喝 a2，转奶先放一放。\n\n怎么说：像评论区接一句或顺手报个信，可以很短。",""',
        ]
    )
    import_response = await asset_client.post(
        "/api/v1/assets/imports/comment-business-rule-set",
        data={
            "asset_key": "a2_simple_comment_rules",
            "display_name": "A2极简评论业务规则",
            "created_by": "ops",
        },
        files={"file": ("a2_极简规则.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert import_response.status_code == 200
    detail_response = await asset_client.get(
        "/api/v1/assets/comment_business_rule_set/a2_simple_comment_rules"
    )
    asset = detail_response.json()["data"]
    item = asset["content_json"]["items"][0]
    assert item["business_rule"] == "有货后先不急着转奶"
    assert item["corpus"] == (
        "写什么：妈妈说自己问到或买到 a2 了，所以先继续喝 a2，转奶先放一放。\n\n"
        "怎么说：像评论区接一句或顺手报个信，可以很短。"
    )
    assert item["examples"] == []

    update_response = await asset_client.post(
        "/api/v1/assets/comment-business-rule-examples",
        json={
            "asset_key": "a2_simple_comment_rules",
            "rule_id": item["rule_id"],
            "source_row_no": item["source_row_no"],
            "examples": ["我的也快到了", "能不换就不换", "我也买到了"],
            "supplements": ["刚问了客服说a2有货了"],
            "created_by": "ops",
        },
    )

    assert update_response.status_code == 200
    updated_asset = update_response.json()["data"]
    assert updated_asset["version_no"] == asset["version_no"] + 1
    updated_item = updated_asset["content_json"]["items"][0]
    assert updated_item["corpus"] == item["corpus"]
    assert updated_item["examples"] == ["我的也快到了", "能不换就不换", "我也买到了", "刚问了客服说a2有货了"]
    assert updated_item["supplements"] == []
    assert updated_asset["metadata_json"]["example_count"] == 4


@pytest.mark.asyncio
async def test_upload_comment_business_rule_set_accepts_direct_rule_bank_csv(asset_client):
    csv_content = "\n".join(
        [
            "rule_id,category,major_category,focus,examples,source_title",
            '"a2_direct_01","有货-直给到货情绪","有货","像妈妈看到 a2 到货后顺手接一句，不回讲以前买不到。","a2终于到货了，我去看看',
            '我也买到a2新货了","A2舆情改善评论-有货直给到货情绪"',
            '"a2_direct_02","批批检-报告信息能看见","批批检","像妈妈扫完报告后顺手补充，入口能点开，不写成安全背书。","我刚扫了我手上这罐，报告能出来',
            '入口能点开，里面有几份报告","A2舆情改善评论-报告信息能看见"',
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/comment-business-rule-set",
        data={
            "asset_key": "a2_sentiment_comment_activity",
            "display_name": "A2舆情改善评论",
            "created_by": "ops",
            "quality_guard_profile_key": "a2_sentiment_comment_202606",
        },
        files={"file": ("a2_rule_bank.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary_json"]["rule_count"] == 2
    assert payload["summary_json"]["example_count"] == 4

    detail_response = await asset_client.get(
        "/api/v1/assets/comment_business_rule_set/a2_sentiment_comment_activity"
    )
    asset = detail_response.json()["data"]
    first = asset["content_json"]["items"][0]
    assert first["rule_id"] == "a2_direct_01"
    assert first["business_rule"] == "有货-直给到货情绪"
    assert first["corpus"] == "像妈妈看到 a2 到货后顺手接一句，不回讲以前买不到。"
    assert first["examples"] == ["a2终于到货了，我去看看", "我也买到a2新货了"]
    assert "a2终于到货了" not in first["corpus"]
    assert asset["content_json"]["quality_guard_profile_key"] == "a2_sentiment_comment_202606"


@pytest.mark.asyncio
async def test_upload_comment_business_rule_set_preserves_prompt_slot_corpus(asset_client):
    csv_content = "\n".join(
        [
            "rule_id,category,focus,examples,说话风格",
            '"a2_direct_01","有货-直给到货情绪","像妈妈看到 a2 到货后顺手接一句。","a2终于到货了","适当加几个网络热词，不要过度。',
            '像评论区接楼，短一点，顺手补一句。"',
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/comment-business-rule-set",
        data={
            "asset_key": "a2_sentiment_comment_activity_with_slots",
            "display_name": "A2舆情改善评论",
            "created_by": "ops",
        },
        files={"file": ("a2_rule_bank_slots.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 200
    detail_response = await asset_client.get(
        "/api/v1/assets/comment_business_rule_set/a2_sentiment_comment_activity_with_slots"
    )
    asset = detail_response.json()["data"]
    first = asset["content_json"]["items"][0]
    assert first["prompt_slots"] == {
        "说话风格": [
            "适当加几个网络热词，不要过度。",
            "像评论区接楼，短一点，顺手补一句。",
        ]
    }


@pytest.mark.asyncio
async def test_comment_business_rule_draft_save_list_and_publish(asset_client):
    csv_content = "\n".join(
        [
            "业务规则,语料",
            '"奶宝找到妈妈","奶宝找到妈妈：',
            "",
            "示例：",
            '- 找到了找到了，我家娃终于肯吃饭了"',
            '"艾尔博士讲A1/A2型奶牛","艾尔博士讲A1/A2型奶牛：',
            "",
            "示例：",
            '- 娃听艾尔博士讲完，又催我去门店看看活动"',
            "",
        ]
    )
    import_response = await asset_client.post(
        "/api/v1/assets/imports/comment-business-rule-set",
        data={
            "asset_key": "a2_plot_discussion_comment",
            "created_by": "ops",
            "display_name": "A2剧情讨论评论",
        },
        files={"file": ("剧情讨论业务规则.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )
    assert import_response.status_code == 200

    draft_corpus = "\n".join(
        [
            "艾尔博士讲A1/A2型奶牛：",
            "",
            "示例：",
            "- 娃听艾尔博士讲A1/A2型奶牛，正好我路过门店补奶粉",
            "- 群里有人晒对讲机，我准备带娃去门店续上奶粉",
        ]
    )

    save_response = await asset_client.post(
        "/api/v1/assets/comment-business-rule-drafts",
        json={
            "asset_key": "a2_plot_discussion_comment",
            "rule_id": "business_rule_002",
            "draft_corpus": draft_corpus,
            "created_by": "ops",
        },
    )
    assert save_response.status_code == 200
    draft = save_response.json()["data"]
    assert draft["status"] == "draft"
    assert draft["base_version_no"] == 1
    assert draft["business_rule"] == "艾尔博士讲A1/A2型奶牛"
    assert draft["original_corpus"].startswith("艾尔博士讲A1/A2型奶牛")
    assert "路过门店补奶粉" in draft["draft_corpus"]

    list_response = await asset_client.get(
        "/api/v1/assets/comment-business-rule-drafts",
        params={
            "asset_key": "a2_plot_discussion_comment",
            "rule_id": "business_rule_002",
        },
    )
    assert list_response.status_code == 200
    drafts = list_response.json()["data"]
    assert [item["id"] for item in drafts] == [draft["id"]]

    before_publish = await asset_client.get(
        "/api/v1/assets/comment_business_rule_set/a2_plot_discussion_comment"
    )
    before_asset = before_publish.json()["data"]
    assert before_asset["version_no"] == 1
    assert "路过门店补奶粉" not in before_asset["content_json"]["items"][1]["corpus"]

    publish_response = await asset_client.post(
        f"/api/v1/assets/comment-business-rule-drafts/{draft['id']}/publish",
        json={"created_by": "ops"},
    )
    assert publish_response.status_code == 200
    published = publish_response.json()["data"]
    assert published["draft"]["status"] == "applied"
    assert published["asset"]["version_no"] == 2
    assert published["asset"]["source_name"] == f"comment_business_rule_draft:{draft['id']}"
    assert published["asset"]["metadata_json"]["last_rule_draft_id"] == draft["id"]

    items = published["asset"]["content_json"]["items"]
    assert items[0]["corpus"] == before_asset["content_json"]["items"][0]["corpus"]
    assert items[1]["corpus"] == "艾尔博士讲A1/A2型奶牛："
    assert "示例：" not in items[1]["corpus"]
    assert items[1]["examples"] == [
        "娃听艾尔博士讲A1/A2型奶牛，正好我路过门店补奶粉",
        "群里有人晒对讲机，我准备带娃去门店续上奶粉",
    ]

    latest_response = await asset_client.get(
        "/api/v1/assets/comment_business_rule_set/a2_plot_discussion_comment"
    )
    latest = latest_response.json()["data"]
    assert latest["version_no"] == 2
    assert latest["content_json"]["items"][1]["corpus"] == "艾尔博士讲A1/A2型奶牛："


@pytest.mark.asyncio
async def test_comment_prompt_bundle_draft_publish_updates_all_five_fields(asset_client):
    csv_content = "\n".join(
        [
            "业务规则名称,生文指令,内容方向,内容素材,写法,注意,示例",
            '"有货-直给简单报喜","生成一条真实用户评论。","旧内容方向","a2已经到货。","字数在20字以内","不要说消极词。","a2终于到货了"',
        ]
    )
    import_response = await asset_client.post(
        "/api/v1/assets/imports/comment-business-rule-set",
        data={
            "asset_key": "a2_bundle_draft",
            "created_by": "ops",
            "display_name": "A2 Bundle 草稿",
        },
        files={"file": ("A2评论业务规则.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )
    assert import_response.status_code == 200
    before_asset = (
        await asset_client.get("/api/v1/assets/comment_business_rule_set/a2_bundle_draft")
    ).json()["data"]
    before_item = before_asset["content_json"]["items"][0]
    draft_bundle = {
        "generation_instruction": "生成一条小红书母婴社区真实用户评论，口语化，有活人感。",
        "content_direction": "写看到有货后的即时反应，可以简单报喜或准备购买。",
        "activity_material": ["a2已经到货或来货。", "品牌或产品名可写a2或a2至初。"],
        "writing_requirements": ["字数在20字以内"],
        "notes": ["不要说缺货、断粮等消极词。"],
    }

    save_response = await asset_client.post(
        "/api/v1/assets/comment-business-rule-drafts",
        json={
            "asset_key": "a2_bundle_draft",
            "rule_id": before_item["rule_id"],
            "draft_corpus": draft_bundle["content_direction"],
            "comment_prompt_bundle": draft_bundle,
            "created_by": "ops",
        },
    )
    assert save_response.status_code == 200
    draft = save_response.json()["data"]
    assert draft["original_comment_prompt_bundle"] == before_item["comment_prompt_bundle"]
    assert draft["draft_comment_prompt_bundle"] == draft_bundle

    publish_response = await asset_client.post(
        f"/api/v1/assets/comment-business-rule-drafts/{draft['id']}/publish",
        json={"created_by": "ops"},
    )
    assert publish_response.status_code == 200
    published_item = publish_response.json()["data"]["asset"]["content_json"]["items"][0]
    assert published_item["prompt_mode"] == "comment_prompt_bundle"
    assert published_item["comment_prompt_bundle"] == draft_bundle
    assert published_item["corpus"] == draft_bundle["content_direction"]
    assert published_item["content_direction"] == draft_bundle["content_direction"]
    assert published_item["activity_material"] == draft_bundle["activity_material"]
    assert published_item["examples"] == before_item["examples"]


@pytest.mark.asyncio
async def test_upload_article_business_rule_set_imports_rule_asset(asset_client):
    csv_content = "\n".join(
        [
            "# 运营本地说明行会被导入器忽略",
            "业务规则,语料,参考示例,补充参考",
            '"奶量补充","## 业务规则',
            "",
            "本文围绕奶量补充相关体验来写。",
            "",
            "提示：",
            "- 像在聊宝宝的喝奶变化。",
            "",
            "可参考素材：",
            "- 刚换源悦那阵子，喂奶没之前那么拉扯。",
            "- 有时候不用追着喂，家里人也松口气。",
            "",
            '注意：参考素材只提供语义方向，生成时换一种自然说法。","- 新列示例1',
            "- 新列示例2",
            '- 新列示例3","- 新列补充1"',
            '"消化吸收","## 业务规则',
            "",
            "本文围绕消化吸收相关体验来写。",
            "",
            "可参考素材：",
            "- 主要看喝完后的肚肚状态和便便节奏。",
            "",
            '注意：参考素材只提供语义方向，生成时换一种自然说法。"',
            "",
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "created_by": "ops",
            "display_name": "源悦生文业务规则",
            "keyword_asset_key": "yuanyue_article_business_keywords",
            "keyword_selection": '{"article_speaking_style":["routine_log","kid_reaction_record"]}',
        },
        files={"file": ("业务规则_子关键词导出.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    data = payload["data"]
    assert data["imported_assets"] == 1
    assert ["article_business_rule_set", "yuanyue_product_experience"] in data["asset_keys"]
    assert data["summary_json"]["rule_count"] == 2
    assert data["summary_json"]["example_count"] == 4
    assert data["summary_json"]["keyword_asset_key"] == "yuanyue_article_business_keywords"
    assert data["summary_json"]["keyword_selection"] == {
        "article_speaking_style": ["routine_log", "kid_reaction_record"]
    }

    detail_response = await asset_client.get(
        "/api/v1/assets/article_business_rule_set/yuanyue_product_experience"
    )
    assert detail_response.status_code == 200
    asset = detail_response.json()["data"]
    assert asset["asset_type"] == "article_business_rule_set"
    assert asset["display_name"] == "源悦生文业务规则"
    assert asset["content_json"]["keyword_asset_key"] == "yuanyue_article_business_keywords"
    assert asset["content_json"]["keyword_selection"] == {
        "article_speaking_style": ["routine_log", "kid_reaction_record"]
    }
    assert asset["metadata_json"]["keyword_asset_key"] == "yuanyue_article_business_keywords"
    assert asset["metadata_json"]["keyword_selection"] == {
        "article_speaking_style": ["routine_log", "kid_reaction_record"]
    }
    assert asset["content_json"]["rule_type"] == "business_rule"
    assert asset["content_json"]["allow_repeat_generation"] is True
    assert asset["metadata_json"]["allow_repeat_generation"] is True
    assert asset["content_json"]["items"][0]["business_rule"] == "奶量补充"
    assert "product_experience" not in asset["content_json"]["items"][0]
    assert "baby_stage" not in asset["content_json"]["items"][0]
    assert "use_duration" not in asset["content_json"]["items"][0]
    assert "topic" not in asset["content_json"]["items"][0]
    assert asset["content_json"]["items"][0]["examples"] == [
        "刚换源悦那阵子，喂奶没之前那么拉扯。",
        "有时候不用追着喂，家里人也松口气。",
        "新列补充1",
    ]
    assert asset["content_json"]["items"][0]["supplements"] == []
    assert asset["content_json"]["items"][1]["examples"] == ["主要看喝完后的肚肚状态和便便节奏。"]
    assert "1 条规则示例少于3条" in asset["metadata_json"]["warnings"]


@pytest.mark.asyncio
async def test_update_article_business_rule_examples_creates_new_asset_version(asset_client):
    csv_content = "\n".join(
        [
            "业务规则名称,规则语料,示例",
            '"到手看报告","写什么：妈妈收到 a2 后看了罐底报告。","- 原示例1\n- 原示例2\n- 原示例3"',
        ]
    )
    import_response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "asset_key": "a2_article_examples",
            "created_by": "ops",
            "display_name": "A2帖子示例维护",
        },
        files={"file": ("A2帖子业务规则.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )
    assert import_response.status_code == 200
    before_asset = (
        await asset_client.get("/api/v1/assets/article_business_rule_set/a2_article_examples")
    ).json()["data"]
    before_item = before_asset["content_json"]["items"][0]

    update_response = await asset_client.post(
        "/api/v1/assets/business-rule-examples",
        params={"asset_type": "article"},
        json={
            "asset_key": "a2_article_examples",
            "source_row_no": before_item["source_row_no"],
            "examples": ["这批报告我扫到了", "罐底一扫信息挺全", "看完心里有数点"],
            "supplements": ["有姐妹会看这种报告吗"],
            "created_by": "ops",
        },
    )

    assert update_response.status_code == 200
    updated_asset = update_response.json()["data"]
    assert updated_asset["asset_type"] == "article_business_rule_set"
    assert updated_asset["version_no"] == before_asset["version_no"] + 1
    updated_item = updated_asset["content_json"]["items"][0]
    assert updated_item["corpus"] == before_item["corpus"]
    assert updated_item["examples"] == ["这批报告我扫到了", "罐底一扫信息挺全", "看完心里有数点", "有姐妹会看这种报告吗"]
    assert updated_item["supplements"] == []
    assert updated_asset["metadata_json"]["example_count"] == 4
    assert updated_asset["metadata_json"]["last_examples_rule_id"] == before_item["rule_id"]


@pytest.mark.asyncio
async def test_article_business_rule_draft_publish_updates_corpus_only(asset_client):
    csv_content = "\n".join(
        [
            "业务规则,语料,参考示例",
            '"有货后看报告","旧规则语料","- 示例1\n- 示例2\n- 示例3"',
        ]
    )
    import_response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "asset_key": "a2_article_draft",
            "created_by": "ops",
            "display_name": "A2帖子规则草稿",
        },
        files={"file": ("A2帖子业务规则.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )
    assert import_response.status_code == 200
    before_asset = (
        await asset_client.get("/api/v1/assets/article_business_rule_set/a2_article_draft")
    ).json()["data"]
    before_item = before_asset["content_json"]["items"][0]

    save_response = await asset_client.post(
        "/api/v1/assets/comment-business-rule-drafts",
        json={
            "asset_key": "a2_article_draft",
            "source_row_no": before_item["source_row_no"],
            "draft_corpus": "新规则语料，只改写什么和怎么说",
            "created_by": "ops",
        },
    )
    assert save_response.status_code == 200
    draft = save_response.json()["data"]

    publish_response = await asset_client.post(
        f"/api/v1/assets/comment-business-rule-drafts/{draft['id']}/publish",
        json={"created_by": "ops"},
    )
    assert publish_response.status_code == 200
    published_asset = publish_response.json()["data"]["asset"]
    assert published_asset["asset_type"] == "article_business_rule_set"
    assert published_asset["version_no"] == before_asset["version_no"] + 1
    updated_item = published_asset["content_json"]["items"][0]
    assert updated_item["corpus"] == "新规则语料，只改写什么和怎么说"
    assert updated_item["examples"] == before_item["examples"]


@pytest.mark.asyncio
async def test_business_rule_copilot_context_resolves_article_rule_and_draft(asset_client):
    csv_content = "\n".join(
        [
            "业务规则,语料,参考示例",
            '"V3M-01｜进阶保护力｜使用反馈","这篇要写的事：妈妈记录孩子喝旺玥后的日常状态。","- 示例1"',
        ]
    )
    import_response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "asset_key": "wangyue_v3_article_rules",
            "created_by": "ops",
            "display_name": "旺玥V3生文业务规则",
        },
        files={"file": ("旺玥V3生文业务规则.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )
    assert import_response.status_code == 200
    asset = (
        await asset_client.get("/api/v1/assets/article_business_rule_set/wangyue_v3_article_rules")
    ).json()["data"]
    item = asset["content_json"]["items"][0]

    context_response = await asset_client.get(
        "/api/v1/assets/business-rule-copilot-context",
        params={
            "asset_key": "wangyue_v3_article_rules",
            "rule_id": item["rule_id"],
        },
    )
    assert context_response.status_code == 200
    context = context_response.json()["data"]
    assert context["content_type"] == "article"
    assert context["asset"]["version_no"] == asset["version_no"]
    assert context["rule"]["business_rule"] == "V3M-01｜进阶保护力｜使用反馈"
    assert context["rule"]["corpus"].startswith("这篇要写的事")
    assert context["workflow"]["test_payloads"]["ten_parallel"]["endpoint"] == "/api/v1/content-agent/batches/start"
    assert context["workflow"]["test_payloads"]["ten_parallel"]["payload"]["count"] == 10
    assert context["workflow"]["test_payloads"]["quick_generate_only"]["payload"]["postprocess_mode"] == "generate_only"

    draft_response = await asset_client.post(
        "/api/v1/assets/comment-business-rule-drafts",
        json={
            "asset_key": "wangyue_v3_article_rules",
            "rule_id": item["rule_id"],
            "draft_corpus": "候选语料：妈妈从真实聚会聊天切入。",
            "created_by": "ops",
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()["data"]

    draft_context_response = await asset_client.get(
        "/api/v1/assets/business-rule-copilot-context",
        params={
            "asset_key": "wangyue_v3_article_rules",
            "draft_id": draft["id"],
        },
    )
    assert draft_context_response.status_code == 200
    draft_context = draft_context_response.json()["data"]
    assert draft_context["selected_draft"]["id"] == draft["id"]
    assert draft_context["drafts"][0]["id"] == draft["id"]
    assert (
        draft_context["workflow"]["test_payloads"]["once_full"]["payload"]["draft_corpus"]
        == "候选语料：妈妈从真实聚会聊天切入。"
    )
    assert draft_context["workflow"]["publish_draft"]["endpoint"].endswith("/{draft_id}/publish")


@pytest.mark.asyncio
async def test_upload_article_business_rule_set_rejects_old_product_experience_header(asset_client):
    csv_content = "\n".join(
        [
            "产品使用体验,语料",
            '"容易中招","## 业务规则',
            "",
            "活动：0705旺玥活动。",
            '可参考素材：\n- 接娃回来先换衣服。"',
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "asset_key": "wangyue_article_business_topic_only",
            "created_by": "ops",
            "display_name": "旺玥-主题粒度",
        },
        files={"file": ("旺玥-旧表头.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 400
    assert "article business rule set is empty" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_article_business_rule_set_preserves_product_permission_slots(asset_client):
    corpus = (
        "活动：0705旺玥活动。篇幅类型：短文；正文约60-120字。\n\n"
        "产品只能作为家里库存物件出现，不要写成种草。"
    )
    csv_content = "\n".join(
        [
            "业务规则,痛点,卖点方向,主正向证据,帖子类型,产品出现方式,UGC类型,生活动机,产品角色,产品浓度,不完美感,产品动作表面,标题形态,标题emoji,正文场景,产品出现位置,收尾方式,语料",
            f'"补货/家务清单｜产品是家里库存物件","容易中招","保护力营养关注","少请假、户外回来不蔫","补货/家务清单","产品是家里库存物件","复购/囤货型","月底看账单","库存物件/补货清单一项","中低","这个月又没少花",,"清单/库存标签","TITLE_EMOJI_LIGHT","快递到货拆箱","清单项中出现","放回位置","{corpus}"',
            f'"使用记录｜产品是日常动作的一部分","营养不足","日常营养补充","饭奶状态稳、日常营养不断档","使用记录","产品是日常动作的一部分","日常使用记录型","早上赶时间","低浓度在场物件","低","当天还是一地乱","物件在场",,"TITLE_EMOJI_NONE",,"中段桌面物件里出现","没总结","{corpus}"',
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "asset_key": "wangyue_product_permission_slots",
            "display_name": "0705旺玥活动-产品出现许可",
            "created_by": "ops",
        },
        files={"file": ("旺玥-产品出现许可.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 200
    detail_response = await asset_client.get(
        "/api/v1/assets/article_business_rule_set/wangyue_product_permission_slots"
    )
    asset = detail_response.json()["data"]
    first, second = asset["content_json"]["items"]
    assert first["post_type"] == "补货/家务清单"
    assert first["product_appearance_mode"] == "产品是家里库存物件"
    assert first["painpoint"] == "容易中招"
    assert first["selling_point"] == "保护力营养关注"
    assert first["positive_evidence"] == "少请假、户外回来不蔫"
    assert first["ugc_post_type"] == "复购/囤货型"
    assert first["life_trigger"] == "月底看账单"
    assert first["product_role"] == "库存物件/补货清单一项"
    assert first["product_density"] == "中低"
    assert first["imperfection"] == "这个月又没少花"
    assert first["title_shape_mode"] == "清单/库存标签"
    assert first["title_emoji_mode"] == "TITLE_EMOJI_LIGHT"
    assert first["scene_motive_bucket"] == "快递到货拆箱"
    assert first["product_position_mode"] == "清单项中出现"
    assert first["ending_mode"] == "放回位置"
    assert second["post_type"] == "使用记录"
    assert second["product_appearance_mode"] == "产品是日常动作的一部分"
    assert second["painpoint"] == "营养不足"
    assert second["selling_point"] == "日常营养补充"
    assert second["positive_evidence"] == "饭奶状态稳、日常营养不断档"
    assert second["ugc_post_type"] == "日常使用记录型"
    assert second["life_trigger"] == "早上赶时间"
    assert second["product_role"] == "低浓度在场物件"
    assert second["product_density"] == "低"
    assert second["imperfection"] == "当天还是一地乱"
    assert second["product_action_surface"] == "物件在场"
    assert second["title_emoji_mode"] == "TITLE_EMOJI_NONE"
    assert second["product_position_mode"] == "中段桌面物件里出现"
    assert second["ending_mode"] == "没总结"


@pytest.mark.asyncio
async def test_upload_article_business_rule_set_infers_activity_and_word_count(asset_client):
    mid_corpus = (
        "## 业务规则\n\n"
        "活动：0705旺玥活动。篇幅类型：中短文；正文按130字左右写，"
        "建议125-145字，可在120-150字之间；只写一段，不换行。\n\n"
        "可参考素材：\n- 接娃回家先换衣服，出门前这杯旺玥也安排上。"
    )
    short_corpus = (
        "## 业务规则\n\n"
        "活动：0705旺玥活动。篇幅类型：短文；正文必须40-80字，"
        "建议45-65字；只写一段，不换行。\n\n"
        "可参考素材：\n- 又开一听旺玥，先记一下这段时间的安排。"
    )
    csv_content = "\n".join(
        [
            "业务规则,语料",
            f'"容易中招，日常保护力","{mid_corpus}"',
            f'"营养不足，挑食营养补充","{short_corpus}"',
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "asset_key": "wangyue_v3_core_storyline_article_rules",
            "display_name": "0705旺玥活动",
            "created_by": "ops",
        },
        files={"file": ("旺玥-业务规则_子关键词导出.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 200
    detail_response = await asset_client.get(
        "/api/v1/assets/article_business_rule_set/wangyue_v3_core_storyline_article_rules"
    )
    asset = detail_response.json()["data"]
    assert asset["content_json"]["activity_name"] == "0705旺玥活动"
    assert asset["metadata_json"]["activity_name"] == "0705旺玥活动"
    assert (
        asset["content_json"]["word_count"]
        == "逐条参考：中短文约120-150字，短一点但像真人不要硬扩写；短文40-80字；标题不计；正文单段不换行"
    )
    assert asset["metadata_json"]["word_count"] == asset["content_json"]["word_count"]


@pytest.mark.asyncio
async def test_upload_article_business_rule_set_uses_its_display_name_as_activity_fallback(asset_client):
    csv_content = "\n".join(
        [
            "业务规则名称,规则语料,示例",
            '"妈妈班+月子中心","写一篇a2妈妈班活动后的分享。","示例"',
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "asset_key": "a2_momclass_month_center",
            "display_name": "a2妈妈班+月子中心",
            "created_by": "ops",
        },
        files={"file": ("a2妈妈班业务规则.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 200
    detail_response = await asset_client.get(
        "/api/v1/assets/article_business_rule_set/a2_momclass_month_center"
    )
    asset = detail_response.json()["data"]
    assert asset["content_json"]["activity_name"] == "a2妈妈班+月子中心"
    assert asset["metadata_json"]["activity_name"] == "a2妈妈班+月子中心"


@pytest.mark.asyncio
async def test_upload_multi_activity_rule_set_uses_package_display_name(asset_client):
    csv_content = "\n".join(
        [
            "业务规则名称,规则语料,示例",
            '"妈妈班","活动：a2妈妈班。\\n\\n这篇要写的事：写待产妈妈参加妈妈班。","示例1"',
            '"月子中心","活动：a2月子中心活动。\\n\\n这篇要写的事：写产后妈妈参加月子中心活动。","示例2"',
        ]
    )

    response = await asset_client.post(
        "/api/v1/assets/imports/article-business-rule-set",
        data={
            "asset_key": "a2_momclass_month_center",
            "display_name": "妈妈班+月子中心",
            "created_by": "ops",
        },
        files={"file": ("a2妈妈班+月子中心.csv", csv_content.encode("utf-8-sig"), "text/csv")},
    )

    assert response.status_code == 200
    detail_response = await asset_client.get(
        "/api/v1/assets/article_business_rule_set/a2_momclass_month_center"
    )
    asset = detail_response.json()["data"]
    assert asset["content_json"]["activity_name"] == "妈妈班+月子中心"
    assert asset["metadata_json"]["activity_name"] == "妈妈班+月子中心"
    assert [item["business_rule"] for item in asset["content_json"]["items"]] == ["妈妈班", "月子中心"]
