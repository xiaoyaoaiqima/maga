#!/usr/bin/env python3
"""Local Wangyue v427 light-comparison source hygiene.

Builds on v426. v426 fixed some gate semantics, but light_comparison was still
rejected because the source event generated old known risks:

- 省心 / 踏实 / 选对 / 满足感;
- 去年 / 刚三岁 old-age timeline ambiguity;
- 试喝装 product-form drift.

This version only tightens source hygiene for light_comparison.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import run_v426_wangyue_light_comparison_gate_semantics as gate_semantics


base = gate_semantics.base
base.EXPERIMENT_ID = "v427_light_comparison_source_hygiene"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)
_original_build_human_event_prompt = base._build_human_event_prompt
_original_validate_plan = base._validate_plan


def _patch_lane(lane: dict[str, Any]) -> dict[str, Any]:
    item = copy.deepcopy(lane)
    if str(item.get("event_type") or "") == "light_comparison":
        item.update(
            {
                "life_theme": (
                    "被朋友或同小区妈妈问起为什么最后选旺玥，妈妈回想前阵子简单对比过几款。"
                    "只写选择原因和孩子接受度，不写具体年份、刚三岁、试喝装、省心、踏实、选对。"
                ),
                "allowed_event_object": "儿童奶粉选择理由、简单对比记忆、孩子口味接受度、一个营养表印象。",
                "disallowed_event_object": (
                    "当前饮用现场、奶瓶、水杯、试喝装、包里露出、出门带奶粉、去年、几年前、刚三岁、"
                    "省心、踏实、满足感、选对、求推荐。"
                ),
                "risk_boundary": (
                    "不要写省心/踏实/心里有底/选对；不要写去年/几年前/刚三岁；不要写试喝装或当前可见饮用物。"
                    "接受度证据只写成当时选择理由。"
                ),
                "natural_stop_hint": "停在当时为什么留下旺玥，或孩子接受这个口味的一个记忆点。",
            }
        )
    return item


base.EVENT_TYPE_POOL = [_patch_lane(lane) for lane in _previous_pool]


def _build_human_event_prompt_v427(row: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_human_event_prompt(row, index))
    event_type = str((payload.get("event_type_plan") or {}).get("event_type") or "")
    if event_type == "light_comparison":
        payload["light_comparison_source_hygiene"] = (
            "本篇不要出现：去年、几年前、刚三岁、试喝装、省心、踏实、选对、满足感、心里有底、求推荐。"
            "只写被问起选择原因，回想当时比较过几款，最后因为孩子接受度或一个营养表印象留下旺玥。"
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v427(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    if _event_type(plan) != "light_comparison":
        return valid, issues
    text = _plan_text(plan)
    extra: list[str] = []
    if re.search(r"(省心|踏实|心里有底|选对|满足感)", text):
        extra.append("light_comparison_closure_source_drift")
    if re.search(r"(去年|几年前|两年前|三年前|刚三岁|刚满三岁)", text):
        extra.append("light_comparison_age_timeline_source_drift")
    if re.search(r"(试喝装|奶瓶|水杯|包里|便携|小包|条装|随身)", text):
        extra.append("light_comparison_product_form_source_drift")
    final = sorted(set([*issues, *extra]))
    return not final, final


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
                    "emotional_impulse",
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


base._build_human_event_prompt = _build_human_event_prompt_v427
base._validate_plan = _validate_plan_v427


if __name__ == "__main__":
    base.main()
