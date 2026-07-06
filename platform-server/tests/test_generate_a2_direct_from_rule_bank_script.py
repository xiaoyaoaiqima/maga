import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_a2_direct_from_rule_bank import (  # noqa: E402
    audit,
    build_plan,
    generalize_competitor_brand_terms,
    near_duplicate_reason,
    prompt_for,
)


def test_build_plan_splits_target_into_default_expansion_chunks():
    rules = [
        {
            "rule_id": "a2_direct_01",
            "major_category": "有货",
            "category": "有货-直给到货情绪",
            "focus": "到货",
            "examples": "a2到了",
        },
        {
            "rule_id": "a2_direct_02",
            "major_category": "有货",
            "category": "有货-渠道线索",
            "focus": "渠道",
            "examples": "山姆到了",
        },
    ]

    plan = build_plan(rules, [("有货", 50)], per_rule_count=20)

    assert [(rule["rule_id"], count) for rule, count in plan] == [
        ("a2_direct_01", 20),
        ("a2_direct_01", 5),
        ("a2_direct_02", 20),
        ("a2_direct_02", 5),
    ]


def test_prompt_allows_reply_style_comments():
    prompt = prompt_for("像评论区求指路", "哪买的啊", 20)

    assert "可以写成跟评、接楼、追问、求指路" in prompt
    assert "不要求每条都独立成完整总结" in prompt
    assert "不要直接说其他奶粉品牌名" in prompt
    assert "生成 20 条评论" in prompt


def test_near_duplicate_reason_uses_jaccard_threshold():
    reason = near_duplicate_reason(
        "我的也到了，等发货中",
        ["我的也到了，等发货"],
        threshold=0.86,
    )

    assert reason.startswith("near_duplicate:")


def test_member_benefit_allows_vague_toy_and_gift_box():
    reason = audit(
        "会员权益-活动礼品",
        "a2至初礼盒里的东西都挺实在，有奶粉有玩具，不是小玩意。",
        set(),
    )

    assert reason == ""


def test_direct_script_generalizes_competitor_brand_terms_before_audit():
    text = generalize_competitor_brand_terms("之前喝爱他美，也看过雀巢每批检，a2报告能扫。")

    assert "爱他美" not in text
    assert "雀巢" not in text
    assert "之前的奶粉" in text
    assert "其他品牌" in text
