from __future__ import annotations

import json
from pathlib import Path

from app.services.content_batch_execution_service import (
    _should_repair_product_experience_llm_quality,
    _should_review_product_experience_llm_quality,
    _should_rewrite_product_experience_llm_quality,
)
from app.services.product_experience_llm_review_service import (
    A2_REIYU_ARTICLE_ASSET_KEY,
    A2_REIYU_REVIEW_RUBRIC_CODE,
    ProductExperienceLLMIssue,
    ProductExperienceLLMReview,
    _review_rubric_code,
    _review_system_prompt,
    _user_prompt,
)


NARRATIVE_GOLD_PATH = (
    Path(__file__).parents[1]
    / "evals"
    / "a2_reiyu_review_gold_v1_narrative_consistency.json"
)
ACTIVITY_NAMING_GOLD_PATH = (
    Path(__file__).parents[1]
    / "evals"
    / "a2_reiyu_review_gold_v1_activity_naming.json"
)
BUSINESS_ALLOWLIST_GOLD_PATH = (
    Path(__file__).parents[1]
    / "evals"
    / "a2_reiyu_review_gold_v1_business_allowlist.json"
)
ACTIVITY_MECHANISM_GOLD_PATH = (
    Path(__file__).parents[1]
    / "evals"
    / "a2_reiyu_review_gold_v1_activity_mechanism.json"
)
SOURCE_STACKING_GOLD_PATH = (
    Path(__file__).parents[1]
    / "evals"
    / "a2_reiyu_review_gold_v1_source_stacking.json"
)
COMMON_LOGIC_GOLD_PATH = (
    Path(__file__).parents[1]
    / "evals"
    / "a2_reiyu_review_gold_v1_common_logic.json"
)


def test_a2_reiyu_asset_routes_to_approved_business_usability_rubric() -> None:
    plan = {
        "asset_key": A2_REIYU_ARTICLE_ASSET_KEY,
        "business_rule": "a2礼遇｜集罐12罐换奶粉｜信息了解后的认可",
        "variation_slots": [
            {
                "slot_code": "activity_content",
                "value": "集12罐兑换1罐奶粉",
            }
        ],
    }

    prompt = _review_system_prompt(plan)
    payload = json.loads(
        _user_prompt(
            title="a2集罐活动",
            body="集12罐可以兑换1罐奶粉。",
            plan=plan,
            phrase_review=None,
        )
    )

    assert _review_rubric_code(plan) == A2_REIYU_REVIEW_RUBRIC_CODE
    assert payload["task"] == "review_a2_reiyu_ugc_business_usability"
    assert payload["plan"]["business_rule"] == plan["business_rule"]
    assert "3罐小车车、6罐自行车、12罐奶粉、18罐婴儿车" in prompt
    assert "活动页面、页面里或页面上提到" in prompt
    assert "集罐过程扫罐码累计" in prompt
    assert "不得建议改成拍罐身、购买记录" in prompt
    assert "疾病、医疗效果" in prompt
    assert "多个独立发现来源" in prompt
    assert "积分兑换小车车、自行车、奶粉或婴儿车等集罐奖品" in prompt
    assert "旅游基金、金手链、夏凉被等抽奖奖品" in prompt
    assert "集罐换积分、集罐兑换积分" in prompt
    assert "奶粉喝完了把罐子存着" in prompt
    assert "换到小车车娃可开心了" in prompt
    assert "之前换a2后" in prompt
    assert "用冷水冲调奶粉" in prompt
    assert "焦虑一下没了" in prompt
    assert "negative_brand_risk" in prompt
    assert "超过20直接判 hard / hold_out" in prompt
    assert "rewrite_required=false" in prompt
    assert "抽奖那种虚的" in prompt
    assert "同一经历里的兴趣变化" in prompt


def test_a2_reiyu_business_review_is_mark_only_in_generation_postprocess() -> None:
    plan = {"asset_key": A2_REIYU_ARTICLE_ASSET_KEY}
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="rewrite",
        issues=[
            ProductExperienceLLMIssue(
                code="activity_mechanism_error",
                evidence="积分换奶粉",
                reason="积分与集罐奖品串换",
                rewrite_direction="删除错误奖品归属",
            )
        ],
        business_usability_tier="hold_out",
    )

    assert _should_review_product_experience_llm_quality(plan) is True
    assert _should_rewrite_product_experience_llm_quality(plan, review) is False
    assert _should_repair_product_experience_llm_quality(plan, review) is False


def test_a2_reiyu_narrative_consistency_gold_keeps_approved_boundary() -> None:
    payload = json.loads(NARRATIVE_GOLD_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_code"] == "a2_reiyu_review_gold_v1"
    assert payload["slice"] == "narrative_consistency_v1"
    assert payload["review_status"] == "approved"
    assert payload["labels"] == ["pass", "light_fix"]

    items = {item["meta"]["case_code"]: item for item in payload["items"]}
    assert set(items) == {
        "A2RY-NC-001",
        "A2RY-NC-002",
        "A2RY-NC-003",
        "A2RY-NC-004",
    }
    assert items["A2RY-NC-001"]["meta"]["expected_label"] == "light_fix"
    assert items["A2RY-NC-002"]["meta"]["expected_label"] == "pass"
    assert items["A2RY-NC-003"]["meta"]["expected_label"] == "pass"
    assert items["A2RY-NC-004"]["meta"]["expected_label"] == "light_fix"


def test_a2_reiyu_gold_pairs_original_with_user_confirmed_minimal_fix() -> None:
    payload = json.loads(NARRATIVE_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    ambiguous = items["A2RY-NC-001"]
    corrected = items["A2RY-NC-002"]

    assert "我本来就一直想囤他们家" in ambiguous["content"]
    assert "我本来就一直囤他们家" in corrected["content"]
    assert "喝了几个月a2至初" in ambiguous["content"]
    assert "继续回购下去" in ambiguous["content"]
    assert ambiguous["meta"]["minimal_fix"] == (
        "将‘我本来就一直想囤他们家’改为‘我本来就一直囤他们家’。"
    )


def test_a2_reiyu_gold_does_not_turn_xiang_into_a_global_banned_word() -> None:
    payload = json.loads(NARRATIVE_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])

    assert "不把单个词机械设为禁词" in rubric
    assert "‘想’不是通用禁词" in rubric


def test_a2_reiyu_narrative_gold_allows_current_user_to_recount_prior_switch() -> None:
    payload = json.loads(NARRATIVE_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    historical_switch = items["A2RY-NC-003"]
    duration_conflict = items["A2RY-NC-004"]

    assert "本来就喝a2至初" in historical_switch["content"]
    assert "之前换a2后" in historical_switch["content"]
    assert historical_switch["meta"]["expected_label"] == "pass"
    assert duration_conflict["meta"]["issue_code"] == "usage_duration_conflict"
    assert "喝a2至初两年" in duration_conflict["content"]
    assert "喝了大半年" in duration_conflict["content"]


def test_a2_reiyu_activity_naming_gold_keeps_approved_boundary() -> None:
    payload = json.loads(ACTIVITY_NAMING_GOLD_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_code"] == "a2_reiyu_review_gold_v1"
    assert payload["slice"] == "activity_naming_v1"
    assert payload["review_status"] == "approved"
    assert payload["labels"] == ["pass", "light_fix"]

    items = {item["meta"]["case_code"]: item for item in payload["items"]}
    assert set(items) == {"A2RY-AN-001", "A2RY-AN-002", "A2RY-AN-003"}
    assert items["A2RY-AN-001"]["meta"]["expected_label"] == "light_fix"
    assert items["A2RY-AN-002"]["meta"]["expected_label"] == "pass"
    assert items["A2RY-AN-003"]["meta"]["expected_label"] == "light_fix"


def test_a2_reiyu_activity_name_is_embedded_in_natural_discovery_sentence() -> None:
    payload = json.loads(ACTIVITY_NAMING_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    explanatory = items["A2RY-AN-001"]
    natural = items["A2RY-AN-002"]

    assert "这个活动叫会员礼遇升级活动" in explanatory["content"]
    assert "发现a2上了会员礼遇升级活动" in natural["content"]
    assert explanatory["meta"]["minimal_fix"] == (
        "将‘说这个活动叫会员礼遇升级活动’改为‘我才发现a2上了会员礼遇升级活动’。"
    )


def test_a2_reiyu_activity_name_is_allowed_but_name_explanation_is_not() -> None:
    payload = json.loads(ACTIVITY_NAMING_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])

    assert "活动名允许出现在正文中" in rubric
    assert "本规则不是禁止写活动名" in rubric
    assert "不要单独介绍‘这个活动叫什么名字’" in rubric


def test_a2_reiyu_activity_is_member_upgrade_is_light_fix() -> None:
    payload = json.loads(ACTIVITY_NAMING_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert "活动是会员升级" in items["A2RY-AN-003"]["content"]
    assert items["A2RY-AN-003"]["meta"]["expected_label"] == "light_fix"


def test_a2_reiyu_business_allowlist_keeps_user_confirmed_passes() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_code"] == "a2_reiyu_review_gold_v1"
    assert payload["slice"] == "business_allowlist_v1"
    assert payload["review_status"] == "approved"
    assert payload["labels"] == ["pass"]

    items = {item["meta"]["case_code"]: item for item in payload["items"]}
    assert set(items) == {
        "A2RY-BA-001",
        "A2RY-BA-002",
        "A2RY-BA-003",
        "A2RY-BA-004",
        "A2RY-BA-005",
        "A2RY-BA-006",
        "A2RY-BA-007",
        "A2RY-BA-008",
        "A2RY-BA-009",
        "A2RY-BA-010",
        "A2RY-BA-011",
    }
    assert all(item["meta"]["expected_label"] == "pass" for item in items.values())


def test_a2_reiyu_business_allowlist_confirms_prize_amount() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])

    assert "‘2w’‘两万’‘万元’" in rubric
    assert "已确认正确事实放行" in rubric
    assert "不再标记事实待核" in rubric


def test_a2_reiyu_business_allowlist_allows_medical_effect_language() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])

    assert "本活动审核不拦截疾病或医疗效果表达" in rubric
    assert "少跑医院" in rubric
    assert "体质/抵抗力/自护力提升" in rubric


def test_a2_reiyu_business_allowlist_separates_generation_constraints_from_review() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])

    assert "正文200-250字属于生文约束" in rubric
    assert "emoji2" in rubric
    assert "加权长度不超过20" in rubric


def test_a2_reiyu_business_allowlist_allows_natural_recommendation_and_brand_reference() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])

    assert "‘别错过’‘值得试试’" in rubric
    assert "上下文已经明确出现a2" in rubric
    assert "后文可用‘品牌’自然指代" in rubric


def test_a2_reiyu_business_allowlist_allows_general_detection_strictness_and_careful_reading() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])

    assert "‘检测很严格’‘标准高’" in rubric
    assert "具体检测项目、数量、结果或报告细节" in rubric
    assert "‘仔细看了下’本身允许" in rubric
    assert "翻看页面、往下翻页面" in rubric


def test_a2_reiyu_business_allowlist_allows_resolved_anxiety_wording() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert "自然情绪词不能按单词机械拦截" in rubric
    assert "老母亲的焦虑一下没了" in items["A2RY-BA-008"]["content"]
    assert items["A2RY-BA-008"]["meta"]["expected_label"] == "pass"


def test_a2_reiyu_business_allowlist_allows_lottery_is_virtual_wording() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert "抽奖那种虚的" in items["A2RY-BA-009"]["content"]
    assert items["A2RY-BA-009"]["meta"]["expected_label"] == "pass"


def test_a2_reiyu_business_allowlist_allows_negated_risk_wording() -> None:
    payload = json.loads(BUSINESS_ALLOWLIST_GOLD_PATH.read_text(encoding="utf-8"))
    rubric = "\n".join(payload["rubric"])
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert "‘闭眼入不踩雷’‘转奶没翻车’" in rubric
    assert "明确负面经历才处理" in rubric
    assert "闭眼入不踩雷" in items["A2RY-BA-010"]["content"]
    assert items["A2RY-BA-010"]["meta"]["expected_label"] == "pass"
    assert "转奶那会儿没翻车" in items["A2RY-BA-011"]["content"]
    assert items["A2RY-BA-011"]["meta"]["expected_label"] == "pass"


def test_a2_reiyu_activity_mechanism_gold_keeps_approved_boundary() -> None:
    payload = json.loads(ACTIVITY_MECHANISM_GOLD_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_code"] == "a2_reiyu_review_gold_v1"
    assert payload["slice"] == "activity_mechanism_v1"
    assert payload["review_status"] == "approved"
    assert payload["labels"] == ["pass", "light_fix", "reject"]

    items = {item["meta"]["case_code"]: item for item in payload["items"]}
    assert set(items) == {
        "A2RY-AM-001",
        "A2RY-AM-002",
        "A2RY-AM-003",
        "A2RY-AM-004",
        "A2RY-AM-005",
        "A2RY-AM-006",
        "A2RY-AM-007",
        "A2RY-AM-008",
        "A2RY-AM-009",
        "A2RY-AM-010",
        "A2RY-AM-011",
        "A2RY-AM-012",
        "A2RY-AM-013",
        "A2RY-AM-014",
        "A2RY-AM-015",
        "A2RY-AM-016",
        "A2RY-AM-017",
        "A2RY-AM-018",
        "A2RY-AM-019",
    }


def test_a2_reiyu_activity_mechanism_allows_scan_eat_and_clear_prize_split() -> None:
    payload = json.loads(ACTIVITY_MECHANISM_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert items["A2RY-AM-001"]["meta"]["expected_label"] == "pass"
    assert "扫罐码集罐" in items["A2RY-AM-001"]["content"]
    assert items["A2RY-AM-002"]["meta"]["expected_label"] == "pass"
    assert "集罐能兑自行车或奶粉" in items["A2RY-AM-002"]["content"]
    assert "抽奖有旅游基金" in items["A2RY-AM-002"]["content"]
    assert items["A2RY-AM-003"]["meta"]["expected_label"] == "pass"
    assert "吃完" in items["A2RY-AM-003"]["content"]


def test_a2_reiyu_activity_mechanism_rejects_confirmed_fact_errors() -> None:
    payload = json.loads(ACTIVITY_MECHANISM_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}
    rubric = "\n".join(payload["rubric"])

    assert "旅游基金也可以自然写成‘新西兰旅游’" in rubric
    assert "3罐换小车车" in rubric
    assert "6罐换自行车" in rubric
    assert "12罐换奶粉" in rubric
    assert "18罐换婴儿车" in rubric
    assert "积分可以正常出现" in rubric
    assert "集罐换积分" in rubric
    assert items["A2RY-AM-004"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-005"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-006"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-012"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-013"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-014"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-015"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-016"]["meta"]["expected_label"] == "light_fix"
    assert items["A2RY-AM-017"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-018"]["meta"]["expected_label"] == "reject"
    assert items["A2RY-AM-019"]["meta"]["expected_label"] == "pass"


def test_a2_reiyu_activity_mechanism_keeps_confirmed_review_passes() -> None:
    payload = json.loads(ACTIVITY_MECHANISM_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert items["A2RY-AM-007"]["meta"]["expected_label"] == "pass"
    assert items["A2RY-AM-008"]["meta"]["expected_label"] == "light_fix"
    assert items["A2RY-AM-009"]["meta"]["expected_label"] == "pass"
    assert items["A2RY-AM-010"]["meta"]["expected_label"] == "pass"
    assert items["A2RY-AM-011"]["meta"]["expected_label"] == "pass"
    assert "2w多的新西兰旅游" in items["A2RY-AM-011"]["content"]
    assert "还有小车车送" in items["A2RY-AM-008"]["content"]


def test_a2_reiyu_activity_mechanism_covers_new_backup_batch_boundaries() -> None:
    payload = json.loads(ACTIVITY_MECHANISM_GOLD_PATH.read_text(encoding="utf-8"))
    items = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert items["A2RY-AM-012"]["meta"]["issue_code"] == "fabricated_reward_experience"
    assert "娃拿到小车" in items["A2RY-AM-012"]["content"]
    assert items["A2RY-AM-013"]["meta"]["issue_code"] == "points_redeem_lottery_prize"
    assert "夏凉被和金手链" in items["A2RY-AM-013"]["content"]
    assert items["A2RY-AM-014"]["meta"]["issue_code"] == "collect_can_redeem_points"
    assert "集罐还能换积分" in items["A2RY-AM-014"]["content"]
    assert "家里正好存了几个罐子" in items["A2RY-AM-015"]["content"]
    assert items["A2RY-AM-016"]["meta"]["minimal_fix"] == (
        "改为‘参加集罐还能换奶粉’，不描述存放空罐。"
    )
    assert items["A2RY-AM-017"]["meta"]["issue_code"] == "fabricated_points_reward"
    assert "小玩具、绘本、奶粉周边" in items["A2RY-AM-017"]["content"]
    assert items["A2RY-AM-018"]["meta"]["issue_code"] == "old_can_eligibility_implied"
    assert "家里刚囤了一箱" in items["A2RY-AM-018"]["content"]
    assert items["A2RY-AM-019"]["meta"]["expected_label"] == "pass"
    assert "活动期间买完后扫罐码累计" in items["A2RY-AM-019"]["content"]


def test_a2_reiyu_source_stacking_gold_rejects_three_discovery_sources() -> None:
    payload = json.loads(SOURCE_STACKING_GOLD_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_code"] == "a2_reiyu_review_gold_v1"
    assert payload["slice"] == "source_stacking_v1"
    assert payload["labels"] == ["pass", "reject"]

    items = {item["meta"]["case_code"]: item for item in payload["items"]}
    assert set(items) == {"A2RY-SS-001", "A2RY-SS-002", "A2RY-SS-003"}
    assert items["A2RY-SS-001"]["meta"]["expected_label"] == "reject"
    assert "邻居说" in items["A2RY-SS-001"]["content"]
    assert "闺蜜也发消息" in items["A2RY-SS-001"]["content"]
    assert "导购打电话" in items["A2RY-SS-001"]["content"]
    assert items["A2RY-SS-002"]["meta"]["expected_label"] == "pass"
    assert items["A2RY-SS-003"]["meta"]["expected_label"] == "pass"
    assert "看到a2官号推会员升级" in items["A2RY-SS-003"]["content"]


def test_a2_reiyu_common_logic_gold_keeps_cold_water_as_light_fix() -> None:
    payload = json.loads(COMMON_LOGIC_GOLD_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_code"] == "a2_reiyu_review_gold_v1"
    assert payload["slice"] == "common_logic_v1"
    assert payload["labels"] == ["light_fix"]

    items = {item["meta"]["case_code"]: item for item in payload["items"]}
    assert set(items) == {"A2RY-CL-001"}
    assert items["A2RY-CL-001"]["meta"]["expected_label"] == "light_fix"
    assert items["A2RY-CL-001"]["meta"]["issue_code"] == "common_sense_error"
    assert "冷水一冲就化开" in items["A2RY-CL-001"]["content"]
