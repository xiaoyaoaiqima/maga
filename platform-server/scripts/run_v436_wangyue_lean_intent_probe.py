#!/usr/bin/env python3
"""Local Wangyue v436 lean-intent probe.

v435 showed that adding posting_intention on top of existing mom_motion,
trigger_motive, partial_answer, and bridge layers improved machine pass but not
human high-score quality. This probe is subtractive: start from the cleaner
v430 stack and replace overlapping intent factors with three controls only:

- post_intent
- product_proof_shape
- stop_rule
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import run_v430_wangyue_stable_lane_subtype_probe as subtype_probe


base = subtype_probe.base
base.EXPERIMENT_ID = "v436_lean_intent_probe"


_original_build_human_event_prompt = base._build_human_event_prompt
_original_build_bridge_prompt = base._build_bridge_prompt
_original_build_writer_prompt = base._build_writer_prompt
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _lane(
    *,
    event_type: str,
    subtype: str,
    post_intent: str,
    life_theme: str,
    allowed_event_object: str,
    product_entry_role: str,
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
            "完整测评表、购买链接、固定喝法、盒装牛奶或吸管饮品。"
        ),
        "product_entry_role": product_entry_role,
        "product_proof_shape": product_proof_shape,
        "stop_rule": stop_rule,
        "risk_boundary": risk_boundary,
        "lean_intent_boundary": (
            "只用 post_intent 决定这篇为什么发；只用 product_proof_shape 决定旺玥怎么种草；"
            "只用 stop_rule 决定哪里停。不要把这些字段改写成正文解释。"
        ),
    }


base.EVENT_TYPE_POOL = [
    _lane(
        event_type="choice_review",
        subtype="choice_validation_current_signal",
        post_intent="妈妈看到一个当下孩子状态或接受信号，觉得当初选旺玥这件事现在仍然说得通。",
        life_theme="从一个现在的普通生活信号写起，再回到当初为什么选这款儿童奶粉；不是被别人追问。",
        allowed_event_object="当下孩子接受度、普通状态观察、无日期选择理由、一个产品配置印象。",
        product_entry_role="旺玥是被当下信号回头验证的选择。",
        product_proof_shape="先写孩子侧的普通正向观察，再轻带一个旺玥理由；两者并列支撑，不写直接功效归因。",
        stop_rule="停在妈妈觉得这个选择仍然成立的生活瞬间，不写安心省心总结。",
        risk_boundary="不要写别人问起；不要写旧年份；不要写每天早晚/固定喝法；不要写选购教程。",
    ),
    _lane(
        event_type="choice_review",
        subtype="choice_validation_one_reason",
        post_intent="妈妈只记得当初一个简单理由，今天看孩子反馈还在，想给自己留个记录。",
        life_theme="整理手机、购物记录或随手笔记时看到一个无日期选择关键词，想起当时留下旺玥的理由。",
        allowed_event_object="无日期选择关键词、一个配置印象、当前孩子接受度或精神状态。",
        product_entry_role="旺玥是那个简单理由对应的实际选择。",
        product_proof_shape="一个产品理由要明确；孩子反馈只做旁证，不补第二个卖点。",
        stop_rule="停在这个理由还说得通，不扩展成复盘长文。",
        risk_boundary="不要写翻配方表、奶粉罐照片高频动作；不要写几个月前/去年；不要写固定喝法。",
    ),
    _lane(
        event_type="choice_review",
        subtype="choice_validation_after_activity",
        post_intent="妈妈在一次普通活动后看到孩子状态不错，回头觉得日常营养选择没白做。",
        life_theme="孩子玩完、回家、吃饭前后这种普通日常里有一个状态信号，妈妈联想到家里儿童奶粉选择。",
        allowed_event_object="活动后精神头、吃饭玩耍节奏、一个日常状态观察、一个产品营养理由。",
        product_entry_role="旺玥是日常营养选择里能被这个状态信号带出的关键证据。",
        product_proof_shape="状态观察和营养配置并列出现；不要写旺玥直接让孩子变好。",
        stop_rule="停在孩子继续玩或妈妈手头事继续，不补完整购买理由。",
        risk_boundary="不要写春游秋游、换季流感、少请假；不要写乳铁蛋白对应长肉/跑跳有劲。",
    ),
    _lane(
        event_type="usage_acceptance",
        subtype="small_acceptance_validation",
        post_intent="孩子一个不夸张的接受反应，让妈妈觉得这罐至少没有踩雷。",
        life_theme="孩子尝了旺玥相关的儿童奶粉后给出普通反馈，生活继续。",
        allowed_event_object="儿童奶粉口味接受、孩子一句普通原话、尝后没有排斥。",
        product_entry_role="旺玥是孩子接受反应指向的儿童奶粉。",
        product_proof_shape="孩子接受度就是主证明；产品理由最多只补口味或清淡奶香，不讲成分课。",
        stop_rule="停在孩子原话或动作，不扩成推荐。",
        risk_boundary="不要写每次喝完、主动要喝、每天喝、奶瓶、小包。",
    ),
    _lane(
        event_type="usage_acceptance",
        subtype="low_key_taste_signal",
        post_intent="妈妈原本担心味道不合适，孩子低调接受后，她想记这个小反差。",
        life_theme="孩子闻味道或尝一口后没有抗拒，妈妈原本准备被拒绝但没发生。",
        allowed_event_object="味道不冲、不腻、还行、不难喝、没有推开。",
        product_entry_role="旺玥是这个低调口味接受里的具体选择。",
        product_proof_shape="只让口味接受成立，不补营养和效果证明。",
        stop_rule="停在妈妈愣一下或孩子继续做自己的事。",
        risk_boundary="不要写惊喜大夸、每天固定喝、喝完整杯。",
    ),
    _lane(
        event_type="family_continuation",
        subtype="family_continue_short_answer",
        post_intent="家里人随口问要不要继续，妈妈按孩子当前状态短短回答。",
        life_theme="家里人问还喝不喝、还买不买或现在喝哪款，妈妈顺口答，家庭生活继续。",
        allowed_event_object="家庭对话、继续喝儿童奶粉、孩子当前接受度或一个产品理由。",
        product_entry_role="旺玥是家里正在继续保留的选择。",
        product_proof_shape="当前接受度或状态做主证据；产品理由只一句，不要补全成分。",
        stop_rule="停在家庭对话结束或继续做手头事；产品说明不能出现在停止点之后。",
        risk_boundary="不要写囤货、补货、价格、固定喝法；不要在对话后追加完整广告段。",
    ),
    _lane(
        event_type="family_continuation",
        subtype="family_current_state",
        post_intent="妈妈发现家里延续使用不是因为习惯，而是孩子当下状态和接受度还支持继续。",
        life_theme="家庭日常里看到孩子喝着顺或状态正常，顺带提到家里还会继续旺玥。",
        allowed_event_object="家庭日常、孩子接受度、普通状态、继续选择。",
        product_entry_role="旺玥是被当前状态支持继续保留的选择。",
        product_proof_shape="孩子状态和产品理由二选一为主，另一个轻轻出现。",
        stop_rule="停在家务/对话/孩子动作，不写妈妈结论口号。",
        risk_boundary="不要写安心省心放心；不要写固定喝法；不要写少生病。",
    ),
    _lane(
        event_type="light_comparison",
        subtype="one_reason_left",
        post_intent="妈妈只保留一个当初留下旺玥的理由，不试图给别人做测评。",
        life_theme="想起当时只在两个方向里轻轻比过，最后留下旺玥的原因很简单。",
        allowed_event_object="两款轻比较、一个接受度理由、一个营养配置印象。",
        product_entry_role="旺玥是轻比较后留下来的选择。",
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
        product_proof_shape="产品理由可以明确；孩子接受度只做短旁证。",
        stop_rule="停在这个配置点和孩子接受，不写推荐语。",
        risk_boundary="不要列成分表；不要写公开建议；不要写每天喝完。",
    ),
    _lane(
        event_type="usage_acceptance",
        subtype="plain_child_sentence",
        post_intent="孩子一句普通话让妈妈确认这款可以继续观察，不需要大夸。",
        life_theme="孩子喝后只说普通一句，妈妈觉得这比夸张好评更真实。",
        allowed_event_object="孩子普通原话、儿童奶粉接受度、低调反应。",
        product_entry_role="旺玥是孩子这句普通反馈背后的具体儿童奶粉。",
        product_proof_shape="孩子原话为主，最多补一句味道顺口。",
        stop_rule="停在原话附近。",
        risk_boundary="不要写这个奶粉太好了；不要写每天主动要；不要写固定喝法。",
    ),
]


def _clean_contract(event_type_plan: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "post_intent",
        "product_entry_role",
        "product_proof_shape",
        "stop_rule",
        "lean_intent_boundary",
    ]
    return {key: event_type_plan.get(key) for key in keys if event_type_plan.get(key)}


def _build_human_event_prompt_v436(row: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_human_event_prompt(row, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload["lean_intent_contract"] = _clean_contract(event_type_plan)
    payload["intent_use"] = (
        "只用 post_intent 生成妈妈为什么此刻想发帖。"
        "不要额外创造第二个发帖动机，不要把 product_proof_shape 写进 human_event。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_bridge_prompt_v436(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_bridge_prompt(row, human_event, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload["lean_intent_contract"] = _clean_contract(event_type_plan)
    payload["bridge_use"] = (
        "旺玥只按 product_entry_role 进入，只按 product_proof_shape 种草。"
        "如果 product_proof_shape 说一个主证据，就不要规划第二个产品证明。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt_v436(
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
    payload["lean_writer_contract"] = _clean_contract(event_type_plan)
    payload["storyline_contract"] = (
        "approved_story_plan.storyline 是唯一主线。正文必须先完成 post_intent，"
        "只按 product_proof_shape 写一个主产品证明；到 stop_rule 对应位置就停，"
        "不要在停止点之后追加营养、成分、效果、妈妈总结或广告收口。"
    )
    payload["writer_task"] = "把 approved_story_plan 写成一篇 110-170 字左右的小红书妈妈UGC正向种草笔记。"
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _local_quality_v436(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = list(quality.get("flags", []))
    text = f"{title}\n{body}"
    if _formulaic_marketing_close(text):
        flags.append("formulaic_marketing_close")
    if _fixed_usage_risk(text):
        flags.append("fixed_usage_added")
    if _asked_chain_overused(text):
        flags.append("asked_chain_overused")
    if _product_after_stop_signal(text):
        flags.append("product_after_stop_signal")
    if _unsafe_self_prepare_formula_risk(text):
        flags.append("unsafe_child_self_prepare_formula")
    if _boxed_milk_form_risk(text):
        flags.append("boxed_milk_form_drift")
    quality["flags"] = sorted(set(flags))
    if quality["flags"]:
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    return quality


def _validate_plan_v436(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    text = _plan_text(plan)
    extra: list[str] = []
    if _unsafe_self_prepare_formula_risk(text):
        extra.append("unsafe_child_self_prepare_formula_in_plan")
    if _boxed_milk_form_risk(text):
        extra.append("boxed_milk_form_drift_in_plan")
    final = sorted(set([*issues, *extra]))
    return not final, final


def _fidelity_gate_v436(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    flags = list(result.get("flags", []))
    text = f"{title}\n{body}"
    if _fixed_usage_risk(text):
        flags.append("fixed_usage_added")
    if _product_after_stop_signal(text):
        flags.append("product_after_stop_signal")
    if _unsafe_self_prepare_formula_risk(text):
        flags.append("unsafe_child_self_prepare_formula_added")
    if _boxed_milk_form_risk(text):
        flags.append("boxed_milk_form_drift_added")
    result["flags"] = sorted(set(flags))
    result["pass"] = not result["flags"]
    return result


def _formulaic_marketing_close(text: str) -> bool:
    return bool(re.search(r"(硬道理|孩子嘴最诚实|这个选择没毛病|理由挺实在|不用费劲去搭配|挺省心|挺安心|挺放心)", text))


def _fixed_usage_risk(text: str) -> bool:
    return bool(re.search(r"(每天早晚|早晚.{0,4}喝|每天.{0,8}(喝|冲)|每次都.{0,6}(喝完|干杯)|一直主动要)", text))


def _asked_chain_overused(text: str) -> bool:
    asked = bool(re.search(r"(问我|问起|有人问|评论.{0,8}问|私信.{0,8}问|她问|邻居问|妈妈问)", text))
    reason = bool(re.search(r"(乳铁蛋白|HMO|钙铁锌|营养配置|成分|配置|营养挺全|营养丰富)", text))
    feedback = bool(re.search(r"(喝得顺|喝得快|喝完|接受度|精神头|状态|饭量|活动量)", text))
    return asked and reason and feedback


def _product_after_stop_signal(text: str) -> bool:
    # The risky shape is interruption/dialogue ending followed by more product proof.
    return bool(
        re.search(
            r"(话题.{0,8}(断|停)|没再问|各忙各的|喊我|跑过来|先去陪|继续收拾)"
            r".{0,40}(旺玥|乳铁蛋白|HMO|钙铁锌|营养|喝得顺|精神头)",
            text,
        )
    )


def _plan_text(plan: dict[str, Any]) -> str:
    human_event = plan.get("human_event") or {}
    product_bridge = plan.get("product_bridge") or {}
    return json.dumps(
        {
            "human_event": {
                key: human_event.get(key)
                for key in (
                    "event_type",
                    "posting_emotion_trigger",
                    "posting_motive",
                    "human_event",
                    "life_entry",
                    "natural_stop",
                    "no_product_post",
                )
            },
            "product_bridge": {
                key: product_bridge.get(key)
                for key in (
                    "permission_reason",
                    "rejection_reason",
                    "bridge_logic",
                    "product_role",
                    "single_selling_point",
                    "positive_evidence",
                    "ending_stop",
                )
            },
            "storyline": plan.get("storyline"),
        },
        ensure_ascii=False,
    )


def _unsafe_self_prepare_formula_risk(text: str) -> bool:
    # A 3-6-year-old participating in a home powder/cup scene can be plausible.
    # Flag only unsafe or product-confusing versions, not every child agency detail.
    child_prepare = bool(
        re.search(
            r"(孩子|娃|小家伙|他|她)[^。！？；;\n]{0,24}"
            r"(自己|主动|踮脚|熟练)[^。！？；;\n]{0,24}"
            r"(舀粉|冲奶|冲开|冲水|泡奶|冲泡)",
            text,
        )
    )
    unsafe_context = bool(re.search(r"(开水|烧水|热水壶|滚水|奶瓶|一岁|两岁|刚断奶|辅食|三段)", text))
    product_form_confusion = bool(re.search(r"(出门|书包|侧袋|便携|小包|小袋|一袋|一包|分装)", text))
    return child_prepare and (unsafe_context or product_form_confusion)


def _self_prepare_formula_risk(text: str) -> bool:
    # Kept for ad-hoc inspection; not used as a hard guard after user correction.
    return bool(
        re.search(
            r"(孩子|娃|小家伙|他|她)[^。！？；;\n]{0,24}"
            r"(自己|主动|踮脚|熟练)[^。！？；;\n]{0,24}"
            r"(舀粉|冲奶|冲开|冲水|泡奶|冲泡)",
            text,
        )
    )


def _boxed_milk_form_risk(text: str) -> bool:
    return bool(re.search(r"(一盒牛奶|牛奶盒|插上?吸管|盒装牛奶|吸管奶)", text))


base._build_human_event_prompt = _build_human_event_prompt_v436
base._build_bridge_prompt = _build_bridge_prompt_v436
base._build_writer_prompt = _build_writer_prompt_v436
base._validate_plan = _validate_plan_v436
base._local_quality = _local_quality_v436
base._fidelity_gate = _fidelity_gate_v436


if __name__ == "__main__":
    base.main()
