#!/usr/bin/env python3
"""Local Wangyue v432 real-trigger-family probe.

Builds on v431 lane/evidence binding. v431 improved coherence but still used
cheap event triggers such as half-cup sipping, someone asking, or flipping a
note. This version adds a real-post-derived trigger family to the human-event
planner only. It does not feed raw real-post facts to the writer.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import run_v431_wangyue_lane_evidence_binding_probe as evidence_binding


base = evidence_binding.base
base.EXPERIMENT_ID = "v432_real_trigger_family_probe"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)
_original_build_human_event_prompt = base._build_human_event_prompt
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _by_subtype(subtype: str) -> dict[str, Any]:
    for item in _previous_pool:
        if item.get("subtype") == subtype:
            return copy.deepcopy(item)
    raise KeyError(subtype)


def _with_trigger(subtype: str, **updates: Any) -> dict[str, Any]:
    item = _by_subtype(subtype)
    item.update(updates)
    item["real_trigger_boundary"] = (
        "触发器只决定妈妈为什么此刻想发帖；不提供产品事实、成分、效果证明或正文句式。"
        "不要照抄触发器字段，不要把触发器写成标题。"
    )
    return item


base.EVENT_TYPE_POOL = [
    _with_trigger(
        "slow_acceptance",
        real_post_trigger_family="mild_problem_then_try_option",
        trigger_motive="孩子平时对味道/新选择比较挑，妈妈看到这次没有直接拒绝，才想记一下。",
        allowed_event_source="一个低强度的接受变化；可以来自闻味道、第一口反应、放下后没拒绝。",
        forbidden_event_source="不要只写半杯/小半杯/抿一口；不要写低龄喂养、奶瓶、固定喝法。",
    ),
    _with_trigger(
        "plain_milk_smell",
        real_post_trigger_family="mild_problem_then_try_option",
        trigger_motive="妈妈原本担心味道不合适，结果孩子反应没有那么抗拒。",
        allowed_event_source="味道轻反馈、闻起来不排斥、试完继续去做自己的事。",
        forbidden_event_source="不要写惊喜大夸、每天要喝、喝完整杯。",
    ),
    _with_trigger(
        "child_plain_sentence",
        real_post_trigger_family="child_plain_reaction",
        trigger_motive="孩子一句普通评价让妈妈觉得有点好笑或值得记。",
        allowed_event_source="一句短短的孩子原话，后面生活继续。",
        forbidden_event_source="不要让孩子说广告话；不要扩成完整推荐。",
    ),
    _with_trigger(
        "asked_and_answered_now",
        real_post_trigger_family="current_question_explains_choice",
        trigger_motive="别人当下问起为什么这么选，妈妈发现自己能说出一个理由。",
        allowed_event_source="聊天里的当前问题、朋友/家人/评论问选择理由。",
        forbidden_event_source="不要来自别人看见孩子手里拿奶粉盒、奶瓶、便携袋或包装。",
    ),
    _with_trigger(
        "current_note_without_date",
        real_post_trigger_family="no_date_choice_memory",
        trigger_motive="看到无日期的选择记录，想起当初留下一款的理由。",
        allowed_event_source="无日期备注、购物车收藏、当时留下的一两个关键词。",
        forbidden_event_source="不要写去年、一年前、几个月前；不要写翻配方表看半天。",
    ),
    _with_trigger(
        "ingredient_memory",
        real_post_trigger_family="remembered_product_reason",
        trigger_motive="被问起后只记得一两个看得懂的配置，不想写成测评。",
        allowed_event_source="一个配置印象、一个孩子反馈。",
        forbidden_event_source="不要写成分课、专家口吻、参数表。",
    ),
    _with_trigger(
        "short_reply_then_life_moves_on",
        real_post_trigger_family="current_question_explains_choice",
        trigger_motive="别人问喝什么，妈妈短答后生活马上把话题打断。",
        allowed_event_source="一句普通问答后被孩子、家务、手头事打断。",
        forbidden_event_source="不要继续补广告说明；不要写邻居/群聊同一模板过重。",
    ),
    _with_trigger(
        "family_member_asks",
        real_post_trigger_family="still_keeping_it_moment",
        trigger_motive="家里人随口问还要不要继续这款，妈妈按现状回答。",
        allowed_event_source="家庭对话、购物清单、家里仍在用的 continuation moment。",
        forbidden_event_source="不要写库存清货、价格取舍、见底焦虑、固定喝法。",
    ),
    _with_trigger(
        "two_options_only",
        real_post_trigger_family="no_date_choice_memory",
        trigger_motive="曾经简单比过两个方向，现在只记得一个留下它的理由。",
        allowed_event_source="两项轻对比、一个记忆点、一个孩子接受反馈。",
        forbidden_event_source="不要攻击另一款；不要写大半罐剩下这类强竞品负面。",
    ),
    _with_trigger(
        "comment_question",
        real_post_trigger_family="current_question_explains_choice",
        trigger_motive="评论/私信问怎么选，妈妈只回复自己的简单经验。",
        allowed_event_source="评论或私信的选择问题。",
        forbidden_event_source="不要求链接、不要在哪里买、不要销售引导。",
    ),
]


def _build_human_event_prompt_v432(row: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_human_event_prompt(row, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload["real_post_trigger_contract"] = {
        key: event_type_plan.get(key)
        for key in (
            "real_post_trigger_family",
            "trigger_motive",
            "allowed_event_source",
            "forbidden_event_source",
            "real_trigger_boundary",
        )
        if event_type_plan.get(key)
    }
    payload["trigger_use"] = (
        "先用 real_post_trigger_contract 决定发帖触发，再生成 human_event。"
        "触发器不能新增产品事实，也不能变成正文可复制句。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v432(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    if _bag_or_pack_formula_risk(_plan_text(plan)):
        issues = [*issues, "wangyue_bag_or_pack_form_in_plan"]
    final = sorted(set(issues))
    return not final, final


def _local_quality_v432(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = list(quality.get("flags", []))
    text = f"{title}\n{body}"
    if _bag_or_pack_formula_risk(text):
        flags.append("wangyue_bag_or_pack_form")
    if _meta_realism_risk(text):
        flags.append("meta_realism_surface")
    quality["flags"] = sorted(set(flags))
    if quality["flags"]:
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    return quality


def _fidelity_gate_v432(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    flags = list(result.get("flags", []))
    text = f"{title}\n{body}"
    if _bag_or_pack_formula_risk(text):
        flags.append("wangyue_bag_or_pack_form_added")
    if _meta_realism_risk(text):
        flags.append("meta_realism_surface_added")
    result["flags"] = sorted(set(flags))
    result["pass"] = not result["flags"]
    return result


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


def _bag_or_pack_formula_risk(text: str) -> bool:
    return bool(
        re.search(r"(拆了?一袋|一袋|袋装|一包|几包|小包|小袋|便携装|分装)[^。！？；;\n]{0,12}(旺玥|皇家美素佳儿|儿童奶粉|奶粉)", text)
        or re.search(r"(旺玥|皇家美素佳儿|儿童奶粉|奶粉)[^。！？；;\n]{0,12}(一袋|袋装|一包|几包|小包|小袋|便携装|分装)", text)
    )


def _meta_realism_risk(text: str) -> bool:
    return bool(re.search(r"(真实吧|琐碎又真实|生活本来|当妈就是这样|话永远说不完整)", text))


base._build_human_event_prompt = _build_human_event_prompt_v432
base._validate_plan = _validate_plan_v432
base._local_quality = _local_quality_v432
base._fidelity_gate = _fidelity_gate_v432


if __name__ == "__main__":
    base.main()
