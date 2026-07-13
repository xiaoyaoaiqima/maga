import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_a2_direct_from_rule_bank import (  # noqa: E402
    audit,
    build_plan,
    forbidden_reason,
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
    assert "不要出现这些词" not in prompt
    assert "不要说缺货、断粮等消极词" not in prompt
    assert "焦虑" not in prompt
    assert "断货" not in prompt


def test_sentiment_news_prompt_omits_old_stock_negative_setup():
    prompt = prompt_for(
        "像评论区看到检测报告可查后的自然反应",
        "刚去查了，真的！扫罐底二维码能看到检测报告",
        20,
        prompt_mode="sentiment_news",
    )

    assert "关于 a2 奶粉新消息的帖子" in prompt
    assert "生成 20 条评论" in prompt
    assert "前段时间" not in prompt
    assert "缺货" not in prompt
    assert "没货" not in prompt
    assert "焦虑" not in prompt
    assert "供应紧张" not in prompt


def test_forbidden_terms_stay_in_post_generation_audit():
    reason = audit("有货-直给到货情绪", "终于不焦虑了，a2有货我先去看看", set())

    assert reason == "forbidden:焦虑"


def test_explicit_detection_values_stay_in_post_generation_audit():
    assert audit("三方检测-直给", "0.03那个数字我记下来了", set()) == "forbidden:0.03"
    assert audit("批批检-直给", "60+检测报告能看到", set()) == "forbidden:60+"
    assert audit("批批检-直给", "60多项检测报告能看到", set()) == "forbidden:60多项"


def test_forbidden_reason_includes_audit_only_hits():
    assert forbidden_reason("我扫了二维码但没找到入口") == "forbidden:没找到"


def test_report_query_friction_is_allowed_in_sentiment_news_batch_comments():
    text = "蹲一下，怎么查报告啊？我扫了二维码但没找到入口。"

    assert audit("批批检-报告查询互动", text, set()) == "forbidden:没找到"
    assert audit("批批检-报告查询互动", text, set(), audit_mode="sentiment_news") == ""


def test_non_report_audit_only_terms_stay_blocked_in_sentiment_news():
    text = "这次还是难买，等得我心焦。"

    assert audit("批批检-报告查询互动", text, set(), audit_mode="sentiment_news") == "forbidden:难买,心焦"


def test_supply_chain_source_query_is_allowed_in_sentiment_news_batch_comments():
    text = "能查到供应链信息吗？想看看源头。"

    assert audit("批批检-报告查询互动", text, set()) == "batch_no_anchor"
    assert audit("批批检-报告查询互动", text, set(), audit_mode="sentiment_news") == ""


def test_single_cause_deescalation_machine_audit_keeps_soft_life_observations():
    category = "舆情缓和-个人经历与个体差异"

    assert audit(category, "我们家喝了快一年暂时没遇到，不过每个宝宝情况确实不一样。", set()) == ""
    assert audit(category, "我家有一阵便便也偏干，刚好那段时间辅食变化挺大，也说不准是哪一个。", set()) == ""
    assert audit(category, "会不会也和最近天气、辅食节奏有关呀？我们家之前也碰到过类似情况。", set()) == ""


def test_single_cause_deescalation_machine_audit_blocks_only_clear_dangerous_structures():
    category = "舆情缓和-个人经历与个体差异"

    assert audit(category, "肯定是辅食导致的，跟奶粉没关系。", set()).startswith("definitive_causality:")
    assert audit(category, "你家就是个例，别被竞品带节奏。", set()).startswith("dismissive_or_attack:")
    assert audit(category, "不用转奶，继续喝a2就行。", set()).startswith("forced_no_switch:")
    assert audit(category, "喝a2不会出现这种情况。", set()).startswith("medical_or_guarantee:")


def test_single_cause_deescalation_prompt_does_not_expose_competitor_background():
    prompt = prompt_for(
        "分享个人经历，提醒个体差异",
        "我们家暂时没遇到，不过每个娃不一样",
        10,
        "single_cause_deescalation",
    )

    assert "大约三成可以自然提到 a2" in prompt
    assert "不直接劝别转奶或继续喝" in prompt
    assert "竞品利用" not in prompt
    assert "断货事件" not in prompt
    assert "这批只写这个子方向" in prompt
    assert "说到意思就停" in prompt
    assert "不补相邻方向或完整解释链" in prompt
    assert "先安慰、再解释、最后总结" not in prompt


def test_sentiment_news_audit_relaxes_batch_transparency_anchor():
    text = "希望一直保持这种透明，让我们买得安心。"

    assert audit("批批检-检测透明中立认可", text, set()) == "batch_no_anchor"
    assert audit("批批检-检测透明中立认可", text, set(), audit_mode="sentiment_news") == ""


def test_sentiment_news_audit_relaxes_transfer_bridge_terms():
    text = "市场认可度高肯定有道理，娃喝习惯了我就不折腾了"

    assert audit("转奶-老用户继续熟悉款", text, set()) == "transfer_pain_only"
    assert audit("转奶-老用户继续熟悉款", text, set(), audit_mode="sentiment_news") == ""


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
