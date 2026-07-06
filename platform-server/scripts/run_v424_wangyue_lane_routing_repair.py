#!/usr/bin/env python3
"""Local Wangyue v424 lane-routing and repair-boundary experiment.

Builds on v423. This version tests architecture routing rather than adding
another broad style prompt:

- route most attempts through lanes that can naturally carry product seeding;
- keep shopping/nutrition as low-density diversity fillers;
- keep growth-stage as exploratory only;
- require the writer to name 旺玥 when the approved plan permits product entry.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import run_v423_wangyue_age_timeline_hard_gate as timeline


base = timeline.base
base.EXPERIMENT_ID = "v424_lane_routing_repair"


CORE_LANES = {"usage_acceptance", "choice_review", "light_comparison", "routine_arrangement"}
FILLER_LANES = {"nutrition_review", "shopping_list_restock"}
EXPLORATORY_LANES = {"growth_stage_observation"}

FIXABLE_FLAGS = {
    "missing_product",
    "business_surface_leak",
    "repeatable_closure_surface",
    "formulaic_closure",
    "formulaic_closure_surface",
}

HARD_FLAGS = {
    "forbidden",
    "body_forbidden_term",
    "title_forbidden_term",
    "age_timeline_absolute_or_multi_year",
    "age_timeline_added",
    "portable_product_form",
    "product_action_or_carrier_risk",
    "handheld_or_portable_formula_form",
    "growth_stage_product_proof",
    "growth_claim_bridge_mismatch",
    "direct_causality",
}


_original_event_type_pool = copy.deepcopy(base.EVENT_TYPE_POOL)
_original_build_writer_prompt = base._build_writer_prompt
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality


def _lane(name: str) -> dict[str, Any]:
    for item in _original_event_type_pool:
        if item.get("event_type") == name:
            return copy.deepcopy(item)
    raise KeyError(name)


def _with_updates(name: str, **updates: Any) -> dict[str, Any]:
    item = _lane(name)
    item.update(updates)
    return item


base.EVENT_TYPE_POOL = [
    _with_updates(
        "usage_acceptance",
        route_role="core",
        route_reason="孩子当场接受是最自然的产品证明。",
        natural_stop_hint="停在孩子的原话、表情或又尝一口；不写长期喝法。",
    ),
    _with_updates(
        "choice_review",
        route_role="core",
        route_reason="选择复盘天然允许产品和一个选择理由出现。",
        life_theme="翻到近阶段的聊天、截图或备忘录，想起当时给孩子选儿童奶粉时认真比较过。",
        natural_stop_hint="停在现在回看那个选择，不写具体年份或几年前。",
    ),
    _with_updates(
        "light_comparison",
        route_role="core",
        route_reason="轻对比允许旺玥作为最后留下的选择。",
        natural_stop_hint="停在孩子接受度、口味或一个普通状态观察；正文必须出现旺玥。",
    ),
    _with_updates(
        "routine_arrangement",
        route_role="core",
        route_reason="被问起家里喝什么时，产品有自然进入资格。",
        risk_boundary="不要写便携、手里拿奶粉、包里露出奶粉罐；不要写固定喝法。",
    ),
    _with_updates(
        "usage_acceptance",
        route_role="core",
        route_reason="重复增加核心强种草 lane 的权重。",
        natural_stop_hint="停在孩子这一次的接受反应，不写每天/早晚/固定。",
    ),
    _with_updates(
        "choice_review",
        route_role="core",
        route_reason="重复增加可承载卖点的复盘 lane 权重。",
        life_theme="被朋友问起或翻到近阶段记录，想起当时为什么最后选旺玥。",
        natural_stop_hint="停在当下回想，不写具体年份、几年前或从小。",
    ),
    _with_updates(
        "nutrition_review",
        route_role="filler",
        route_reason="只做低密度生活纹理，不承担主种草。",
        product_entry_role="产品只作为饭桌/厨房日常里被顺带想起的一项。",
        risk_boundary="不要写固定喝法、孩子提醒喝奶、产品解决营养焦虑。",
    ),
    _with_updates(
        "shopping_list_restock",
        route_role="filler",
        route_reason="只做低密度多样性，不承担效果证明。",
        product_entry_role="产品只作为清单上的一个名字出现。",
        risk_boundary="不要写孩子要喝、快没了、囤货、回购、常备项、效果证明。",
    ),
    _with_updates(
        "growth_stage_observation",
        route_role="exploratory",
        route_reason="高风险探索 lane；产品不承接成长证明。",
        product_entry_eligible=False,
        product_entry_role="默认不进入；除非事件本身已有明确日常营养复盘。",
        risk_boundary="不要把旺玥接到长高、长肉、结实、衣服短、饭量大、跑跳有劲。",
    ),
    _with_updates("pure_child_sentence", route_role="negative_control"),
    _with_updates("home_mess_loop", route_role="negative_control"),
    _with_updates("pure_playground_moment", route_role="negative_control"),
]


def _build_writer_prompt_v424(
    row: dict[str, Any],
    plan: dict[str, Any],
    *,
    plan_valid: bool,
    plan_issues: list[str],
) -> str:
    payload = json.loads(_original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues))
    event_type = _event_type(plan)
    payload["lane_route"] = {
        "event_type": event_type,
        "role": _route_role(event_type),
        "core_lanes": sorted(CORE_LANES),
        "filler_lanes": sorted(FILLER_LANES),
        "exploratory_lanes": sorted(EXPLORATORY_LANES),
    }
    if _permission_true(plan.get("product_permission")):
        payload["brand_presence_contract"] = (
            "正文必须自然出现“旺玥”至少一次；不要全程用这个/这款/它替代。"
            "如果只写这款但不写旺玥，本篇不可用。"
        )
    payload["repair_boundary"] = (
        "可修的是漏品牌名、轻微公式收口、内部业务词露出；"
        "不可修且必须避开的是低龄/旧年份履历、便携奶粉形态、禁词、产品承接成长证明。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v424(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    text = _plan_relevant_text(plan)
    event_type = _event_type(plan)
    if event_type in EXPLORATORY_LANES and _permission_true(plan.get("product_permission")):
        if _growth_proof_risk(text):
            issues = [*issues, "exploratory_growth_lane_product_risk"]
    if _near_stage_timeline_risk(text):
        issues = [*issues, "near_stage_timeline_risk"]
    return not issues, sorted(set(issues))


def _local_quality_v424(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = list(quality.get("flags", []))
    if _permission_true(plan.get("product_permission")) and "旺玥" not in f"{title}\n{body}":
        flags.append("missing_product")
    if _near_stage_timeline_risk(f"{title}\n{body}"):
        flags.append("near_stage_timeline_risk")
    flags = sorted(set(flags))
    quality["flags"] = flags

    if any(flag in HARD_FLAGS or flag.startswith("forbidden:") for flag in flags):
        quality["hard_pass"] = False
        quality["business_tier"] = "hard_reject"
        quality["business_reason"] = "硬风险：" + "；".join(flags)
    elif any(flag in FIXABLE_FLAGS for flag in flags):
        quality["hard_pass"] = False
        quality["business_tier"] = "repairable"
        quality["business_reason"] = "可修复问题：" + "；".join(flags)
    else:
        quality["hard_pass"] = True
        quality["business_tier"] = "direct_pool"
        quality["business_reason"] = "本地架构实验粗审通过"
    return quality


def _event_type(plan: dict[str, Any]) -> str:
    return str(((plan.get("human_event") or {}).get("event_type") or "")).strip()


def _route_role(event_type: str) -> str:
    if event_type in CORE_LANES:
        return "core"
    if event_type in FILLER_LANES:
        return "filler"
    if event_type in EXPLORATORY_LANES:
        return "exploratory"
    return "negative_control"


def _permission_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


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


def _growth_proof_risk(text: str) -> bool:
    return bool(
        re.search(r"(长高|长肉|结实|有力|跑跳有劲|衣服短|裤子短|饭量大|两碗饭|没饱)", text)
        and re.search(r"(旺玥|儿童奶粉|奶粉|营养)", text)
    )


def _near_stage_timeline_risk(text: str) -> bool:
    return bool(re.search(r"(去年|上年|前两年|前几年).{0,24}(选|喝|定|换|旺玥|奶粉)", text))


base._build_writer_prompt = _build_writer_prompt_v424
base._validate_plan = _validate_plan_v424
base._local_quality = _local_quality_v424


if __name__ == "__main__":
    base.main()
