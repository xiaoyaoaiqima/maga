#!/usr/bin/env python3
"""Local Wangyue v429 production-lane mix probe.

Builds on v428. This version changes the planner mix rather than adding broad
copy rules:

- remove nutrition_review, growth_stage_observation, and pure-life negative
  controls from this production-leaning probe;
- keep only lanes where Wangyue has narrative permission;
- keep v428's light-comparison source cleanup and contextual product-form gate.

This is still a local experiment and does not replace the production baseline.
"""

from __future__ import annotations

import copy
from typing import Any

import run_v428_wangyue_form_and_light_source_cleanup as form_cleanup


base = form_cleanup.base
base.EXPERIMENT_ID = "v429_production_lane_mix_probe"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)


def _lane(name: str) -> dict[str, Any]:
    for item in _previous_pool:
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
        route_reason="孩子当场接受就是产品进入资格，承担强种草。",
    ),
    _with_updates(
        "usage_acceptance",
        route_role="core",
        route_reason="增加口味接受类强证明的权重。",
    ),
    _with_updates(
        "usage_acceptance",
        route_role="core",
        route_reason="继续保留一次性接受证明，不扩展为固定喝法。",
    ),
    _with_updates(
        "usage_acceptance",
        route_role="core",
        route_reason="口味接受是当前最稳的强种草 lane。",
    ),
    _with_updates(
        "choice_review",
        route_role="core",
        route_reason="选择复盘允许产品、成分印象和一个正向观察出现。",
        natural_stop_hint="停在回想当时选择理由和现在一个普通观察，不写具体年份或几年前。",
    ),
    _with_updates(
        "choice_review",
        route_role="core",
        route_reason="用朋友或自己翻记录触发，承载成分/配置种草。",
        natural_stop_hint="停在当时为什么选择旺玥，不用安心、省心或选对收口。",
    ),
    _with_updates(
        "choice_review",
        route_role="core",
        route_reason="复盘 lane 承担部分卖点表达。",
        natural_stop_hint="只写一个选择理由和一个孩子接受/状态观察。",
    ),
    _with_updates(
        "choice_review",
        route_role="core",
        route_reason="提高选择复盘占比，替代不稳定的 nutrition_review。",
    ),
    _with_updates(
        "routine_arrangement",
        route_role="core",
        route_reason="日常对话中被问起家里儿童奶粉选择，产品自然进入。",
        life_theme="一次普通聊天里被问家里儿童奶粉怎么选或喝什么，妈妈按日常经验简单回答。",
        allowed_event_object="家里儿童奶粉选择、被问喝什么、日常经验里的简单回答。",
        disallowed_event_object="孩子个子、孩子身体状态、成分讲解课、正在喝的杯子、包里的奶粉。",
        risk_boundary="不要从孩子个子或身体状态引出；不要把回答写成产品解决方案；不要写成分讲解课。",
    ),
    _with_updates(
        "routine_arrangement",
        route_role="core",
        route_reason="保留 routine lane，但入口只来自普通对话，不来自可见产品形态。",
        life_theme="接娃、楼下、朋友闲聊时被问起儿童奶粉选择，回答短一点，像真实对话。",
        allowed_event_object="被问儿童奶粉选择、家里正在喝什么、为什么继续喝。",
        disallowed_event_object="奶瓶、水杯、试喝装、小袋、孩子身高体重、完整测评。",
        risk_boundary="不要写可见杯瓶袋；不要写孩子身体外观作为提问原因；不要写固定喝法。",
    ),
    _with_updates(
        "light_comparison",
        route_role="core",
        route_reason="轻对比已在 v428 恢复，可小比例进入生产候选。",
    ),
    _with_updates(
        "light_comparison",
        route_role="core",
        route_reason="继续验证被问选择原因 -> 简单对比 -> 旺玥的稳定性。",
    ),
]


if __name__ == "__main__":
    base.main()
