#!/usr/bin/env python3
"""Local Wangyue bridge-contract-by-lane experiment.

Builds on v416. The writer contract and usage-trial gate semantics stay intact.
This version changes product_bridge strength by lane, so light lanes are not
upgraded into usage/effect-proof chains before writing.
"""

from __future__ import annotations

import json
from typing import Any

import run_v416_wangyue_usage_trial_gate_semantics as usage_gate


base = usage_gate.base
base.EXPERIMENT_ID = "v418_bridge_contract_by_lane"


BRIDGE_LANE_CONTRACTS: dict[str, dict[str, str]] = {
    "choice_review": {
        "product_strength": "中强。可以写最后选择了旺玥、一个选择理由、一个现在的普通观察。",
        "allowed_bridge": "朋友问起或翻旧记录 -> 回想当初对比 -> 最后选旺玥。",
        "must_not_bridge": "不写三年前/几年前的模糊年龄履历；不写完整测评闭环；不把产品变成解决问题的答案。",
    },
    "nutrition_review": {
        "product_strength": "中等。旺玥是日常营养安排中的一项，可以有一个普通状态观察。",
        "allowed_bridge": "饭桌/厨房/日常营养片段 -> 想到家里在喝旺玥 -> 一个温和观察。",
        "must_not_bridge": "不规划每天早餐/每天都喝/晚饭后冲/固定流程；不把营养安排写成管理任务。",
    },
    "routine_arrangement": {
        "product_strength": "中等偏轻。被问起时说家里喝旺玥，可以给一个自然理由。",
        "allowed_bridge": "别人问起 -> 顺口说旺玥 -> 一个选择理由或接受度。",
        "must_not_bridge": "不写固定喝、一直这么用、每天、早晚、常规流程；不写安心省心总结。",
    },
    "growth_stage_observation": {
        "product_strength": "弱。只可作为阶段营养背景，不承接成长证明。",
        "allowed_bridge": "成长观察 -> 妈妈顺带提阶段营养有留意。",
        "must_not_bridge": "不写陪伴成长、见证成长、长肉长高结实、裤子短、饭量大由产品承接。",
    },
    "shopping_list_restock": {
        "product_strength": "轻。产品只是清单项或备忘录里的一个名字。",
        "allowed_bridge": "购物清单/备忘录 -> 写下旺玥或儿童奶粉。",
        "must_not_bridge": "不写冲一杯、泡一杯、孩子喝、喝完、接受度、精神头、饭量活动量、效果证明、复购囤货。",
    },
    "usage_acceptance": {
        "product_strength": "强。产品价值由一次试喝接受度自然证明。",
        "allowed_bridge": "孩子闻/抿/尝/喝一口的反应 -> 旺玥作为被接受的儿童奶粉。",
        "must_not_bridge": "不写每天主动喝、固定喝法、奶瓶、便携、小包、功效解释。",
    },
    "light_comparison": {
        "product_strength": "中强。可以写简单对比后留下旺玥，理由是孩子接受或基础营养合适。",
        "allowed_bridge": "被问选择原因 -> 简单对比 -> 旺玥被留下。",
        "must_not_bridge": "不写奶瓶、喝完奶瓶、每次都、完整测评、攻击竞品、选对了省心。",
    },
}


base.PRODUCT_BRIDGE_SYSTEM = base.PRODUCT_BRIDGE_SYSTEM.replace(
    "- 强种草可以正面，但产品价值必须顺着 human_event 和 event_type_plan.product_value_role 进入。",
    "- 强种草可以正面，但产品价值必须顺着 human_event、event_type_plan.product_value_role 和 bridge_lane_contract 进入。",
)

base.PRODUCT_BRIDGE_SYSTEM = base.PRODUCT_BRIDGE_SYSTEM.replace(
    "- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。",
    "- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。\n"
    "- bridge_lane_contract 的 must_not_bridge 是本篇桥接边界；不要为了补种草力越过它。",
)


_original_build_bridge_prompt = base._build_bridge_prompt


def _build_bridge_prompt_v418(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_bridge_prompt(row, human_event, index))
    event_type = str(human_event.get("event_type") or "")
    payload["bridge_lane_contract"] = BRIDGE_LANE_CONTRACTS.get(
        event_type,
        {
            "product_strength": "按 event_type_plan 判断，不额外增强。",
            "allowed_bridge": "只顺着已批准的人类事件判断。",
            "must_not_bridge": "不新增使用动作、效果证明或第二生活入口。",
        },
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


base._build_bridge_prompt = _build_bridge_prompt_v418

_original_validate_plan = base._validate_plan


def _validate_plan_v418(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    human_event = plan.get("human_event") or {}
    event_type = str(human_event.get("event_type") or "")
    bridge_text = json.dumps({
        key: plan.get(key)
        for key in (
            "storyline",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)
    product_bridge_text = json.dumps(plan.get("product_bridge") or {}, ensure_ascii=False)
    if event_type == "shopping_list_restock":
        overupgrade_terms = ["冲", "泡", "喝完", "喝着顺", "精神头", "饭量", "活动量", "接受度", "效果", "复购", "囤"]
        if any(term in bridge_text for term in overupgrade_terms):
            issues = [*issues, "shopping_list_bridge_overupgraded"]
    if event_type == "light_comparison":
        if any(term in product_bridge_text for term in ("奶瓶", "小包", "便携", "一包", "条装")):
            issues = [*issues, "product_form_in_bridge"]
    if event_type == "growth_stage_observation":
        if any(term in bridge_text for term in ("陪伴成长", "见证成长", "陪他度过", "长肉", "长高", "结实")):
            issues = [*issues, "growth_bridge_overupgraded"]
    return not issues, issues


base._validate_plan = _validate_plan_v418


if __name__ == "__main__":
    base.main()
