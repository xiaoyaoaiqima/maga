#!/usr/bin/env python3
"""Local Wangyue v439 product-relation kernel probe.

This probe tests the architecture decision from v439:

product relationship stage -> proof mechanism -> post shape -> allowed selling point

It intentionally does not optimize a single scene. The purpose is to verify
whether the product relation stage keeps selling points from drifting into the
wrong story.
"""

from __future__ import annotations

import re
from typing import Any

import run_v437_wangyue_minimal_four_control_probe as four_control


base = four_control.base
base.EXPERIMENT_ID = "v439_product_relation_kernel_probe"
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _lane(
    *,
    event_type: str,
    subtype: str,
    product_relation_stage: str,
    proof_mechanism: str,
    post_intent: str,
    life_theme: str,
    allowed_event_object: str,
    product_entry_role: str,
    product_physics_boundary: str,
    product_proof_shape: str,
    stop_rule: str,
    risk_boundary: str,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "subtype": subtype,
        "product_relation_stage": product_relation_stage,
        "proof_mechanism": proof_mechanism,
        "product_entry_eligible": True,
        "post_intent": post_intent,
        "life_theme": life_theme,
        "allowed_event_object": allowed_event_object,
        "disallowed_event_object": (
            "低龄喂养、奶瓶、盒装牛奶、吸管饮品、便携小包、书包/侧袋携带奶粉、"
            "户外冲奶、开水/热水壶、医生建议、体检指标、公共疾病环境、当前季节、"
            "春游、秋游、换季、流感、完整测评表、购买链接。"
        ),
        "product_entry_role": product_entry_role,
        "product_physics_boundary": product_physics_boundary,
        "product_proof_shape": product_proof_shape,
        "stop_rule": stop_rule,
        "risk_boundary": risk_boundary,
        "four_control_boundary": (
            "本篇先服从 product_relation_stage 和 proof_mechanism。"
            "不要把其他关系阶段的证明硬塞进来；如果卖点和关系阶段不匹配，宁可少写一个卖点。"
        ),
    }


HOME_CUP_PHYSICS = (
    "旺玥按3岁以上儿童奶粉的家庭杯子场景写。可以是妈妈冲好后放在台面/餐桌，"
    "孩子拿杯子、喝一口或几口、放下杯子、继续做自己的事；"
    "不要写孩子独立操作开水/热水壶，不写奶瓶、盒装/吸管奶、便携小包、户外携带。"
)

GENERAL_FORMULA_PHYSICS = (
    "旺玥按3岁以上、3-6岁学龄前儿童可喝的4段儿童奶粉写。"
    "可以写家里正在喝、买了/补了/收到、妈妈选择或对比；"
    "如果出现饮用现场，只写家里杯子，不写奶瓶、盒装/吸管奶、便携小包或孩子独立冲泡。"
)


base.HUMAN_EVENT_SYSTEM = """你是小红书母婴UGC的人类事件规划器。
你不写正文，也不写产品卖点。
目标是：先规划一个没有旺玥、没有具体品牌、没有成分卖点也能成立的妈妈发帖冲动。
输出 JSON，字段只能是：
event_type, posting_emotion_trigger, posting_motive, human_event, emotional_impulse, life_entry, natural_stop, no_product_post, avoid_links, self_check。
要求：
- event_type 必须照抄 event_type_plan.event_type。
- 只按 four_control_contract.post_intent 生成一个发帖原因，不额外创造第二个动机。
- human_event 必须遵守 product_physics_boundary：可以是家庭杯子、对比选择、补货、阶段营养安排或状态观察，但不要提前写旺玥、具体品牌、成分、卖点、功效证明。
- 用“孩子”或“娃”，不要用“宝宝/宝妈”。
- 每篇只要一个生活触发，不要叠加被问、补货、活动后状态、对比等多个入口。
- no_product_post 写如果完全不提产品，这条帖子为什么仍然像妈妈会发。
- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。
- 不写三年前、从小、小时候、刚断奶、刚上幼儿园、一岁、两岁这类可能暗示3岁前产品使用的时间履历。
"""

base.PRODUCT_BRIDGE_SYSTEM = """你是小红书母婴UGC的产品进入桥规划器。
你只基于 approved_human_event 判断旺玥有没有进入资格。
输出 JSON，字段只能是：
product_permission, permission_reason, rejection_reason, bridge_logic, product_role, single_selling_point, positive_evidence, ending_stop, avoid_links, self_check。
要求：
- product_permission 可以是 false；如果旺玥进入会显得强插，就直接 false。
- 旺玥只按 four_control_contract.product_entry_role 进入，不要换成另一个关系阶段。
- 所有产品动作、载体和场景必须符合 four_control_contract.product_physics_boundary。
- positive_evidence 不能空，但只按 four_control_contract.product_proof_shape 规划一个主种草证明。
- 不重写 approved_human_event，不新增第二个生活入口。
- 成分可以出现，但不要直接写成导致孩子变化的原因。
- 不规划固定喝法，例如每天一杯、早晚一杯、早餐奶、睡前喝。
- 不写瓶装、盒装、小包、便携装、随身带、书包侧袋；旺玥按儿童奶粉语境处理。
- 不用安心、省心、放心、踏实、心里有底当结尾逻辑。
- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。
"""

base.WRITER_SYSTEM = """你是小红书妈妈UGC写手。
你只能根据给定主线写标题和正文，不重新规划新事实。
输出 JSON，字段只能是 title 和 body。
写法要求：
- 正文先服务 approved_story_plan.storyline；每句话都要能接上这条主线。
- approved_story_plan.human_event 是生活主线，approved_story_plan.product_bridge 只是产品进入方式。
- 正文必须服从 four_control_writer_contract：post_intent、product_physics_boundary、product_proof_shape、stop_rule。
- 旺玥要自然出现，产品价值要写到位，但只写一个主产品证明。
- 如果关系阶段是熟悉日常使用，只能讲接受度/口味低阻力，不讲保护力、钙铁锌、DHA或成长效果。
- 如果关系阶段是对比选择、阶段营养安排或长期使用，卖点可以更明确，种草性可以强。
- 如果生活入口、产品理由、效果观察放在一起不顺，就删掉其中一个，不要硬拼。
- 不写禁词，不写当前季节/公共疾病大环境。
- 标题不超过20字，emoji算2字。
- 不要把主线没有写的固定喝法、回购、安心省心总结、第二个效果证明补进去。
"""


base.EVENT_TYPE_POOL = [
    _lane(
        event_type="usage_acceptance",
        subtype="familiar_home_cup",
        product_relation_stage="熟悉日常使用",
        proof_mechanism="孩子动作接受",
        post_intent="妈妈记录孩子很自然地喝了家里这杯儿童奶粉，生活没有被打断。",
        life_theme="家里杯子/餐桌/台面，孩子喝几口后继续做自己的事。",
        allowed_event_object="家庭杯子、孩子喝几口、放下杯子、继续玩或看书。",
        product_entry_role="旺玥是家里已经自然出现、被孩子顺手接受的儿童奶粉。",
        product_physics_boundary=HOME_CUP_PHYSICS,
        product_proof_shape="孩子动作就是主证明；只能承载接受度、口味温和或低阻力，不承载营养和保护力。",
        stop_rule="停在孩子动作或妈妈一句轻观察。",
        risk_boundary="不要写第一次试喝、意外、不嫌弃、不抗拒、没皱眉、保护力、钙铁锌、DHA、成长效果。",
    ),
    _lane(
        event_type="first_try",
        subtype="new_can_acceptance",
        product_relation_stage="初试/新开罐",
        proof_mechanism="从担心到接受",
        post_intent="妈妈记录新开一罐后孩子接受得比预想顺。",
        life_theme="刚买回来或新开罐，在家里试了几次，孩子愿意喝。",
        allowed_event_object="新开罐、家里杯子、尝几口、愿意继续喝、口味反馈。",
        product_entry_role="旺玥是刚进入家里的儿童奶粉，先用接受度证明没有踩雷。",
        product_physics_boundary=GENERAL_FORMULA_PHYSICS,
        product_proof_shape="只证明口味接受和清淡顺口；不要证明少请假、成长或专注变化。",
        stop_rule="停在孩子接受或妈妈决定继续观察。",
        risk_boundary="不要混入长期使用、复购、少请假、孩子状态大变化。",
    ),
    _lane(
        event_type="choice_review",
        subtype="comparison_one_reason",
        product_relation_stage="对比选择/做功课",
        proof_mechanism="妈妈筛选标准",
        post_intent="妈妈复盘自己为什么最后选了旺玥，但不写成完整测评。",
        life_theme="选儿童奶粉时只抓住一两个自己在意的标准，最后选了旺玥。",
        allowed_event_object="轻比较、选择标准、一个产品配置理由、孩子接受度短旁证。",
        product_entry_role="旺玥是对比后被选中的那款。",
        product_physics_boundary=GENERAL_FORMULA_PHYSICS,
        product_proof_shape="筛选标准是主证明；可以明确讲保护力/眼脑/营养配置中的一个方向。",
        stop_rule="停在自己的选择理由成立，不转成选购教程。",
        risk_boundary="不要堆参数，不写翻配方表高频动作，不攻击竞品，不写价格取舍。",
    ),
    _lane(
        event_type="stage_nutrition",
        subtype="preschool_nutrition_arrangement",
        product_relation_stage="阶段营养安排",
        proof_mechanism="3岁后阶段需求",
        post_intent="妈妈发现孩子3岁后吃饭和日常消耗都更复杂，于是把儿童奶粉作为营养安排的一部分。",
        life_theme="饭量不稳、活动量大、成长阶段需要更完整的日常营养。",
        allowed_event_object="3岁后、饭量不稳、日常营养安排、阶段需求。",
        product_entry_role="旺玥是3岁后阶段营养安排里被选中的儿童奶粉。",
        product_physics_boundary=GENERAL_FORMULA_PHYSICS,
        product_proof_shape="阶段需求是主证明；可以讲钙铁锌、30+关键营养、DHA/燕窝酸或整体营养。",
        stop_rule="停在日常营养安排变得更有抓手。",
        risk_boundary="不要写医生建议、体检指标、低龄语境、固定早晚杯数。",
    ),
    _lane(
        event_type="repurchase",
        subtype="continue_buying_one_reason",
        product_relation_stage="长期使用/复购",
        proof_mechanism="复购动作证明认可",
        post_intent="妈妈买的时候顺手又带了旺玥，因为家里这段时间喝下来有一个明确的继续理由。",
        life_theme="买东西时顺手补、收到快递、家里继续喝，一个状态观察支撑复购。",
        allowed_event_object="买了/补了/收到、继续喝、一个状态观察、一个产品理由。",
        product_entry_role="旺玥是家里长期喝下来还会继续买的选择。",
        product_physics_boundary=GENERAL_FORMULA_PHYSICS,
        product_proof_shape="复购动作 + 一个继续理由；可以写状态稳、少请假、精神头或接受度之一。",
        stop_rule="停在继续买的动作或一个观察，不补完整广告闭环。",
        risk_boundary="不要高频见底库存，不要每篇都安心省心踏实，不要补第二个卖点长段。",
    ),
    _lane(
        event_type="state_feedback",
        subtype="positive_state_observation",
        product_relation_stage="状态反馈/效果观察",
        proof_mechanism="一个生活观察证明",
        post_intent="妈妈看到孩子一个正向状态，想记录这段时间的日常营养没有白安排。",
        life_theme="老师/家人一句话，或妈妈自己看到孩子状态比之前稳一点。",
        allowed_event_object="少请假、精神头、能坐住、饭量不稳时状态稳定、看着结实。",
        product_entry_role="旺玥是这个阶段日常营养里被带出来的产品。",
        product_physics_boundary=GENERAL_FORMULA_PHYSICS,
        product_proof_shape="一个状态观察是主证明；成分只能做支撑，不直接归因成神效。",
        stop_rule="停在观察本身或孩子继续生活的画面。",
        risk_boundary="不要把乳铁蛋白直接接长肉/抱起来沉/衣服撑起来/跑跳有劲；不要写医生体检。",
    ),
    _lane(
        event_type="stock_trigger",
        subtype="restock_or_delivery",
        product_relation_stage="补货/库存/快递",
        proof_mechanism="购买动作证明长期关系",
        post_intent="妈妈在一次补货或收快递的小动作里意识到，旺玥已经是家里会继续买的东西。",
        life_theme="购物车、快递、家里补货、顺手又买一罐或一箱。",
        allowed_event_object="顺手加购、收到快递、又买了一罐/一箱、家里继续喝。",
        product_entry_role="旺玥是被补货动作证明还会继续选择的儿童奶粉。",
        product_physics_boundary=GENERAL_FORMULA_PHYSICS,
        product_proof_shape="补货动作是主证明；只补一个继续买的理由，如接受度、状态稳或营养配置。",
        stop_rule="停在补货动作或拆快递后的生活继续。",
        risk_boundary="不要写见底/半罐高频，不要强行补对比选择长链路。",
    ),
    _lane(
        event_type="followup_feedback",
        subtype="asked_before_followup",
        product_relation_stage="求助后反馈",
        proof_mechanism="之前纠结后的使用反馈",
        post_intent="妈妈之前纠结过儿童奶粉选择，现在用过一段时间，给自己或同类问题一个反馈。",
        life_theme="之前纠结/问过/被问过，后来选了旺玥，现在只反馈一个最明显的点。",
        allowed_event_object="曾经纠结、后来选择、一个使用反馈、一个选择理由。",
        product_entry_role="旺玥是纠结之后实际选下来的儿童奶粉。",
        product_physics_boundary=GENERAL_FORMULA_PHYSICS,
        product_proof_shape="选择理由 + 轻反馈；可以强种草，但不要写成测评大全。",
        stop_rule="停在这个反馈够回答当初的问题。",
        risk_boundary="不要互动提问收口，不要完整教学，不要列多条购买建议。",
    ),
]


def _allow_neutral_category_product_words(issue: str, text: str) -> bool:
    if not issue.startswith("human_event_contains_product:"):
        return False
    forbidden_brand_or_claim = re.search(r"(旺玥|皇家美素|乳铁蛋白|HMO|DHA|燕窝酸|钙铁锌|保护力)", text)
    return not forbidden_brand_or_claim


def _portable_form_really_present(text: str) -> bool:
    return bool(re.search(r"(便携|小包|小袋|分装|书包|侧袋|吸管|盒装|一袋|一包)", text))


def _validate_plan_v439(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    human_event = plan.get("human_event") or {}
    text = " ".join(
        str(human_event.get(key) or "")
        for key in ("posting_emotion_trigger", "posting_motive", "human_event", "life_entry", "natural_stop")
    )
    filtered: list[str] = []
    for issue in issues:
        if _allow_neutral_category_product_words(issue, text):
            continue
        if issue == "portable_product_form_in_plan" and not _portable_form_really_present(text):
            continue
        filtered.append(issue)
    return not filtered, filtered


def _relation_surface_flags(text: str) -> list[str]:
    flags: list[str] = []
    if re.search(r"旺玥.{0,4}牛奶|旺玥牛奶", text):
        flags.append("wrong_product_form_wangyue_milk")
    if re.search(r"今天这杯是旺玥[^。！？\n]{0,24}(不抗拒|意外|没想到)", text):
        flags.append("familiar_scene_first_trial_contrast")
    if re.search(r"(固定喝它|现在就固定喝)", text):
        flags.append("fixed_usage_closure")
    return flags


def _local_quality_v439(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = sorted(set([*(quality.get("flags") or []), *_relation_surface_flags(f"{title}\n{body}")]))
    quality["flags"] = flags
    if flags:
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(flags)
    return quality


def _fidelity_gate_v439(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    flags = sorted(set([*(result.get("flags") or []), *_relation_surface_flags(f"{title}\n{body}")]))
    result["flags"] = flags
    result["pass"] = not flags
    return result


base._validate_plan = _validate_plan_v439
base._local_quality = _local_quality_v439
base._fidelity_gate = _fidelity_gate_v439


if __name__ == "__main__":
    import sys

    if "--count" not in sys.argv:
        sys.argv.extend(["--count", "10"])
    base.main()
