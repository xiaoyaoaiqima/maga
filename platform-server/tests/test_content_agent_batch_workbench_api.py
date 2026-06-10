"""API tests for the operator-facing content-agent workbench batch flow."""

import json
import re
from collections import Counter
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook
from pydantic import ValidationError
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.content_agent import router
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import (
    ContentAgentStageCall,
    ContentBatchItem,
    ContentBatchItemVersion,
    ContentFeedback,
    ExecutorRegistry,
)
from app.models.llm_provider_config import LLMProviderConfig
from app.models.maga_assets import AssetChangeRequest, AssetRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.schemas.content_batch_report import (
    ContentBatchReportResponse,
    ContentBatchReportSummary,
    ContentBatchReportItem,
    ContentBatchStartRequest,
    ContentCommentBatchStartRequest,
)
from app.services.activity_quality_guard_service import ActivityQualityGuardService, resolve_quality_guard_profile
from app.services.comment_batch_variation_review_service import CommentBatchVariationReviewService
from app.services.content_comment_batch_service import ContentCommentBatchService
from app.services.content_batch_report_service import _article_pool_excel_filename, _article_pool_export_items
from app.services.comment_realness_review_service import (
    _remove_or_replace_realness_terms,
    find_comment_realness_hits,
)


@pytest_asyncio.fixture
async def content_agent_workbench_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                profile_name="maga-worker",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                supported_capabilities_json=[
                    {"capability": "asset.import", "schema_version": "1"},
                    {"capability": "content.generate", "schema_version": "1"},
                    {"capability": "content.rewrite", "schema_version": "1"},
                ],
                enabled=1,
            )
        )
        session.add_all(_yuanyue_assets())
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/content-agent")

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory

    await engine.dispose()


def test_article_batch_start_request_allows_one_thousand_items():
    assert ContentBatchStartRequest(count=1000).count == 1000
    with pytest.raises(ValidationError):
        ContentBatchStartRequest(count=1001)


def test_comment_batch_start_request_allows_one_hundred_items():
    assert ContentCommentBatchStartRequest(count=100).count == 100
    with pytest.raises(ValidationError):
        ContentCommentBatchStartRequest(count=101)


def test_comment_rule_selection_balances_angles_when_rule_pool_is_large():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rules = [
        {
            "comment_angle": angle,
            "corpus": f"{angle} corpus {index}",
            "source_row_no": index,
        }
        for angle, start in [("便便问题", 1), ("奶量补充", 11), ("生长发育", 21)]
        for index in range(start, start + 10)
    ]

    selected = service._select_rules(rules, 6)

    assert len(selected) == 6
    assert {rule["comment_angle"] for rule in selected} == {"便便问题", "奶量补充", "生长发育"}
    assert [rule["source_row_no"] for rule in selected] != list(range(1, 7))


def test_a2_profile_rule_selection_balances_required_keywords():
    profile = resolve_quality_guard_profile("a2_sentiment_comment_202606")
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rules = [
        {"comment_angle": "A2舆情改善评论", "corpus": f"有货+批批检规则-{index}\n有货补货物流码报告0.03"}
        for index in range(6)
    ] + [
        {"comment_angle": "A2舆情改善评论", "corpus": f"批批检+转奶规则-{index}\n转奶肚肚物流码报告0.03"}
        for index in range(6)
    ] + [
        {"comment_angle": "A2舆情改善评论", "corpus": f"有货+转奶规则-{index}\n有货转奶物流码报告0.03"}
        for index in range(6)
    ]

    selected, selection_mode = service._select_rules_for_batch(
        rules,
        12,
        focus_comment_angle=None,
        profile=profile,
    )

    assert selection_mode == "keyword_balanced_random"
    assert len(selected) == 12
    assert sum("有货+批批检" in rule["corpus"] for rule in selected) == 4
    assert sum("批批检+转奶" in rule["corpus"] for rule in selected) == 4
    assert sum("有货+转奶" in rule["corpus"] for rule in selected) == 4


def test_a2_profile_rule_selection_repeats_balanced_keywords_for_large_count():
    profile = resolve_quality_guard_profile("a2_sentiment_comment_202606")
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rules = [
        {"comment_angle": "A2舆情改善评论", "corpus": f"有货+批批检规则-{index}\n有货补货物流码报告0.03"}
        for index in range(2)
    ] + [
        {"comment_angle": "A2舆情改善评论", "corpus": f"批批检+转奶规则-{index}\n转奶肚肚物流码报告0.03"}
        for index in range(2)
    ] + [
        {"comment_angle": "A2舆情改善评论", "corpus": f"有货+转奶规则-{index}\n有货转奶物流码报告0.03"}
        for index in range(2)
    ]
    asset = SimpleNamespace(metadata_json={}, content_json={})

    limit = service._generation_limit(asset, rules, requested_count=20)
    selected, selection_mode = service._select_rules_for_batch(
        rules,
        limit,
        focus_comment_angle=None,
        profile=profile,
    )

    assert limit == 20
    assert selection_mode == "keyword_balanced_random_with_replacement"
    assert len(selected) == 20
    counts = [
        sum("有货+批批检" in rule["corpus"] for rule in selected),
        sum("批批检+转奶" in rule["corpus"] for rule in selected),
        sum("有货+转奶" in rule["corpus"] for rule in selected),
    ]
    assert min(counts) >= 6
    assert max(counts) <= 7


def test_comment_rule_selection_repeats_every_rule_evenly_when_requested_multiple():
    profile = resolve_quality_guard_profile("a2_sentiment_comment_202606")
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rules = [
        {
            "comment_angle": "A2舆情改善评论",
            "corpus": f"切角-{index}\n关键词方向是有货+批批检。",
            "source_row_no": index,
        }
        for index in range(1, 24)
    ]
    asset = SimpleNamespace(metadata_json={}, content_json={})

    limit = service._generation_limit(asset, rules, requested_count=46)
    selected, selection_mode = service._select_rules_for_batch(
        rules,
        limit,
        focus_comment_angle=None,
        profile=profile,
    )

    assert limit == 46
    assert selection_mode == "even_rule_repetition"
    assert len(selected) == 46
    counts = Counter(rule["source_row_no"] for rule in selected)
    assert set(counts) == set(range(1, 24))
    assert set(counts.values()) == {2}


def test_comment_focus_selection_repeats_rules_for_requested_count():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rules = [
        {
            "comment_angle": "整体适应",
            "corpus": "像妈妈在评论区聊刚开始喝源悦的观察。",
            "examples": ["我家刚开始也在看源悦，想蹲蹲真实反馈"],
            "source_row_no": 1,
        }
    ]
    asset = SimpleNamespace(metadata_json={"default_generation_count": 1}, content_json={})

    limit = service._generation_limit(asset, rules, requested_count=5, allow_repeat=True)
    selected = service._select_rules_with_replacement(rules, limit)

    assert limit == 5
    assert len(selected) == 5
    assert all(rule["comment_angle"] == "整体适应" for rule in selected)


def test_comment_single_rule_filter_supports_by_case_generation():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rules = [
        {"rule_id": "comment_angle_001", "source_row_no": 1, "comment_angle": "剧情讨论", "corpus": "剧情事实"},
        {"rule_id": "comment_angle_002", "source_row_no": 2, "comment_angle": "剧情讨论", "corpus": "对讲机"},
    ]
    asset = SimpleNamespace(metadata_json={}, content_json={})

    filtered = service._rules_for_single_item(rules, rule_id="comment_angle_001", source_row_no=None)
    limit = service._generation_limit(asset, filtered, requested_count=10, allow_repeat=True)
    selected, selection_mode = service._select_rules_for_batch(
        filtered,
        limit,
        focus_comment_angle="剧情讨论",
        profile=None,
    )

    assert limit == 10
    assert selection_mode == "random_with_replacement"
    assert {rule["rule_id"] for rule in selected} == {"comment_angle_001"}


def test_comment_draft_rule_override_keeps_active_rule_unchanged():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rules = [
        {
            "rule_id": "comment_angle_002",
            "source_row_no": 2,
            "comment_angle": "剧情讨论",
            "corpus": "旧语料",
            "examples": ["旧示例"],
        }
    ]
    draft = {
        "rule_id": "comment_angle_002",
        "source_row_no": None,
        "corpus": "新语料：\n\n示例：\n- 新示例1\n- 新示例2\n\n注意：示例只作为语义素材。",
    }

    updated = service._rules_with_draft_override(rules, draft)

    assert rules[0]["corpus"] == "旧语料"
    assert rules[0]["examples"] == ["旧示例"]
    assert updated[0]["corpus"].startswith("新语料")
    assert updated[0]["examples"] == ["新示例1", "新示例2"]
    assert updated[0]["draft_rule_override"]["enabled"] is True


def test_comment_plan_injects_one_reference_example_from_pool():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rule = {
        "rule_id": "comment_angle_001",
        "comment_angle": "便便问题",
        "corpus": "像评论区宝妈接话，聊便便频率和软硬。",
        "examples": ["同款，崽崽都是香蕉软便便", "加一，现在固定一天一次"],
        "supplements": ["我家拉得挺轻松的，没有那么费劲"],
        "source_row_no": 1,
    }
    asset = SimpleNamespace(asset_key="yuanyue", id=7, version_no=3)

    plan = service._plan_from_rule(rule, asset=asset, item_no=1)

    assert len(plan["examples"]) == 1
    assert plan["examples"][0] in rule["examples"]
    assert plan["supplements"] == []
    assert plan["example_pool_count"] == 2
    assert plan["supplement_pool_count"] == 1
    assert plan["selected_example_source"] == "examples"


def test_comment_plan_copies_generation_requirements_from_rule_asset():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rule = {
        "rule_id": "comment_angle_001",
        "comment_angle": "剧情讨论",
        "corpus": "剧情规则",
        "examples": ["剧情示例"],
        "source_row_no": 1,
    }
    asset = SimpleNamespace(
        asset_key="a2_plot_discussion_comment",
        id=7,
        version_no=3,
        content_json={"generation_requirements": "只输出21到35字剧情讨论评论。"},
        metadata_json={},
    )

    plan = service._plan_from_rule(rule, asset=asset, item_no=1)

    assert plan["generation_requirements"] == "只输出21到35字剧情讨论评论。"


def test_comment_plan_copies_batch_variation_review_from_rule_asset():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    config = {
        "enabled": True,
        "expression_frequency": [
            {
                "group_key": "activity_status_question",
                "terms": ["活动还在不在", "活动还有没有"],
                "max_ratio": 0.2,
            }
        ],
    }
    asset = SimpleNamespace(
        asset_key="a2_plot_discussion_comment",
        id=7,
        version_no=3,
        content_json={"batch_variation_review": config},
        metadata_json={},
    )

    plan = service._plan_from_rule({"comment_angle": "剧情讨论", "corpus": "剧情规则"}, asset=asset, item_no=1)

    assert plan["batch_variation_review"] == config


def test_comment_length_fallback_keeps_short_natural_clause():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)

    comment = service._fit_comment_length("从旧奶转源悦，我家娃皮肤敏感，先少量掺着喝。", max_chars=20)

    assert comment == "从旧奶转源悦，我家娃皮肤敏感"
    assert len(comment) <= 20


def test_comment_length_fallback_avoids_dangling_clause():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)

    comment = service._fit_comment_length("我家从转奶第三天开始，拉臭臭就没那么费劲了。", max_chars=20)

    assert comment != "我家从转奶第三天开始"
    assert not comment.endswith("开始")
    assert len(comment) <= 20


def test_comment_length_default_caps_at_thirty_five_chars():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)

    comment = service._fit_comment_length(
        "我们喝这款好几个月了，拉的时候没费过劲，前面也不见羊屎蛋，换纸尿裤时软软的挺舒坦"
    )

    assert len(comment) <= 35


def test_a2_comment_length_allows_combo_information_density():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    item = ContentBatchItem(plan_json={"quality_guard_profile_key": "a2_sentiment_comment_202606"})
    comment = "刚转奶先看物流码报告，爱他美样批也看，a2报告里那项0.03再结合肚肚便便状态"

    fitted = service._fit_comment_length(comment, max_chars=service._comment_max_chars(item))

    assert fitted == comment
    assert len(fitted) > 35
    assert service._comment_max_chars(item) == 45


def test_a2_plot_discussion_length_is_not_trimmed_before_guard():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    item = ContentBatchItem(plan_json={"quality_guard_profile_key": "a2_plot_discussion_comment_202606"})
    comment = "娃刚看完山洞求援那段正演得起劲，我去店里续奶粉就打听有没有巴克队长款对讲机"

    normalized = service._normalize_comment_length(item, comment)

    assert normalized == comment
    assert len(normalized) > 35
    assert service._comment_max_chars(item) == 50


def test_comment_length_fallback_leaves_short_comment_unchanged():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)

    assert service._fit_comment_length("纸尿裤里不吓人") == "纸尿裤里不吓人"


def test_low_information_comment_detection_only_catches_empty_openers():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)

    assert service._looks_low_information_comment("我们家")
    assert service._looks_low_information_comment("同款！")
    assert not service._looks_low_information_comment("我家不硬")
    assert not service._looks_low_information_comment("同款，便便软多了")


def test_yuanyue_brand_hallucination_guard_is_asset_scoped():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    item = ContentBatchItem(
        body="一直喝星飞帆，后来还看过a2、A2和爱他美。",
        plan_json={"asset_key": "yuanyue_comment_activity"},
        quality_json={},
    )

    service._sanitize_brand_hallucinations(item)

    assert "星飞帆" not in item.body
    assert "a2" not in item.body
    assert "A2" not in item.body
    assert "爱他美" not in item.body
    assert set(item.quality_json["brand_hallucination_guard"]["hits"]) == {"星飞帆", "爱他美", "a2", "A2"}

    other = ContentBatchItem(
        body="一直喝星飞帆，后来还看过a2、A2和爱他美。",
        plan_json={"asset_key": "other_activity"},
        quality_json={},
    )
    service._sanitize_brand_hallucinations(other)

    assert other.body == "一直喝星飞帆，后来还看过a2、A2和爱他美。"


def _a2_guard_plan(corpus: str) -> dict:
    return {
        "quality_guard_profile_key": "a2_sentiment_comment_202606",
        "comment_angle": "A2舆情改善评论",
        "corpus": corpus,
        "unified_generation": {
            "selected_keywords": [
                {"category_code": "persona", "category_name": "人设", "keyword_name": "普通妈妈"},
                {"category_code": "comment_writing_instruction", "category_name": "生文指令", "keyword_name": "评论-短句"},
                {"category_code": "perturbation_rule", "category_name": "扰动规则", "keyword_name": "通用"},
                {"category_code": "comment_format_control", "category_name": "生文输出格式", "keyword_name": "生文输出格式-评论"},
            ]
        },
    }


def _a2_plot_guard_plan(corpus: str = "剧情讨论评论切角") -> dict:
    return {
        "quality_guard_profile_key": "a2_plot_discussion_comment_202606",
        "comment_angle": "评论切角-剧情讨论",
        "corpus": corpus,
        "unified_generation": {
            "selected_keywords": [
                {"category_code": "persona", "category_name": "人设", "keyword_name": "家庭妈妈"},
                {"category_code": "comment_writing_instruction", "category_name": "生文指令", "keyword_name": "评论-短句"},
                {"category_code": "perturbation_rule", "category_name": "扰动规则", "keyword_name": "通用"},
                {"category_code": "comment_format_control", "category_name": "生文输出格式", "keyword_name": "生文输出格式-评论"},
            ]
        },
    }


def test_a2_plot_discussion_guard_accepts_plot_with_store_activity():
    item = ContentBatchItem(
        body="第3集奶宝找到妈妈了，我下班顺路去门店把奶粉续上",
        plan_json=_a2_plot_guard_plan(),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert payload["context_list"]["关键词"] == "剧情讨论+门店引流"
    assert not payload["issues"]


@pytest.mark.parametrize(
    "body",
    [
        "找到了找到了，我家看到小奶宝扑进妈妈怀里才肯好好喝奶，奶粉罐子也快空了，正好明天路过母婴店去续上。",
        "后面就团聚了，我娃看得眼泪汪汪才肯睡，明天路过母婴店把奶粉续上",
    ],
)
def test_a2_plot_discussion_guard_accepts_maternity_store_and_xushang(body):
    item = ContentBatchItem(
        body=body,
        plan_json=_a2_plot_guard_plan(),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_plot_discussion_guard_flags_pure_plot_and_repairs_a2_cow_wording():
    item = ContentBatchItem(
        body="娃也认出奶宝是稀有A2奶牛了",
        plan_json=_a2_plot_guard_plan(),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert item.body == "娃也认出奶宝是稀有A2型奶牛了"
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_length_out_of_range" for issue in payload["issues"])
    assert any(issue["code"] == "activity_body_missing_store_activity" for issue in payload["issues"])


def test_a2_plot_discussion_guard_repairs_loose_a2_and_cave_wording():
    item = ContentBatchItem(
        body="娃说奶宝是稀有A2牛，山洞救援那段还想回看，它是稀有A2型的，我去门店续奶粉",
        plan_json=_a2_plot_guard_plan(),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert item.body == "娃说奶宝是稀有A2型奶牛，山洞求援那段还想回看，它是稀有A2型奶牛，我去门店续奶粉"
    assert payload["pass"] is True
    assert not payload["issues"]


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        ("娃看完山洞求援还念叨奶宝，补货时问对讲机还有没有，愿意喝着演剧情", "activity_body_odd_drinking_play_phrase"),
        ("周末陪娃看这集热气球救小奶宝，奶粉快没了顺路去店里看看", "activity_body_unsupported_plot_detail"),
        ("顺路补奶粉带回对讲机，娃回来就开始演雪地救援那集", "activity_body_unsupported_plot_detail"),
        ("娃看完一直喊奶宝是A2牛牛，我准备去门店补奶粉顺便问活动", "activity_body_invalid_plot_wording"),
        ("娃说所有奶粉都叫A2型，周末去母婴店补货时我问问活动", "activity_body_invalid_plot_wording"),
        ("宝宝走散那段看得我家着急，明天去门店续奶粉顺便问活动", "activity_body_invalid_plot_wording"),
        ("宝宝找到妈妈啦，我明天去店里补奶粉顺便问活动", "activity_body_invalid_plot_wording"),
        ("我娃看完总念叨艾尔博士打A1怪兽，我续奶粉顺便问店员活动", "activity_body_invalid_plot_wording"),
        ("我娃说要看艾尔博士打A1大怪兽，我续奶粉顺便问店员活动", "activity_body_invalid_plot_wording"),
        ("娃最近刚看完第6集山洞求援，正好去店里补奶粉", "activity_body_unsupported_plot_detail"),
        ("娃最近刚看完第六集山洞求援，正好去店里补奶粉", "activity_body_unsupported_plot_detail"),
        ("最新一集看完娃还在念叨奶宝，我下班去门店补奶粉", "activity_body_unsupported_plot_detail"),
        ("奶宝救援队那段娃很爱看，我准备去母婴店续奶粉", "activity_body_unsupported_plot_detail"),
        ("奶宝团聚后娃喊洞穴救援开始，我到店把奶粉续上", "activity_body_unsupported_plot_detail"),
        ("山洞求援看完娃还在演，我去超市买奶粉时顺便问活动", "activity_body_activity_misstatement"),
        ("奶宝团聚那段娃放心了，我补两罐顺便领对讲机", "activity_body_activity_misstatement"),
        ("奶宝团聚后我去店里问有没有小礼物", "activity_body_activity_misstatement"),
        ("奶宝团聚后娃还在念叨，我补货前顺便问问盲盒活动", "activity_body_activity_misstatement"),
        ("奶宝团聚后娃拉着汪汪队喊支援，我到店把奶粉续上", "activity_body_invalid_plot_wording"),
        ("我娃看完山洞求援说想去店里找同款对讲机，我准备补奶粉", "activity_child_knows_store_gift"),
        ("我娃看完救援非要组队，奶粉快见底了正好群里说店里搞活动", "activity_body_missing_plot_anchor"),
    ],
)
def test_a2_plot_discussion_guard_rejects_odd_play_and_unsupported_plot(body, expected_code):
    item = ContentBatchItem(
        body=body,
        plan_json=_a2_plot_guard_plan(),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == expected_code for issue in payload["issues"])


def test_a2_plot_discussion_guard_allows_store_phrase_for_batch_frequency_review():
    item = ContentBatchItem(
        body="奶牛群转移那段娃看紧张了，我去门店看看活动还在不在",
        plan_json=_a2_plot_guard_plan(),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_bad_store_phrase" for issue in payload["issues"])


def test_a2_plot_discussion_guard_rejects_over_fifty_chars_without_trimming():
    body = "娃刚看完山洞求援那段正演得起劲，我去店里续奶粉就打听有没有巴克队长款对讲机，顺便看看活动和补货安排详情"
    item = ContentBatchItem(
        body=body,
        plan_json=_a2_plot_guard_plan(),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert item.body == body
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_length_out_of_range" for issue in payload["issues"])


def test_comment_batch_variation_review_flags_only_overflow_items():
    config = {
        "enabled": True,
        "expression_frequency": [
            {
                "group_key": "activity_status_question",
                "label": "活动状态提问",
                "terms": ["活动还在不在"],
                "max_ratio": 0.4,
            }
        ],
    }
    items = [
        ContentBatchItem(item_no=1, status="generated", body="奶宝团聚了，我去问活动还在不在", plan_json={"batch_variation_review": config}, quality_json={"hard_pass": True}),
        ContentBatchItem(item_no=2, status="generated", body="山洞求援看完，顺路问活动还在不在", plan_json={"batch_variation_review": config}, quality_json={"hard_pass": True}),
        ContentBatchItem(item_no=3, status="generated", body="艾尔博士讲完，我再问活动还在不在", plan_json={"batch_variation_review": config}, quality_json={"hard_pass": True}),
        ContentBatchItem(item_no=4, status="generated", body="巴克队长同款对讲机，我补货时看看", plan_json={"batch_variation_review": config}, quality_json={"hard_pass": True}),
        ContentBatchItem(item_no=5, status="generated", body="第三集奶宝找妈妈，我到店续奶粉", plan_json={"batch_variation_review": config}, quality_json={"hard_pass": True}),
    ]

    result = CommentBatchVariationReviewService().review_batch(items)

    assert result is not None
    assert result["pass"] is False
    assert items[0].quality_json["hard_pass"] is True
    assert items[1].quality_json["hard_pass"] is True
    assert items[2].quality_json["hard_pass"] is False
    assert items[2].quality_json["batch_variation_review"]["expression_frequency"]["issues"][0]["code"] == "batch_expression_frequency_cap_exceeded"
    assert items[4].quality_json["batch_variation_review"]["expression_frequency"]["metrics"][0]["max_allowed_count"] == 2


def test_a2_activity_guard_repairs_marker_and_entry_terms():
    item = ContentBatchItem(
        body="爱他美0.03有货，今天扫罐底批次物流码那个物流码的码查报告，截图保存了，新的一罐先看报告，纸尿裤和擦屁屁总有点红先不聊，我没慌",
        plan_json=_a2_guard_plan("补货前先扫物流码：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert payload["context_list"]["关键词"] == "有货+批批检"
    assert "0.03" in item.body
    assert "a2报告里那项0.03" in item.body
    assert "爱他美" in item.body
    assert "物流码" in item.body
    assert "物流码物流码" not in item.body
    assert "物流码那个物流码" not in item.body
    assert "记录" in item.body
    assert "一罐" not in item.body
    assert "纸尿裤" not in item.body
    assert "擦屁屁" not in item.body
    assert "慌" not in item.body
    assert "担心" not in item.body
    assert "补货" in item.body or "有货" in item.body or "到货" in item.body
    assert not payload["issues"]
    assert payload["repairs"]


def test_a2_activity_guard_repairs_60_plus_and_detection_project_wording():
    item = ContentBatchItem(
        body="有货了先补a2，60+检测项目能看到，报告出来就放心了",
        plan_json=_a2_guard_plan("60多项质检数据：\n关键词方向是有货+批批检，像妈妈看到报告数据后放心补货。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "60+" not in item.body
    assert "检测项目" not in item.body
    assert "60多项检测项" in item.body
    assert not payload["issues"]
    assert any(repair["source"] == "60+" for repair in payload["repairs"])
    assert any(repair["source"] == "检测项目" for repair in payload["repairs"])


def test_a2_activity_guard_still_rejects_professional_indicator_wording():
    item = ContentBatchItem(
        body="有货了先补a2，专业指标能看到，报告出来就放心了",
        plan_json=_a2_guard_plan("60多项质检数据：\n关键词方向是有货+批批检，像妈妈看到报告数据后放心补货。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_forbidden_terms" for issue in payload["issues"])


def test_a2_activity_guard_repairs_bad_kan_shuo_wording():
    item = ContentBatchItem(
        body="同款刚补货，看说新批次有检测报告就安心，慢慢来",
        plan_json=_a2_guard_plan("补货后慢慢转：\n关键词方向是有货+转奶，像妈妈补货后慢慢转。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "看说" not in item.body
    assert "看到新批次有检测报告" in item.body
    assert not payload["issues"]
    assert any(repair["source"] == "看说" and repair["replacement"] == "看到" for repair in payload["repairs"])


def test_a2_activity_guard_repairs_bad_a2_code_wording():
    item = ContentBatchItem(
        body="这罐a2码一查报告60多项都在，比导购说得具体",
        plan_json=_a2_guard_plan("60多项质检数据看得见：\n关键词方向是有货+批批检，像妈妈看到报告数据后放心补货。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "a2码" not in item.body
    assert "这罐a2一查报告60多项都在" in item.body
    assert not payload["issues"]
    assert any(repair["source"] == "a2码" and repair["replacement"] == "a2" for repair in payload["repairs"])


def test_a2_activity_guard_repairs_incomplete_scan_bottom_wording():
    item = ContentBatchItem(
        body="我家宝快喝完了，刚好看到a2新到货，扫完罐底才安心带回家",
        plan_json=_a2_guard_plan("补货前先扫物流码：\n关键词方向是有货+批批检，像妈妈补货前看这罐报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "扫完罐底物流码看报告" in item.body
    assert not payload["issues"]
    assert any(repair["source"] == "扫完罐底" for repair in payload["repairs"])


def test_a2_activity_guard_repairs_bad_waxy_report_detail_wording():
    item = ContentBatchItem(
        body="刚转a2，扫批次报告看到蜡样报告细节是小于0.03，心里有底。",
        plan_json=_a2_guard_plan("转奶前看蜡样检测：\n关键词方向是批批检+转奶，像妈妈转奶前看这罐蜡样检测报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "蜡样报告细节" not in item.body
    assert "蜡样检测标准是小于0.03" in item.body
    assert not payload["issues"]
    assert any(repair["source"] == "蜡样报告细节" for repair in payload["repairs"])


def test_a2_activity_guard_accepts_batch_quality_data_wording():
    item = ContentBatchItem(
        body="我们家转奶时也对比过雀巢，a2这罐能直接扫出这批的质检数据，感觉更透明些。",
        plan_json=_a2_guard_plan("对雀巢打新西兰三方和60多项：\n关键词方向是批批检+转奶。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_body_missing_combo_marker" for issue in payload["issues"])


def test_a2_activity_guard_keeps_waxy_detection_standard_wording():
    item = ContentBatchItem(
        body="刚转a2，扫批次报告看到蜡样检测标准是小于0.03，心里有底。",
        plan_json=_a2_guard_plan("转奶前看蜡样检测：\n关键词方向是批批检+转奶，像妈妈转奶前看这罐蜡样检测报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "蜡样检测标准是小于0.03" in item.body
    assert "报告细节" not in item.body
    assert not payload["issues"]


def test_a2_activity_guard_accepts_short_complete_report_comment():
    item = ContentBatchItem(
        body="补上a2了，看到报告就安心些",
        plan_json=_a2_guard_plan("因为a2的优势转奶选择a2：\n关键词方向是有货+转奶，像妈妈补货后看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_body_incomplete_comment" for issue in payload["issues"])
    assert not payload["issues"]


@pytest.mark.parametrize("competitor", ["爱他美", "达能", "雀巢", "超启能恩", "美素", "皇家美素", "皇美"])
def test_a2_activity_guard_accepts_competitor_group_aliases(competitor):
    competitor_phrase = "爱他美样批也看" if competitor == "爱他美" else f"{competitor}也看"
    item = ContentBatchItem(
        body=f"有货了想转奶，先看物流码报告，{competitor_phrase}，a2能查到自己手里这批次更踏实",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert payload["context_list"]["关键词"] == "有货+转奶"


@pytest.mark.parametrize(
    "body",
    [
        "我们家刚转奶的时候也是扫罐底物流码看报告，看到蜡样检测那项才放心",
        "今天记录转奶第5天，会顺手扫罐底物流码看下这罐报告，蜡样检测那项0.03的数值心里比较有谱",
        "转奶前特意扫了罐底看报告，蜡样检测这关过了才放心",
        "之前看别的牌子没注意批次报告，转a2才留意到罐底能扫出来",
    ],
)
def test_a2_activity_guard_accepts_natural_scan_report_chain_without_forced_brand(body):
    item = ContentBatchItem(
        body=body,
        plan_json=_a2_guard_plan("转奶前看蜡样检测：\n关键词方向是批批检+转奶，像妈妈转奶前看这罐蜡样检测报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert payload["context_list"]["关键词"] == "批批检+转奶"
    assert not any(issue["code"] == "activity_body_missing_a2_specific_advantage" for issue in payload["issues"])
    assert not payload["issues"]


@pytest.mark.parametrize(
    "body",
    [
        "刚到手先扫了下物流码，报告出来就感觉靠谱多了",
        "刚收到就扫了码，这份报告能对上就省事",
    ],
)
def test_a2_activity_guard_accepts_arrival_scan_report_short_comments(body):
    item = ContentBatchItem(
        body=body,
        plan_json=_a2_guard_plan("自己这批能扫出报告：\n关键词方向是有货+批批检，像妈妈拿到a2后扫物流码看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_body_missing_a2_specific_advantage" for issue in payload["issues"])
    assert not payload["issues"]


@pytest.mark.parametrize(
    "body",
    [
        "最近这批检测报告都能查到了吗？要是能看见我就打算先补货试试",
        "同款，这次补货刚好看到检测报告，转奶选它更踏实些。",
        "有货先囤两件，看见报告就能踏实转奶了",
        "正准备转奶就赶上补货，看到有批次报告，放心先囤了。",
        "前两天还在看奶粉，正好看到a2新批次有报告，补货时就顺手带了罐先试试",
        "新一批能看报告确实安心，先补上慢慢转。",
        "刚好这次补货a2有批次报告，我打算补上了慢慢换",
        "a2这波补货看到报告有蜡样检测那项，就打算慢慢转了",
        "看到报告显示最新批次都有蜡样检测，就补上慢慢转了",
    ],
)
def test_a2_activity_guard_accepts_contextual_report_advantage_without_forced_brand(body):
    item = ContentBatchItem(
        body=body,
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_body_missing_a2_specific_advantage" for issue in payload["issues"])
    assert not payload["issues"]


def test_a2_activity_guard_repairs_duplicate_negative_prefix_wording():
    item = ContentBatchItem(
        body="囤货收到先扫罐底物流码看报告，批次和报告都能查到心里就踏实，慢慢转也不不悬",
        plan_json=_a2_guard_plan("补货后慢慢转：\n关键词方向是有货+转奶，像妈妈补货后慢慢转。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "不不悬" not in item.body
    assert "踏实些" in item.body
    assert not payload["issues"]


def test_a2_activity_guard_accepts_huangmei_transfer_back_to_a2():
    item = ContentBatchItem(
        body="我家之前转奶喝皇美，后来更在意a2至初每批蜡样检测能不能看到，还是准备慢慢换回去。",
        plan_json=_a2_guard_plan("从皇美转回a2至初：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert payload["context_list"]["关键词"] == "批批检+转奶"
    assert not payload["issues"]


def test_a2_activity_guard_does_not_require_competitor_for_general_combo_keyword():
    general_combo = ContentBatchItem(
        body="有货了想转奶，先看物流码报告，a2能查到自己手里这批次更踏实",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(general_combo)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_allows_implicit_competitor_when_angle_names_competitor_comparison():
    item = ContentBatchItem(
        body="有货了想转奶，先看物流码报告，a2能查到自己手里这批次更踏实",
        plan_json=_a2_guard_plan("爱他美/达能转奶对比：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_body_missing_competitor_group" for issue in payload["issues"])


def test_a2_activity_guard_repairs_lab_notation():

    repaired = ContentBatchItem(
        body="有货了想转奶，先看物流码报告，a2蜡样检测标准是<0.03μg/kg我也会看",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    repaired_payload = ActivityQualityGuardService().review_item(repaired)

    assert repaired_payload is not None
    assert repaired_payload["pass"] is True
    assert "μg/kg" not in repaired.body
    assert "<0.03" in repaired.body
    assert "0.03" in repaired.body
    assert repaired_payload["repairs"]


def test_a2_activity_guard_accepts_natural_batch_report_comment_without_003():
    item = ContentBatchItem(
        body="补货时我也对比过爱他美样批和美素，最后还是更看重a2能不能查到手里这罐批次报告。",
        plan_json=_a2_guard_plan("补货前先扫物流码：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "0.03" not in item.body
    assert not payload["issues"]


def test_a2_activity_guard_accepts_split_batch_report_action_chain():
    item = ContentBatchItem(
        body="一直喝爱他美这次换a2了，店里有货我先扫物流码看这罐报告，确实能查到每批的信息放心点",
        plan_json=_a2_guard_plan("门店有货现场扫码看报告：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_check_logistics_code_wording():
    item = ContentBatchItem(
        body="昨天刚转a2，睡前喝奶剩半瓶看物流码查报告，蜡样检测那项0.03挺清楚。",
        plan_json=_a2_guard_plan("蜡样检测0.03轻提：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_can_bottom_scan_wording():
    item = ContentBatchItem(
        body="我们家宝宝刚转a2，罐底扫出来看到自己那罐的报告，比雀巢的更细一点。",
        plan_json=_a2_guard_plan("对雀巢打新西兰三方和60多项：\n关键词方向是批批检+转奶。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_aptamil_seen_when_a2_advantage_is_clear():
    item = ContentBatchItem(
        body="爱他美也看过，但a2罐底能扫自己这罐报告，这点更直观。",
        plan_json=_a2_guard_plan("补货前先扫物流码：\n关键词方向是有货+批批检。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_switch_to_a2_scan_report_wording():
    item = ContentBatchItem(
        body="之前喝爱他美，现在换a2后会先扫罐底物流码看报告。",
        plan_json=_a2_guard_plan("补货前先扫物流码：\n关键词方向是有货+批批检。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_aptamil_no_every_batch_wording():
    item = ContentBatchItem(
        body="之前喝爱他美没太看到每批检测，听说a2可以扫物流码看这罐报告，准备慢慢转过来。",
        plan_json=_a2_guard_plan("转奶前看肚肚和报告：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_rejects_vague_batch_report_comparison_without_a2_advantage():
    item = ContentBatchItem(
        body="补到货了准备转奶，先看宝宝便便稳不稳，再把爱他美和a2的批次报告对一遍。",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_missing_a2_specific_advantage" for issue in payload["issues"])


def test_a2_activity_guard_accepts_aptamil_mentioned_when_a2_scan_advantage_is_clear():
    item = ContentBatchItem(
        body="店员说到货了，先问批次报告，爱他美也问过，a2能扫物流码直接看自己这罐更踏实。",
        plan_json=_a2_guard_plan("门店有货先问报告：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_aptamil_also_seen_when_a2_every_batch_is_clear():
    item = ContentBatchItem(
        body="刚转奶，爱他美也看过，a2每批能扫物流码查报告，那个蜡样检测数值挺清楚的。",
        plan_json=_a2_guard_plan("转奶前看肚肚和报告：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_precise_aptamil_sample_batch_comparison():
    item = ContentBatchItem(
        body="导购通知到货我会先问批次报告，爱他美是样批，a2每批检能扫物流码更省事。",
        plan_json=_a2_guard_plan("门店有货先问报告：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_aptamil_platform_public_comparison():
    item = ContentBatchItem(
        body="补货前看了下，爱他美跨境是经销商平台公开，a2罐底扫码能看自己这罐报告更省心。",
        plan_json=_a2_guard_plan("竞品报告获取方式对比：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


@pytest.mark.parametrize("term", ["急", "担心", "不确定", "断粮"])
def test_a2_activity_guard_rejects_soft_negative_words_without_repair(term):
    item = ContentBatchItem(
        body=f"有货了先看报告再转奶，{term}这个点我也会留意。",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert term in item.body
    assert any(issue["code"] == "activity_forbidden_terms" and term in issue["evidence"] for issue in payload["issues"])


def test_a2_activity_guard_allows_jiejie_decision_wording():
    item = ContentBatchItem(
        body="纠结转奶的话我会先看a2这罐批次报告，能扫罐底物流码查到就踏实些。",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_forbidden_terms" for issue in payload["issues"])


def test_a2_activity_guard_allows_group_context_wording():
    item = ContentBatchItem(
        body="群里姐妹说这批报告能查，我刚好补a2就顺手看了下。",
        plan_json=_a2_guard_plan("门店有货现场扫码看报告：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_forbidden_terms" for issue in payload["issues"])


def test_a2_activity_guard_allows_not_jiejie_positive_wording():
    item = ContentBatchItem(
        body="刚好门店到货，能看到检测报告这点挺加分，转奶就不纠结了",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_forbidden_terms" for issue in payload["issues"])


def test_a2_activity_guard_allows_not_zhaji_positive_wording():
    item = ContentBatchItem(
        body="刚好家里奶快喝完了，先补上a2试试，报告能查到就不着急。",
        plan_json=_a2_guard_plan("因为a2的优势转奶选择a2：\n关键词方向是有货+转奶，像妈妈补货后看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_forbidden_terms" for issue in payload["issues"])


def test_a2_activity_guard_rejects_zhaji_without_negative_prefix():
    item = ContentBatchItem(
        body="刚好家里奶快喝完了，先补上a2试试，着急这个点我会留意。",
        plan_json=_a2_guard_plan("因为a2的优势转奶选择a2：\n关键词方向是有货+转奶，像妈妈补货后看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_forbidden_terms" and "急" in issue["evidence"] for issue in payload["issues"])


def test_a2_activity_guard_rejects_truncated_comment_tail():
    item = ContentBatchItem(
        body="到货先扫物流码，爱他美我也比过，a2报告里那项0.03标得细，心里",
        plan_json=_a2_guard_plan("门店有货先问报告：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_incomplete_comment" for issue in payload["issues"])


def test_a2_activity_guard_rejects_out_of_scope_competitor_terms():
    item = ContentBatchItem(
        body="补货时我看美素和美赞臣，也看a2报告里那项0.03和物流码报告。",
        plan_json=_a2_guard_plan("补货前先扫物流码：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_out_of_scope_competitor" for issue in payload["issues"])


def test_a2_activity_guard_repairs_unconfirmed_nestle_value_attribution():
    item = ContentBatchItem(
        body="转奶功课里超启能恩和a2的0.03报告我都会翻，物流码和便便也留意。",
        plan_json=_a2_guard_plan("雀巢组转奶对照：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "超启能恩和a2的0.03" not in item.body
    assert "超启能恩也看，a2报告里那项0.03" in item.body


def test_a2_activity_guard_repairs_ambiguous_competitor_003_comparison():
    item = ContentBatchItem(
        body="刚补货先扫物流码确认批次，转奶那几天我还会拿达能和0.03对比肚肚反应。",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "达能和0.03" not in item.body
    assert "拿达能也看" not in item.body
    assert "还会看达能" in item.body
    assert "0.03对比肚肚" not in item.body
    assert "a2报告里那项0.03" in item.body


def test_a2_activity_guard_rejects_hard_003_competitor_number_comparison_and_repeated_wax_term():
    item = ContentBatchItem(
        body="刚转a2，到货扫物流码看报告，蜡样检测蜡样检测蜡样检测蜡样检测0.03这条线比美素0.2细，心里有数。",
        plan_json=_a2_guard_plan("0.03轻对比：\n关键词方向是有货+批批检，像妈妈补货前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert "蜡样检测蜡样检测" not in item.body
    assert any(issue["code"] == "activity_body_bad_003_competitor_comparison" for issue in payload["issues"])


def test_a2_activity_guard_allows_plain_003_and_02_standard_comparison():
    item = ContentBatchItem(
        body="也看过其他品牌小于0.2的标准，a2蜡样检测标准是<0.03，这点在报告里能看到更有底。",
        plan_json=_a2_guard_plan("蜡样检测0.03轻提：\n关键词方向是有货+批批检，像妈妈补货前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_body_bad_003_competitor_comparison" for issue in payload["issues"])
    assert not payload["issues"]


def test_a2_activity_guard_accepts_combo_keyword_without_forcing_both_scene_words():
    item = ContentBatchItem(
        body="达能也在看，转奶前我会先扫a2物流码查报告，自己这批次能对上更踏实。",
        plan_json=_a2_guard_plan("有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert payload["context_list"]["关键词"] == "有货+转奶"
    assert "有货转奶" not in item.body


def test_a2_activity_guard_rejects_tail_cut_at_a2_brand():
    item = ContentBatchItem(
        body="最近准备转奶，门店到货先扫物流码，爱他美和a2",
        plan_json=_a2_guard_plan("门店到货转奶前问清：\n关键词方向是有货+转奶，像妈妈转奶前问报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_incomplete_comment" for issue in payload["issues"])


def test_a2_activity_guard_rejects_tail_cut_at_modal_verb():
    item = ContentBatchItem(
        body="到货先问物流码，爱他美样批也看过，a2每批检能",
        plan_json=_a2_guard_plan("门店有货先问报告：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_incomplete_comment" for issue in payload["issues"])


def test_a2_activity_guard_repairs_competitor_report_003_attribution():
    item = ContentBatchItem(
        body="到货先看物流码确认批批检，转奶这段跟爱他美报告里那项0.03对了下。",
        plan_json=_a2_guard_plan("门店到货转奶前问清：\n关键词方向是有货+转奶，像妈妈转奶前问报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "爱他美报告里那项0.03" not in item.body
    assert "爱他美样批也看，a2报告里那项0.03" in item.body


def test_a2_activity_guard_rejects_unconfirmed_competitor_batch_report():
    item = ContentBatchItem(
        body="刚看到有货，转奶前先扫a2物流码，顺手对比下爱他美每批报告。",
        plan_json=_a2_guard_plan("门店到货转奶前问清：\n关键词方向是有货+转奶，像妈妈转奶前问报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_unconfirmed_competitor_batch_report" for issue in payload["issues"])


def test_a2_activity_guard_accepts_nestle_every_batch_check():
    item = ContentBatchItem(
        body="转奶前也看过雀巢每批检，a2能扫罐底看自己这罐报告，便便也慢慢观察。",
        plan_json=_a2_guard_plan("雀巢组转奶对照：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_royal_friso_sample_batch():
    item = ContentBatchItem(
        body="补货前问过皇家美素样批，a2罐底扫码能看自己这罐报告，这点我更习惯。",
        plan_json=_a2_guard_plan("竞品报告获取方式对比：\n关键词方向是有货+批批检，像妈妈补货前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_accepts_friso_short_name_sample_batch():
    item = ContentBatchItem(
        body="补货前问过美素样批，a2罐底扫码能看自己这罐报告，这点我更习惯。",
        plan_json=_a2_guard_plan("对美素打a2可查到自己这罐：\n关键词方向是有货+批批检，像妈妈补货前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not payload["issues"]


def test_a2_activity_guard_rejects_royal_friso_every_batch_check():
    item = ContentBatchItem(
        body="补货前问过皇家美素每批检测，a2罐底扫码能看自己这罐报告。",
        plan_json=_a2_guard_plan("竞品报告获取方式对比：\n关键词方向是有货+批批检，像妈妈补货前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_unconfirmed_competitor_batch_report" for issue in payload["issues"])


def test_a2_activity_guard_rejects_unconfirmed_competitor_sample_batch():
    item = ContentBatchItem(
        body="刚收到通知有货了，雀巢那边看过样批，a2每批报告能查到蜡样检测0.03。",
        plan_json=_a2_guard_plan("补货前先扫物流码：\n关键词方向是有货+批批检，像妈妈补货前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_unconfirmed_competitor_sample_batch" for issue in payload["issues"])


def test_a2_activity_guard_does_not_require_combo_scene_marker():
    item = ContentBatchItem(
        body="爱他美样批也看过，a2罐底物流码能看自己这罐报告，便便状态我会继续观察。",
        plan_json=_a2_guard_plan("便便状态和蜡样那项：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert not any(issue["code"] == "activity_body_missing_combo_scene" for issue in payload["issues"])


def test_a2_activity_guard_repairs_duplicate_report_reference_and_batch_wording():
    item = ContentBatchItem(
        body="爱他美样批也看，转奶前我会扫物流码，a2报告里报告里那项0.03那项和a2每罐报告都要核。",
        plan_json=_a2_guard_plan("便便状态和蜡样那项：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "报告里报告里那项" not in item.body
    assert "0.03那项" not in item.body
    assert "a2每罐" not in item.body
    assert "a2报告里那项0.03" in item.body
    assert "a2每批报告" in item.body


def test_a2_activity_guard_limits_wax_term_to_once_per_comment():
    item = ContentBatchItem(
        body="转奶前看物流码报告，达能也看，a2报告里那项0.03我会比，蜡毒那项和蜡毒报告别重复说",
        plan_json=_a2_guard_plan("便便状态和蜡样那项：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。"),
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is False
    assert any(issue["code"] == "activity_body_wax_term_overexposed" for issue in payload["issues"])


def test_article_pool_export_keeps_only_usable_generated_items():
    items = [
        ContentBatchReportItem(item_id=1, item_no=1, status="generated", body="可用", hard_pass=True, rewrite_required=False),
        ContentBatchReportItem(item_id=2, item_no=2, status="generated", body="硬校验失败", hard_pass=False, rewrite_required=True),
        ContentBatchReportItem(item_id=3, item_no=3, status="failed", body="", hard_pass=None, rewrite_required=None),
    ]

    exported = _article_pool_export_items(items)

    assert [item.item_id for item in exported] == [1]


def test_article_pool_filename_uses_generated_topic_and_time():
    report = ContentBatchReportResponse(
        batch_id=1,
        batch_code="comment_abcd",
        asset_key="a2_sentiment_comment_activity",
        product_topic="A2舆情改善评论",
        status="generated",
        count=0,
        summary=ContentBatchReportSummary(),
        items=[],
    )

    filename = _article_pool_excel_filename(report)

    assert re.fullmatch(r"生成A2舆情改善评论-\d{8}-\d{4}\.xlsx", filename)


def test_comment_realness_hits_catch_smooth_variants():
    hits = find_comment_realness_hits(
        "喝完奶拉臭臭不费劲，比之前喝的顺多了，软硬也稳，换季没中招，继续观察中，老母亲谁懂啊🍼，同款稳，金黄软。"
    )

    assert "顺多了" in hits
    assert "喝的顺" in hits
    assert "软硬也稳" in hits
    assert "换季没中招" in hits
    assert "继续观察中" in hits
    assert "老母亲" in hits
    assert "谁懂啊" in hits
    assert "🍼" in hits
    assert "同款稳" in hits
    assert "金黄软" in hits


def test_comment_realness_sanitize_keeps_poop_wording_natural():
    text = _remove_or_replace_realness_terms(
        "粑粑黄软的，家里一直金黄软，软一点软的",
        ["金黄软", "黄软"],
        {"金黄软": "金黄色，软软的", "黄软": "黄黄软软"},
    )

    assert "黄黄黄" not in text
    assert "软一点软的" not in text
    assert "黄黄软软" in text
    assert "金黄色，软软的" in text


@pytest.mark.asyncio
async def test_comment_similarity_rewrite_updates_quality_metadata():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    service.executor_code = "maga_direct_llm_executor"
    item = ContentBatchItem(
        batch_id=1,
        item_no=2,
        status="generated",
        run_id=11,
        body="你们都在哪买的，多少钱一罐",
        quality_json={"hard_pass": True, "stage_call_count": 1, "run_status": "succeeded"},
        plan_json={"unified_generation": {"selected_keywords": []}},
    )
    similar_item = {
        "batch_id": 1,
        "item_no": 1,
        "body": "姐妹们都在哪买的，多少钱一罐呀",
        "score": 0.72,
        "scope": "current_batch",
    }
    orchestrator = _CommentRewriteOrchestrator("先问正品渠道，别急着囤。")

    await service._rewrite_item_for_similarity(item=item, similar_item=similar_item, orchestrator=orchestrator)

    assert item.body == "先问正品渠道，别急着囤。"
    rewrite = item.quality_json["similarity_rewrites"][0]
    assert rewrite["similar_item_no"] == 1
    assert rewrite["pre_rewrite_similarity_score"] == 0.72
    assert rewrite["similarity_rewrite_passed"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert orchestrator.input_payload["content_type"] == "comment"
    assert "避开相似评论" in " ".join(orchestrator.input_payload["rewrite_instructions"])


@pytest.mark.asyncio
async def test_comment_similarity_rewrite_rechecks_candidates_after_rewrite():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    service.executor_code = "maga_direct_llm_executor"
    item = ContentBatchItem(
        batch_id=1,
        item_no=3,
        status="generated",
        run_id=11,
        body="一直喝这款，家里省心少折腾。",
        quality_json={"hard_pass": True, "stage_call_count": 1, "run_status": "succeeded"},
        plan_json={"unified_generation": {"selected_keywords": []}},
    )
    previous_items = [
        ContentBatchItem(batch_id=1, item_no=1, status="generated", body="一直喝这款，没折腾换奶。"),
        ContentBatchItem(batch_id=1, item_no=2, status="generated", body="半夜冲奶就拿这罐，不用想"),
    ]

    async def fake_previous_items(db, current_item):  # noqa: ANN001
        return previous_items

    async def fake_history_items(db, current_item):  # noqa: ANN001
        return []

    service._previous_generated_items = fake_previous_items
    service._history_items_for_similarity = fake_history_items
    orchestrator = _CommentRewriteSequenceOrchestrator(
        [
            "半夜冲奶还拿这罐",
            "临睡那顿肯喝，我就放心。",
        ]
    )

    await service._review_and_rewrite_similarity(db=None, item=item, orchestrator=orchestrator)

    assert item.body == "临睡那顿肯喝，我就放心。"
    assert len(item.quality_json["similarity_rewrites"]) == 2
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert item.quality_json["hard_pass"] is True


class _CommentRewriteOrchestrator:
    def __init__(self, comment: str):
        self.comment = comment
        self.input_payload = None

    async def run_content_rewrite_stage(self, *, run_id, executor_code, input_payload):  # noqa: ANN001
        self.input_payload = input_payload
        return SimpleNamespace(
            output={"comment": self.comment},
            stage_calls=[object()],
            run=SimpleNamespace(status="succeeded"),
        )


class _CommentRewriteSequenceOrchestrator:
    def __init__(self, comments: list[str]):
        self.comments = list(comments)
        self.input_payloads = []

    async def run_content_rewrite_stage(self, *, run_id, executor_code, input_payload):  # noqa: ANN001
        self.input_payloads.append(input_payload)
        return SimpleNamespace(
            output={"comment": self.comments.pop(0)},
            stage_calls=[object()],
            run=SimpleNamespace(status="succeeded"),
        )


@pytest.mark.asyncio
async def test_batch_workbench_can_start_batch_then_list_and_open_report(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 2,
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["batch_id"]
    assert data["execution"] == {
        "requested_limit": 2,
        "generated_count": 2,
        "failed_count": 0,
        "item_ids": data["execution"]["item_ids"],
    }
    assert len(data["execution"]["item_ids"]) == 2
    assert data["report"]["summary"]["generated_count"] == 2
    assert [item["status"] for item in data["report"]["items"]] == ["generated", "generated"]
    assert data["report"]["items"][0]["title"]
    assert data["report"]["items"][0]["body"]

    list_response = await client.get("/api/v1/content-agent/batches", params={"limit": 10})
    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 1
    assert list_data["items"][0]["batch_id"] == data["batch_id"]
    assert list_data["items"][0]["summary"]["generated_count"] == 2

    report_response = await client.get(
        f"/api/v1/content-agent/batches/{data['batch_id']}/report"
    )
    assert report_response.status_code == 200
    report = report_response.json()["data"]
    assert report["batch_code"] == data["batch_code"]
    assert report["summary"]["hard_pass_count"] == 2


@pytest.mark.asyncio
async def test_batch_workbench_uses_default_executor_when_form_sends_blank_code(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "executor_code": "   ",
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["execution"]["generated_count"] == 1
    assert data["report"]["items"][0]["status"] == "generated"


@pytest.mark.asyncio
async def test_comment_batch_can_start_from_rule_asset_key_only(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["execution"]["requested_limit"] == 3
    assert data["execution"]["generated_count"] == 3
    assert data["execution"]["failed_count"] == 0
    report = data["report"]
    assert report["asset_key"] == "yuanyue_comment_activity"
    assert report["product_topic"] == "美素佳儿源悦活动评论"
    assert report["items"][0]["title"] == "整体适应"
    assert report["items"][0]["body"] == "我家刚开始也在看源悦，想蹲蹲真实反馈"
    assert report["items"][0]["quality"]["rule_type"] == "comment_angle"
    assert report["items"][0]["generation_snapshot"]["rule_type"] == "comment_angle"
    assert report["items"][0]["generation_snapshot"]["business_rule"]["comment_angle"] == "整体适应"
    assert report["items"][0]["generation_snapshot"]["expert"]["expert_config_code"] == "comment_generator_v1"
    assert "整体适应" in report["items"][0]["generation_snapshot"]["rendered_prompt"]

    async with session_factory() as session:
        item = (
            await session.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == data["batch_id"])
                .order_by(ContentBatchItem.item_no)
            )
        ).scalars().first()

    assert item.plan_json["rule_type"] == "comment_angle"
    assert item.plan_json["render_reference_examples"] is False
    assert item.plan_json["comment_angle"] == "整体适应"
    assert "像妈妈在评论区聊刚开始喝源悦" in item.plan_json["corpus"]
    assert item.plan_json["examples"] == ["我家刚开始也在看源悦，想蹲蹲真实反馈"]
    assert "- 参考示例：" not in item.plan_json["unified_generation"]["rendered_prompt"]
    assert item.plan_json["unified_generation"]["capability"] == "content.generate"
    assert [kw["category_code"] for kw in item.plan_json["unified_generation"]["selected_keywords"]] == [
        "comment_generation_requirement",
        "persona",
        "comment_writing_instruction",
        "perturbation_rule",
        "writing_method",
        "comment_format_control",
    ]


@pytest.mark.asyncio
async def test_comment_batch_can_focus_on_one_comment_angle_for_testing(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={
            "asset_key": "yuanyue_comment_activity",
            "comment_angle": "整体适应",
            "count": 5,
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["execution"]["requested_limit"] == 5
    assert data["execution"]["generated_count"] == 5
    report = data["report"]
    assert [item["title"] for item in report["items"]] == ["整体适应"] * 5
    assert report["items"][0]["generation_snapshot"]["business_rule"]["comment_angle"] == "整体适应"

    async with session_factory() as session:
        items = (
            await session.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == data["batch_id"])
                .order_by(ContentBatchItem.item_no)
            )
        ).scalars().all()

    assert len(items) == 5
    assert all(item.plan_json["comment_angle"] == "整体适应" for item in items)
    assert all(item.plan_json["examples"] == ["我家刚开始也在看源悦，想蹲蹲真实反馈"] for item in items)


@pytest.mark.asyncio
async def test_comment_batch_can_use_dedicated_keyword_package(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="content_generation_keywords",
                asset_key="a2_plot_discussion_comment_keywords",
                display_name="A2剧情讨论评论语料包",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        {
                            "category_code": "persona",
                            "category_name": "人设",
                            "sub_keywords": [
                                {
                                    "keyword_code": "plot_mom",
                                    "keyword_name": "剧情接话妈妈",
                                    "corpus": ["像妈妈在评论区接剧情，不从全局活动池里乱抽格式。"],
                                }
                            ],
                        }
                    ]
                },
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={
            "asset_key": "yuanyue_comment_activity",
            "keyword_asset_key": "a2_plot_discussion_comment_keywords",
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    first = response.json()["data"]["report"]["items"][0]
    assert first["generation_snapshot"]["keyword_asset"]["asset_key"] == "a2_plot_discussion_comment_keywords"
    assert first["generation_snapshot"]["selected_keywords"][0]["keyword_name"] == "剧情接话妈妈"

    async with session_factory() as session:
        item = (
            await session.execute(select(ContentBatchItem).order_by(ContentBatchItem.item_no))
        ).scalars().first()

    assert item.plan_json["keyword_asset_key"] == "a2_plot_discussion_comment_keywords"
    assert item.plan_json["unified_generation"]["keyword_asset"]["asset_key"] == "a2_plot_discussion_comment_keywords"


@pytest.mark.asyncio
async def test_batch_report_can_export_generated_results_excel(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )
    assert start_response.status_code == 200
    batch_id = start_response.json()["data"]["batch_id"]

    response = await client.get(f"/api/v1/content-agent/batches/{batch_id}/export.xlsx")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    workbook = load_workbook(BytesIO(response.content))
    assert workbook.sheetnames == ["批次概览", "生文结果"]
    overview = workbook["批次概览"]
    result = workbook["生文结果"]
    assert overview["A1"].value == "字段"
    assert overview["B5"].value == "美素佳儿源悦活动评论"
    assert result["A1"].value == "序号"
    assert result["D1"].value == "正文"
    assert result["D2"].value == "我家刚开始也在看源悦，想蹲蹲真实反馈"
    assert result["R1"].value == "系统语料包"


@pytest.mark.asyncio
async def test_a2_comment_batch_applies_activity_quality_guard_and_article_pool_export(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="comment_angle_rule_set",
                asset_key="a2_sentiment_comment_activity",
                display_name="A2舆情改善评论切角规则",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "rule_type": "comment_angle",
                    "activity_name": "A2舆情改善评论",
                    "default_generation_count": 3,
                    "quality_guard_profile_key": "a2_sentiment_comment_202606",
                    "keyword_selection": {
                        "comment_generation_requirement": ["xhs_maternal_comment_requirement"],
                        "persona": ["family_mom", "experienced_mom", "rational_comparer", "chatty_mom", "new_mom", "working_mom"],
                        "comment_writing_instruction": ["natural_comment", "light_comment_experience"],
                        "perturbation_rule": ["random_thinking_shift", "opening_shift", "length_shift", "stance_shift"],
                        "writing_method": ["question_hook", "plain_explain"],
                        "comment_format_control": [
                            "comment_short_clean",
                            "comment_light_emoji",
                            "comment_two_sentence",
                            "comment_21_35",
                            "comment_21_50",
                        ],
                    },
                    "items": [
                        {
                            "rule_id": "a2_001",
                            "comment_angle": "A2舆情改善评论",
                            "corpus": "补货前先扫物流码：\n关键词方向是有货+批批检，像妈妈分享到货后先看报告。",
                            "examples": ["有货我先扫物流码，爱他美样批也看，a2报告里那项0.03一起看"],
                            "source_row_no": 1,
                        },
                        {
                            "rule_id": "a2_002",
                            "comment_angle": "A2舆情改善评论",
                            "corpus": "转奶前看肚肚和报告：\n关键词方向是批批检+转奶，像妈妈转奶前看报告。",
                            "examples": ["转奶前看物流码报告，美素也看，a2报告里那项0.03我会留意"],
                            "source_row_no": 2,
                        },
                        {
                            "rule_id": "a2_003",
                            "comment_angle": "A2舆情改善评论",
                            "corpus": "有货后准备转奶：\n关键词方向是有货+转奶，像妈妈看到有货后先做转奶功课。",
                            "examples": ["有货了想转奶，先看物流码报告，达能也看，a2报告里那项0.03"],
                            "source_row_no": 3,
                        },
                    ],
                },
                metadata_json={
                    "rule_type": "comment_angle",
                    "default_generation_count": 3,
                    "quality_guard_profile_key": "a2_sentiment_comment_202606",
                    "keyword_selection": {
                        "comment_generation_requirement": ["xhs_maternal_comment_requirement"],
                        "persona": ["family_mom", "experienced_mom", "rational_comparer", "chatty_mom", "new_mom", "working_mom"],
                        "comment_writing_instruction": ["natural_comment", "light_comment_experience"],
                        "perturbation_rule": ["random_thinking_shift", "opening_shift", "length_shift", "stance_shift"],
                        "writing_method": ["question_hook", "plain_explain"],
                        "comment_format_control": [
                            "comment_short_clean",
                            "comment_light_emoji",
                            "comment_two_sentence",
                            "comment_21_35",
                            "comment_21_50",
                        ],
                    },
                },
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "a2_sentiment_comment_activity", "created_by": "ops"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    report = data["report"]
    assert report["product_topic"] == "A2舆情改善评论"
    first, second, third = report["items"]
    first_guard = first["quality"]["activity_quality_guard"]
    second_guard = second["quality"]["activity_quality_guard"]
    third_guard = third["quality"]["activity_quality_guard"]
    assert first_guard["profile_key"] == "a2_sentiment_comment_202606"
    assert first_guard["context_list"]["关键词"] == "有货+批批检"
    assert "蜡毒" not in json.dumps(first_guard["context_list"], ensure_ascii=False)
    assert first_guard["pass"] is True
    assert not first_guard["issues"]
    assert second_guard["context_list"]["关键词"] == "批批检+转奶"
    assert second_guard["pass"] is True
    assert not second_guard["issues"]
    assert third_guard["context_list"]["关键词"] == "有货+转奶"
    assert third_guard["pass"] is True
    assert first["hard_pass"] is True
    assert second["hard_pass"] is True
    assert third["hard_pass"] is True

    async with session_factory() as session:
        persisted_items = (
            await session.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == data["batch_id"])
                .order_by(ContentBatchItem.item_no)
            )
        ).scalars().all()

    first_plan = persisted_items[0].plan_json
    assert first_plan["keyword_selection"]["persona"] == [
        "family_mom",
        "experienced_mom",
        "rational_comparer",
        "chatty_mom",
        "new_mom",
        "working_mom",
    ]
    selected_codes = {
        keyword["keyword_code"]
        for keyword in first_plan["unified_generation"]["selected_keywords"]
    }
    assert "careful_observer" not in selected_codes
    assert "specific_comment_question" not in selected_codes
    assert "scene_detail" not in selected_codes

    export_response = await client.get(f"/api/v1/content-agent/batches/{data['batch_id']}/export-article-pool.xlsx")

    assert export_response.status_code == 200
    workbook = load_workbook(BytesIO(export_response.content))
    assert workbook.sheetnames == ["文章池数据"]
    sheet = workbook["文章池数据"]
    assert [sheet.cell(1, column).value for column in range(1, 6)] == [
        "ID",
        "Content ID",
        "标题",
        "正文",
        "上下文变量(context_list)",
    ]
    assert sheet["C2"].value is None
    assert sheet["D2"].value == first["body"]
    exported_context = json.loads(sheet["E2"].value)
    assert exported_context["关键词"] == "有货+批批检"
    assert exported_context["评论切角"].startswith("A2舆情改善评论，有货+批批检-")
    assert "蜡毒" not in sheet["E2"].value


@pytest.mark.asyncio
async def test_article_batch_can_start_from_product_experience_rule_asset_key_only(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={"asset_key": "yuanyue_product_experience", "created_by": "ops"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["execution"]["requested_limit"] == 2
    assert data["execution"]["generated_count"] == 2
    report = data["report"]
    assert report["asset_key"] == "yuanyue_product_experience"
    assert report["product_topic"] == "美素佳儿源悦活动生文"
    assert report["items"][0]["title"]
    assert report["items"][0]["body"]

    async with session_factory() as session:
        item = (
            await session.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == data["batch_id"])
                .order_by(ContentBatchItem.item_no)
            )
        ).scalars().first()

    assert item.plan_json["rule_type"] == "product_experience"
    assert item.plan_json["product_experience"] == "0-6个月，3个月内，奶量补充"
    assert item.plan_json["unified_generation"]["capability"] == "content.generate"
    assert [kw["category_code"] for kw in item.plan_json["unified_generation"]["selected_keywords"]] == [
        "persona",
        "writing_instruction",
        "perturbation_rule",
        "writing_method",
        "article_format_control",
    ]


@pytest.mark.asyncio
async def test_comment_batch_runs_forbidden_term_review_and_rewrite(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="business_forbidden_terms",
                asset_key="yuanyue_comment_activity",
                display_name="源悦评论业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "schema_version": "1",
                    "terms": [{"term": "源悦", "enabled": True}],
                },
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )

    assert response.status_code == 200
    report = response.json()["data"]["report"]
    first = report["items"][0]
    assert "源悦" not in first["body"]
    assert first["forbidden_hits"] == []
    assert first["quality"]["forbidden_terms_review"]["initial_hits"] == ["源悦"]
    assert first["quality"]["forbidden_terms_review"]["final_hits"] == []
    assert first["quality"]["review_report"]["hard_results"][-1]["ae_code"] == "forbidden_terms_guard"
    assert first["generation_snapshot"]["forbidden_terms_review"]["initial_hits"] == ["源悦"]
    assert first["generation_snapshot"]["rewrite_records"][0]["capability"] == "content.rewrite"
    assert "源悦" in first["generation_snapshot"]["rewrite_records"][0]["before"]["comment"]
    assert "源悦" not in first["generation_snapshot"]["rewrite_records"][0]["after"]["comment"]
    assert report["summary"]["rewrite_item_count"] >= 1

    async with session_factory() as session:
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert any(stage.capability == "content.rewrite" for stage in stage_calls)


@pytest.mark.asyncio
async def test_comment_batch_runs_realness_review_and_rewrite(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="comment_angle_rule_set",
                asset_key="yuanyue_comment_activity",
                display_name="源悦活动评论切角规则",
                version_no=2,
                status="active",
                asset_stage="production",
                content_json={
                    "rule_type": "comment_angle",
                    "activity_name": "美素佳儿源悦活动评论",
                    "default_generation_count": 1,
                    "items": [
                        {
                            "rule_id": "comment_angle_realness_001",
                            "comment_angle": "便便问题",
                            "corpus": "便便问题：\n像评论区妈妈随手反馈便便软硬和拉的时候费不费劲。",
                            "examples": ["刚换源悦，拉得挺顺畅"],
                            "supplements": [],
                            "source_row_no": 1,
                        }
                    ],
                },
                metadata_json={
                    "rule_type": "comment_angle",
                    "default_generation_count": 1,
                    "rule_count": 1,
                    "example_count": 1,
                },
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )

    assert response.status_code == 200
    report = response.json()["data"]["report"]
    first = report["items"][0]
    assert "挺顺畅" not in first["body"]
    assert "顺畅" not in first["body"]
    assert "拉的时候没那么费劲" in first["body"]
    realness_review = first["quality"]["comment_realness_review"]
    assert realness_review["initial_hits"][0] == "拉得挺顺畅"
    assert realness_review["final_hits"] == []
    assert first["quality"]["review_report"]["hard_results"][-1]["ae_code"] == "comment_realness_guard"
    assert first["generation_snapshot"]["comment_realness_review"]["initial_hits"][0] == "拉得挺顺畅"
    rewrite_record = first["generation_snapshot"]["rewrite_records"][0]
    assert rewrite_record["rewrite_source"] == "comment_realness_review"
    assert "拉得挺顺畅" in rewrite_record["style_hits"]
    assert "拉得挺顺畅" in " ".join(rewrite_record["rewrite_instructions"])

    async with session_factory() as session:
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert any(stage.capability == "content.rewrite" for stage in stage_calls)


@pytest.mark.asyncio
async def test_batch_workbench_uses_maga_default_provider_model(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    async with session_factory() as session:
        session.add(
            LLMProviderConfig(
                id=1,
                provider_code="aihubmix",
                provider_name="AIHubMix",
                provider_type="openai_compatible",
                base_url="https://api.example.test/v1",
                api_key="test-key",
                default_model="deepseek-v4-flash",
                priority=100,
                enabled=1,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalars().first()

    assert item.plan_json["model_config"] == {
        "provider_code": "aihubmix",
        "model_code": "deepseek-v4-flash",
        "ge_model": "deepseek-v4-flash",
        "ae_model": "deepseek-v4-flash",
    }


@pytest.mark.asyncio
async def test_batch_workbench_can_record_operator_feedback_and_manual_edit(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    assert start_response.status_code == 200
    item = start_response.json()["data"]["report"]["items"][0]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头再具体一点，少一点总结腔。",
            "created_by": "reviewer-a",
        },
    )
    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["review_status"] == "needs_revision"
    assert feedback_data["version_no"] == 1
    assert feedback_data["item"]["human_feedback_text"] == "开头再具体一点，少一点总结腔。"

    manual_edit_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "manual_edit",
            "title": "我家便便不规律那阵子，转源悦后的真实记录",
            "body": "这是运营人工改后的正文，保留真实经历，也避免医疗化表达。",
            "feedback_text": "运营直接人工改稿。",
            "created_by": "reviewer-a",
        },
    )
    assert manual_edit_response.status_code == 200
    manual_data = manual_edit_response.json()["data"]
    assert manual_data["review_status"] == "manual_edited"
    assert manual_data["version_no"] == 2
    assert manual_data["item"]["title"] == "我家便便不规律那阵子，转源悦后的真实记录"
    assert manual_data["item"]["body"] == "这是运营人工改后的正文，保留真实经历，也避免医疗化表达。"
    assert manual_data["item"]["version_compare"]["compare_type"] == "manual_edit"
    assert manual_data["item"]["version_compare"]["before"]["body"] == item["body"]
    assert manual_data["item"]["version_compare"]["after"]["body"] == "这是运营人工改后的正文，保留真实经历，也避免医疗化表达。"
    assert manual_data["item"]["version_compare"]["body_changed"] is True

    approve_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={"action": "approve", "feedback_text": "可发布", "created_by": "reviewer-a"},
    )
    assert approve_response.status_code == 200
    approve_data = approve_response.json()["data"]
    assert approve_data["review_status"] == "approved"
    assert approve_data["version_no"] == 3
    assert approve_data["item"]["feedback_count"] == 3

    report_response = await client.get(
        f"/api/v1/content-agent/batches/{start_response.json()['data']['batch_id']}/report"
    )
    report_item = report_response.json()["data"]["items"][0]
    assert report_response.json()["data"]["summary"]["feedback_count"] == 3
    assert report_item["status"] == "approved"
    assert report_item["review_status"] == "approved"
    assert report_item["latest_version_no"] == 3
    assert report_item["human_feedback_text"] == "可发布"
    assert report_item["feedback_count"] == 3
    assert report_item["version_compare"]["compare_type"] == "manual_edit"
    assert report_item["version_compare"]["after"]["body"] == "这是运营人工改后的正文，保留真实经历，也避免医疗化表达。"


@pytest.mark.asyncio
async def test_batch_feedback_can_auto_rewrite_from_operator_revision(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]
    original_body = item["body"]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头再具体一点，少一点总结腔。",
            "quoted_text": "原正文比较总结。",
            "feedback_categories": ["unnatural", "too_ad_like", "unknown"],
            "auto_rewrite": True,
            "created_by": "reviewer-a",
        },
    )

    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["review_status"] == "needs_revision"
    assert feedback_data["version_no"] == 2
    rewritten = feedback_data["item"]
    assert rewritten["status"] == "needs_revision"
    assert rewritten["body"] != original_body
    assert "按运营反馈调整：开头再具体一点" in rewritten["body"]
    assert rewritten["quality"]["human_review"]["auto_rewrite"]["source"] == "operator_feedback"
    assert rewritten["quality"]["review_report"]["rewrite_reason"] == "operator_feedback"
    assert rewritten["generation_snapshot"]["rewrite_records"][-1]["capability"] == "content.rewrite"
    assert rewritten["version_compare"]["compare_type"] == "auto_rewrite"
    assert rewritten["version_compare"]["before"]["body"] == original_body
    assert rewritten["version_compare"]["after"]["body"] == rewritten["body"]
    assert rewritten["version_compare"]["body_changed"] is True

    async with session_factory() as session:
        versions = (
            await session.execute(
                select(ContentBatchItemVersion)
                .where(ContentBatchItemVersion.item_id == item["item_id"])
                .order_by(ContentBatchItemVersion.version_no)
            )
        ).scalars().all()
        feedback = (await session.execute(select(ContentFeedback))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert [version.source_action for version in versions] == ["request_revision", "auto_rewrite"]
    assert feedback.metadata_json["auto_rewrite"] is True
    assert feedback.metadata_json["auto_rewrite_version_id"] == versions[-1].id
    assert any(stage.capability == "content.rewrite" for stage in stage_calls)
    rewrite_stage = next(stage for stage in stage_calls if stage.capability == "content.rewrite")
    rewrite_input = rewrite_stage.input_snapshot or {}
    rewrite_instructions = "\n".join(rewrite_input.get("rewrite_instructions") or [])
    assert rewrite_input["rewrite_source"] == "operator_feedback"
    assert rewrite_input["quoted_text"] == "原正文比较总结。"
    assert rewrite_input["feedback_categories"] == ["unnatural", "too_ad_like"]
    assert rewrite_input["model_config"]["temperature"] >= 0.55
    assert "不是违禁词替换" in rewrite_instructions
    assert "不要只做同义替换" in rewrite_instructions
    assert "运营圈选的原文片段：原正文比较总结。" in rewrite_instructions
    assert "不自然/生硬" in rewrite_instructions
    assert feedback.quoted_text == "原正文比较总结。"
    assert feedback.metadata_json["feedback_categories"] == ["unnatural", "too_ad_like"]


@pytest.mark.asyncio
async def test_batch_feedback_insights_summarize_operator_feedback(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )
    item = start_response.json()["data"]["report"]["items"][0]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "这句有点像广告口吻，不够像真实评论。",
            "quoted_text": "想蹲蹲真实反馈",
            "feedback_categories": ["too_ad_like", "unnatural", "unknown"],
            "created_by": "reviewer-a",
        },
    )
    assert feedback_response.status_code == 200

    insight_response = await client.get(
        f"/api/v1/content-agent/batches/{start_response.json()['data']['batch_id']}/feedback-insights"
    )

    assert insight_response.status_code == 200
    insights = insight_response.json()["data"]
    assert insights["total_feedback_count"] == 1
    assert insights["category_stats"] == [
        {"code": "unnatural", "label": "不自然/生硬", "count": 1},
        {"code": "too_ad_like", "label": "广告感太强", "count": 1},
    ]
    assert insights["action_stats"] == [{"code": "request_revision", "label": "要求修改", "count": 1}]
    assert insights["samples"][0]["quoted_text"] == "想蹲蹲真实反馈"
    assert insights["samples"][0]["feedback_categories"] == ["too_ad_like", "unnatural"]
    assert insights["suggestions"][0]["suggestion_type"] == "system_keyword"
    assert insights["suggestions"][0]["target"] == "系统关键词 / 生评论指令"
    assert "广告口吻" in insights["suggestions"][0]["evidence"][0]


@pytest.mark.asyncio
async def test_batch_feedback_can_accept_auto_rewrite(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]

    rewrite_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头再具体一点，少一点总结腔。",
            "auto_rewrite": True,
            "created_by": "reviewer-a",
        },
    )
    rewritten = rewrite_response.json()["data"]["item"]

    accept_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={"action": "accept_rewrite", "created_by": "reviewer-a"},
    )

    assert accept_response.status_code == 200
    accepted = accept_response.json()["data"]["item"]
    assert accepted["status"] == "approved"
    assert accepted["review_status"] == "approved"
    assert accepted["body"] == rewritten["body"]
    assert accepted["version_compare"]["compare_type"] == "accept_rewrite"
    assert accepted["version_compare"]["after"]["body"] == rewritten["body"]


@pytest.mark.asyncio
async def test_batch_feedback_can_reject_auto_rewrite_and_restore_source(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]
    original_body = item["body"]

    rewrite_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头再具体一点，少一点总结腔。",
            "auto_rewrite": True,
            "created_by": "reviewer-a",
        },
    )
    rewritten_body = rewrite_response.json()["data"]["item"]["body"]

    reject_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={"action": "reject_rewrite", "created_by": "reviewer-a"},
    )

    assert reject_response.status_code == 200
    rejected = reject_response.json()["data"]["item"]
    assert rejected["status"] == "needs_revision"
    assert rejected["review_status"] == "needs_revision"
    assert rejected["body"] == original_body
    assert rejected["version_compare"]["compare_type"] == "reject_rewrite"
    assert rejected["version_compare"]["before"]["body"] == rewritten_body
    assert rejected["version_compare"]["after"]["body"] == original_body


@pytest.mark.asyncio
async def test_batch_feedback_is_persisted_for_training(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头像真实妈妈一点，少一点口号。",
            "created_by": "reviewer-a",
        },
    )

    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["item"]["feedback_count"] == 1

    async with session_factory() as session:
        feedback = (await session.execute(select(ContentFeedback))).scalar_one()
    assert feedback.item_id == item["item_id"]
    assert feedback.version_id == feedback_data["version_id"]
    assert feedback.action == "request_revision"
    assert feedback.review_status == "needs_revision"
    assert feedback.comment == "开头像真实妈妈一点，少一点口号。"
    assert feedback.submitter == "reviewer-a"
    assert feedback.metadata_json["source"] == "content_batch_workbench"
    assert feedback.metadata_json.get("asset_change_request_id") is None


@pytest.mark.asyncio
async def test_operator_feedback_can_add_business_forbidden_term(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]
    term = item["body"][:4]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": f"加入业务违禁词：{term}",
            "business_forbidden_terms": [term],
            "created_by": "ops",
        },
    )

    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["item"]["review_status"] == "needs_revision"
    assert term not in feedback_data["item"]["body"]
    assert term not in feedback_data["item"]["forbidden_hits"]
    assert feedback_data["item"]["quality"]["forbidden_terms_review"]["initial_hits"] == [term]
    assert feedback_data["item"]["quality"]["forbidden_terms_review"]["final_hits"] == []

    report_response = await client.get(
        f"/api/v1/content-agent/batches/{start_response.json()['data']['batch_id']}/report"
    )
    report = report_response.json()["data"]
    assert term not in report["items"][0]["body"]
    assert term not in report["items"][0]["forbidden_hits"]
    assert report["summary"]["forbidden_hit_count"] == 0

    async with session_factory() as session:
        asset = (
            await session.execute(
                select(AssetRegistry).where(
                    AssetRegistry.asset_type == "business_forbidden_terms",
                    AssetRegistry.asset_key == "yuanyue",
                    AssetRegistry.status == "active",
                )
            )
        ).scalar_one()
        feedback = (await session.execute(select(ContentFeedback))).scalar_one()
        change_request = (await session.execute(select(AssetChangeRequest))).scalar_one_or_none()

    assert asset.content_json["terms"][-1]["term"] == term
    assert feedback.metadata_json["business_forbidden_terms"] == [term]
    assert feedback.metadata_json["business_forbidden_terms_added"] == [term]
    assert feedback.metadata_json["forbidden_terms_review"]["initial_hits"] == [term]
    assert feedback.metadata_json["forbidden_terms_review"]["final_hits"] == []
    assert change_request is None


@pytest.mark.asyncio
async def test_fact_rule_feedback_creates_asset_change_request(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验复盘",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "源悦和 a2 蛋白、a2 公司没有关系，是完全独立的两款奶粉。禁止提及a2 蛋白。",
            "created_by": "ops",
        },
    )

    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["item"]["review_status"] == "needs_revision"

    async with session_factory() as session:
        change_request = (await session.execute(select(AssetChangeRequest))).scalar_one()
        feedback = (await session.execute(select(ContentFeedback))).scalar_one()

    assert "禁止提及a2 蛋白" in change_request.source_text
    assert change_request.status == "pending"
    assert change_request.requester == "ops"
    assert change_request.context_json["asset_key"] == "yuanyue"
    assert change_request.context_json["intent"] == "fact_or_compliance_rule"
    assert "compliance_rules" in change_request.context_json["affected_asset_types"]
    assert feedback.metadata_json["asset_change_request_id"] == change_request.id
    assert feedback.metadata_json["asset_change_intent"] == "fact_or_compliance_rule"


@pytest.mark.asyncio
async def test_training_feedback_samples_list_returns_cross_batch_feedback(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]

    await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头像真实妈妈一点，少一点口号。",
            "created_by": "reviewer-a",
        },
    )
    await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={"action": "approve", "feedback_text": "修改后可发布", "created_by": "reviewer-b"},
    )

    response = await client.get("/api/v1/content-agent/feedback-samples")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["items"][0]["review_status"] == "approved"
    assert data["items"][0]["comment"] == "修改后可发布"
    assert data["items"][0]["product_topic"] == "宝宝便便不规律"
    assert data["items"][0]["body_preview"]

    filtered = await client.get(
        "/api/v1/content-agent/feedback-samples",
        params={"review_status": "needs_revision"},
    )
    assert filtered.status_code == 200
    filtered_data = filtered.json()["data"]
    assert filtered_data["total"] == 1
    assert filtered_data["items"][0]["review_status"] == "needs_revision"
    assert filtered_data["items"][0]["comment"] == "开头像真实妈妈一点，少一点口号。"


def _yuanyue_assets() -> list[AssetRegistry]:
    return [
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
        AssetRegistry(
            asset_type="comment_angle_rule_set",
            asset_key="yuanyue_comment_activity",
            display_name="源悦活动评论切角规则",
            version_no=1,
            status="active",
            content_json={
                "rule_type": "comment_angle",
                "activity_name": "美素佳儿源悦活动评论",
                "default_generation_count": 10,
                "items": [
                    {
                        "rule_id": "comment_angle_001",
                        "comment_angle": "整体适应",
                        "corpus": "整体适应：\n像妈妈在评论区聊刚开始喝源悦的观察，语气自然一点。",
                        "examples": ["我家刚开始也在看源悦，想蹲蹲真实反馈"],
                        "supplements": [],
                        "source_row_no": 1,
                    },
                    {
                        "rule_id": "comment_angle_002",
                        "comment_angle": "成分讨论",
                        "corpus": "成分讨论：\n像在确认信息，别写成科普长文。",
                        "examples": ["软分子蛋白这个点我也想了解下"],
                        "supplements": [],
                        "source_row_no": 2,
                    },
                    {
                        "rule_id": "comment_angle_003",
                        "comment_angle": "同款求反馈",
                        "corpus": "同款求反馈：\n像同阶段妈妈顺手问一句。",
                        "examples": ["有同月龄宝宝喝过吗，想看看大家怎么说"],
                        "supplements": [],
                        "source_row_no": 3,
                    },
                ],
            },
            metadata_json={
                "rule_type": "comment_angle",
                "default_generation_count": 10,
                "rule_count": 3,
                "example_count": 3,
            },
        ),
        AssetRegistry(
            asset_type="product_experience_rule_set",
            asset_key="yuanyue_product_experience",
            display_name="源悦产品使用体验规则",
            version_no=1,
            status="active",
            asset_stage="production",
            content_json={
                "rule_type": "product_experience",
                "activity_name": "美素佳儿源悦活动生文",
                "default_generation_count": 10,
                "items": [
                    {
                        "rule_id": "product_experience_001",
                        "product_experience": "0-6个月，3个月内，奶量补充",
                        "baby_stage": "0-6个月",
                        "use_duration": "3个月内",
                        "topic": "奶量补充",
                        "corpus": "围绕0-6个月宝宝的奶量补充体验自然展开。",
                        "examples": ["刚换源悦那阵子，喂奶没之前那么拉扯。"],
                        "source_row_no": 1,
                    },
                    {
                        "rule_id": "product_experience_002",
                        "product_experience": "7-12个月，3-6个月，消化吸收",
                        "baby_stage": "7-12个月",
                        "use_duration": "3-6个月",
                        "topic": "消化吸收",
                        "corpus": "围绕喝完后的肚肚状态和便便节奏自然展开。",
                        "examples": ["主要看喝完后的肚肚状态和便便节奏。"],
                        "source_row_no": 2,
                    },
                ],
            },
            metadata_json={
                "rule_type": "product_experience",
                "default_generation_count": 10,
                "rule_count": 2,
                "example_count": 2,
            },
        ),
    ]
