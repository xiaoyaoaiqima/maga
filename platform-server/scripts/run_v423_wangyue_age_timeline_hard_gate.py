#!/usr/bin/env python3
"""Local Wangyue v423 age-timeline hard gate.

Builds on v422. Adds a hard gate for absolute-year or multi-year product
selection/use history that may imply 旺玥 was used before age 3.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v422_wangyue_growth_form_closure_tighten as tighten


base = tighten.base
base.EXPERIMENT_ID = "v423_age_timeline_hard_gate"


AGE_TIMELINE_RISK_PATTERNS = [
    r"20(1\d|2[0-3])年",
    r"(两|二|三|四|五|几)年前",
    r"从小",
    r"小时候",
    r"刚断奶",
    r"刚上幼儿园",
]


_original_build_writer_prompt = base._build_writer_prompt
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _build_writer_prompt_v423(
    row: dict[str, Any],
    plan: dict[str, Any],
    *,
    plan_valid: bool,
    plan_issues: list[str],
) -> str:
    payload = json.loads(_original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues))
    payload["age_timeline_boundary"] = (
        "不要写具体年份、几年前、两年前、三年前、从小、小时候、刚断奶、刚上幼儿园等产品选择或使用履历；"
        "旺玥只按3岁以上孩子现在或近阶段的儿童奶粉语境写。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v423(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    text = _plan_relevant_text(plan)
    if _age_timeline_risk(text):
        issues = [*issues, "age_timeline_absolute_or_multi_year"]
    return not issues, sorted(set(issues))


def _local_quality_v423(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    text = f"{title}\n{body}"
    if _age_timeline_risk(text):
        quality["flags"] = sorted(set([*quality.get("flags", []), "age_timeline_absolute_or_multi_year"]))
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    return quality


def _fidelity_gate_v423(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    if _age_timeline_risk(f"{title}\n{body}"):
        result["flags"] = sorted(set([*result.get("flags", []), "age_timeline_added"]))
        result["pass"] = False
    return result


def _plan_relevant_text(plan: dict[str, Any]) -> str:
    human_event = plan.get("human_event") or {}
    product_bridge = plan.get("product_bridge") or {}
    return json.dumps(
        {
            "human_event": {
                key: human_event.get(key)
                for key in (
                    "event_type",
                    "posting_motive",
                    "posting_emotion_trigger",
                    "human_event",
                    "life_entry",
                    "natural_stop",
                )
            },
            "product_bridge": {
                key: product_bridge.get(key)
                for key in (
                    "bridge_logic",
                    "product_role",
                    "single_selling_point",
                    "positive_evidence",
                    "ending_stop",
                )
            },
            "storyline": plan.get("storyline"),
            "product_role": plan.get("product_role"),
            "single_selling_point": plan.get("single_selling_point"),
            "positive_evidence": plan.get("positive_evidence"),
            "ending_stop": plan.get("ending_stop"),
        },
        ensure_ascii=False,
    )


def _age_timeline_risk(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in AGE_TIMELINE_RISK_PATTERNS)


base._build_writer_prompt = _build_writer_prompt_v423
base._validate_plan = _validate_plan_v423
base._local_quality = _local_quality_v423
base._fidelity_gate = _fidelity_gate_v423


if __name__ == "__main__":
    base.main()
