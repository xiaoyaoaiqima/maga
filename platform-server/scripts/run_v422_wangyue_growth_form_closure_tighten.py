#!/usr/bin/env python3
"""Local Wangyue v422 diagnostic tightening.

Builds on v421. This version only tightens issues observed in the v421 20-item
sample:

- growth-stage posts must not let 旺玥 carry clothing-size / body-growth proof;
- portable or hand-held formula forms are flagged earlier;
- formulaic closure includes 心里一松;
- shopping-list bridge can use the list action itself as positive evidence,
  without adding product experience proof.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v421_wangyue_hybrid_surface_and_form_gate as hybrid


base = hybrid.base
base.EXPERIMENT_ID = "v422_growth_form_closure_tighten"


ADDITIONAL_FORM_PATTERNS = [
    r"手里.{0,10}(奶粉|旺玥|奶粉罐|罐子)",
    r"(奶粉|旺玥|奶粉罐|罐子).{0,10}手里",
    r"包里.{0,16}(奶粉|旺玥|奶粉罐|罐子)",
    r"水杯.{0,16}(奶粉|旺玥)",
]

GROWTH_STAGE_PROOF_PATTERNS = [
    r"(外套|裤子|袖子|衣服).{0,16}(短|小|穿不下)",
    r"(长大|长高|长肉|结实|有力|跑跳有劲|饭量上来|吃了两碗|没饱)",
]

FORMULAIC_CLOSURE_PATTERNS = [
    r"心里一松",
    r"老母亲心里一松",
    r"功夫没白(做|费)",
    r"都有回声",
]


_original_build_bridge_prompt = base._build_bridge_prompt
_original_validate_plan = base._validate_plan
_original_build_writer_prompt = base._build_writer_prompt
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _build_bridge_prompt_v422(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_bridge_prompt(row, human_event, index))
    if str(human_event.get("event_type") or "") == "shopping_list_restock":
        payload["bridge_lane_contract"] = {
            "product_strength": "轻。旺玥可以作为清单/备忘录里的一个名字出现。",
            "allowed_bridge": "购物清单/备忘录里写到儿童奶粉 -> 具体到旺玥这个名字。",
            "must_not_bridge": (
                "positive_evidence 只能写清单动作本身，例如被写进清单；"
                "不写孩子喝、喝完、接受度、精神头、饭量活动量、效果证明、常备项、回购或囤货。"
            ),
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt_v422(
    row: dict[str, Any],
    plan: dict[str, Any],
    *,
    plan_valid: bool,
    plan_issues: list[str],
) -> str:
    payload = json.loads(_original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues))
    payload["surface_negative_examples"] = (
        "不要用这些可复制收口或载体：心里一松、功夫没白费、都有回声、"
        "手里拿着奶粉、包里露出奶粉罐、水杯里泡好的奶粉。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v422(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    text = _plan_relevant_text(plan)
    event_type = _event_type(plan)
    if _pattern_hits(text, ADDITIONAL_FORM_PATTERNS):
        issues = [*issues, "handheld_or_portable_formula_form_in_plan"]
    if event_type == "growth_stage_observation" and _pattern_hits(text, GROWTH_STAGE_PROOF_PATTERNS):
        if "旺玥" in text or "儿童奶粉" in text or "奶粉" in text:
            issues = [*issues, "growth_stage_product_proof_in_plan"]
    return not issues, sorted(set(issues))


def _local_quality_v422(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    text = f"{title}\n{body}"
    extra_flags: list[str] = []
    if _pattern_hits(text, ADDITIONAL_FORM_PATTERNS):
        extra_flags.append("handheld_or_portable_formula_form")
    if _event_type(plan) == "growth_stage_observation" and _pattern_hits(text, GROWTH_STAGE_PROOF_PATTERNS):
        extra_flags.append("growth_stage_product_proof")
    if _pattern_hits(body[-60:], FORMULAIC_CLOSURE_PATTERNS):
        extra_flags.append("formulaic_closure_surface")
    if extra_flags:
        quality["flags"] = sorted(set([*quality.get("flags", []), *extra_flags]))
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    return quality


def _fidelity_gate_v422(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    text = f"{title}\n{body}"
    flags = list(result.get("flags", []))
    if _pattern_hits(text, ADDITIONAL_FORM_PATTERNS):
        flags.append("handheld_or_portable_formula_form_added")
    if _event_type(plan) == "growth_stage_observation" and _pattern_hits(text, GROWTH_STAGE_PROOF_PATTERNS):
        flags.append("growth_stage_product_proof_added")
    if _pattern_hits(body[-60:], FORMULAIC_CLOSURE_PATTERNS):
        flags.append("formulaic_closure_surface_added")
    result["flags"] = sorted(set(flags))
    result["pass"] = not result["flags"]
    return result


def _event_type(plan: dict[str, Any]) -> str:
    return str(((plan.get("human_event") or {}).get("event_type") or "")).strip()


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


def _pattern_hits(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text)]


base._build_bridge_prompt = _build_bridge_prompt_v422
base._build_writer_prompt = _build_writer_prompt_v422
base._validate_plan = _validate_plan_v422
base._local_quality = _local_quality_v422
base._fidelity_gate = _fidelity_gate_v422


if __name__ == "__main__":
    base.main()
