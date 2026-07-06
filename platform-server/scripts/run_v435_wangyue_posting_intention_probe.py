#!/usr/bin/env python3
"""Local Wangyue v435 posting-intention probe.

v434 shortened the "asked -> full product explanation" chain, but the output
still lacked a durable reason for the mother to post. This probe keeps the
v434 stack and adds a non-copyable posting-intention contract: each article
must know whether it is validating a past choice, remembering one reason,
recording a small acceptance signal, or replying only as a fragment.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import run_v434_wangyue_partial_answer_probe as partial_answer


base = partial_answer.base
base.EXPERIMENT_ID = "v435_posting_intention_probe"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)
_original_build_human_event_prompt = base._build_human_event_prompt
_original_build_bridge_prompt = base._build_bridge_prompt
_original_build_writer_prompt = base._build_writer_prompt
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _patch_intention(item: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(item)
    subtype = str(clone.get("subtype") or "")
    variant = str(clone.get("subtype_variant") or "")

    if subtype == "child_plain_sentence":
        _set_intention(
            clone,
            archetype="small_validation",
            job="孩子一句普通反馈，让妈妈觉得这次选择至少没有踩空。",
            wangyue_role="旺玥是这个普通反馈背后的具体儿童奶粉选择。",
            evidence_shape="孩子反应先成立；产品理由最多轻补一个，不写成推荐。",
            stop_logic="停在孩子原话、动作或妈妈短暂反应，不总结成选购建议。",
        )
    elif subtype in {"current_note_without_date", "ingredient_memory"}:
        _set_intention(
            clone,
            archetype="choice_validation",
            job="妈妈看到一个当时留下的理由，验证自己当初选旺玥不是随便选。",
            wangyue_role="旺玥是被回头验证的选择，不是被重新推销的产品。",
            evidence_shape="一个孩子状态或接受度 + 一个产品理由互相支撑；不要写成三段证明。",
            stop_logic="停在选择仍然成立的感觉或一个眼前生活动作。",
        )
    elif subtype == "two_options_only" and variant == "two_options_product_reason_first":
        _set_intention(
            clone,
            archetype="choice_validation",
            job="妈妈回看两项轻比较，发现留下旺玥的理由到现在还说得通。",
            wangyue_role="旺玥是轻比较后留下来的那一项。",
            evidence_shape="产品理由可以明确；孩子反馈作为旁证，不再扩成测评。",
            stop_logic="停在为什么留下它，不写公开购买建议。",
        )
    elif subtype == "two_options_only":
        _set_intention(
            clone,
            archetype="light_comparison_validation",
            job="妈妈只记得一个留下旺玥的原因，不试图复盘完整测评。",
            wangyue_role="旺玥是被孩子反馈或营养印象留下的选择。",
            evidence_shape="一个留下原因就够；别同时写价格、成分、状态和建议。",
            stop_logic="停在自己的选择原因，别转成教程。",
        )
    elif subtype == "asked_and_answered_now" and variant == "asked_reason_life_interruption":
        _set_intention(
            clone,
            archetype="light_reply_fragment",
            job="别人问起时，妈妈只答了最顺口的一句，生活把回答截断。",
            wangyue_role="旺玥是短答里的具体选择，不是完整推荐主题。",
            evidence_shape="只落一个产品理由或孩子反馈；另一个最多擦边出现。",
            stop_logic="被孩子、手头事或对话打断后就停，不补产品说明。",
        )
    elif subtype in {"asked_and_answered_now", "comment_question"}:
        _set_intention(
            clone,
            archetype="remembered_reason",
            job="被问起后，妈妈只想起一个自己真正记得住的理由。",
            wangyue_role="旺玥是这个记忆点对应的实际选择。",
            evidence_shape="理由可以直接，但像普通人回答；不要把所有卖点一次讲完。",
            stop_logic="停在一个记得住的理由，不给陌生人做完整选购建议。",
        )
    elif subtype == "family_member_asks":
        _set_intention(
            clone,
            archetype="family_continuation",
            job="家里人问还要不要继续，妈妈按孩子当前状态判断继续就行。",
            wangyue_role="旺玥是家里已经在喝、被继续保留的选择。",
            evidence_shape="当前接受度或状态先成立；产品理由轻补，不写囤货和固定喝法。",
            stop_logic="停在家庭对话或手头事继续。",
        )
    elif subtype == "short_reply_then_life_moves_on":
        _set_intention(
            clone,
            archetype="light_reply_fragment",
            job="妈妈短答后生活继续，这条帖只记录那个短答片段。",
            wangyue_role="旺玥是短答里出现的家里选择。",
            evidence_shape="产品名 + 一个理由或反馈即可；别把短答扩成推介。",
            stop_logic="停在生活继续，不补总结。",
        )
    else:
        _set_intention(
            clone,
            archetype="small_validation",
            job="一个普通生活反应让妈妈觉得这款选择还站得住。",
            wangyue_role="旺玥是这个反应背后的具体选择。",
            evidence_shape="孩子反馈和产品理由只保留一个主证据。",
            stop_logic="停在现场，不写广告收口。",
        )

    clone["posting_intention_boundary"] = (
        "以下发帖心理只用于规划，不是正文句式；不要照抄字段，不要写成'验证当初选对了'这种解释话。"
    )
    return clone


def _set_intention(
    item: dict[str, Any],
    *,
    archetype: str,
    job: str,
    wangyue_role: str,
    evidence_shape: str,
    stop_logic: str,
) -> None:
    item.update(
        {
            "posting_intention_archetype": archetype,
            "posting_intention_job": job,
            "wangyue_role_under_intention": wangyue_role,
            "intention_evidence_shape": evidence_shape,
            "intention_stop_logic": stop_logic,
        }
    )


base.EVENT_TYPE_POOL = [_patch_intention(item) for item in _previous_pool]


def _intention_contract(event_type_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: event_type_plan.get(key)
        for key in (
            "posting_intention_archetype",
            "posting_intention_job",
            "wangyue_role_under_intention",
            "intention_evidence_shape",
            "intention_stop_logic",
            "posting_intention_boundary",
        )
        if event_type_plan.get(key)
    }


def _build_human_event_prompt_v435(row: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_human_event_prompt(row, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload["posting_intention_contract"] = _intention_contract(event_type_plan)
    payload["posting_intention_use"] = (
        "先按 posting_intention_contract 生成妈妈为什么此刻想发帖。"
        "human_event 只写真实生活触发，不新增旺玥事实、成分或效果证明。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_bridge_prompt_v435(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_bridge_prompt(row, human_event, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload["posting_intention_contract"] = _intention_contract(event_type_plan)
    payload["posting_intention_bridge_use"] = (
        "product_bridge 必须让旺玥服务于这篇的发帖心理。"
        "如果发帖心理是验证过去选择，旺玥承担'选择仍然成立'的关键证据；"
        "如果是片段回答，旺玥只承担短答里的一个理由或反馈。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt_v435(
    row: dict[str, Any],
    plan: dict[str, Any],
    *,
    plan_valid: bool,
    plan_issues: list[str],
) -> str:
    payload = json.loads(
        _original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues)
    )
    event_type_plan = payload.get("event_type_plan") or {}
    payload["posting_intention_writer_contract"] = _intention_contract(event_type_plan)
    payload["writer_posture_v435"] = (
        "正文要像妈妈在完成这篇的发帖心理，不像在完成卖点清单。"
        "可以正面写旺玥的好处，但每篇只让一个主证据推动内容；"
        "不要把发帖心理、产品理由、孩子状态写成并列表。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _local_quality_v435(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = list(quality.get("flags", []))
    text = f"{title}\n{body}"
    if _meta_realism_risk_v435(text):
        flags.append("meta_realism_surface")
    if _answer_then_full_explanation(text):
        flags.append("answer_then_full_explanation")
    quality["flags"] = sorted(set(flags))
    if quality["flags"]:
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    return quality


def _fidelity_gate_v435(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    flags = list(result.get("flags", []))
    text = f"{title}\n{body}"
    if _meta_realism_risk_v435(text):
        flags.append("meta_realism_surface_added")
    result["flags"] = sorted(set(flags))
    result["pass"] = not result["flags"]
    return result


def _meta_realism_risk_v435(text: str) -> bool:
    return bool(
        re.search(
            r"(真实吧|琐碎又真实|生活本来|当妈就是这样|话永远说不完整|生活就是这些小片段)",
            text,
        )
    )


def _answer_then_full_explanation(text: str) -> bool:
    asked = any(term in text for term in ("问我", "问起", "有人问", "评论", "私信", "她问"))
    product_reason = any(term in text for term in ("乳铁蛋白", "HMO", "钙铁锌", "营养配置", "营养表", "成分"))
    child_state = any(term in text for term in ("精神头", "饭量", "活动量", "状态", "喝得顺", "喝完", "接受度"))
    closure = any(term in text for term in ("关键", "理由", "放心", "省心", "挺简单", "硬道理"))
    return asked and product_reason and child_state and closure


base._build_human_event_prompt = _build_human_event_prompt_v435
base._build_bridge_prompt = _build_bridge_prompt_v435
base._build_writer_prompt = _build_writer_prompt_v435
base._local_quality = _local_quality_v435
base._fidelity_gate = _fidelity_gate_v435


if __name__ == "__main__":
    base.main()
