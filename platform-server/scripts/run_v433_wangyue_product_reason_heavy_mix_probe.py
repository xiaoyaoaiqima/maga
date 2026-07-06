#!/usr/bin/env python3
"""Local Wangyue v433 product-reason-heavy mix probe.

v432 showed that real trigger families improve cleanliness a little, but
usage_acceptance still collapses into cup/sip/okay scenes. This probe keeps the
v432 trigger layer and tests a different mix: fewer pure acceptance posts, more
choice-review and light-comparison posts where Wangyue has stronger product
reason permission.
"""

from __future__ import annotations

import copy
from typing import Any

import run_v432_wangyue_real_trigger_family_probe as trigger_probe


base = trigger_probe.base
base.EXPERIMENT_ID = "v433_product_reason_heavy_mix_probe"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)


def _lane(subtype: str, **updates: Any) -> dict[str, Any]:
    for item in _previous_pool:
        if item.get("subtype") == subtype:
            clone = copy.deepcopy(item)
            clone.update(updates)
            return clone
    raise KeyError(subtype)


base.EVENT_TYPE_POOL = [
    _lane(
        "child_plain_sentence",
        route_reason="只保留一个使用反馈样本，验证低占比接受度 lane 是否可作为轻证明。",
    ),
    _lane(
        "asked_and_answered_now",
        route_reason="主力：当前被问起，允许一个产品理由和一个孩子反馈。",
    ),
    _lane(
        "current_note_without_date",
        route_reason="主力：无日期选择记忆，避免旧时间锚点。",
    ),
    _lane(
        "ingredient_memory",
        route_reason="主力：一个记得住的配置，不写成成分课。",
    ),
    _lane(
        "asked_and_answered_now",
        subtype_variant="asked_reason_life_interruption",
        route_reason="主力：当前被问起，但停在生活打断，避免完整推荐。",
        stop_mode="停在回答没讲完或生活动作打断，不补第二个效果证明。",
        forbidden_expansion="不写成长篇解释，不写销售式收尾。",
    ),
    _lane(
        "short_reply_then_life_moves_on",
        route_reason="辅助：日常问答里轻带旺玥。",
    ),
    _lane(
        "family_member_asks",
        route_reason="辅助：家庭 continuation moment，验证比邻居/群聊更自然。",
    ),
    _lane(
        "two_options_only",
        route_reason="主力：两项轻对比，保留一个产品记忆点。",
    ),
    _lane(
        "comment_question",
        route_reason="主力：评论/私信问题触发，不写购买引导。",
    ),
    _lane(
        "two_options_only",
        subtype_variant="two_options_product_reason_first",
        route_reason="主力：两项轻对比，但优先产品理由，再接孩子接受度。",
        main_evidence="一个产品理由或营养配置记忆点。",
        secondary_evidence="孩子接受度或日常状态二选一。",
        forbidden_expansion="不攻击另一款，不写完整测评表，不写购买建议。",
    ),
]


if __name__ == "__main__":
    base.main()
