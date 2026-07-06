#!/usr/bin/env python3
"""Local Wangyue v428 form and light-comparison source cleanup.

Builds on v427. This version only addresses two concrete failures exposed by
v427:

- Wangyue product-form drift such as trial packs or a small formula bag;
- light_comparison source workarounds such as describing that the child had
  nothing in hand before another mother asked about milk powder.

It does not change the production baseline or broaden style instructions.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v427_wangyue_light_comparison_source_hygiene as source_hygiene


base = source_hygiene.base
base.EXPERIMENT_ID = "v428_form_and_light_source_cleanup"


_original_build_human_event_prompt = base._build_human_event_prompt
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _build_human_event_prompt_v428(row: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_human_event_prompt(row, index))
    event_type = str((payload.get("event_type_plan") or {}).get("event_type") or "")
    if event_type == "light_comparison":
        payload["light_comparison_source_hygiene"] = (
            str(payload.get("light_comparison_source_hygiene") or "")
            + " 被问起可以来自聊天、朋友顺口问、评论里问或小区闲聊；"
            "不需要描写孩子手里有没有杯子、奶粉或东西。"
        ).strip()
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v428(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    text = _plan_text(plan)
    extra: list[str] = []
    if _wangyue_formula_form_risk(text):
        extra.append("wangyue_formula_form_source_drift")
    if _event_type(plan) == "light_comparison" and _empty_hand_workaround(text):
        extra.append("light_comparison_empty_hand_workaround")
    final = sorted(set([*issues, *extra]))
    return not final, final


def _local_quality_v428(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = list(quality.get("flags", []))
    text = f"{title}\n{body}"
    if _wangyue_formula_form_risk(text):
        flags.append("wangyue_formula_form_added")
    if _event_type(plan) == "light_comparison" and _empty_hand_workaround(text):
        flags.append("light_comparison_empty_hand_workaround_added")
    quality["flags"] = sorted(set(flags))
    if quality["flags"]:
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    else:
        quality["hard_pass"] = True
        quality["business_tier"] = "direct_pool"
        quality["business_reason"] = "本地架构实验粗审通过"
    return quality


def _fidelity_gate_v428(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    flags = list(result.get("flags", []))
    text = f"{title}\n{body}"
    if _wangyue_formula_form_risk(text):
        flags.append("wangyue_formula_form_added")
    if _event_type(plan) == "light_comparison" and _empty_hand_workaround(text):
        flags.append("light_comparison_empty_hand_workaround_added")
    result["flags"] = sorted(set(flags))
    result["pass"] = not result["flags"]
    return result


def _event_type(plan: dict[str, Any]) -> str:
    return str(((plan.get("human_event") or {}).get("event_type") or "")).strip()


def _plan_text(plan: dict[str, Any]) -> str:
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
                    "no_product_post",
                )
            },
            "product_bridge": {
                key: product_bridge.get(key)
                for key in (
                    "permission_reason",
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


def _wangyue_formula_form_risk(text: str) -> bool:
    return bool(
        re.search(r"(试喝装|小袋装|奶粉袋|奶粉小袋|小袋.{0,8}(奶粉|儿童奶粉)|装.{0,8}(儿童奶粉|奶粉).{0,8}小袋)", text)
    )


def _empty_hand_workaround(text: str) -> bool:
    return bool(re.search(r"(手里空空|手里没拿|没拿东西|空着手).{0,24}(问|奶粉|喝什么)", text))


base._build_human_event_prompt = _build_human_event_prompt_v428
base._validate_plan = _validate_plan_v428
base._local_quality = _local_quality_v428
base._fidelity_gate = _fidelity_gate_v428


if __name__ == "__main__":
    base.main()
