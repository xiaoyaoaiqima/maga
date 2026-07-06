#!/usr/bin/env python3
"""Local Wangyue emotion-lane compatibility experiment.

Builds on v412. The test is whether each product-entry lane gets a compatible
posting emotion, instead of applying the same "realness" pressure everywhere.
"""

from __future__ import annotations

import run_v412_wangyue_posting_emotion_trigger_experiment as emotion


base = emotion.base
base.EXPERIMENT_ID = "v413_emotion_lane_compatibility"

base.HUMAN_EVENT_SYSTEM = base.HUMAN_EVENT_SYSTEM.replace(
    "- posting_emotion_trigger 可以是被问住、小意外、有点累、被孩子打断、孩子反应好笑、松一口气、家务中途顺手想到；每篇只要一个。",
    "- posting_emotion_trigger 必须贴合 event_type_plan.emotion_trigger_allowed，不要写 event_type_plan.emotion_trigger_disallowed。\n"
    "- 每篇只要一个触发；不要为了真人感叠加多个入口。",
)

base.HUMAN_EVENT_SYSTEM = base.HUMAN_EVENT_SYSTEM.replace(
    "- human_event 从这个触发往下长，写一个具体生活事件，不要写成商业 brief 或家庭管理备忘录。",
    "- human_event 从这个触发往下长，写一个具体生活事件，不要写成商业 brief、家庭管理备忘录或求建议帖。",
)

base.PRODUCT_BRIDGE_SYSTEM = base.PRODUCT_BRIDGE_SYSTEM.replace(
    "- 强种草可以正面，但产品价值必须顺着 human_event 进入。",
    "- 强种草可以正面，但产品价值必须顺着 human_event 和 event_type_plan.product_value_role 进入。",
)

base.WRITER_SYSTEM = base.WRITER_SYSTEM.replace(
    "- 正文自然出现旺玥，产品价值要写到位，但不要把 source_row 里的素材逐项覆盖。",
    "- 正文自然出现旺玥，产品价值要写到位；强弱跟着 approved_story_plan.product_bridge.product_role，不要把 source_row 里的素材逐项覆盖。",
)

for event_type in base.EVENT_TYPE_POOL:
    name = event_type["event_type"]
    if name == "choice_review":
        event_type["emotion_trigger_allowed"] = "被别人问为什么选儿童奶粉时卡了一下；翻到旧记录时突然想起当初纠结，但不写不踏实。"
        event_type["emotion_trigger_disallowed"] = "心里不踏实、求建议、每天喝得开心、身体不错、完整做功课链。"
        event_type["product_value_role"] = "可以写选择理由和一个正向观察，但不要变成成分安心链。"
    elif name == "nutrition_review":
        event_type["emotion_trigger_allowed"] = "饭桌上一个小插曲让妈妈想起儿童奶粉也在日常营养里；不是单纯管理清单。"
        event_type["emotion_trigger_disallowed"] = "盘算安排、完整饮食计划、孩子指奶粉罐要喝、妈妈冲一瓶。"
        event_type["product_value_role"] = "可以写日常营养搭配中的一项，并带一个温和状态观察。"
    elif name == "routine_arrangement":
        event_type["emotion_trigger_allowed"] = "被问起家里儿童奶粉怎么选，顺口解释已经喝这款；语气是顺手说，不是求建议。"
        event_type["emotion_trigger_disallowed"] = "心里不踏实、超市随便拿、正在考虑旺玥、求大家推荐。"
        event_type["product_value_role"] = "可以写家里在喝旺玥和一个选择理由，避免固定杯数和每天流程。"
    elif name == "growth_stage_observation":
        event_type["emotion_trigger_allowed"] = "看到孩子阶段变化时顺手想到日常营养安排，但不把产品解释成成长原因。"
        event_type["emotion_trigger_disallowed"] = "孩子变强、长肉、长高、跑跳更厉害、产品帮忙。"
        event_type["product_value_role"] = "只允许阶段营养安排背景，不做强因果证明。"
    elif name == "shopping_list_restock":
        event_type["emotion_trigger_allowed"] = "家务中途被孩子打断，顺手把儿童奶粉记一笔；产品是背景，不承担强种草。"
        event_type["emotion_trigger_disallowed"] = "囤货、见底焦虑、回购、常备总结、产品价值展开。"
        event_type["product_value_role"] = "低频真人纹理 lane，只轻带产品，不负责主要种草。"
    elif name == "usage_acceptance":
        event_type["emotion_trigger_allowed"] = "孩子尝一口后的意外接受、表情变化、顺口评价；妈妈有点意外或松一口气。"
        event_type["emotion_trigger_disallowed"] = "每天主动喝、固定喝法、喝完整杯、夸张惊喜、功效解释。"
        event_type["product_value_role"] = "强种草主力 lane，可以正面写口味接受和孩子反应。"
    elif name == "light_comparison":
        event_type["emotion_trigger_allowed"] = "被问起为什么最后选这款，妈妈回忆简单对比和孩子接受度。"
        event_type["emotion_trigger_disallowed"] = "每天喝、完全不纠结、求推荐、完整测评、攻击竞品。"
        event_type["product_value_role"] = "可以写轻对比、留下旺玥、一个接受度或营养配置理由。"
    else:
        event_type["emotion_trigger_allowed"] = "按原纯生活事件自然出现。"
        event_type["emotion_trigger_disallowed"] = "产品、奶粉、营养选择。"
        event_type["product_value_role"] = "不允许产品进入。"

base.PLAN_GATE_PATTERNS["emotion_shortcut_in_plan"].extend([
    r"心里不踏实",
    r"求建议",
    r"是不是该认真选",
    r"大家.*推荐",
])


if __name__ == "__main__":
    base.main()

