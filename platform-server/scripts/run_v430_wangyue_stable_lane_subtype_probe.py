#!/usr/bin/env python3
"""Local Wangyue v430 stable-lane subtype probe.

Builds on v429. v429 made the storylines coherent by keeping only lanes where
Wangyue has narrative permission. Its new bottleneck was within-lane repetition:
usage_acceptance collapsed into "one sip -> sweet/tasty -> mom surprised", and
choice_review kept reaching for old-year records.

This version keeps the same architecture, but replaces repeated lane weights
with concrete subtypes inside the stable lanes.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import run_v429_wangyue_production_lane_mix_probe as lane_mix


base = lane_mix.base
base.EXPERIMENT_ID = "v430_stable_lane_subtype_probe"


_previous_pool = copy.deepcopy(base.EVENT_TYPE_POOL)
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality


def _lane(name: str) -> dict[str, Any]:
    for item in _previous_pool:
        if item.get("event_type") == name:
            return copy.deepcopy(item)
    raise KeyError(name)


def _with_updates(name: str, **updates: Any) -> dict[str, Any]:
    item = _lane(name)
    item.update(updates)
    return item


base.EVENT_TYPE_POOL = [
    _with_updates(
        "usage_acceptance",
        subtype="slow_acceptance",
        route_reason="孩子从犹豫到接受，靠动作变化证明口味接受，不靠夸张好喝。",
        life_theme="孩子对儿童奶粉先犹豫，后来通过多尝一口、没推开、表情放松这类小动作表现接受。",
        emotion_trigger_allowed="妈妈看到孩子没有推开、没有皱很久、愿意再试一口时有点意外。",
        emotion_trigger_disallowed="直接大夸好喝、每天主动要喝、喝完整杯、功效解释。",
        natural_stop_hint="停在动作变化或一句很轻的评价，不一定写甜或好喝。",
    ),
    _with_updates(
        "usage_acceptance",
        subtype="plain_milk_smell",
        route_reason="口味证据来自清淡奶香、不冲、不腻这类低夸张描述。",
        life_theme="孩子闻了闻或尝了一口后，说味道不冲、香香的、还行，妈妈记录这种低调接受。",
        emotion_trigger_allowed="孩子对味道的轻反馈；妈妈发现没有排斥。",
        emotion_trigger_disallowed="甜到喜欢、惊喜大夸、固定喝法、和竞品攻击对比。",
        natural_stop_hint="停在低调口味反馈，少用眼睛亮、好好喝。",
    ),
    _with_updates(
        "usage_acceptance",
        subtype="unfinished_parent_reaction",
        route_reason="妈妈自己的预期被轻轻打断，比孩子夸奖更像日常。",
        life_theme="妈妈本来准备接受孩子拒绝，结果孩子多尝了一口或没把杯子推回来，她的话头停住。",
        emotion_trigger_allowed="妈妈原本以为要失败，结果孩子反应比预期好一点。",
        emotion_trigger_disallowed="老母亲狂喜、终于找到救星、每天主动喝、喝完整杯。",
        natural_stop_hint="停在妈妈话头被打断或愣一下，不做总结。",
    ),
    _with_updates(
        "usage_acceptance",
        subtype="child_plain_sentence",
        route_reason="产品证明来自孩子一句普通原话，避免重复甜/好喝。",
        life_theme="孩子尝后只说一句很普通的话，比如还可以、不难喝、这个可以、味道还行。",
        emotion_trigger_allowed="孩子一句不夸张的原话让妈妈觉得有记录价值。",
        emotion_trigger_disallowed="强烈推荐、夸张惊喜、固定喝法、喝完还要。",
        natural_stop_hint="停在孩子原话，正文短一点。",
    ),
    _with_updates(
        "choice_review",
        subtype="asked_and_answered_now",
        route_reason="选择复盘由当下被问起触发，不靠旧年份记录。",
        life_theme="朋友或同小区妈妈现在问起为什么选这款儿童奶粉，妈妈当场想起一个选择理由。",
        allowed_event_object="当下被问选择理由、当前聊天里的简短回答、一个选择理由。",
        risk_boundary="不要写去年、一年前、半年前、几个月前、旧截图；不要写完整做功课链。",
        natural_stop_hint="停在这次回答本身，不翻旧记录。",
    ),
    _with_updates(
        "choice_review",
        subtype="current_note_without_date",
        route_reason="可以有记录感，但不出现旧时间锚点。",
        life_theme="妈妈翻到手机里存着的一条无日期选择备注，想起当时为什么留下旺玥。",
        allowed_event_object="无日期备注、手机备忘录里的一两条选择关键词、当前整理手机时看到的记录。",
        risk_boundary="不要写去年、一年前、半年前、几个月前；不要写低龄或三岁前选择。",
        natural_stop_hint="停在一个选择理由和一个现在普通观察。",
    ),
    _with_updates(
        "choice_review",
        subtype="ingredient_memory",
        route_reason="复盘只保留一个成分印象，避免完整参数表。",
        life_theme="别人问起时，妈妈只记得旺玥有一两个自己看得懂的配置，不展开成测评。",
        allowed_event_object="选择理由、一个成分印象、孩子接受度或普通状态观察。",
        risk_boundary="不要写成分课、不要列一串专业词、不要说看配方表看半天。",
        natural_stop_hint="停在一个记得住的配置和孩子接受度。",
    ),
    _with_updates(
        "routine_arrangement",
        subtype="short_reply_then_life_moves_on",
        route_reason="日常回答后马上回到生活动作，降低广告感。",
        life_theme="被问家里喝什么儿童奶粉，妈妈短短答一句，随后被孩子或家务打断。",
        allowed_event_object="被问喝什么、简短回答、孩子或家务打断。",
        risk_boundary="不要把回答扩成完整推荐；不要用顺手记一下收尾。",
        natural_stop_hint="停在孩子喊人、拿东西、回家这类生活动作。",
    ),
    _with_updates(
        "routine_arrangement",
        subtype="family_member_asks",
        route_reason="把提问者从邻居/群聊扩展到家人，增加真实入口。",
        life_theme="家里人随口问儿童奶粉还喝不喝或买哪款，妈妈按家里现状回答旺玥。",
        allowed_event_object="家人随口问、家里正在喝什么、一个简短理由。",
        risk_boundary="不要写囤货、补货焦虑、固定喝法、价格取舍。",
        natural_stop_hint="停在家里对话结束或继续做手头事。",
    ),
    _with_updates(
        "light_comparison",
        subtype="two_options_only",
        route_reason="轻对比只保留两款之间的选择感，避免完整测评。",
        life_theme="被问起时，妈妈想起当时只是在两款儿童奶粉里简单比了一下，最后留下旺玥。",
        allowed_event_object="两款轻对比、孩子接受度、一个营养表印象。",
        risk_boundary="不要写去年、一年前、试喝装、问在哪里买、竞品攻击。",
        natural_stop_hint="停在为什么留下旺玥，不扩展购买建议。",
    ),
    _with_updates(
        "light_comparison",
        subtype="comment_question",
        route_reason="用评论/私信里的问题触发，减少小区妈妈模板。",
        life_theme="有人在评论或私信里问儿童奶粉怎么选，妈妈简短说自己当时的轻对比。",
        allowed_event_object="评论或私信提问、简短选择过程、孩子接受度。",
        risk_boundary="不要写求链接、怎么买、在哪里买；不要写固定喝法。",
        natural_stop_hint="停在自己的选择原因，不写销售引导。",
    ),
]


def _validate_plan_v430(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    text = _plan_text(plan)
    event_type = _event_type(plan)
    extra: list[str] = []
    if event_type in {"choice_review", "light_comparison"} and _old_selection_time_anchor(text):
        extra.append("old_selection_time_anchor")
    final = sorted(set([*issues, *extra]))
    return not final, final


def _local_quality_v430(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    flags = list(quality.get("flags", []))
    text = f"{title}\n{body}"
    event_type = _event_type(plan)
    if event_type in {"choice_review", "light_comparison"} and _old_selection_time_anchor(text):
        flags.append("old_selection_time_anchor_added")
    if event_type == "usage_acceptance" and "direct_causality" in flags and _usage_acceptance_try_text(text):
        flags.remove("direct_causality")
    quality["flags"] = sorted(set(flags))
    if quality["flags"]:
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    else:
        quality["hard_pass"] = True
        quality["business_tier"] = "direct_pool"
        quality["business_reason"] = "本地架构实验粗审通过"
    return quality


def _event_type(plan: dict[str, Any]) -> str:
    return str(((plan.get("human_event") or {}).get("event_type") or "")).strip()


def _plan_text(plan: dict[str, Any]) -> str:
    return str(plan)


def _old_selection_time_anchor(text: str) -> bool:
    return bool(re.search(r"(去年|上年|一年前|两年前|三年前|半年前|几个月前|上个月|前几年).{0,32}(选|挑|定|留下|旺玥|奶粉)", text))


def _usage_acceptance_try_text(text: str) -> bool:
    has_try = re.search(r"(让|给).{0,8}(他|她|孩子|娃).{0,6}(试|尝)|试试|尝一口|抿了一口|喝了一口", text)
    has_effect = re.search(r"旺玥.{0,12}(改善|提升|解决|带来|导致|使)", text)
    return bool(has_try and not has_effect)


base._validate_plan = _validate_plan_v430
base._local_quality = _local_quality_v430


if __name__ == "__main__":
    base.main()
