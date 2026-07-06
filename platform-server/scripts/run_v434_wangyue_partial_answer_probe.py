#!/usr/bin/env python3
"""Local Wangyue v434 partial-answer probe.

v433 improved valid generation by shifting weight toward choice/reason lanes,
but the output became too much like "being asked -> explain sell point -> add
child status". This probe keeps the v433 mix and adds a partial-answer
constraint for choice, routine, and light-comparison lanes.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import run_v433_wangyue_product_reason_heavy_mix_probe as reason_mix


base = reason_mix.base
base.EXPERIMENT_ID = "v434_partial_answer_probe"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)
_original_build_bridge_prompt = base._build_bridge_prompt
_original_build_writer_prompt = base._build_writer_prompt


def _patch_lane(item: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(item)
    event_type = str(clone.get("event_type") or "")
    if event_type == "choice_review":
        clone.update(
            {
                "partial_answer_mode": (
                    "被问起时只讲一个最顺口的理由，不把产品理由、孩子状态和妈妈总结全讲完。"
                ),
                "partial_answer_allowed": (
                    "可以只说一个配置记忆点；也可以只说孩子接受度，再轻带一个产品理由。"
                ),
                "partial_answer_forbidden": (
                    "不要连续补齐：选择理由 + 成分配置 + 孩子状态 + 选择正确总结。"
                ),
            }
        )
    elif event_type == "routine_arrangement":
        clone.update(
            {
                "partial_answer_mode": "日常问答只短答。如果孩子/家务打断，正文必须停在打断处。",
                "partial_answer_allowed": "回答里只保留产品名和一个短理由，或只保留孩子接受度。",
                "partial_answer_forbidden": "不要在打断之后继续补营养、成分、精神头或总结。",
            }
        )
    elif event_type == "light_comparison":
        clone.update(
            {
                "partial_answer_mode": "轻对比只讲一个留下它的原因，另一半留白。",
                "partial_answer_allowed": "可以是一个产品记忆点，也可以是孩子接受度。",
                "partial_answer_forbidden": "不要写成完整测评表，不要给公开选购建议。",
            }
        )
    return clone


base.EVENT_TYPE_POOL = [_patch_lane(item) for item in _previous_pool]


def _build_bridge_prompt_v434(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_bridge_prompt(row, human_event, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload["partial_answer_contract"] = {
        key: event_type_plan.get(key)
        for key in (
            "partial_answer_mode",
            "partial_answer_allowed",
            "partial_answer_forbidden",
        )
        if event_type_plan.get(key)
    }
    payload["partial_answer_use"] = (
        "如果有 partial_answer_contract，product_bridge 只规划一个最必要的产品证明。"
        "不要为了强种草把理由、成分、状态和总结全部补齐。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt_v434(row: dict[str, Any], plan: dict[str, Any], *, plan_valid: bool, plan_issues: list[str]) -> str:
    payload = json.loads(_original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues))
    event_type = str(((plan.get("human_event") or {}).get("event_type") or ""))
    if event_type in {"choice_review", "routine_arrangement", "light_comparison"}:
        payload["partial_answer_writer_contract"] = (
            "这篇不要写成完整回答。只让一个产品理由或一个孩子反馈真正落地；"
            "另一个如果出现，只能很轻。若主线里有孩子/家务/对话打断，正文停在打断处，"
            "不要在打断之后补充产品营养、成分、精神头或妈妈总结。"
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


base._build_bridge_prompt = _build_bridge_prompt_v434
base._build_writer_prompt = _build_writer_prompt_v434


if __name__ == "__main__":
    base.main()
