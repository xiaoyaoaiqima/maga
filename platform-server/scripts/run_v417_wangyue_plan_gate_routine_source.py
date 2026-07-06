#!/usr/bin/env python3
"""Local Wangyue plan-gate routine-source experiment.

Builds on v416. This keeps the usage-trial gate semantics and only fixes two
plan-level issues:

- shopping-list lanes may use neutral category wording such as 儿童奶粉.
- fixed daily routine wording should be caught at plan level, not only when the
  writer adds it later.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v416_wangyue_usage_trial_gate_semantics as usage_gate


base = usage_gate.base
base.EXPERIMENT_ID = "v417_plan_gate_routine_source"

_original_validate_plan = base._validate_plan


def _validate_plan_v417(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    human_event = plan.get("human_event") or {}
    event_type = str(human_event.get("event_type") or "")
    issues = _relax_shopping_list_neutral_category(issues, plan, event_type)
    issues = _add_plan_source_routine_issues(issues, plan, event_type)
    issues = _add_growth_adjacency_issues(issues, plan, event_type)
    return not issues, issues


def _relax_shopping_list_neutral_category(
    issues: list[str],
    plan: dict[str, Any],
    event_type: str,
) -> list[str]:
    if event_type != "shopping_list_restock":
        return issues
    human_event = plan.get("human_event") or {}
    human_text = str(human_event.get("human_event") or "")
    disallowed = ["快见底", "见底", "囤", "必须补", "快喝完", "补上"]
    if any(word in human_text for word in disallowed):
        return issues
    relaxed: list[str] = []
    for issue in issues:
        if issue in {
            "human_event_contains_product:奶粉",
            "human_event_contains_product:儿童奶粉",
            "human_event_contains_product:奶粉,儿童奶粉",
        }:
            continue
        relaxed.append(issue)
    return relaxed


def _add_plan_source_routine_issues(
    issues: list[str],
    plan: dict[str, Any],
    event_type: str,
) -> list[str]:
    if event_type == "usage_acceptance":
        return issues
    story_text = json.dumps({
        key: plan.get(key)
        for key in (
            "storyline",
            "life_entry",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)
    routine_patterns = [
        r"每天.{0,12}(早餐|搭|固定|冲|泡)",
        r"早餐.{0,12}(搭|固定).{0,12}(儿童奶粉|奶粉|旺玥|这个)",
        r"晚饭后.{0,12}(冲|泡)",
        r"早晚.{0,12}(一杯|喝|冲|泡)",
        r"睡前.{0,12}(喝|冲|泡)",
    ]
    if base._pattern_hits(story_text, routine_patterns) and "fixed_routine_in_plan" not in issues:
        return [*issues, "fixed_routine_in_plan"]
    return issues


def _add_growth_adjacency_issues(
    issues: list[str],
    plan: dict[str, Any],
    event_type: str,
) -> list[str]:
    if event_type != "growth_stage_observation":
        return issues
    text = json.dumps({
        key: plan.get(key)
        for key in (
            "storyline",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)
    risky_patterns = [
        r"旺玥.{0,24}(陪|见证).{0,12}(成长|阶段)",
        r"(成长|阶段).{0,24}旺玥.{0,12}(陪|见证)",
        r"旺玥.{0,20}(长大|长肉|长高|结实)",
        r"(长大|长肉|长高|结实).{0,20}旺玥",
    ]
    if base._pattern_hits(text, risky_patterns) and "growth_product_adjacency_in_plan" not in issues:
        return [*issues, "growth_product_adjacency_in_plan"]
    return issues


_original_local_quality = base._local_quality


def _local_quality_v417(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    event_type = str(((plan.get("human_event") or {}).get("event_type") or ""))
    if event_type == "growth_stage_observation":
        text = f"{title}\n{body}"
        if re.search(r"旺玥.{0,24}(陪|见证).{0,12}(成长|阶段)", text):
            quality["flags"].append("growth_product_adjacency")
            quality["hard_pass"] = False
            quality["business_tier"] = "needs_manual_review"
            quality["business_reason"] = "growth_product_adjacency"
    return quality


base._validate_plan = _validate_plan_v417
base._local_quality = _local_quality_v417


if __name__ == "__main__":
    base.main()
