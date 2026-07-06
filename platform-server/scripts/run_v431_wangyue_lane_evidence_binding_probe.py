#!/usr/bin/env python3
"""Local Wangyue v431 lane-evidence binding probe.

v429 proved that product-entry-eligible lanes improve coherence.
v430 added lane subtypes, but most changes were still surface-level.

This probe tests the next requirement-model step: each lane subtype carries one
dominant mom psychology, one main evidence direction, one secondary evidence
direction, and one stop mode. These are planner constraints, not copywriting
phrases.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import run_v430_wangyue_stable_lane_subtype_probe as subtype_probe


base = subtype_probe.base
base.EXPERIMENT_ID = "v431_lane_evidence_binding_probe"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)
_original_build_human_event_prompt = base._build_human_event_prompt
_original_build_bridge_prompt = base._build_bridge_prompt
_original_build_writer_prompt = base._build_writer_prompt
_original_local_quality = base._local_quality


def _lane(subtype: str) -> dict[str, Any]:
    for item in _previous_pool:
        if item.get("subtype") == subtype:
            return copy.deepcopy(item)
    raise KeyError(subtype)


def _with_binding(subtype: str, **updates: Any) -> dict[str, Any]:
    item = _lane(subtype)
    item.update(updates)
    item["lane_binding_boundary"] = (
        "以下字段只用于内部规划。生成正文时不得照抄字段名、内部标签或解释口吻。"
        "每篇只沿一个妈妈心理动作推进。"
    )
    return item


base.EVENT_TYPE_POOL = [
    _with_binding(
        "slow_acceptance",
        mom_motion="记录型：孩子从不确定到能接受，妈妈只是记住这个小反应。",
        main_evidence="接受动作：没有推开、愿意再尝、表情放松。",
        secondary_evidence="只允许补一个轻产品理由，例如味道不冲或清淡奶香。",
        product_key_role="旺玥是这个接受瞬间里的具体儿童奶粉。",
        stop_mode="停在孩子动作或一句普通评价，不做妈妈总结。",
        forbidden_expansion="不扩成选择复盘、固定喝法、效果总结。",
    ),
    _with_binding(
        "plain_milk_smell",
        mom_motion="省事型：孩子不排斥，家里少一次折腾。",
        main_evidence="口味低调接受：不冲、不腻、味道还行。",
        secondary_evidence="妈妈可以轻轻带到以后愿意继续选，但不写省心安心。",
        product_key_role="旺玥是家里可以继续留下的选择。",
        stop_mode="停在妈妈当下反应或孩子继续做别的事。",
        forbidden_expansion="不写甜到喜欢、惊喜大夸、每天主动喝。",
    ),
    _with_binding(
        "child_plain_sentence",
        mom_motion="记录型：孩子一句普通原话让妈妈觉得值得发。",
        main_evidence="孩子原话里的接受度。",
        secondary_evidence="只补一个产品理由，优先口味或营养配置里最容易理解的一点。",
        product_key_role="旺玥是孩子这句话指向的对象。",
        stop_mode="停在孩子原话附近。",
        forbidden_expansion="不把一句话扩成完整推荐。",
    ),
    _with_binding(
        "asked_and_answered_now",
        mom_motion="谨慎型：别人当下问起，妈妈能说出为什么选。",
        main_evidence="一个选择理由或配置印象。",
        secondary_evidence="孩子接受度或日常状态里的一个观察。",
        product_key_role="旺玥是被问起后能解释清楚的选择。",
        stop_mode="停在这次回答本身，不翻旧年份记录。",
        forbidden_expansion="不写完整做功课链、不写去年/一年前/几个月前。",
    ),
    _with_binding(
        "current_note_without_date",
        mom_motion="谨慎型：看到无日期备注，回想当时为什么留下它。",
        main_evidence="一个记得住的产品理由。",
        secondary_evidence="现在孩子接受或状态还可以。",
        product_key_role="旺玥是回看后仍然成立的选择。",
        stop_mode="停在选择仍然成立，不写大总结。",
        forbidden_expansion="不写旧时间锚点、不写低龄履历。",
    ),
    _with_binding(
        "ingredient_memory",
        mom_motion="谨慎型：妈妈只记住少数看得懂的配置。",
        main_evidence="一个成分/营养配置记忆点。",
        secondary_evidence="孩子愿意喝或日常状态正常。",
        product_key_role="旺玥是配置记忆点和孩子反馈能对上的选择。",
        stop_mode="停在一个配置印象和一个自家反馈。",
        forbidden_expansion="不列成分表、不写成分课、不翻配方表看半天。",
    ),
    _with_binding(
        "short_reply_then_life_moves_on",
        mom_motion="省事型：被问时短短回答，生活马上继续。",
        main_evidence="家里正在喝什么的简短回答。",
        secondary_evidence="只选产品理由或状态反馈之一。",
        product_key_role="旺玥是日常回答里的具体选择，不是推荐演讲。",
        stop_mode="停在孩子喊人、回消息结束或手头事继续。",
        forbidden_expansion="不扩成完整推荐，不用顺手记一下。",
    ),
    _with_binding(
        "family_member_asks",
        mom_motion="实用型：家里人问还喝不喝，妈妈按现状判断。",
        main_evidence="当前接受度或状态反馈。",
        secondary_evidence="一个简短选择理由。",
        product_key_role="旺玥是家里已经在用、能继续选的那罐。",
        stop_mode="停在家庭对话结束或继续忙手头事。",
        forbidden_expansion="不写囤货、补货焦虑、价格取舍、固定喝法。",
    ),
    _with_binding(
        "two_options_only",
        mom_motion="谨慎型：只保留两款之间的轻比较记忆。",
        main_evidence="一个产品记忆点。",
        secondary_evidence="孩子接受度。",
        product_key_role="旺玥是轻比较后留下来的选择。",
        stop_mode="停在为什么留下旺玥。",
        forbidden_expansion="不写完整测评表、不攻击竞品、不写购买建议。",
    ),
    _with_binding(
        "comment_question",
        mom_motion="谨慎型或省事型：有人问怎么选，妈妈只说自己的简单经验。",
        main_evidence="一个选择理由。",
        secondary_evidence="接受度或状态反馈二选一。",
        product_key_role="旺玥是个人经验里的具体选择。",
        stop_mode="停在自己的选择原因，不做销售引导。",
        forbidden_expansion="不写求链接、怎么买、在哪里买。",
    ),
]


def _build_human_event_prompt_v431(row: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_human_event_prompt(row, index))
    payload["high_score_lane_binding"] = {
        key: (payload.get("event_type_plan") or {}).get(key)
        for key in (
            "mom_motion",
            "main_evidence",
            "secondary_evidence",
            "stop_mode",
            "forbidden_expansion",
            "lane_binding_boundary",
        )
        if (payload.get("event_type_plan") or {}).get(key)
    }
    payload["binding_use"] = (
        "只用 high_score_lane_binding 决定这条发帖冲动的心理方向和停笔位置；"
        "不要把内部字段名或字段值写进 human_event。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_bridge_prompt_v431(row: dict[str, Any], human_event: dict[str, Any], index: int) -> str:
    payload = json.loads(_original_build_bridge_prompt(row, human_event, index))
    event_type_plan = payload.get("event_type_plan") or {}
    payload["high_score_product_contract"] = {
        key: event_type_plan.get(key)
        for key in (
            "main_evidence",
            "secondary_evidence",
            "product_key_role",
            "stop_mode",
            "forbidden_expansion",
            "lane_binding_boundary",
        )
        if event_type_plan.get(key)
    }
    payload["contract_use"] = (
        "product_bridge 必须沿 high_score_product_contract 规划旺玥的进入方式；"
        "主证据和辅证据不要并列堆满，能自然连接才写。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt_v431(row: dict[str, Any], plan: dict[str, Any], *, plan_valid: bool, plan_issues: list[str]) -> str:
    payload = json.loads(_original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues))
    payload["high_score_writer_contract"] = (
        "这篇只保留一个主心理动作；旺玥承担关键证据，但不要把文章扩成广告闭环。"
        "如果主线已经有产品理由，就不要再补第二个理由；如果已经有状态反馈，就不要再补第二个效果证明。"
        "结尾停在 approved_story_plan.ending_stop 附近。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _local_quality_v431(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = list(quality.get("flags", []))
    text = f"{title}\n{body}"
    if _multi_psychology_stitching(text):
        flags.append("multi_psychology_stitching")
    quality["flags"] = sorted(set(flags))
    if quality["flags"]:
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    return quality


def _multi_psychology_stitching(text: str) -> bool:
    choice = any(term in text for term in ("对比", "选了", "看中", "配置", "营养表", "成分"))
    asked = any(term in text for term in ("问我", "被问", "追问", "评论", "私信"))
    acceptance = any(term in text for term in ("好喝", "还行", "不冲", "不腻", "没推开", "愿意喝"))
    status = any(term in text for term in ("精神头", "饭量", "活动量", "状态", "出勤", "请假", "专注"))
    return sum(bool(item) for item in (choice, asked, acceptance, status)) >= 4


base._build_human_event_prompt = _build_human_event_prompt_v431
base._build_bridge_prompt = _build_bridge_prompt_v431
base._build_writer_prompt = _build_writer_prompt_v431
base._local_quality = _local_quality_v431


if __name__ == "__main__":
    base.main()
