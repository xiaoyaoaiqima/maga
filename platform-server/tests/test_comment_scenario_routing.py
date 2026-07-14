from types import SimpleNamespace

import pytest

from app.models.content_agent import ContentBatchItem
from app.schemas.content_batch_report import ContentCommentBatchStartRequest
from app.services.activity_quality_guard_service import (
    ActivityQualityGuardService,
    resolve_quality_guard_profile,
)
from app.services.content_comment_batch_service import (
    ContentCommentBatchService,
    _comment_plan_output_count,
    _comment_scenario_from_asset,
    _keyword_selection_with_rule_overrides,
    _rule_with_comment_scenario,
    _weighted_comment_scenario_allocations,
)
from app.services.unified_content_generation_service import _comment_prompt_text


def _scenario() -> dict:
    return {
        "scenario_code": "news_kol_interpretation",
        "scenario_name": "新闻/KOL解读类笔记",
        "sentiment_mix": {"positive": 80, "neutral": 20},
        "interaction_reply_ratio": 0.1,
        "style_hint": "像普通妈妈看完解读后顺手评论。",
        "directions": [
            {
                "direction_code": "batch_check_positive",
                "direction_name": "批批检正向",
                "weight": 25,
                "sentiment": "positive",
                "guard_keyword": "有货+批批检",
                "rule_ids": ["r1"],
                "post_context": "你正在小红书母婴评论区，回复一篇解读a2检测信息的帖子。",
                "prompt_hint": "说一个自己看到的报告信息。",
                "examples": ["我刚扫了下，报告真能看到"],
            },
            {
                "direction_code": "in_stock_positive",
                "direction_name": "恢复供货",
                "weight": 20,
                "sentiment": "positive",
                "rule_ids": ["r2"],
            },
            {
                "direction_code": "process_positive",
                "direction_name": "工艺认可",
                "weight": 15,
                "sentiment": "positive",
                "rule_ids": ["r3"],
            },
            {
                "direction_code": "continue_positive",
                "direction_name": "继续熟悉款",
                "weight": 10,
                "sentiment": "positive",
                "rule_ids": ["r4"],
            },
            {
                "direction_code": "interaction_reply",
                "direction_name": "互动盖楼",
                "weight": 10,
                "sentiment": "positive",
                "interaction_reply": True,
                "rule_ids": ["r5"],
            },
            {
                "direction_code": "neutral_transparency",
                "direction_name": "透明度中立观望",
                "weight": 10,
                "sentiment": "neutral",
                "rule_ids": ["r6"],
            },
            {
                "direction_code": "neutral_market",
                "direction_name": "业绩少量讨论",
                "weight": 10,
                "sentiment": "neutral",
                "rule_ids": ["r7"],
            },
        ],
    }


def _rules() -> list[dict]:
    return [
        {
            "asset_key": "a2_sentiment_comment_activity",
            "rule_id": f"r{index}",
            "business_rule": f"测试-方向{index}",
            "corpus": f"方向{index}语料",
            "examples": [f"方向{index}示例"],
            "source_row_no": index,
        }
        for index in range(1, 8)
    ]


def test_comment_batch_request_accepts_scenario_code():
    request = ContentCommentBatchStartRequest(scenario_code="crm_ec_regular")

    assert request.scenario_code == "crm_ec_regular"


def test_news_scenario_allocation_keeps_80_20_and_ten_percent_reply_for_ten_items():
    directions = _scenario()["directions"]

    allocations = _weighted_comment_scenario_allocations(directions, 10)

    positive = sum(
        count for direction, count in zip(directions, allocations) if direction["sentiment"] == "positive"
    )
    neutral = sum(
        count for direction, count in zip(directions, allocations) if direction["sentiment"] == "neutral"
    )
    replies = sum(
        count for direction, count in zip(directions, allocations) if direction.get("interaction_reply")
    )
    assert (positive, neutral, replies) == (8, 2, 1)


def test_scenario_selection_adds_direction_prompt_and_uses_scenario_examples():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    scenario = _scenario()

    selected, mode = service._select_rules_for_scenario(_rules(), scenario, 10)

    assert mode == "scenario_weighted"
    assert len(selected) == 10
    assert sum(rule["scenario_sentiment"] == "positive" for rule in selected) == 8
    assert sum(rule["scenario_sentiment"] == "neutral" for rule in selected) == 2
    assert sum(rule["scenario_interaction_reply"] for rule in selected) == 1
    batch_rule = next(rule for rule in selected if rule["scenario_direction"] == "batch_check_positive")
    assert batch_rule["scenario_examples"] == ["我刚扫了下，报告真能看到"]
    assert batch_rule["scenario_guard_keyword"] == "有货+批批检"
    assert batch_rule["scenario_post_context"] == "你正在小红书母婴评论区，回复一篇解读a2检测信息的帖子。"
    assert batch_rule["scenario_generation_requirements"] == "像普通妈妈看完解读后顺手评论。"
    assert "批批检正向" not in batch_rule["scenario_generation_requirements"]


def test_scenario_examples_do_not_replace_rule_examples():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rule = {
        "business_rule": "会员权益-集罐换礼",
        "corpus": "集罐换奶粉",
        "examples": ["a2集罐换奶粉，我先留空罐。", "导购提醒我集罐能换奶粉。"],
        "scenario_examples": ["积分抽奖和礼品都可以看看。"],
    }

    selected, meta = service._selected_prompt_examples(rule)

    assert set(selected).issubset(set(rule["examples"]))
    assert meta["selected_example_source"] == "examples"


def test_scenario_prompt_only_carries_context_and_style_not_direction_facts():
    scenario = _scenario()
    direction = scenario["directions"][0]
    rule = _rules()[0]

    merged = _rule_with_comment_scenario(rule, scenario, direction)

    assert merged["scenario_generation_requirements"] == "像普通妈妈看完解读后顺手评论。"
    assert "说一个自己看到的报告信息" not in merged["scenario_generation_requirements"]
    assert "批批检正向" not in merged["scenario_generation_requirements"]


def test_same_a2_rule_can_render_different_source_post_contexts():
    rule = {
        "asset_key": "a2_sentiment_comment_activity",
        "business_rule": "有货-直给到货情绪",
        "corpus": "像刷到a2到货后的一句自然接话。",
        "examples": ["a2终于到货了，我去看看"],
    }
    news_scenario = {
        "scenario_code": "news_kol_interpretation",
        "scenario_name": "新闻/KOL解读类笔记",
        "style_hint": "像普通妈妈看完解读后顺手评论。",
    }
    complaint_scenario = {
        "scenario_code": "consumer_complaint",
        "scenario_name": "素人消费者吐槽类",
        "style_hint": "先接住博主正在吐槽的点。",
    }
    news_rule = _rule_with_comment_scenario(
        rule,
        news_scenario,
        {
            "direction_code": "in_stock_positive",
            "post_context": "你正在小红书母婴评论区，回复一篇解读a2恢复供货消息的帖子。",
        },
    )
    complaint_rule = _rule_with_comment_scenario(
        rule,
        complaint_scenario,
        {
            "direction_code": "supply_recovery",
            "post_context": "你正在小红书母婴评论区，回复一篇消费者吐槽a2此前不好买的帖子。",
        },
    )

    news_prompt = _comment_prompt_text(news_rule)
    complaint_prompt = _comment_prompt_text(complaint_rule)

    assert news_prompt.splitlines()[0] == news_rule["scenario_post_context"]
    assert complaint_prompt.splitlines()[0] == complaint_rule["scenario_post_context"]
    assert "像刷到a2到货后的一句自然接话" in news_prompt
    assert "像刷到a2到货后的一句自然接话" in complaint_prompt


def test_request_post_context_override_survives_scenario_merge():
    rule = {
        "asset_key": "a2_sentiment_comment_activity",
        "business_rule": "有货-直给到货情绪",
        "scenario_post_context": "你正在回复一篇消费者吐槽a2此前不好买的帖子。",
    }

    merged = _rule_with_comment_scenario(
        rule,
        {
            "scenario_code": "consumer_complaint",
            "scenario_name": "素人消费者吐槽类",
            "style_hint": "先接住博主正在吐槽的点。",
        },
        {"direction_code": "supply_recovery"},
    )

    assert merged["scenario_post_context"] == rule["scenario_post_context"]
    assert merged["scenario_generation_requirements"] == "先接住博主正在吐槽的点。"
    assert "当前是" not in merged["scenario_generation_requirements"]


def test_direction_generation_requirements_override_scenario_style_hint():
    merged = _rule_with_comment_scenario(
        {"asset_key": "a2_sentiment_comment_activity", "business_rule": "会员权益-抽奖活动"},
        {
            "scenario_code": "consumer_complaint",
            "scenario_name": "素人消费者吐槽类",
            "style_hint": "分享一条自己的当前经历。",
        },
        {
            "direction_code": "member_benefits",
            "generation_requirements": "只说自己看到或了解到的活动信息，不写已经中奖或领取。",
        },
    )

    assert merged["scenario_generation_requirements"] == (
        "只说自己看到或了解到的活动信息，不写已经中奖或领取。"
    )


def test_round_robin_gift_slot_is_selected_before_example_sampling():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rule = {
        "rule_id": "a2_direct_28",
        "business_rule": "会员权益-集罐换礼",
        "corpus": "像在聊集罐换礼。",
        "examples": [
            "a2集罐能换奶粉",
            "a2集罐礼里有自行车",
            "a2集罐换礼可以问问规则",
        ],
        "prompt_slot_selection_mode": "round_robin",
        "prompt_slots": {"集罐可换": ["奶粉", "自行车"]},
    }
    asset = SimpleNamespace(
        asset_key="a2_sentiment_comment_activity",
        id=1,
        version_no=45,
        content_json={},
        metadata_json={},
    )

    first = service._plan_from_rule(rule, asset=asset, item_no=1, rule_occurrence_no=0)
    second = service._plan_from_rule(rule, asset=asset, item_no=2, rule_occurrence_no=1)

    assert first["prompt_slots"] == {"集罐可换": ["奶粉"]}
    assert second["prompt_slots"] == {"集罐可换": ["自行车"]}
    assert first["examples"] == ["a2集罐能换奶粉"]
    assert second["examples"] == ["a2集罐礼里有自行车"]


def test_member_benefit_rule_uses_activity_only_keyword_selection():
    base = {
        "comment_writing_instruction": ["natural_comment", "light_comment_experience"],
        "comment_format_control": ["comment_two_sentence"],
    }

    selected, meta = _keyword_selection_with_rule_overrides(
        base,
        {
            "business_rule": "会员权益-抽奖活动",
            "scenario_guard_keyword": "会员权益",
        },
        item_no=1,
    )

    assert selected == {
        "comment_writing_instruction": ["natural_comment"],
        "comment_format_control": ["comment_short_clean"],
    }
    assert meta["keyword_selection_override"]["reason"] == "member_benefit_activity_only"
    assert base["comment_writing_instruction"] == ["natural_comment", "light_comment_experience"]


def test_scenario_selection_batches_target_outputs_without_multiplying_requested_count():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    scenario = {
        "scenario_code": "routed",
        "scenario_name": "模型分流",
        "directions": [
            {
                "direction_code": "simple",
                "direction_name": "简单方向",
                "weight": 60,
                "rule_ids": ["r1"],
                "output_batch_size": 20,
                "model_config": {
                    "provider_code": "ollama_local",
                    "model_code": "qwen3-4b-instruct-2507",
                },
            },
            {
                "direction_code": "complex",
                "direction_name": "复杂方向",
                "weight": 40,
                "rule_ids": ["r2"],
                "output_batch_size": 20,
                "model_config": {
                    "provider_code": "deepseek",
                    "model_code": "deepseek-v4-flash",
                },
            },
        ],
    }

    selected, mode = service._select_rules_for_scenario(_rules(), scenario, 50)
    plans = [
        service._plan_from_rule(
            rule,
            asset=SimpleNamespace(
                asset_key="a2_sentiment_comment_activity",
                id=7,
                version_no=38,
                content_json={},
                metadata_json={},
            ),
            item_no=index,
        )
        for index, rule in enumerate(selected, start=1)
    ]

    assert mode == "scenario_weighted_seed_expansion"
    assert len(plans) == 3
    assert sorted(plan["expansion_count"] for plan in plans) == [10, 20, 20]
    assert sum(_comment_plan_output_count(plan) for plan in plans) == 50
    assert {
        (plan["model_config"]["provider_code"], plan["model_config"]["model_code"])
        for plan in plans
    } == {
        ("ollama_local", "qwen3-4b-instruct-2507"),
        ("deepseek", "deepseek-v4-flash"),
    }


def test_comment_scenario_lookup_rejects_unknown_code():
    asset = SimpleNamespace(content_json={"comment_scenarios": [_scenario()]})

    with pytest.raises(ValueError, match="comment scenario not found: missing"):
        _comment_scenario_from_asset(asset, "missing")


def test_a2_comment_guard_does_not_require_duplicate_persona_slot():
    profile = resolve_quality_guard_profile("a2_sentiment_comment_202606")

    assert profile is not None
    assert "人设" not in profile.context_required_fields


def test_crm_third_party_direction_preserves_business_report_terms():
    item = ContentBatchItem(
        body="a2罐底码扫出来是新西兰三方检测报告，批次信息也有",
        plan_json={
            "quality_guard_profile_key": "a2_sentiment_comment_202606",
            "business_rule": "批批检-自己这批报告可查",
            "scenario_code": "crm_ec_regular",
            "scenario_direction": "third_party_report",
        },
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert payload["pass"] is True
    assert "罐底码" in item.body
    assert "三方检测报告" in item.body


@pytest.mark.parametrize(
    ("direction", "body"),
    [
        ("arrival", "补货了，我今天买了！"),
        ("batch_check", "每批都有报告，挺透明"),
        ("third_party_report", "三方报告能看到"),
        ("can_bottom_scan", "罐底扫码能看信息"),
    ],
)
def test_crm_short_directions_allow_complete_direct_comments(direction, body):
    item = ContentBatchItem(
        body=body,
        plan_json={
            "quality_guard_profile_key": "a2_sentiment_comment_202606",
            "business_rule": "CRM短评论",
            "scenario_code": "crm_ec_regular",
            "scenario_direction": direction,
        },
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert not any(issue["code"] == "activity_body_incomplete_comment" for issue in payload["issues"])


def test_crm_short_direction_still_rejects_empty_generic_fragment():
    item = ContentBatchItem(
        body="这个挺好",
        plan_json={
            "quality_guard_profile_key": "a2_sentiment_comment_202606",
            "business_rule": "CRM短评论",
            "scenario_code": "crm_ec_regular",
            "scenario_direction": "arrival",
        },
        quality_json={},
    )

    payload = ActivityQualityGuardService().review_item(item)

    assert payload is not None
    assert any(issue["code"] == "activity_body_incomplete_comment" for issue in payload["issues"])
