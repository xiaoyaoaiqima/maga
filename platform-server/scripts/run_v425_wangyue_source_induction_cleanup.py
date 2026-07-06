#!/usr/bin/env python3
"""Local Wangyue v425 source-induction cleanup.

Builds on v424. This version does not add broad style rules. It only fixes the
source event induction that made light_comparison/routine_arrangement drift
into visible cup/bottle/portable-form scenes before writing.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import run_v424_wangyue_lane_routing_repair as routing


base = routing.base
base.EXPERIMENT_ID = "v425_source_induction_cleanup"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)
_original_build_human_event_prompt = base._build_human_event_prompt
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality


def _patched_lane(lane: dict[str, Any]) -> dict[str, Any]:
    item = copy.deepcopy(lane)
    event_type = str(item.get("event_type") or "")
    if event_type == "light_comparison":
        item.update(
            {
                "life_theme": (
                    "被朋友或同小区妈妈问起为什么最后选这款儿童奶粉，妈妈回想当时简单对比过几款。"
                    "问题来自聊天里的选择原因，不来自孩子当场拿杯子、奶瓶或奶粉罐。"
                ),
                "allowed_event_object": "儿童奶粉选择理由、简单对比记忆、口味/营养表/孩子接受度的回看。",
                "disallowed_event_object": "现场正在喝、手里拿杯子、水杯、奶瓶、包里露出奶粉罐、出门带奶粉。",
                "risk_boundary": "不要写当前可见饮用物；不要写奶瓶/水杯/手里拿/包里露出；不要完整测评。",
                "natural_stop_hint": "停在回忆当时为什么留下旺玥，或一个自家接受度观察。",
            }
        )
    elif event_type == "routine_arrangement":
        item.update(
            {
                "life_theme": (
                    "接娃、楼下闲聊或家人随口问起家里儿童奶粉怎么选，妈妈顺口说出家里喝的那款。"
                    "对话来自选择话题，不来自别人看到孩子手里的杯子、奶瓶或包里的奶粉罐。"
                ),
                "allowed_event_object": "被问起家里儿童奶粉选择、日常选择被顺口说出来。",
                "disallowed_event_object": "现场手持饮品、可见奶粉罐、包里露出、出门携带、固定喝法。",
                "risk_boundary": "不要写便携、手里拿奶粉、水杯、奶瓶、包里露出奶粉罐；不要写每天固定喝。",
            }
        )
    elif event_type == "nutrition_review":
        item.update(
            {
                "life_theme": (
                    "饭桌或厨房的小插曲让妈妈想到家里儿童奶粉也是日常的一项；"
                    "不是因为孩子不吃菜、挑食或某顿饭失败才用产品补救。"
                ),
                "risk_boundary": "不要写孩子拒绝蔬菜/饭菜后用旺玥补上；不要写营养也够了、产品解决营养焦虑。",
                "natural_stop_hint": "停在擦桌子、收碗、孩子跑去玩；产品只轻带，不做答案。",
            }
        )
    return item


base.EVENT_TYPE_POOL = [_patched_lane(lane) for lane in _previous_pool]


def _build_human_event_prompt_v425(row: dict[str, Any], index: int) -> str:
    prompt = json.loads(_original_build_human_event_prompt(row, index))
    event_type_plan = prompt.get("event_type_plan") or {}
    event_type = str(event_type_plan.get("event_type") or "")
    if event_type in {"light_comparison", "routine_arrangement"}:
        prompt["source_induction_boundary"] = (
            "本篇的发帖触发是别人问选择原因或家里怎么选，不是看到孩子正在喝。"
            "human_event 不要出现奶瓶、水杯、杯子里泡奶粉、手里拿奶粉、包里露出奶粉罐、出门带奶粉。"
        )
    elif event_type == "nutrition_review":
        prompt["source_induction_boundary"] = (
            "本篇不是用奶粉补救一顿饭，也不是孩子不吃菜后的解决方案。"
            "饭桌/厨房只提供生活触发，旺玥不能成为营养焦虑答案。"
        )
    return json.dumps(prompt, ensure_ascii=False, indent=2)


def _validate_plan_v425(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    text = _plan_relevant_text(plan)
    event_type = _event_type(plan)
    if event_type in {"light_comparison", "routine_arrangement"} and _visible_drinking_scene(text):
        issues = [*issues, "visible_drinking_scene_source_drift"]
    if event_type == "nutrition_review" and _nutrition_fix_drift(text):
        issues = [*issues, "nutrition_fix_source_drift"]
    return not issues, sorted(set(issues))


def _local_quality_v425(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    text = f"{title}\n{body}"
    event_type = _event_type(plan)
    flags = list(quality.get("flags", []))
    if event_type in {"light_comparison", "routine_arrangement"} and _visible_drinking_scene(text):
        flags.append("visible_drinking_scene_source_drift")
    if event_type == "nutrition_review" and _nutrition_fix_drift(text):
        flags.append("nutrition_fix_source_drift")
    if flags:
        quality["flags"] = sorted(set(flags))
        if any(flag in {"visible_drinking_scene_source_drift", "nutrition_fix_source_drift"} for flag in flags):
            quality["hard_pass"] = False
            quality["business_tier"] = "source_drift"
            quality["business_reason"] = "源头事件偏移：" + "；".join(quality["flags"])
    return quality


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


def _visible_drinking_scene(text: str) -> bool:
    return bool(
        re.search(r"(奶瓶|水杯|杯子里|手里.{0,8}(杯|奶粉|罐)|包里.{0,12}(奶粉|罐)|出门.{0,16}(奶粉|冲好|泡好))", text)
    )


def _nutrition_fix_drift(text: str) -> bool:
    meal_problem = re.search(r"(不吃|拒绝|推开|挑食|没吃|剩饭|剩菜|饭菜)", text)
    fix_language = re.search(r"(补上|补一补|营养也够|营养够了|解决|顶上|靠.{0,8}旺玥|旺玥.{0,12}(补|够|解决))", text)
    return bool(meal_problem and fix_language)


base._build_human_event_prompt = _build_human_event_prompt_v425
base._validate_plan = _validate_plan_v425
base._local_quality = _local_quality_v425


if __name__ == "__main__":
    base.main()
