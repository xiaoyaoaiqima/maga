#!/usr/bin/env python3
"""Local Wangyue timeline-safety experiment.

Builds on v409 event-object calibration and adds a product-history gate for
3+ usage safety. It does not replace production content.generate.
"""

from __future__ import annotations

import json
import re
from typing import Any

import run_v409_wangyue_event_object_calibration_experiment as calibrated


base = calibrated.base
base.EXPERIMENT_ID = "v410_timeline_safety"

base.HUMAN_EVENT_SYSTEM = base.HUMAN_EVENT_SYSTEM.replace(
    "- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。",
    "- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。\n"
    "- 不写三年前、从小、小时候、刚断奶、刚上幼儿园、一岁、两岁这类可能暗示3岁前产品使用的时间履历。",
)

base.PRODUCT_BRIDGE_SYSTEM = base.PRODUCT_BRIDGE_SYSTEM.replace(
    "- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。",
    "- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。\n"
    "- 不把旺玥放进3岁前的选择或使用履历；如果 approved_human_event 有三年前、从小、小时候等风险时间锚点，优先拒绝进入。",
)

base.WRITER_SYSTEM = base.WRITER_SYSTEM.replace(
    "- 不要把主线没有写的固定喝法、回购、继续喝、安心省心总结、第二个效果证明补进去。",
    "- 不要把主线没有写的固定喝法、回购、继续喝、安心省心总结、第二个效果证明补进去。\n"
    "- 不写三年前选旺玥、从小喝、小时候喝、刚断奶后喝这类可能暗示3岁前使用的履历。",
)

_original_validate_plan = base._validate_plan
_original_local_quality = base._local_quality


TIMELINE_RISK_PATTERNS = [
    r"三年前.{0,40}(旺玥|儿童奶粉|奶粉|选)",
    r"(旺玥|儿童奶粉|奶粉|选).{0,40}三年前",
    r"从小.{0,20}(旺玥|喝|奶粉)",
    r"小时候.{0,20}(旺玥|喝|奶粉)",
    r"刚断奶.{0,20}(旺玥|喝|奶粉)",
    r"(一岁|1岁|两岁|2岁|一岁半|两岁半).{0,30}(旺玥|喝|奶粉)",
    r"(旺玥|奶粉).{0,30}(一岁|1岁|两岁|2岁|一岁半|两岁半)",
    r"从孩子.{0,8}开始喝",
]


def _timeline_risk(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in TIMELINE_RISK_PATTERNS:
        if re.search(pattern, text):
            hits.append(pattern)
    return hits


def _validate_plan_with_timeline(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    valid, issues = _original_validate_plan(plan)
    plan_text = json.dumps(plan, ensure_ascii=False)
    if _timeline_risk(plan_text):
        issues = [*issues, "age_timeline_risk"]
    return not issues, issues


def _local_quality_with_timeline(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    quality = _original_local_quality(title, body, plan)
    if _timeline_risk(f"{title}\n{body}"):
        quality["flags"].append("age_timeline_risk")
        quality["hard_pass"] = False
        quality["business_tier"] = "needs_manual_review"
        quality["business_reason"] = "age_timeline_risk"
    return quality


base._validate_plan = _validate_plan_with_timeline
base._local_quality = _local_quality_with_timeline


if __name__ == "__main__":
    base.main()

