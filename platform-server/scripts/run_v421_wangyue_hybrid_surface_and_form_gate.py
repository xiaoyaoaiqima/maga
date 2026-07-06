#!/usr/bin/env python3
"""Local Wangyue hybrid surface/form gate experiment.

Builds on v419. This keeps the lane-contract architecture, but addresses the
v420 human bucket findings:

- preserve strong proof in usage_acceptance / choice_review / light_comparison;
- reduce copyable campaign/planner surface in final writing;
- catch portable product-form drift earlier.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v419_wangyue_bridge_contract_gate_cleanup as cleanup


base = cleanup.base
base.EXPERIMENT_ID = "v421_hybrid_surface_and_form_gate"


SURFACE_TRANSLATION_CONTRACTS: dict[str, dict[str, str]] = {
    "choice_review": {
        "keep_strength": "可以直接说最后选了旺玥、当时记住的一个理由、现在一个自家观察。",
        "surface": "把进阶保护力/营养配置这类词写成妈妈记得住的选择理由，不写成活动卖点口播。",
    },
    "nutrition_review": {
        "keep_strength": "可以写日常饭桌/饮食小片段里顺带提旺玥，并给一个普通状态观察。",
        "surface": "不要把日常写成营养管理任务；少用日常营养安排、阶段营养、常备项。",
    },
    "routine_arrangement": {
        "keep_strength": "可以写别人问起后顺口说家里喝旺玥，再补一个自然理由。",
        "surface": "不要让产品以随身携带、包里露出奶粉罐、水杯泡好奶粉的形式出现。",
    },
    "growth_stage_observation": {
        "keep_strength": "只允许弱带旺玥，作为妈妈有留意营养的一项。",
        "surface": "不要让旺玥承接长高、长肉、结实、跑跳有劲、衣服变短等成长证明。",
    },
    "shopping_list_restock": {
        "keep_strength": "产品只做清单里的一项；这条不承担主要种草。",
        "surface": "不写常备项、阶段营养刚好合适、回购、囤货、喝完、效果证明。",
    },
    "usage_acceptance": {
        "keep_strength": "强种草保留，孩子当场反应就是产品证明。",
        "surface": "不需要补成分解释；可以停在孩子的表情、原话、又尝一口。",
    },
    "light_comparison": {
        "keep_strength": "可以写简单对比后留下旺玥，理由是接受度、口味或一个营养点。",
        "surface": "不要写完整测评，也不要把儿童奶粉写成出门水杯/奶瓶/便携装。",
    },
}

BUSINESS_SURFACE_LEAK_PATTERNS = [
    r"进阶保护力(配方|配置|这块|加加油)?",
    r"阶段营养(刚好合适|安排|这块)?",
    r"日常营养安排",
    r"常备项",
    r"营养不用我操心",
    r"功夫没白(做|费)",
    r"都有回声",
    r"成长的注脚",
    r"茁壮",
]

PRODUCT_FORM_RISK_PATTERNS = [
    r"包里.{0,12}(奶粉罐|旺玥罐|罐子)",
    r"(奶粉罐|旺玥罐|罐子).{0,12}(露出来|露出|放包里|带着|拿出)",
    r"水杯里.{0,12}(泡好|冲好).{0,12}(奶粉|旺玥)",
    r"(拿出|掏出).{0,12}水杯.{0,12}(奶粉|旺玥)",
    r"(出门|滑梯|小区|游乐场).{0,30}(泡好|冲好).{0,12}(奶粉|旺玥)",
    r"(奶瓶|便携|小包|条装|随身带|侧袋)",
]


_original_build_writer_prompt = base._build_writer_prompt
_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality
_original_fidelity_gate = base._fidelity_gate


def _build_writer_prompt_v421(
    row: dict[str, Any],
    plan: dict[str, Any],
    *,
    plan_valid: bool,
    plan_issues: list[str],
) -> str:
    payload = json.loads(_original_build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues))
    event_type = _event_type(plan)
    payload["surface_translation_contract"] = SURFACE_TRANSLATION_CONTRACTS.get(
        event_type,
        {
            "keep_strength": "按 approved_story_plan 的产品强度写。",
            "surface": "不要把内部规则词、任务词、卖点标签原样写进正文。",
        },
    )
    payload["writer_task"] = (
        "把 approved_story_plan 写成一篇 120-180 字左右的小红书妈妈UGC正向种草笔记。"
        "先保证一条主线自然推进，再按 surface_translation_contract 写成妈妈会说的话；"
        "强种草可以保留，但不要露出内部规则词或产品载体幻觉。"
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_plan_v421(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    text = _plan_relevant_text(plan)
    event_type = _event_type(plan)
    if _pattern_hits(text, PRODUCT_FORM_RISK_PATTERNS):
        issues = [*issues, "portable_product_form_in_plan"]
    if event_type == "growth_stage_observation" and _growth_claim_mismatch(text):
        issues = [*issues, "growth_claim_bridge_mismatch"]
    return not issues, issues


def _local_quality_v421(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    text = f"{title}\n{body}"
    if _pattern_hits(text, PRODUCT_FORM_RISK_PATTERNS):
        quality["flags"].append("portable_product_form")
    if _pattern_hits(text, BUSINESS_SURFACE_LEAK_PATTERNS):
        quality["flags"].append("business_surface_leak")
    if "顺手记一下" in body[-50:]:
        quality["flags"].append("repeatable_closure_surface")
    if _growth_claim_mismatch(text):
        quality["flags"].append("growth_claim_bridge_mismatch")
    quality["flags"] = sorted(set(quality["flags"]))
    quality["hard_pass"] = not quality["flags"]
    if not quality["hard_pass"] and quality.get("business_tier") == "direct_pool":
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "；".join(quality["flags"])
    elif not quality["hard_pass"]:
        quality["business_reason"] = "；".join(quality["flags"])
    return quality


def _fidelity_gate_v421(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    result = _original_fidelity_gate(title, body, plan)
    if _pattern_hits(f"{title}\n{body}", PRODUCT_FORM_RISK_PATTERNS):
        result["flags"] = sorted(set([*result.get("flags", []), "portable_product_form_added"]))
        result["pass"] = False
    return result


def _event_type(plan: dict[str, Any]) -> str:
    return str(((plan.get("human_event") or {}).get("event_type") or "")).strip()


def _plan_relevant_text(plan: dict[str, Any]) -> str:
    human_event = plan.get("human_event") or {}
    product_bridge = plan.get("product_bridge") or {}
    return json.dumps(
        {
            "human_event": {
                key: human_event.get(key)
                for key in (
                    "event_type",
                    "posting_motive",
                    "posting_emotion_trigger",
                    "human_event",
                    "life_entry",
                    "natural_stop",
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
            "product_role": plan.get("product_role"),
            "single_selling_point": plan.get("single_selling_point"),
            "positive_evidence": plan.get("positive_evidence"),
            "ending_stop": plan.get("ending_stop"),
        },
        ensure_ascii=False,
    )


def _growth_claim_mismatch(text: str) -> bool:
    if "旺玥" not in text:
        return False
    growth_terms = ["长高", "长肉", "结实", "抱起来", "撑起来", "衣服短", "裤子短", "跑跳有劲"]
    protection_terms = ["乳铁蛋白", "HMO", "进阶保护力"]
    return any(term in text for term in growth_terms) and any(term in text for term in protection_terms)


def _pattern_hits(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text)]


base._build_writer_prompt = _build_writer_prompt_v421
base._validate_plan = _validate_plan_v421
base._local_quality = _local_quality_v421
base._fidelity_gate = _fidelity_gate_v421


if __name__ == "__main__":
    base.main()
