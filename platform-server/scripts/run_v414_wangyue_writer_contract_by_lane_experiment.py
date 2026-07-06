#!/usr/bin/env python3
"""Local Wangyue writer-contract-by-lane experiment.

Builds on v413. The planner is intentionally unchanged; this tests whether the
writer can obey each product-entry lane's strength and boundary instead of
auto-completing fixed usage, formulaic closure, or growth causality.
"""

from __future__ import annotations

import json
from typing import Any

import run_v413_wangyue_emotion_lane_compatibility_experiment as compat


base = compat.base
base.EXPERIMENT_ID = "v414_writer_contract_by_lane"


LANE_WRITER_CONTRACTS: dict[str, dict[str, str]] = {
    "choice_review": {
        "strength": "中强种草。可以写最后选择了旺玥和一个选择理由。",
        "must_keep": "像一次回看当初选择的发帖，不写成完整测评。",
        "must_not_add": "不要补固定喝法、安心省心收口、值了/选对了总结、第二个效果证明。",
    },
    "nutrition_review": {
        "strength": "中强种草。可以写日常营养记录和一个正向状态观察。",
        "must_keep": "旺玥是日常营养安排里被提到的一项，正文仍要围绕饭桌或家里营养观察。",
        "must_not_add": "不要写每天一杯、晚饭后固定喝、吃睡玩全都稳、🍼、管理备忘录收口。",
    },
    "routine_arrangement": {
        "strength": "中等种草。可以写家里在喝旺玥和一个自然理由。",
        "must_keep": "像被问起后顺口说清楚，而不是主动做产品介绍。",
        "must_not_add": "不要写固定杯数、早晚安排、长期流程、安心省心结论。",
    },
    "growth_stage_observation": {
        "strength": "弱到中等种草。只把旺玥放在阶段营养背景里。",
        "must_keep": "成长变化可以写，但不能让旺玥解释成长变化。",
        "must_not_add": "不要写长肉、长高、结实、成长小信号、乳铁蛋白导致身体变化、每天都会喝。",
    },
    "shopping_list_restock": {
        "strength": "轻种草。产品可以只是清单项或生活背景。",
        "must_keep": "这条 lane 的作用是稀释广告感，不强求卖点展开。",
        "must_not_add": "不要写回购、囤货、见底焦虑、必须补上、常备总结。",
    },
    "usage_acceptance": {
        "strength": "强种草。重点写孩子接受度、口味反应、妈妈意外。",
        "must_keep": "产品价值来自孩子当下接受，不需要成分解释。",
        "must_not_add": "不要写每天主动喝、固定喝法、喝完整杯、功效解释、夸张惊喜。",
    },
    "light_comparison": {
        "strength": "中强种草。可以写简单对比后最后选择了旺玥。",
        "must_keep": "只保留一个选择理由或一个接受度观察。",
        "must_not_add": "不要写选对了、省心、不纠结、值了、完整测评、攻击竞品。",
    },
}


base.WRITER_SYSTEM = base.WRITER_SYSTEM.replace(
    "- 正文自然出现旺玥，产品价值要写到位；强弱跟着 approved_story_plan.product_bridge.product_role，不要把 source_row 里的素材逐项覆盖。",
    "- 正文自然出现旺玥，产品价值要写到位；强弱跟着 lane_writer_contract，不要把 source_row 里的素材逐项覆盖。",
)

base.WRITER_SYSTEM = base.WRITER_SYSTEM.replace(
    "- 不要把主线没有写的固定喝法、回购、继续喝、安心省心总结、第二个效果证明补进去。",
    "- 不要把主线没有写的固定喝法、回购、继续喝、安心省心总结、第二个效果证明补进去。\n"
    "- lane_writer_contract 的 must_not_add 是本篇写作边界；如果和 source_row 或 approved_story_plan 冲突，以 lane_writer_contract 为准。",
)


_original_build_writer_prompt = base._build_writer_prompt


def _build_writer_prompt_by_lane(
    row: dict[str, Any],
    plan: dict[str, Any],
    *,
    plan_valid: bool,
    plan_issues: list[str],
) -> str:
    payload = json.loads(_original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues))
    event_type = str(((plan.get("human_event") or {}).get("event_type") or "")).strip()
    payload["lane_writer_contract"] = LANE_WRITER_CONTRACTS.get(
        event_type,
        {
            "strength": "按 approved_story_plan 写，不额外增强种草。",
            "must_keep": "只沿当前主线写。",
            "must_not_add": "不要新增产品动作、固定喝法、公式收口或第二条生活入口。",
        },
    )
    payload["writer_task"] = (
        "把 approved_story_plan 写成一篇 120-180 字左右的小红书妈妈UGC正向种草笔记。"
        "先看 lane_writer_contract，再写正文。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


base._build_writer_prompt = _build_writer_prompt_by_lane

base.FIDELITY_PATTERNS["growth_causality_added"] = [
    r"成长的小信号",
    r"旺玥.{0,24}(长肉|长高|结实|抱起来|撑起来|有劲)",
    r"(长肉|长高|结实|抱起来|撑起来|有劲).{0,24}旺玥",
]


if __name__ == "__main__":
    base.main()
