#!/usr/bin/env python3
"""Local Wangyue gate-calibration experiment after v414.

Builds on v414. The writer contract is kept; this only narrows plan-gate
inspection to real story fields so category-neutral milk events and negated
self-check text do not kill strong usable lanes.
"""

from __future__ import annotations

import json
from typing import Any

import run_v414_wangyue_writer_contract_by_lane_experiment as writer_contract


base = writer_contract.base
base.EXPERIMENT_ID = "v415_gate_calibration_after_writer_contract"

base.PRODUCT_BRIDGE_SYSTEM = base.PRODUCT_BRIDGE_SYSTEM.replace(
    "positive_evidence, ending_stop, avoid_links, self_check。",
    "positive_evidence, ending_stop, avoid_links, self_check。\n"
    "positive_evidence 不能空；可以是孩子接受度、喝着顺、精神头还可以、饭量活动量这类自家观察，不需要额外补第二个效果。",
)


def _validate_plan_gate_calibrated(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    human_event = plan.get("human_event") or {}
    product_bridge = plan.get("product_bridge") or {}
    event_type = str(human_event.get("event_type") or "")
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
    human_real_text = json.dumps({
        key: human_event.get(key)
        for key in (
            "event_type",
            "posting_motive",
            "posting_emotion_trigger",
            "human_event",
            "emotional_impulse",
            "life_entry",
            "natural_stop",
        )
    }, ensure_ascii=False)
    story_real_text = json.dumps({
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

    product_terms = ["旺玥", "配方", "成分", "乳铁蛋白", "HMO", "钙铁锌", "DHA", "燕窝酸", "补货"]
    category_allowed = event_type in {
        "choice_review",
        "nutrition_review",
        "routine_arrangement",
        "usage_acceptance",
        "light_comparison",
    }
    if not category_allowed:
        product_terms.extend(["奶粉", "儿童奶粉", "喝奶"])
    else:
        product_terms.extend(["喝奶时间", "喝法"])
    human_product_hits = base._hits(human_real_text, product_terms)
    if human_product_hits:
        issues.append(f"human_event_contains_product:{','.join(human_product_hits)}")

    category_substitute_hits = base._hits(
        human_real_text,
        ["儿童营养饮", "营养饮", "盒装儿童营养", "盒装饮品", "盒装"],
    )
    if category_substitute_hits:
        issues.append(f"wrong_category_substitute:{','.join(category_substitute_hits)}")
    if hits := base._hits(story_real_text, base.FORBIDDEN_TERMS):
        issues.append(f"forbidden:{','.join(hits)}")
    if base._pattern_hits(story_real_text, base.DIRECT_CAUSE_PATTERNS):
        issues.append("direct_causality")
    if base._pattern_hits(story_real_text, base.SEASON_ENV_PATTERNS):
        issues.append("season_or_environment_anchor")
    if writer_contract.compat.emotion.category.timeline._timeline_risk(story_real_text):
        issues.append("age_timeline_risk")
    if any(word in product_bridge_text for word in ("安心", "省心", "放心", "心里有底", "心安")):
        issues.append("closure_shortcut")
    for flag, patterns in base.PLAN_GATE_PATTERNS.items():
        hits = base._pattern_hits(story_real_text, patterns)
        if not hits:
            continue
        if flag == "product_as_answer_in_plan" and base._only_negated_product_answer(story_real_text, hits):
            continue
        issues.append(flag)
    return not issues, issues


base._validate_plan = _validate_plan_gate_calibrated


if __name__ == "__main__":
    base.main()
