#!/usr/bin/env python3
"""Local Wangyue category-neutral human-event experiment.

Builds on v410 timeline safety. The change is architectural: human_event may
use the neutral category "儿童奶粉/奶粉", while brand, ingredients, benefits,
usage process, and effect proof stay out of the human-event stage.
"""

from __future__ import annotations

import json
from typing import Any

import run_v410_wangyue_timeline_safety_experiment as timeline


base = timeline.base
base.EXPERIMENT_ID = "v411_category_neutral_event"

base.HUMAN_EVENT_SYSTEM = base.HUMAN_EVENT_SYSTEM.replace(
    "- 不出现旺玥、具体奶粉名、配方、成分、卖点、喝法、补货。",
    "- 可以出现“儿童奶粉/奶粉”这个中性品类对象。\n"
    "- 不出现旺玥、具体奶粉名、配方、成分、卖点、效果证明、喝法、补货。",
)

base.PRODUCT_BRIDGE_SYSTEM = base.PRODUCT_BRIDGE_SYSTEM.replace(
    "- 不重写 approved_human_event，不新增第二个生活入口。",
    "- 不重写 approved_human_event，不新增第二个生活入口。\n"
    "- 如果 approved_human_event 已经是儿童奶粉/奶粉这个中性品类事件，可以顺着这个品类关系判断旺玥是否进入。",
)

for event_type in base.EVENT_TYPE_POOL:
    if event_type["event_type"] == "nutrition_review":
        event_type["allowed_event_object"] = "儿童奶粉/奶粉相关的日常营养安排、阶段营养选择、家里已有儿童奶粉选择复盘。"
        event_type["disallowed_event_object"] = "单纯蔬菜肉类搭配、医生建议、体检指标、治疗、疾病环境。"
    elif event_type["event_type"] == "routine_arrangement":
        event_type["allowed_event_object"] = "被问起家里儿童奶粉怎么选、奶粉是否固定、阶段营养选择；不是完整放学流程。"
        event_type["disallowed_event_object"] = "固定杯数、每天早晚、加餐时段、一杯旺玥、睡前奶、完整放学流程。"
        event_type["life_theme"] = "被别的妈妈或家人随口问起家里儿童奶粉怎么选，才发现这个选择已经用了一段时间。"
    elif event_type["event_type"] == "usage_acceptance":
        event_type["allowed_event_object"] = "儿童奶粉口味接受、孩子对奶粉接受度、第一次试某款儿童奶粉。"
        event_type["disallowed_event_object"] = "麦片、酸奶、零食、辅食、新菜、儿童营养饮、盒装饮品。"
    elif event_type["event_type"] == "light_comparison":
        event_type["allowed_event_object"] = "儿童奶粉选择对比、儿童奶粉口味或配方印象对比、阶段营养选择对比。"
        event_type["disallowed_event_object"] = "课程、玩具、兴趣班、游乐活动、衣服用品、营养饮。"


_original_local_quality = base._local_quality


def _validate_plan_category_neutral(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    human_event = plan.get("human_event") or {}
    product_bridge = plan.get("product_bridge") or {}
    product_bridge_text = json.dumps({
        key: product_bridge.get(key)
        for key in (
            "bridge_logic",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)
    human_event_text = json.dumps({
        key: human_event.get(key)
        for key in (
            "event_type",
            "posting_motive",
            "human_event",
            "emotional_impulse",
            "life_entry",
            "natural_stop",
            "no_product_post",
        )
    }, ensure_ascii=False)
    story_text = json.dumps({
        key: plan.get(key)
        for key in (
            "posting_motive",
            "storyline",
            "life_entry",
            "product_permission",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)
    issues: list[str] = []
    required = [
        "posting_motive",
        "storyline",
        "life_entry",
        "product_permission",
        "ending_stop",
        "avoid_links",
    ]
    if base._permission_true(plan.get("product_permission")):
        required.extend(["product_role", "single_selling_point", "positive_evidence"])
    for key in required:
        if not str(plan.get(key) or "").strip():
            issues.append(f"missing:{key}")
    if not str(human_event.get("event_type") or "").strip():
        issues.append("missing:event_type")
    if not base._permission_true(plan.get("product_permission")):
        issues.append("product_permission_false")

    human_product_hits = base._hits(
        human_event_text,
        ["旺玥", "配方", "成分", "乳铁蛋白", "HMO", "钙铁锌", "DHA", "燕窝酸", "补货", "喝奶", "每天", "早晚"],
    )
    if human_product_hits:
        issues.append(f"human_event_contains_product:{','.join(human_product_hits)}")
    category_substitute_hits = base._hits(
        human_event_text,
        ["儿童营养饮", "营养饮", "盒装儿童营养", "盒装饮品", "盒装"],
    )
    if category_substitute_hits:
        issues.append(f"wrong_category_substitute:{','.join(category_substitute_hits)}")
    if hits := base._hits(story_text, base.FORBIDDEN_TERMS):
        issues.append(f"forbidden:{','.join(hits)}")
    if base._pattern_hits(story_text, base.DIRECT_CAUSE_PATTERNS):
        issues.append("direct_causality")
    if base._pattern_hits(story_text, base.SEASON_ENV_PATTERNS):
        issues.append("season_or_environment_anchor")
    if timeline._timeline_risk(json.dumps(plan, ensure_ascii=False)):
        issues.append("age_timeline_risk")
    if any(word in product_bridge_text for word in ("安心", "省心", "放心", "心里有底", "心安")):
        issues.append("closure_shortcut")
    for flag, patterns in base.PLAN_GATE_PATTERNS.items():
        hits = base._pattern_hits(story_text, patterns)
        if not hits:
            continue
        if flag == "product_as_answer_in_plan" and base._only_negated_product_answer(story_text, hits):
            continue
        issues.append(flag)
    return not issues, issues


def _local_quality_category_neutral(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    text = f"{title}\n{body}"
    substitute_hits = base._hits(text, ["儿童营养饮", "营养饮", "盒装儿童营养", "盒装饮品", "盒装"])
    if substitute_hits:
        quality["flags"].append("wrong_category_substitute")
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "wrong_category_substitute"
    return quality


base._validate_plan = _validate_plan_category_neutral
base._local_quality = _local_quality_category_neutral


if __name__ == "__main__":
    base.main()

