#!/usr/bin/env python3
"""Local Wangyue v437 minimal four-control probe.

Builds on v436's subtractive result and the user correction that 3+ children
can plausibly participate in a home cup/powder scene. This probe tests the
minimal stable control set:

- post_intent
- product_physics_boundary
- product_proof_shape
- stop_rule

It keeps only six items so the next decision is based on signal, not another
large slow batch.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import run_v436_wangyue_lean_intent_probe as lean


base = lean.base
base.EXPERIMENT_ID = "v437_minimal_four_control_probe"

base.HUMAN_EVENT_SYSTEM = """你是小红书母婴UGC的人类事件规划器。
你不写正文，也不写产品。
目标是：先规划一个没有旺玥、没有具体品牌、没有成分卖点也能成立的妈妈发帖冲动。
输出 JSON，字段只能是：
event_type, posting_emotion_trigger, posting_motive, human_event, emotional_impulse, life_entry, natural_stop, no_product_post, avoid_links, self_check。
要求：
- event_type 必须照抄 event_type_plan.event_type。
- 只按 four_control_contract.post_intent 生成一个发帖原因，不额外创造第二个动机。
- human_event 必须遵守 product_physics_boundary：可以有家里杯子、温水、孩子拿杯子/喝/评价/轻参与；不要写盒装牛奶、吸管、奶瓶、便携小包、书包携带、户外冲奶、开水/热水壶或低龄喂养。
- human_event 可以出现“儿童奶粉/奶粉”这个中性品类对象，但不出现旺玥、具体品牌名、成分、卖点、功效证明、补货。
- 用“孩子”或“娃”，不要用“宝宝/宝妈”。
- 每篇只要一个生活触发，不要叠加被问、翻记录、活动后状态、对比等多个入口。
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
- 旺玥只按 four_control_contract.product_entry_role 进入，不要把产品写成答案、救场、兜底或解决方案。
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
- 3岁以上孩子可以在家里拿杯子、喝、评价或轻微参与；不要写低龄、奶瓶、盒装/吸管奶、便携小包、书包携带、户外冲奶、开水/热水壶。
- 像妈妈顺手发帖，不像广告 brief，也不像家庭营养管理备忘录。
- 如果生活入口、产品理由、效果观察放在一起不顺，就删掉其中一个，不要硬拼。
- 不写禁词，不写当前季节/公共疾病大环境。
- 标题不超过20字，emoji算2字。
- 不要把主线没有写的固定喝法、回购、安心省心总结、第二个效果证明补进去。
"""


_original_build_human_event_prompt = base._build_human_event_prompt
_original_build_bridge_prompt = base._build_bridge_prompt
_original_build_writer_prompt = base._build_writer_prompt


def _lane(
    *,
    event_type: str,
    subtype: str,
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
        "product_entry_eligible": True,
        "post_intent": post_intent,
        "life_theme": life_theme,
        "allowed_event_object": allowed_event_object,
        "disallowed_event_object": (
            "低龄喂养、奶瓶、便携袋、小包、试喝装、医生建议、公共疾病环境、当前季节、"
            "完整测评表、购买链接、固定喝法、盒装牛奶、牛奶盒、吸管饮品、书包/侧袋携带奶粉。"
        ),
        "product_entry_role": product_entry_role,
        "product_physics_boundary": product_physics_boundary,
        "product_proof_shape": product_proof_shape,
        "stop_rule": stop_rule,
        "risk_boundary": risk_boundary,
        "four_control_boundary": (
            "本篇只服从四个主控：post_intent 决定为什么发，product_physics_boundary 决定物理真实，"
            "product_proof_shape 决定怎么种草，stop_rule 决定在哪里停。不要额外补第五条主线。"
        ),
    }


HOME_CUP_PHYSICS = (
    "旺玥按3岁以上儿童奶粉的家庭场景写。可以有杯子、温水、家里台面、孩子参与拿杯子或轻微参与；"
    "不要写奶瓶、盒装牛奶、吸管、便携小包、书包携带、户外冲奶、开水/热水壶、低龄喂养。"
)

PREPARED_CUP_PHYSICS = (
    "如果写饮用现场，默认是家里已经冲好的杯子或妈妈在旁边处理；孩子可以尝、喝、评价、拿杯子，"
    "不要把旺玥写成盒装/瓶装/吸管奶，也不要写出门携带或小包装。"
)


base.EVENT_TYPE_POOL = [
    _lane(
        event_type="choice_review",
        subtype="choice_validation_after_activity",
        post_intent="妈妈看到孩子活动后状态还在线，回头觉得日常营养选择有被验证到。",
        life_theme="普通玩耍或户外回来后的饭桌/客厅片段，孩子状态不错，妈妈联想到儿童奶粉选择。",
        allowed_event_object="活动后精神头、吃饭玩耍节奏、一个日常状态观察、一个产品营养理由。",
        product_entry_role="旺玥是被当下状态回头验证的日常营养选择。",
        product_physics_boundary=PREPARED_CUP_PHYSICS,
        product_proof_shape="孩子状态先成立；旺玥理由只接一个，如钙铁锌/关键营养/乳铁蛋白HMO中的一个方向，不写直接功效归因。",
        stop_rule="停在孩子继续玩、吃饭或妈妈手头事继续，不补完整购买理由。",
        risk_boundary="不要写换季、流感、春游、秋游、少请假；不要把乳铁蛋白接到长肉、跑跳有劲。",
    ),
    _lane(
        event_type="choice_review",
        subtype="choice_validation_current_signal",
        post_intent="妈妈看到一个当下接受信号，觉得当初选旺玥这件事现在仍然说得通。",
        life_theme="孩子在家里自然接受这款儿童奶粉，妈妈从这个小动作回看当初为什么选。",
        allowed_event_object="当下孩子接受度、普通状态观察、一个产品配置印象。",
        product_entry_role="旺玥是被当下接受信号回头验证的选择。",
        product_physics_boundary=HOME_CUP_PHYSICS,
        product_proof_shape="先写孩子侧接受信号，再轻带一个旺玥理由；不要把理由、状态、总结写成三连证明。",
        stop_rule="停在生活动作或妈妈一瞬间的确认感，不写安心省心总结。",
        risk_boundary="不要写别人追问；不要写旧年份；不要写固定喝法或选购教程。",
    ),
    _lane(
        event_type="choice_review",
        subtype="choice_validation_one_reason",
        post_intent="妈妈只记得当初一个简单理由，今天看孩子反馈还在，想给自己留个记录。",
        life_theme="看到一个无日期的选择关键词，想起当时留下旺玥的理由，眼前孩子反馈也对得上。",
        allowed_event_object="无日期选择关键词、一个配置印象、当前孩子接受度或精神状态。",
        product_entry_role="旺玥是那个简单理由对应的实际选择。",
        product_physics_boundary=PREPARED_CUP_PHYSICS,
        product_proof_shape="产品理由明确一个；孩子反馈做旁证，不补第二个卖点。",
        stop_rule="停在这个理由还说得通，不扩展成复盘长文。",
        risk_boundary="不要写翻配方表/营养表照片高频动作；不要写几个月前/去年；不要写固定喝法。",
    ),
    _lane(
        event_type="light_comparison",
        subtype="one_reason_left",
        post_intent="妈妈只保留一个当初留下旺玥的理由，不试图给别人做测评。",
        life_theme="想起当时只轻轻比过两个方向，最后留下旺玥的原因很简单。",
        allowed_event_object="两款轻比较、一个接受度理由、一个营养配置印象。",
        product_entry_role="旺玥是轻比较后留下来的选择。",
        product_physics_boundary=PREPARED_CUP_PHYSICS,
        product_proof_shape="只写一个留下理由；不要同时写竞品、价格、配置、状态和建议。",
        stop_rule="停在自己的一个选择原因，不转成选购教程。",
        risk_boundary="不要写试喝装、竞品攻击、购买建议、孩子嘴最诚实、硬道理。",
    ),
    _lane(
        event_type="light_comparison",
        subtype="one_product_reason_left",
        post_intent="妈妈回看轻比较时，记住的是一个产品配置理由，而不是完整测评过程。",
        life_theme="当时对比不复杂，只记得旺玥有一个配置点比较合适，孩子也接受。",
        allowed_event_object="一个产品配置印象、孩子接受度、轻比较记忆。",
        product_entry_role="旺玥是因为这个配置点被留下的选择。",
        product_physics_boundary=PREPARED_CUP_PHYSICS,
        product_proof_shape="产品理由可以明确；孩子接受度只做短旁证。",
        stop_rule="停在这个配置点和孩子接受，不写推荐语。",
        risk_boundary="不要列成分表；不要写公开建议；不要写每天喝完。",
    ),
    _lane(
        event_type="usage_acceptance",
        subtype="home_cup_child_participation",
        post_intent="孩子在家里自然参与了一点点，妈妈觉得这款至少被他接住了。",
        life_theme="家里杯子/温水/台面这种普通场景，孩子参与拿杯子或尝一口，反馈低调。",
        allowed_event_object="家庭杯子场景、孩子参与拿杯子、尝后普通评价、儿童奶粉接受度。",
        product_entry_role="旺玥是孩子这个家庭接受动作指向的儿童奶粉。",
        product_physics_boundary=HOME_CUP_PHYSICS,
        product_proof_shape="孩子接受度就是主证明；最多补一句味道顺口，不讲成分课。",
        stop_rule="停在孩子原话、喝完后的动作或继续做自己的事。",
        risk_boundary="不要写孩子完全负责热水冲泡；不要写奶瓶、盒装牛奶、吸管、小包、出门带。",
    ),
]


def _contract(event_type_plan: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "post_intent",
        "product_physics_boundary",
        "product_entry_role",
        "product_proof_shape",
        "stop_rule",
        "four_control_boundary",
    ]
    return {key: event_type_plan.get(key) for key in keys if event_type_plan.get(key)}


def _build_human_event_prompt_v437(row: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_human_event_prompt(row, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload.pop("lean_intent_contract", None)
    payload["four_control_contract"] = _contract(event_type_plan)
    payload["intent_use"] = (
        "只用 post_intent 生成妈妈为什么此刻想发帖；human_event 必须遵守 product_physics_boundary，"
        "但不要写旺玥、成分或卖点。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_bridge_prompt_v437(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_bridge_prompt(row, human_event, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload.pop("lean_intent_contract", None)
    payload.pop("bridge_lane_contract", None)
    payload["four_control_contract"] = _contract(event_type_plan)
    payload["bridge_use"] = (
        "旺玥只按 product_entry_role 进入；任何桥接都必须符合 product_physics_boundary；"
        "只按 product_proof_shape 规划一个主种草证明。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt_v437(
    row: dict[str, Any],
    plan: dict[str, Any],
    *,
    plan_valid: bool,
    plan_issues: list[str],
) -> str:
    payload = json.loads(
        _original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues)
    )
    event_type_plan = base.EVENT_TYPE_POOL[(int(row.get("item_no") or row.get("source_row_no") or 1) - 1) % len(base.EVENT_TYPE_POOL)]
    payload.pop("lean_writer_contract", None)
    payload["four_control_writer_contract"] = _contract(event_type_plan)
    payload["storyline_contract"] = (
        "approved_story_plan.storyline 是唯一主线。正文必须先完成 post_intent，"
        "所有产品动作和载体必须符合 product_physics_boundary；"
        "只按 product_proof_shape 写一个主产品证明；到 stop_rule 对应位置就停。"
    )
    payload["writer_task"] = "把 approved_story_plan 写成一篇 110-170 字左右的小红书妈妈UGC正向种草笔记。"
    return json.dumps(payload, ensure_ascii=False, indent=2)


base._build_human_event_prompt = _build_human_event_prompt_v437
base._build_bridge_prompt = _build_bridge_prompt_v437
base._build_writer_prompt = _build_writer_prompt_v437


if __name__ == "__main__":
    # Keep this probe small on purpose.
    import sys

    if "--count" not in sys.argv:
        sys.argv.extend(["--count", "6"])
    base.main()
