#!/usr/bin/env python3
"""Local Wangyue posting-emotion-trigger experiment.

Builds on v411 category-neutral human events. This tests whether a concrete
posting impulse makes the output less like household management notes while
preserving product-entry permission.
"""

from __future__ import annotations

import run_v411_wangyue_category_neutral_event_experiment as category


base = category.base
base.EXPERIMENT_ID = "v412_posting_emotion_trigger"

base.HUMAN_EVENT_SYSTEM = base.HUMAN_EVENT_SYSTEM.replace(
    "event_type, posting_motive, human_event, emotional_impulse, life_entry, natural_stop, no_product_post, avoid_links, self_check。",
    "event_type, posting_emotion_trigger, posting_motive, human_event, emotional_impulse, life_entry, natural_stop, no_product_post, avoid_links, self_check。",
)

base.HUMAN_EVENT_SYSTEM = base.HUMAN_EVENT_SYSTEM.replace(
    "- human_event 写一个具体生活事件，不要写成商业 brief。",
    "- posting_emotion_trigger 先写妈妈为什么此刻拿起手机想发，不要写成“记录/复盘/分享/安排/选择”这类内容结构。\n"
    "- posting_emotion_trigger 可以是被问住、小意外、有点累、被孩子打断、孩子反应好笑、松一口气、家务中途顺手想到；每篇只要一个。\n"
    "- human_event 从这个触发往下长，写一个具体生活事件，不要写成商业 brief 或家庭管理备忘录。",
)

base.HUMAN_EVENT_SYSTEM = base.HUMAN_EVENT_SYSTEM.replace(
    "- 可以写“日常选择、日常安排、清单、复盘、别人问起”，但不能提前写具体品牌或具体产品功效。",
    "- 可以写“日常选择、日常安排、清单、复盘、别人问起”，但它们只能服务情绪触发，不能变成整篇的管理任务。",
)

base.PRODUCT_BRIDGE_SYSTEM = base.PRODUCT_BRIDGE_SYSTEM.replace(
    "- 不重写 approved_human_event，不新增第二个生活入口。",
    "- 不重写 approved_human_event，不新增第二个生活入口。\n"
    "- 不要把 approved_human_event.posting_emotion_trigger 改写成产品理由；产品只能顺着这个发帖冲动轻轻进入。",
)

base.WRITER_SYSTEM = base.WRITER_SYSTEM.replace(
    "- 正文先服务 approved_story_plan.storyline；每句话都要能接上这条主线。",
    "- 正文先服务 approved_story_plan.storyline 和 human_event.posting_emotion_trigger；每句话都要能接上这条主线。",
)

base.WRITER_SYSTEM = base.WRITER_SYSTEM.replace(
    "- 像妈妈顺手发帖，不像广告 brief。",
    "- 像妈妈顺手发帖，不像广告 brief，也不像家庭营养管理备忘录。",
)

base.WRITER_SYSTEM = base.WRITER_SYSTEM.replace(
    "- 如果生活入口、被问起、产品理由、效果观察放在一起不顺，就删掉其中一个，不要硬拼。",
    "- 如果生活入口、被问起、产品理由、效果观察放在一起不顺，就删掉其中一个，不要硬拼。\n"
    "- 不用“心里默默盘算/安排更稳妥/任务完成/清单列完”这类管理型收口。",
)

for event_type in base.EVENT_TYPE_POOL:
    if event_type["event_type"] == "nutrition_review":
        event_type["life_theme"] = (
            "饭桌或厨房里，孩子一个小反应打断了妈妈的家务节奏，妈妈临时想到儿童奶粉/奶粉相关的日常营养安排。"
        )
    elif event_type["event_type"] == "routine_arrangement":
        event_type["life_theme"] = (
            "被别的妈妈或家人随口问起家里儿童奶粉怎么选，妈妈一时被问住，才发现这个选择已经用了一段时间。"
        )
    elif event_type["event_type"] == "shopping_list_restock":
        event_type["life_theme"] = (
            "家务或购物清单做到一半被孩子打断，妈妈顺手把儿童奶粉/奶粉这项记下来，不把清单写成主线。"
        )
    elif event_type["event_type"] == "usage_acceptance":
        event_type["life_theme"] = (
            "孩子对儿童奶粉/奶粉的一个小反应让妈妈有点意外，顺手想记下这个接受度瞬间。"
        )

base.PLAN_GATE_PATTERNS["emotion_shortcut_in_plan"].extend([
    r"心里默默盘算",
    r"安排更稳妥",
    r"任务完成",
    r"清单列完",
])

base.FIDELITY_PATTERNS["formulaic_closure_added"].extend([
    r"任务完成",
    r"清单列完",
    r"安排好了",
])


if __name__ == "__main__":
    base.main()

