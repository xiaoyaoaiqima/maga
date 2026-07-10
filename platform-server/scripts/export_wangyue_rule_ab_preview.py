#!/usr/bin/env python3
"""Export a Wangyue business-rule A/B preview from two batch report JSON files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.export_content_ab_review import render_experiment_preview  # noqa: E402


WATCH_PHRASES = (
    "不用额外补",
    "不用额外再补",
    "一杯就够",
    "专注力上来了",
    "专注力进步",
    "专注力有提升",
    "专注力明显好了",
    "神药",
    "一次性搞定",
    "被问爆",
    "被问800遍",
    "老母亲",
)


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a content-agent batch report response")
    return data


def first_item(report: dict[str, Any]) -> dict[str, Any]:
    items = report.get("items") or []
    if not items:
        return {}
    return items[0] if isinstance(items[0], dict) else {}


def task_text(report: dict[str, Any]) -> str:
    item = first_item(report)
    corpus = (
        item.get("generation_snapshot", {})
        .get("business_rule", {})
        .get("corpus")
        or ""
    )
    match = re.search(r"这篇要写的事：\s*(.*?)\n\s*硬边界：", corpus, re.S)
    if match:
        return match.group(1).strip()
    return str(corpus).strip()


def business_rule_name(report: dict[str, Any]) -> str:
    item = first_item(report)
    return str(
        item.get("generation_snapshot", {})
        .get("business_rule", {})
        .get("business_rule")
        or item.get("business_rule")
        or ""
    )


def watch_reasons(item: dict[str, Any]) -> list[str]:
    body = str(item.get("body") or item.get("body_preview") or "")
    reasons = [phrase for phrase in WATCH_PHRASES if phrase in body]
    rewrite_reason = str(item.get("rewrite_reason") or "")
    if rewrite_reason:
        reasons.append(rewrite_reason)
    reasons.extend(quality_rewrite_labels(item))
    quality = item.get("quality") or {}
    review_report = quality.get("review_report") or {}
    phrase_review = review_report.get("product_experience_phrase_review") or {}
    for key in ("ai_phrase_hits", "odd_phrase_hits", "hard_risk_hits"):
        for hit in phrase_review.get(key) or []:
            hit_text = str(hit)
            if hit_text and hit_text not in reasons:
                reasons.append(hit_text)
    return reasons


def quality_rewrite_labels(item: dict[str, Any]) -> list[str]:
    quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
    labels: list[str] = []
    for key, value in quality.items():
        if not key.endswith("_rewrites"):
            continue
        if not value:
            continue
        count = 0
        if isinstance(value, list):
            count = len(value)
        elif isinstance(value, dict):
            count = int(value.get("count") or 0)
        if count:
            label = key.replace("_", " ")
            labels.append(f"{label} x{count}")
    return labels


def rendered_prompt(report: dict[str, Any], item_no: int | None) -> tuple[int, str, str]:
    items = [item for item in report.get("items") or [] if isinstance(item, dict)]
    if not items:
        raise ValueError("candidate report has no items")
    selected = None
    if item_no is not None:
        selected = next((item for item in items if int(item.get("item_no") or 0) == item_no), None)
    if selected is None:
        selected = next((item for item in items if item.get("body")), items[0])
    snapshot = selected.get("generation_snapshot") or {}
    prompt = str(snapshot.get("rendered_prompt") or "")
    if not prompt:
        raise ValueError("selected candidate item has no rendered_prompt")
    return int(selected.get("item_no") or 0), str(selected.get("title") or ""), prompt


def write_prompt(path: Path, report: dict[str, Any], source_path: Path, item_no: int | None) -> None:
    selected_no, title, prompt = rendered_prompt(report, item_no)
    lines = [
        f"# Wangyue rendered prompt sample",
        "",
        f"- batch_id：{report.get('batch_id')}",
        f"- batch_code：`{report.get('batch_code')}`",
        f"- item_no：{selected_no}",
        f"- title：{title}",
        f"- source JSON：`{source_path}`",
        "",
        "```text",
        prompt,
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_preview(
    path: Path,
    *,
    control_path: Path,
    candidate_path: Path,
    control: dict[str, Any],
    candidate: dict[str, Any],
    title: str,
    appendix_path: Path | None,
) -> None:
    control_task = task_text(control)
    candidate_task = task_text(candidate)
    rule_name = business_rule_name(candidate) or business_rule_name(control)
    artifacts = {
        "control_report": str(control_path),
        "candidate_report": str(candidate_path),
    }
    if appendix_path:
        artifacts["appendix_source"] = str(appendix_path)
    experiment = {
        "experiment_id": f"{control.get('batch_id')}_vs_{candidate.get('batch_id')}",
        "title": title,
        "content_type": "article",
        "comparison_mode": "aggregate",
        "conclusion": "先比较唯一变量和两组业务可用性，再决定候选组是否转正；不能只看机器通过数。",
        "changed_dimensions": [
            {
                "name": "业务语料",
                "values": {"control": control_task, "candidate": candidate_task},
            }
        ],
        "controlled_dimensions": [
            {"name": "业务规则", "value": rule_name},
            {"name": "内容类型", "value": "article"},
        ],
        "group_conclusions": [
            "候选组是本次待 review 的新结果；是否已入库以批次说明为准。",
            "先看业务语料变化，再看批量输出是否复现风险。",
        ],
        "arms": [
            _normalized_wangyue_arm(control, arm_id="control", label="A｜当前线上对照组"),
            _normalized_wangyue_arm(candidate, arm_id="candidate", label="B｜候选组"),
        ],
        "artifacts": artifacts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_experiment_preview(experiment), encoding="utf-8")


def _normalized_wangyue_arm(
    report: dict[str, Any],
    *,
    arm_id: str,
    label: str,
) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    items: list[dict[str, Any]] = []
    for item in report.get("items") or []:
        if not isinstance(item, dict):
            continue
        quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
        raw_llm_review = quality.get("product_experience_llm_quality_review")
        has_llm_review = isinstance(raw_llm_review, dict) and bool(raw_llm_review)
        llm_review = raw_llm_review if has_llm_review else {}
        tier = str(item.get("business_usability_tier") or llm_review.get("business_usability_tier") or "")
        if tier not in {"direct_pool", "light_fix_usable", "hold_out"}:
            tier = "not_run"
        issue_codes = [
            str(issue.get("code"))
            for issue in llm_review.get("issues") or []
            if isinstance(issue, dict) and issue.get("code")
        ]
        machine_reasons = [
            *[str(value) for value in item.get("forbidden_hits") or []],
            *[str(value) for value in item.get("reject_reasons") or []],
            *watch_reasons(item),
        ]
        items.append(
            {
                "item_no": item.get("item_no"),
                "pair_id": f"item-{int(item.get('item_no') or 0):02d}",
                "category": business_rule_name(report),
                "title": item.get("title"),
                "content": item.get("body") or item.get("body_preview") or "",
                "status": "failed" if item.get("run_status") == "failed" else "generated",
                "machine_review": {
                    "pass": bool(item.get("hard_pass")),
                    "reason": "；".join(dict.fromkeys(machine_reasons)),
                },
                "llm_review": {
                    "tier": tier,
                    "reason": item.get("business_usability_reason")
                    or llm_review.get("business_usability_reason")
                    or llm_review.get("overall_reason")
                    or "not run",
                    "issue_codes": issue_codes,
                    "rewrite_direction": "；".join(
                        str(issue.get("rewrite_direction") or "")
                        for issue in llm_review.get("issues") or []
                        if isinstance(issue, dict) and issue.get("rewrite_direction")
                    ),
                },
            }
        )
    return {
        "arm_id": arm_id,
        "label": label,
        "metrics": {
            "attempted": summary.get("total_count", report.get("count", len(items))),
            "max_pairwise_similarity": summary.get("max_pairwise_jaccard_2gram"),
            "similarity_warning_count": summary.get("similarity_warning_count"),
            "forbidden_hit_count": summary.get("forbidden_hit_count"),
        },
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-report", required=True, type=Path)
    parser.add_argument("--candidate-report", required=True, type=Path)
    parser.add_argument("--preview-md", required=True, type=Path)
    parser.add_argument("--prompt-md", required=True, type=Path)
    parser.add_argument("--title", default="Wangyue business-rule A/B preview")
    parser.add_argument("--prompt-item-no", type=int)
    parser.add_argument("--appendix-source", type=Path)
    args = parser.parse_args()

    control = load_report(args.control_report)
    candidate = load_report(args.candidate_report)
    write_preview(
        args.preview_md,
        control_path=args.control_report,
        candidate_path=args.candidate_report,
        control=control,
        candidate=candidate,
        title=args.title,
        appendix_path=args.appendix_source,
    )
    write_prompt(args.prompt_md, candidate, args.candidate_report, args.prompt_item_no)
    print(f"preview={args.preview_md}")
    print(f"prompt={args.prompt_md}")


if __name__ == "__main__":
    main()
