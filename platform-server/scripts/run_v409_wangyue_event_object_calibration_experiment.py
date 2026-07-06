#!/usr/bin/env python3
"""Local Wangyue event-object calibration experiment.

This is a wrapper around v408. It keeps the architecture layer intact and only
tests whether event-object boundaries reduce wasted plans and fixed-usage drift.
It does not replace production content.generate.
"""

from __future__ import annotations

import json

import run_v408_wangyue_event_type_architecture_experiment as base


base.EXPERIMENT_ID = "v409_event_object_calibration"

base.HUMAN_EVENT_SYSTEM = """你是小红书母婴UGC的人类事件规划器。
你不写正文，也不写产品。
目标是：先规划一个没有旺玥、没有具体奶粉、没有成分、没有卖点也能成立的妈妈发帖冲动。
输出 JSON，字段只能是：
event_type, posting_motive, human_event, emotional_impulse, life_entry, natural_stop, no_product_post, avoid_links, self_check。
要求：
- event_type 必须照抄 event_type_plan.event_type。
- human_event 的对象必须落在 event_type_plan.allowed_event_object 内，不要写 disallowed_event_object 里的对象。
- 不出现旺玥、具体奶粉名、配方、成分、卖点、喝法、补货。
- 可以写“日常选择、日常安排、清单、复盘、别人问起”，但不能提前写具体品牌或具体产品功效。
- 用“孩子”或“娃”，不要用“宝宝/宝妈”。
- human_event 写一个具体生活事件，不要写成商业 brief。
- no_product_post 写如果完全不提产品，这条帖子为什么仍然像妈妈会发。
- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。
"""

base.PRODUCT_BRIDGE_SYSTEM = """你是小红书母婴UGC的产品进入桥规划器。
你只基于 approved_human_event 判断旺玥有没有进入资格。
输出 JSON，字段只能是：
product_permission, permission_reason, rejection_reason, bridge_logic, product_role, single_selling_point, positive_evidence, ending_stop, avoid_links, self_check。
要求：
- product_permission 可以是 false；如果旺玥进入会显得强插，就直接 false。
- 如果 event_type_plan.product_entry_eligible=false，默认 product_permission=false，除非 approved_human_event 明确出现选择/营养/清单复盘。
- permission_reason 或 rejection_reason 必须具体说明判断依据。
- 不重写 approved_human_event，不新增第二个生活入口。
- 旺玥只能作为这个人类事件里家里在喝、后来选择、日常营养安排中的一项，不是答案、救场、兜底或解决方案。
- 强种草可以正面，但产品价值必须顺着 human_event 进入。
- 成分可以出现，但不要直接写成导致孩子变化的原因。
- 不规划固定喝法，例如每天一杯、早晚一杯、一杯旺玥、加餐时段、早餐奶、睡前喝。
- 不写瓶装、盒装、小包、便携装、随身带；旺玥按儿童奶粉语境处理。
- 不用安心、省心、放心、踏实、心里有底当结尾逻辑。
- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。
"""

base.EVENT_TYPE_POOL = [
    {
        "event_type": "choice_review",
        "product_entry_eligible": True,
        "source": "v407有效方向：回看当时选择过程",
        "life_theme": "翻旧照片、旧记录、聊天记录或备忘录时，想起当初给孩子做一个日常营养选择时纠结过一阵。",
        "allowed_event_object": "儿童日常营养选择、儿童口粮选择、阶段营养安排。",
        "disallowed_event_object": "书包、课程、玩具、幼儿园、兴趣班、游乐项目。",
        "product_entry_role": "产品可以作为当时后来选择的那一项出现。",
        "risk_boundary": "不要把多个选择链叠满；不要写成选园、选奶、效果证明三段广告闭环。",
        "natural_stop_hint": "停在现在回看那个选择，觉得当时花的功夫有了回声。",
    },
    {
        "event_type": "nutrition_review",
        "product_entry_eligible": True,
        "source": "v407有效方向：厨房/饭桌复盘",
        "life_theme": "饭桌、厨房或手机备忘录里，妈妈回想最近几顿饭忽好忽坏，顺手复盘孩子日常营养怎么安排更稳。",
        "allowed_event_object": "孩子一段时间的吃饭表现、日常营养安排、家里已有的营养选择。",
        "disallowed_event_object": "医生建议、体检指标、治疗、疾病环境。",
        "product_entry_role": "产品可以作为日常营养安排里的一个记录项出现。",
        "risk_boundary": "不要把旺玥写成解决挑食或营养焦虑的答案；不要加互动提问收口。",
        "natural_stop_hint": "停在擦桌子、收拾碗筷、孩子跑去玩这类生活尾巴。",
    },
    {
        "event_type": "routine_arrangement",
        "product_entry_eligible": True,
        "source": "v407方向：被问起日常安排",
        "life_theme": "被别的妈妈或家人随口问起孩子最近日常怎么安排，才发现自己有些选择已经固定下来。",
        "allowed_event_object": "放学后安排、家里日常营养选择、长期保留的儿童奶粉选择。",
        "disallowed_event_object": "固定杯数、每天早晚、加餐时段、一杯旺玥、睡前奶。",
        "product_entry_role": "产品可以作为日常安排里的一个轻量背景选择出现。",
        "risk_boundary": "不要写成瓶装饮品；不要写固定喝法；不要让产品抢走日常安排主线。",
        "natural_stop_hint": "停在对方一句追问或自己回完消息后的生活动作。",
    },
    {
        "event_type": "growth_stage_observation",
        "product_entry_eligible": True,
        "source": "v407方向：成长阶段变化观察",
        "life_theme": "接娃、整理衣服或看孩子日常活动时，突然感觉孩子进入了一个新阶段，饭量、活动量或作息都和以前不太一样。",
        "allowed_event_object": "成长阶段变化、阶段营养安排、整体营养配置。",
        "disallowed_event_object": "乳铁蛋白解释长肉长高、医生建议、体检指标。",
        "product_entry_role": "产品可以作为阶段营养安排的一部分出现。",
        "risk_boundary": "不要把乳铁蛋白连接到长肉、长高、结实；不要写具体功效因果。",
        "natural_stop_hint": "停在牵手回家、整理衣物或孩子继续去玩。",
    },
    {
        "event_type": "shopping_list_restock",
        "product_entry_eligible": True,
        "source": "v407方向：购物清单/补货低频可用",
        "life_theme": "买家里常用东西或整理购物清单时，顺手复盘孩子这阵子的日常消耗和固定选择。",
        "allowed_event_object": "家庭购物清单、常用儿童日常营养品、日常消耗记录。",
        "disallowed_event_object": "囤货、快喝完、必须补上、大量回购。",
        "product_entry_role": "产品可以作为清单上的一个补充项出现。",
        "risk_boundary": "补货/消耗链只能轻写；不要写囤货、回购、快喝完、必须补上。",
        "natural_stop_hint": "停在下单后继续忙别的，或把清单划掉一项。",
    },
    {
        "event_type": "usage_acceptance",
        "product_entry_eligible": True,
        "source": "旺玥真实帖：口味接受、愿意喝",
        "life_theme": "妈妈原本担心孩子不接受某个日常营养选择，后来发现口味接受度比预期顺。",
        "allowed_event_object": "儿童奶粉口味接受、儿童日常营养选择的接受度。",
        "disallowed_event_object": "麦片、酸奶、零食、辅食、新菜。",
        "product_entry_role": "产品可以作为被接受的对象出现，重点是孩子接受度。",
        "risk_boundary": "不要写每次喝完、每天喝、主动要喝；不写奶瓶/瓶装/小包。",
        "natural_stop_hint": "停在孩子当下一个轻反应，不做强推荐。",
    },
    {
        "event_type": "light_comparison",
        "product_entry_eligible": True,
        "source": "旺玥参考示例：简单对比选择",
        "life_theme": "妈妈曾经简单对比过几个儿童日常营养选择，最后留下一个更适合自家日常的。",
        "allowed_event_object": "儿童日常营养选择对比、儿童口粮选择对比、儿童奶粉选择对比。",
        "disallowed_event_object": "课程、玩具、兴趣班、游乐活动、衣服用品。",
        "product_entry_role": "产品可以作为最后留下的选择出现。",
        "risk_boundary": "不要攻击竞品；不要把对比写成完整测评；不要堆多个成分。",
        "natural_stop_hint": "停在自家目前使用感或日常观察。",
    },
    {
        "event_type": "pure_child_sentence",
        "product_entry_eligible": False,
        "source": "v406负例：纯孩子童言童语",
        "life_theme": "孩子突然说了一句让妈妈心软或被逗笑的话，妈妈只是想记录这句话。",
        "allowed_event_object": "孩子原话。",
        "disallowed_event_object": "任何产品、营养、选择复盘。",
        "product_entry_role": "不适合产品进入。",
        "risk_boundary": "如果产品进入，会破坏童言童语的纯度。",
        "natural_stop_hint": "停在孩子原话。",
    },
    {
        "event_type": "home_mess_loop",
        "product_entry_eligible": False,
        "source": "v406负例：家里乱/收拾循环",
        "life_theme": "家里刚收拾好一块地方，另一边又被孩子翻乱，妈妈顺手记录这种日常循环。",
        "allowed_event_object": "家庭收拾、玩具、客厅角落。",
        "disallowed_event_object": "任何产品、奶粉罐、冲奶动作。",
        "product_entry_role": "不适合产品进入。",
        "risk_boundary": "不要为了带产品强行写柜子、奶粉罐或冲奶动作。",
        "natural_stop_hint": "停在一个还没收完的小角落，不做产品总结。",
    },
    {
        "event_type": "pure_playground_moment",
        "product_entry_eligible": False,
        "source": "v406负例：纯游乐场成长瞬间",
        "life_theme": "放学后孩子在游乐场尝试了一个以前不敢玩的动作，妈妈坐在旁边记录成长瞬间。",
        "allowed_event_object": "游乐场动作、孩子一句话、牵手回家。",
        "disallowed_event_object": "任何产品、活动表现归因、营养解释。",
        "product_entry_role": "通常不适合产品进入，除非原事件本身有明确日常营养复盘。",
        "risk_boundary": "不要把活动表现直接归因到产品。",
        "natural_stop_hint": "停在孩子回头笑、喊再玩一次或牵手回家。",
    },
]

base.PLAN_GATE_PATTERNS["fixed_usage_in_plan"].extend([
    r"一杯旺玥",
    r"准备一杯",
    r"加餐时段",
    r"固定流程",
    r"雷打不动",
])

base.FIDELITY_PATTERNS["fixed_usage_added"].extend([
    r"一杯旺玥",
    r"准备一杯",
    r"加餐时段",
    r"固定流程",
    r"雷打不动",
])


def _format_prompt_sample(human_event_prompt, bridge_prompt, writer_prompt, human_event, product_bridge, plan):
    return base._format_prompt_sample(
        human_event_prompt,
        bridge_prompt,
        writer_prompt,
        human_event,
        product_bridge,
        plan,
    )


if __name__ == "__main__":
    base.main()

