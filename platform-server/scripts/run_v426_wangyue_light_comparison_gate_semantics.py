#!/usr/bin/env python3
"""Local Wangyue v426 light-comparison gate semantics.

Builds on v425. This version only calibrates gate semantics for
light_comparison:

- do not treat negated self_check text as product-form evidence;
- allow selection-reason causality such as "because the child accepted it,
  we left/selected 旺玥";
- keep rejecting real portable/bottle/cup scenes and true product-effect
  causality.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v425_wangyue_source_induction_cleanup as source_cleanup


base = source_cleanup.base
base.EXPERIMENT_ID = "v426_light_comparison_gate_semantics"


_original_build_bridge_prompt = base._build_bridge_prompt
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _build_bridge_prompt_v426(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_bridge_prompt(row, human_event, index))
    event_type = str(human_event.get("event_type") or "")
    if event_type == "light_comparison":
        contract = payload.get("bridge_lane_contract") or {}
        contract["must_not_bridge"] = (
            "不写奶瓶、水杯里泡好、手里拿、包里露出、便携、小包、条装、每天、早晚、固定流程、完整测评、攻击竞品。"
            "可以写一次选择记忆里的接受度证据，例如愿意喝、不抗拒、不剩、又喝一口、还要、喝得顺；"
            "这些只作为当时为什么留下旺玥的选择理由，不写成固定喝法。"
        )
        payload["bridge_lane_contract"] = contract
        payload["gate_semantics_hint"] = (
            "self_check 只写检查结论，不要堆禁止词；避免写'没有奶瓶/便携/小包'这类会污染规则扫描的否定句。"
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v426(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    event_type = _event_type(plan)
    if event_type != "light_comparison":
        return valid, issues

    filtered = list(issues)
    if "product_form_in_bridge" in filtered and not _real_product_form_risk(plan):
        filtered.remove("product_form_in_bridge")
    if "direct_causality" in filtered and _selection_reason_causality(plan) and not _true_product_effect_causality(plan):
        filtered.remove("direct_causality")
    if "fixed_usage_in_plan" in filtered and _only_acceptance_memory(plan):
        filtered.remove("fixed_usage_in_plan")
    return not filtered, sorted(set(filtered))


def _local_quality_v426(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    if _event_type(plan) != "light_comparison":
        return quality

    flags = list(quality.get("flags", []))
    text = f"{title}\n{body}"
    if "direct_causality" in flags and _selection_reason_causality_text(text) and not _true_product_effect_causality_text(text):
        flags.remove("direct_causality")
    if "product_action_or_carrier_risk" in flags and not _real_product_form_risk_text(text):
        flags.remove("product_action_or_carrier_risk")
    if "visible_drinking_scene_source_drift" in flags and not _visible_drinking_scene_text(text):
        flags.remove("visible_drinking_scene_source_drift")

    quality["flags"] = sorted(set(flags))
    if quality["flags"]:
        quality["hard_pass"] = False
        quality["business_tier"] = quality.get("business_tier") or "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    else:
        quality["hard_pass"] = True
        quality["business_tier"] = "direct_pool"
        quality["business_reason"] = "本地架构实验粗审通过"
    return quality


def _fidelity_gate_v426(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    if _event_type(plan) != "light_comparison":
        return result

    flags = list(result.get("flags", []))
    text = f"{title}\n{body}"
    if "new_usage_process_added" in flags and _only_acceptance_memory_text(text):
        flags.remove("new_usage_process_added")
    if "fixed_usage_added" in flags and _only_acceptance_memory_text(text):
        flags.remove("fixed_usage_added")
    result["flags"] = sorted(set(flags))
    result["pass"] = not result["flags"]
    return result


def _event_type(plan: dict[str, Any]) -> str:
    return str(((plan.get("human_event") or {}).get("event_type") or "")).strip()


def _core_plan_text(plan: dict[str, Any]) -> str:
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


def _real_product_form_risk(plan: dict[str, Any]) -> bool:
    return _real_product_form_risk_text(_core_plan_text(plan))


def _real_product_form_risk_text(text: str) -> bool:
    return bool(
        re.search(
            r"(奶瓶|水杯里|杯子里.{0,12}(泡|冲|奶粉|旺玥)|手里.{0,8}(拿|端).{0,8}(奶粉|奶瓶|罐|杯)|"
            r"包里.{0,12}(奶粉|罐)|便携装|随身带|小包|条装|一包|一瓶旺玥|一盒旺玥)",
            text,
        )
    )


def _visible_drinking_scene_text(text: str) -> bool:
    return bool(re.search(r"(奶瓶|水杯里|杯子里|手里.{0,8}(杯|奶粉|罐)|包里.{0,12}(奶粉|罐)|出门.{0,16}(奶粉|冲好|泡好))", text))


def _selection_reason_causality(plan: dict[str, Any]) -> bool:
    return _selection_reason_causality_text(_core_plan_text(plan))


def _selection_reason_causality_text(text: str) -> bool:
    return bool(
        re.search(
            r"(因为|因|看).*?(孩子|娃).{0,16}(接受|愿意|不抗拒|不排斥|喜欢|喝得顺|喝完|不剩|还要).*?(留下|选|定|选择).*?旺玥",
            text,
        )
        or re.search(
            r"(留下|选|定|选择).*?旺玥.{0,20}(因为|主要是).*?(孩子|娃).{0,16}(接受|愿意|不抗拒|不排斥|喜欢|喝得顺|喝完|不剩|还要)",
            text,
        )
    )


def _true_product_effect_causality(plan: dict[str, Any]) -> bool:
    return _true_product_effect_causality_text(_core_plan_text(plan))


def _true_product_effect_causality_text(text: str) -> bool:
    return bool(
        re.search(r"旺玥.{0,16}(让|使|带来|导致|改善|提升|解决|帮|帮助)", text)
        or re.search(r"(靠|多亏).{0,12}旺玥", text)
        or re.search(r"旺玥.{0,20}(长高|长肉|结实|少请假|不中招|专注|不生病)", text)
    )


def _only_acceptance_memory(plan: dict[str, Any]) -> bool:
    return _only_acceptance_memory_text(_core_plan_text(plan))


def _only_acceptance_memory_text(text: str) -> bool:
    acceptance = re.search(r"(尝|抿|喝了?一口|又喝|喝完|不剩|还要|愿意喝|接受|不抗拒|不排斥|喝得顺)", text)
    fixed = re.search(r"(每天|早晚|固定|长期|睡前|早餐奶|每到喝奶时间|一直.{0,8}(喝|这么喝)|每天早上|每天晚上)", text)
    return bool(acceptance and not fixed)


base._build_bridge_prompt = _build_bridge_prompt_v426
base._validate_plan = _validate_plan_v426
base._local_quality = _local_quality_v426
base._fidelity_gate = _fidelity_gate_v426


if __name__ == "__main__":
    base.main()
