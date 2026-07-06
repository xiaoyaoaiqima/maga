from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import run_content_ppl_profile as ppl


DEFAULT_OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence")
DEFAULT_PROFILE_CODE = "wangyue_v2_0705_article"


def _item_no(item: dict[str, Any]) -> int:
    try:
        return int(item.get("item_no") or 0)
    except (TypeError, ValueError):
        return 0


def _snapshot_rule(item: dict[str, Any]) -> dict[str, Any]:
    snapshot = item.get("generation_snapshot") if isinstance(item.get("generation_snapshot"), dict) else {}
    rule = snapshot.get("business_rule")
    return rule if isinstance(rule, dict) else {}


def _phrase_review(item: dict[str, Any]) -> dict[str, Any]:
    quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
    report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
    review = quality.get("product_experience_phrase_guard") or report.get("product_experience_phrase_review")
    return review if isinstance(review, dict) else {}


def _llm_review(item: dict[str, Any]) -> dict[str, Any]:
    quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
    report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
    review = quality.get("product_experience_llm_quality_review") or report.get("product_experience_llm_review")
    return review if isinstance(review, dict) else {}


def _ai_review(item: dict[str, Any]) -> dict[str, Any]:
    quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
    report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
    review = quality.get("ai_flavor_humanizer") or report.get("ai_flavor_review")
    return review if isinstance(review, dict) else {}


def _issue_code(issue: Any) -> str:
    if isinstance(issue, dict):
        return str(issue.get("code") or issue.get("reason") or issue.get("message") or "other")
    return str(issue or "other")


def _issue_evidence(issue: Any) -> str:
    if isinstance(issue, dict):
        return str(issue.get("evidence") or issue.get("reason") or "")
    return ""


def _issue_rewrite_direction(issue: Any) -> str:
    if isinstance(issue, dict):
        return str(issue.get("rewrite_direction") or "")
    return ""


def _iter_issues(item: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for reason in _phrase_review(item).get("reasons") or []:
        issues.append({"source": "phrase_guard", "code": str(reason), "evidence": "", "rewrite_direction": ""})
    for issue in _llm_review(item).get("issues") or []:
        issues.append(
            {
                "source": "llm_review",
                "code": _issue_code(issue),
                "evidence": _issue_evidence(issue),
                "rewrite_direction": _issue_rewrite_direction(issue),
            }
        )
    for reason in _ai_review(item).get("reasons") or []:
        issues.append({"source": "ai_flavor", "code": str(reason), "evidence": "", "rewrite_direction": ""})
    if item.get("rewrite_required") and item.get("rewrite_reason"):
        issues.append(
            {
                "source": "rewrite_required",
                "code": str(item.get("rewrite_reason") or "rewrite_required"),
                "evidence": "",
                "rewrite_direction": "",
            }
        )
    return issues


def _items(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in report.get("items") or [] if isinstance(item, dict)]


def _load_report(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def write_issue_taxonomy(report: dict[str, Any], path: Path) -> dict[str, Any]:
    items = _items(report)
    issue_counter: Counter[str] = Counter()
    lane_counter: Counter[str] = Counter()
    manual_items: list[int] = []

    for item in items:
        if item.get("rewrite_required") or item.get("hard_pass") is not True or item.get("status") != "generated":
            manual_items.append(_item_no(item))
        rule = _snapshot_rule(item)
        lane = " / ".join(
            part for part in (str(rule.get("post_type") or ""), str(rule.get("painpoint") or "")) if part
        ) or "unset"
        for issue in _iter_issues(item):
            issue_counter[f"{issue['source']}:{issue['code']}"] += 1
            lane_counter[f"{lane} -> {issue['source']}:{issue['code']}"] += 1

    lines = [
        f"# Wangyue v2 Issue Taxonomy - batch {report.get('batch_id')}",
        "",
        f"- batch_id: `{report.get('batch_id')}`",
        f"- batch_code: `{report.get('batch_code')}`",
        f"- asset_key: `{report.get('asset_key')}`",
        f"- generated_items: {len([item for item in items if item.get('status') == 'generated'])}/{len(items)}",
        f"- manual_or_rewrite_items: {manual_items or []}",
        "",
        "## Issue Counts",
        "",
    ]
    if issue_counter:
        lines.extend(f"- {key}: {count}" for key, count in issue_counter.most_common())
    else:
        lines.append("- none")
    lines.extend(["", "## Lane Counts", ""])
    if lane_counter:
        lines.extend(f"- {key}: {count}" for key, count in lane_counter.most_common())
    else:
        lines.append("- none")
    lines.extend(["", "## Item Notes", ""])
    for item in items:
        issues = _iter_issues(item)
        if not issues and item.get("status") == "generated" and item.get("hard_pass") is True:
            continue
        rule = _snapshot_rule(item)
        lines.extend(
            [
                f"### {_item_no(item)}. {item.get('title') or '(no title)'}",
                "",
                f"- rule_id: `{rule.get('rule_id') or ''}`; source_row_no: `{rule.get('source_row_no') or ''}`",
                f"- lane: `{rule.get('post_type') or ''}` / `{rule.get('painpoint') or ''}` / `{rule.get('selling_point') or ''}`",
                f"- machine: status={item.get('status')}, final_pass={item.get('hard_pass')}, rewrite_required={item.get('rewrite_required')}",
                "",
            ]
        )
        if issues:
            for issue in issues:
                lines.append(f"- {issue['source']} / {issue['code']}: {issue['rewrite_direction'] or issue['evidence'] or '-'}")
        else:
            lines.append("- no structured issue surfaced")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"issue_taxonomy_md": str(path), "issue_count": sum(issue_counter.values())}


def write_rules_patch(report: dict[str, Any], path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in _items(report):
        rule = _snapshot_rule(item)
        issues = _iter_issues(item)
        if not issues and item.get("status") == "generated" and item.get("hard_pass") is True:
            continue
        if not issues:
            issues = [{"source": "machine", "code": "manual_review", "evidence": "", "rewrite_direction": ""}]
        for issue in issues:
            rows.append(
                {
                    "item_no": _item_no(item),
                    "source_row_no": rule.get("source_row_no") or "",
                    "rule_id": rule.get("rule_id") or "",
                    "post_type": rule.get("post_type") or "",
                    "painpoint": rule.get("painpoint") or "",
                    "selling_point": rule.get("selling_point") or "",
                    "issue_source": issue["source"],
                    "issue_code": issue["code"],
                    "evidence": issue.get("evidence") or "",
                    "rewrite_direction": issue.get("rewrite_direction") or "",
                    "suggested_rule_patch": "",
                }
            )
    fieldnames = [
        "item_no",
        "source_row_no",
        "rule_id",
        "post_type",
        "painpoint",
        "selling_point",
        "issue_source",
        "issue_code",
        "evidence",
        "rewrite_direction",
        "suggested_rule_patch",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return {"rules_patch_csv": str(path), "rules_patch_rows": len(rows)}


def _ppl_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        base_url=args.base_url,
        profile_code=DEFAULT_PROFILE_CODE,
        count=args.count,
        articles_per_prompt=args.articles_per_prompt,
        created_by=args.created_by,
        executor_code=args.executor_code,
        keyword_asset_key=args.keyword_asset_key,
        quality_guard_profile_key=None,
        business_rule=None,
        rule_id=args.rule_id,
        source_row_no=args.source_row_no,
        draft_corpus=None,
        draft_rule_id=None,
        draft_source_row_no=None,
        model_config_json=args.model_config_json,
        model_config_rotation_json=args.model_config_rotation_json,
        output_dir=str(Path(args.output_dir).expanduser()),
        prompt_item_no=args.prompt_item_no,
        no_run=args.no_run,
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    result = ppl.run(_ppl_args(args))
    if args.no_run:
        return result
    report = _load_report(result.get("full_report_json"))
    preview_path = Path(result["preview_md"])
    issue_path = preview_path.with_name(preview_path.name.replace("_preview.md", "_issue_taxonomy.md"))
    patch_path = preview_path.with_name(preview_path.name.replace("_preview.md", "_rules_patch.csv"))
    return {
        **result,
        **write_issue_taxonomy(report, issue_path),
        **write_rules_patch(report, patch_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Wangyue v2 MAGA debug loop.")
    parser.add_argument("--base-url", default=ppl.DEFAULT_BASE_URL)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--articles-per-prompt", type=int, choices=(1, 2), default=2)
    parser.add_argument("--created-by", default="codex-wangyue-v2-debug")
    parser.add_argument("--executor-code")
    parser.add_argument("--keyword-asset-key")
    parser.add_argument("--rule-id")
    parser.add_argument("--source-row-no", type=int)
    parser.add_argument("--model-config-json")
    parser.add_argument("--model-config-rotation-json")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--prompt-item-no", type=int)
    parser.add_argument("--no-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except ppl.ApiError as exc:
        print(str(exc))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
