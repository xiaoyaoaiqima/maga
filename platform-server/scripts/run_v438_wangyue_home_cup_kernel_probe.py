#!/usr/bin/env python3
"""Local Wangyue v438 home-cup kernel probe.

This probe focuses on one kernel only:

home cup scene + 3+ child light participation + low-key acceptance.

The goal is to polish this kernel before extracting additional kernels from
real examples.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v437_wangyue_minimal_four_control_probe as four_control


base = four_control.base
base.EXPERIMENT_ID = "v438_home_cup_kernel_probe"
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _lane(
    *,
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
        "event_type": "usage_acceptance",
        "subtype": subtype,
        "product_entry_eligible": True,
        "post_intent": post_intent,
        "life_theme": life_theme,
        "allowed_event_object": allowed_event_object,
        "disallowed_event_object": (
            "低龄喂养、奶瓶、盒装牛奶、牛奶盒、吸管饮品、便携袋、小包、试喝装、"
            "书包/侧袋携带奶粉、户外冲奶、开水/热水壶、固定喝法、完整选择复盘。"
        ),
        "product_entry_role": product_entry_role,
        "product_physics_boundary": (
            "旺玥按3岁以上儿童奶粉的家庭杯子场景写。可以是妈妈冲好后放在台面/餐桌，"
            "孩子拿杯子、尝一口、端着喝、放下杯子、评价一句或回去玩；"
            "可以轻微参与拿杯子或看着妈妈冲，但不要写孩子操作开水/热水壶，不要写奶瓶、盒装/吸管奶、便携小包、户外携带。"
        ),
        "product_proof_shape": product_proof_shape,
        "stop_rule": stop_rule,
        "risk_boundary": risk_boundary,
        "four_control_boundary": (
            "本篇只打磨 home-cup kernel：家里杯子物理场景 + 孩子低调接受 + 旺玥作为被接受对象。"
            "默认这不是第一次试喝，而是家里已经自然出现的杯子场景。"
            "不要扩展成选择复盘、被问回答、完整测评或家庭营养总结；"
            "不要让孩子像新品试喝一样评价这个味道还行、今天这个好喝；也不要写妈妈以为孩子不习惯。"
            "不要写妈妈意外、愣住、没想到、本来以为会拒绝；熟悉场景里不需要惊讶反差。"
            "不要用不嫌弃、不抗拒、不皱眉来证明，改用喝几口、放下、继续玩这类平常动作。"
            "不要明说真实、可信、不夸张、比好评更真，让孩子动作自己承担真实感。"
        ),
    }


base.EVENT_TYPE_POOL = [
    _lane(
        subtype="familiar_cup_small_moment",
        post_intent="家里熟悉的一杯儿童奶粉被孩子自然接受，妈妈顺手记下这个小瞬间。",
        life_theme="妈妈冲好一杯儿童奶粉放在家里台面，孩子自然拿起喝一口或几口，然后生活继续。",
        allowed_event_object="家里杯子、冲好的儿童奶粉、孩子自然拿起/喝/放下、低调接受。",
        product_entry_role="旺玥是家里这杯已经自然出现、被孩子顺手接受的儿童奶粉。",
        product_proof_shape="孩子动作是主证明；孩子原话只能围绕当下杯子或继续玩，不做新品试喝式口味评价。",
        stop_rule="停在孩子喝完一口/几口、放下杯子或转身继续玩。",
        risk_boundary="不要写第一次试喝、新开一罐、不习惯、意外、愣住、没想到、不嫌弃、不抗拒、这个味道还行、今天这个好喝、每天喝、固定喝法、慢慢喝惯、成分理由。",
    ),
    _lane(
        subtype="tiny_self_participation",
        post_intent="孩子自己参与了一点点，妈妈发现他不是被迫喝，而是自然愿意喝。",
        life_theme="孩子自己拿杯子或把杯子推过来，妈妈在旁边处理好，孩子喝一口后反应正常。",
        allowed_event_object="孩子拿杯子、妈妈在旁边、冲好的儿童奶粉、低调接受。",
        product_entry_role="旺玥是这个家庭杯子动作里被孩子接受的那款。",
        product_proof_shape="自主参与是主证明；不要写不抗拒，不要让孩子像第一次试喝一样评价味道，不要补产品配置。",
        stop_rule="停在孩子放下杯子或回去玩。",
        risk_boundary="不要写孩子独立操作热水，不写完全自理爽文，不写妈妈以为孩子不习惯、意外、愣住、没想到。",
    ),
    _lane(
        subtype="after_sip_life_moves_on",
        post_intent="孩子喝完一小口就继续自己的事，妈妈觉得这种自然接受值得记一下。",
        life_theme="孩子喝一口儿童奶粉，放下杯子，继续拼图/翻书/玩积木，妈妈在旁边看到。",
        allowed_event_object="喝一口、放下杯子、继续玩、自然接受。",
        product_entry_role="旺玥是孩子喝完后自然继续生活的那杯儿童奶粉。",
        product_proof_shape="生活继续是主证明；不写不抗拒，不补第二个卖点，不写孩子口味测评。",
        stop_rule="停在孩子继续自己的事。",
        risk_boundary="不要写喝完一整杯、每天固定、精神头效果、妈妈自己尝奶粉或拿孩子喝剩的杯子尝。",
    ),
    _lane(
        subtype="mom_taste_observation_light",
        post_intent="妈妈从孩子熟悉地喝这杯奶粉里，轻轻带到自己对口味的判断。",
        life_theme="家里杯子场景里孩子自然喝几口，妈妈只从旁边观察到它味道不冲或不齁。",
        allowed_event_object="冲好的儿童奶粉、孩子自然喝、妈妈的口味观察。",
        product_entry_role="旺玥是孩子熟悉接受、妈妈觉得口味不冲的那款儿童奶粉。",
        product_proof_shape="孩子动作是主证明，妈妈口味观察为辅；不要让孩子像第一次试喝一样评价，也不要写惊讶反差。",
        stop_rule="停在孩子继续做自己的事，妈妈不展开选择复盘。",
        risk_boundary="不要写第一次试喝、不习惯、意外、愣住、没想到、不嫌弃、不抗拒、这个味道还行、今天这个好喝、妈妈自己尝奶粉或拿孩子喝剩的杯子尝、完整选择复盘、对比好多款、包装/营养表。",
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


def _build_human_event_prompt_v438(row: dict[str, Any], index: int) -> str:
    payload = json.loads(four_control._original_build_human_event_prompt(row, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload.pop("lean_intent_contract", None)
    payload["four_control_contract"] = _contract(event_type_plan)
    payload["intent_use"] = (
        "只生成 home-cup kernel 的人类事件：家里杯子/台面/餐桌 + 孩子低调接受。"
        "默认不是第一次试喝，而是家里已经自然出现的熟悉杯子场景。"
        "不要生成被问起、翻记录、对比、完整选择复盘；不要把发帖动机写成证明真实感。"
        "posting_motive、emotional_impulse、no_product_post 也不要出现真实、可信、推销感这类元评价。"
        "孩子原话不要像新品试喝评价；不要写这个味道还行、今天这个好喝、有点甜，也不要写妈妈以为孩子不习惯。"
        "不要生成妈妈意外、愣住、没想到、本来以为会拒绝、抗拒、不嫌弃这类反差验证。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_bridge_prompt_v438(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(four_control._original_build_bridge_prompt(row, human_event, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload.pop("lean_intent_contract", None)
    payload.pop("bridge_lane_contract", None)
    payload["four_control_contract"] = _contract(event_type_plan)
    payload["bridge_use"] = (
        "旺玥只作为 home-cup kernel 里被孩子接受的儿童奶粉进入。"
        "只规划一个主证明，不要扩成选择复盘、对比或推荐；不要用真实、可信、不夸张来解释证明。"
        "如果妈妈冲的是旺玥，正文里应从冲泡动作自然带出，不要写成事后才看见/才发现杯子里是旺玥。"
        "ending_stop 只能停在孩子动作或原话，不要规划安心、省心、满意、不操心这类妈妈总结。"
        "默认孩子不是第一次喝旺玥，positive_evidence 以喝几口、放下、继续玩这类熟悉动作为主，不规划新品试喝式口味评价。"
        "这里的证明不要写成不抗拒/不嫌弃/不皱眉，而要写成喝几口、放下、继续玩。"
        "不要规划妈妈自己尝奶粉、尝孩子喝剩的杯子或尝后评价口味。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt_v438(row: dict[str, Any], plan: dict[str, Any], *, plan_valid: bool, plan_issues: list[str]) -> str:
    payload = json.loads(
        four_control._original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues)
    )
    event_type_plan = base.EVENT_TYPE_POOL[(int(row.get("item_no") or row.get("source_row_no") or 1) - 1) % len(base.EVENT_TYPE_POOL)]
    payload.pop("lean_writer_contract", None)
    payload["four_control_writer_contract"] = _contract(event_type_plan)
    payload["storyline_contract"] = (
        "approved_story_plan.storyline 是唯一主线。只写 home-cup kernel："
        "家里杯子场景、孩子低调接受、旺玥作为被接受对象。"
        "不补选择复盘、被问回答、对比、第二个效果证明、固定喝法或广告收口。"
        "不把真实感说出口，停在孩子动作、原话或妈妈当下的一下反应。"
        "标题只能从正文动作或孩子原话里长出来，不新增选奶焦虑、治好、真香、推荐等正文没有的因果。"
        "旺玥不要写成“我一看才发现/那杯是/今天泡的是”的事后标签，能在冲泡句自然出现就直接出现。"
        "不写话题标签，不写能喝下去就是好事这类低标准夸法。"
        "如果写口味，只能是妈妈旁观观察：顺口、不冲、不齁、清淡奶香；不要让孩子说这个味道还行、今天这个好喝或有点甜。"
        "不要写妈妈以为孩子不习惯、终于习惯、慢慢接受；不要写妈妈自己尝奶粉、尝孩子喝剩的杯子或尝后评价口味。"
        "不要写妈妈意外、愣住、没想到、本来以为会拒绝，也不要写不嫌弃味道、不抗拒、不皱眉。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v438(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    # avoid_links is a structural safety field, not content logic. If the model
    # omits it while the story is otherwise valid, default it instead of leaving
    # a blank preview item.
    if plan.get("avoid_links") in (None, ""):
        plan["avoid_links"] = True
    human_event = plan.get("human_event") or {}
    product_bridge = plan.get("product_bridge") or {}
    if human_event.get("avoid_links") in (None, ""):
        human_event["avoid_links"] = True
    if product_bridge.get("avoid_links") in (None, ""):
        product_bridge["avoid_links"] = True
    valid, issues = _original_validate_plan(plan)
    story_text = json.dumps(
        {
            "storyline": plan.get("storyline"),
            "human_event": plan.get("human_event"),
            "product_bridge": plan.get("product_bridge"),
        },
        ensure_ascii=False,
    )
    true_fixed_usage = bool(
        re.search(
            r"(每天|早晚|睡前|早餐奶|每到喝奶时间|固定.{0,8}(喝|安排)|每天.{0,10}(一杯|喝|冲|泡|来一杯))",
            story_text,
        )
    )
    filtered = []
    for issue in issues:
        if issue == "missing:avoid_links":
            continue
        if issue == "fixed_usage_in_plan" and not true_fixed_usage:
            continue
        filtered.append(issue)
    return not filtered, filtered


def _bad_home_cup_surface(text: str) -> list[str]:
    flags: list[str] = []
    if re.search(r"(接住了|被.*接住|真的接住)", text):
        flags.append("brief_translation_phrase")
    if re.search(r"(我|妈妈|老母亲)[^。！？\n]{0,12}(尝了|尝一口|自己尝)", text):
        flags.append("mom_tastes_leftover_or_formula")
    if re.search(r"(意外|愣住|没想到|本来以为|以为.*(拒绝|不喝|抗拒)|不嫌弃|不抗拒|没皱眉|不皱眉)", text):
        flags.append("first_trial_or_rejection_contrast")
    if re.search(r"(我一看|才发现|那杯是|今天泡的是|原来是)[^。！？\n]{0,16}旺玥", text):
        flags.append("brand_afterthought_label")
    if re.search(r"(营养丰富|这样一杯刚好|刚好一杯|他肯喝就行)", text):
        flags.append("generic_nutrition_or_low_bar_claim")
    return flags


def _local_quality_v438(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = list(quality.get("flags") or [])
    flags.extend(_bad_home_cup_surface(f"{title}\n{body}"))
    quality["flags"] = sorted(set(flags))
    if quality["flags"]:
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    return quality


def _fidelity_gate_v438(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    flags = list(result.get("flags") or [])
    flags.extend(_bad_home_cup_surface(f"{title}\n{body}"))
    result["flags"] = sorted(set(flags))
    result["pass"] = not result["flags"]
    return result


base._build_human_event_prompt = _build_human_event_prompt_v438
base._build_bridge_prompt = _build_bridge_prompt_v438
base._build_writer_prompt = _build_writer_prompt_v438
base._validate_plan = _validate_plan_v438
base._local_quality = _local_quality_v438
base._fidelity_gate = _fidelity_gate_v438


if __name__ == "__main__":
    import sys

    if "--count" not in sys.argv:
        sys.argv.extend(["--count", "5"])
    base.main()
