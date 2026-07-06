#!/usr/bin/env python3
"""Local Wangyue bridge-contract gate cleanup experiment.

Builds on v418. It keeps bridge contracts and only cleans two discovered issues:

- shopping-list lanes may use neutral 儿童奶粉/奶粉 category wording.
- light-comparison lanes must not use digestion/health-status proof.
"""

from __future__ import annotations

import json
from typing import Any

import run_v418_wangyue_bridge_contract_by_lane as bridge_contract


base = bridge_contract.base
base.EXPERIMENT_ID = "v419_bridge_contract_gate_cleanup"

bridge_contract.BRIDGE_LANE_CONTRACTS["light_comparison"]["must_not_bridge"] = (
    "不写奶瓶、喝完奶瓶、每次都、完整测评、攻击竞品、选对了省心；"
    "不把选择理由落到便便、消化、肚子、身体小状况或健康状态。"
)

_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality


def _validate_plan_v419(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    human_event = plan.get("human_event") or {}
    event_type = str(human_event.get("event_type") or "")
    if event_type == "shopping_list_restock":
        issues = _relax_shopping_list_neutral_category(issues, plan)
    if event_type == "light_comparison":
        issues = _add_health_proof_issue(issues, plan)
    return not issues, issues


def _relax_shopping_list_neutral_category(issues: list[str], plan: dict[str, Any]) -> list[str]:
    human_event = plan.get("human_event") or {}
    human_text = str(human_event.get("human_event") or "")
    disallowed = ["快见底", "见底", "必须补", "快喝完", "囤"]
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


def _add_health_proof_issue(issues: list[str], plan: dict[str, Any]) -> list[str]:
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
    health_terms = ["便便", "排便", "消化", "肚子", "拉肚子", "小状况", "少生病", "不生病"]
    if any(term in text for term in health_terms):
        return [*issues, "health_status_proof_in_light_comparison"]
    return issues


def _local_quality_v419(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    event_type = str(((plan.get("human_event") or {}).get("event_type") or ""))
    if event_type == "light_comparison":
        text = f"{title}\n{body}"
        if any(term in text for term in ("便便", "排便", "消化", "肚子", "拉肚子", "小状况", "少生病", "不生病")):
            quality["flags"].append("health_status_proof_in_light_comparison")
            quality["hard_pass"] = False
            quality["business_tier"] = "needs_manual_review"
            quality["business_reason"] = "health_status_proof_in_light_comparison"
    return quality


base._validate_plan = _validate_plan_v419
base._local_quality = _local_quality_v419


if __name__ == "__main__":
    base.main()
