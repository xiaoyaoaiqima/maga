#!/usr/bin/env python3
"""Local Wangyue usage-trial gate semantics experiment.

Builds on v415. This keeps the writer contract intact and calibrates gates that
confused one-time trial/acceptance actions with fixed drinking routines.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v415_wangyue_gate_calibration_after_writer_contract as gate_calibrated


base = gate_calibrated.base
base.EXPERIMENT_ID = "v416_usage_trial_gate_semantics"


_original_validate_plan = base._validate_plan
_original_fidelity_gate = base._fidelity_gate


def _validate_plan_v416(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    human_event = plan.get("human_event") or {}
    event_type = str(human_event.get("event_type") or "")
    if event_type == "light_comparison":
        issues = _relax_light_comparison_generic_terms(issues, plan)
    return not issues, issues


def _relax_light_comparison_generic_terms(issues: list[str], plan: dict[str, Any]) -> list[str]:
    human_event = plan.get("human_event") or {}
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

    strict_ingredient_hits = base._hits(human_real_text, ["乳铁蛋白", "HMO", "钙铁锌", "DHA", "燕窝酸"])
    relaxed: list[str] = []
    for issue in issues:
        if issue == "human_event_contains_product:成分" and not strict_ingredient_hits:
            continue
        if issue == "direct_benefit_in_plan" and _only_generic_growth_need(story_real_text):
            continue
        relaxed.append(issue)
    return relaxed


def _only_generic_growth_need(text: str) -> bool:
    risky_patterns = [
        r"旺玥.{0,16}(让|使|改善|提升|帮助|促进)",
        r"(靠|因为|多亏).{0,16}旺玥",
        r"(长肉|长高|结实|抱起来|撑起来).{0,20}旺玥",
        r"旺玥.{0,20}(长肉|长高|结实|抱起来|撑起来)",
    ]
    if base._pattern_hits(text, risky_patterns):
        return False
    allowed_patterns = [
        r"基础营养.{0,12}(成长需求|日常)",
        r"钙铁锌.{0,12}(基础营养|日常)",
        r"营养成分",
        r"日常成长需求",
    ]
    return bool(base._pattern_hits(text, allowed_patterns))


def _fidelity_gate_v416(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    human_event = plan.get("human_event") or {}
    event_type = str(human_event.get("event_type") or "")
    if event_type == "usage_acceptance" and _is_one_time_trial_acceptance(title, body, plan):
        result["flags"] = [
            flag for flag in result.get("flags", [])
            if flag not in {"fixed_usage_added", "new_usage_process_added"}
        ]
        result["pass"] = not result["flags"]
    return result


def _is_one_time_trial_acceptance(title: str, body: str, plan: dict[str, Any]) -> bool:
    text = f"{title}\n{body}"
    plan_text = json.dumps(plan, ensure_ascii=False)
    trial_cues = [
        "试",
        "尝",
        "抿",
        "第一口",
        "一小口",
        "又喝了一口",
        "接受",
        "好喝",
        "眼睛亮",
        "没抗拒",
        "换换口味",
    ]
    if not any(cue in text or cue in plan_text for cue in trial_cues):
        return False
    fixed_routine_patterns = [
        r"每天",
        r"早晚",
        r"固定",
        r"睡前",
        r"早餐奶",
        r"晚饭后.{0,8}(冲|泡|喝)",
        r"每次都",
        r"每到喝奶时间",
        r"一直.{0,8}(这样|这么|喝)",
        r"雷打不动",
        r"长期.{0,8}(喝|安排)",
    ]
    return not bool(base._pattern_hits(text, fixed_routine_patterns))


base._validate_plan = _validate_plan_v416
base._fidelity_gate = _fidelity_gate_v416


if __name__ == "__main__":
    base.main()
