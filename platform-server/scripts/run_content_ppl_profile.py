from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:5100"
DEFAULT_OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/content_ppl_runs")
API_PREFIX = "/api/v1/content-agent"


class ApiError(RuntimeError):
    def __init__(self, status: int, method: str, path: str, body: str) -> None:
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"{method} {path} failed with HTTP {status}: {body}")


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return text.strip("-") or "ppl"


def _json_arg(value: str | None, *, expected_type: type) -> Any:
    if value is None:
        return None
    raw = value.strip()
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, expected_type):
        raise argparse.ArgumentTypeError(
            f"expected JSON {expected_type.__name__}, got {type(parsed).__name__}"
        )
    return parsed


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None and value != []}


def _request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 600,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise ApiError(exc.code, method, path, error_body) from exc
    return json.loads(response_body)


def _response_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def _items(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in report.get("items") or [] if isinstance(item, dict)]


def _item_no(item: dict[str, Any]) -> int:
    try:
        return int(item.get("item_no") or 0)
    except (TypeError, ValueError):
        return 0


def _text(item: dict[str, Any]) -> str:
    return f"{item.get('title') or ''}\n{item.get('body') or ''}"


def _route(item: dict[str, Any]) -> str:
    stages = item.get("trace_stage_calls") or []
    if any(stage.get("capability") == "content.rewrite" for stage in stages if isinstance(stage, dict)):
        return "post-rewrite"
    if item.get("rewrite_rounds") or item.get("rewrite_reason"):
        return "post-rewrite"
    return "direct"


def _quality(item: dict[str, Any]) -> dict[str, Any]:
    quality = item.get("quality")
    return quality if isinstance(quality, dict) else {}


def _phrase_review(item: dict[str, Any]) -> dict[str, Any]:
    quality = _quality(item)
    report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
    review = quality.get("product_experience_phrase_guard") or report.get("product_experience_phrase_review")
    return review if isinstance(review, dict) else {}


def _llm_review(item: dict[str, Any]) -> dict[str, Any]:
    quality = _quality(item)
    report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
    review = quality.get("product_experience_llm_quality_review") or report.get("product_experience_llm_review")
    return review if isinstance(review, dict) else {}


def _ai_review(item: dict[str, Any]) -> dict[str, Any]:
    quality = _quality(item)
    report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
    review = quality.get("ai_flavor_humanizer") or report.get("ai_flavor_review")
    return review if isinstance(review, dict) else {}


def _counter_from_values(values: list[Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for value in values:
        if isinstance(value, dict):
            label = value.get("code") or value.get("reason") or value.get("message") or str(value)
        else:
            label = value
        if label:
            counter[str(label)] += 1
    return counter


def _quality_counters(items: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    phrase: Counter[str] = Counter()
    llm: Counter[str] = Counter()
    ai: Counter[str] = Counter()
    for item in items:
        phrase.update(_counter_from_values(_phrase_review(item).get("reasons") or []))
        llm.update(_counter_from_values(_llm_review(item).get("issues") or []))
        ai.update(_counter_from_values(_ai_review(item).get("reasons") or []))
    return {"phrase_guard": phrase, "llm_review": llm, "ai_flavor": ai}


def _machine_issue_summary(item: dict[str, Any]) -> str:
    parts: list[str] = []
    if item.get("error_message"):
        parts.append(f"error: {item['error_message']}")
    if item.get("rewrite_reason"):
        parts.append(f"rewrite: {item['rewrite_reason']}")
    if item.get("forbidden_hits"):
        parts.append(f"forbidden hits: {item['forbidden_hits']}")
    phrase_reasons = _phrase_review(item).get("reasons") or []
    if phrase_reasons:
        parts.append("phrase guard: " + ", ".join(map(str, phrase_reasons)))
    llm_issues = _llm_review(item).get("issues") or []
    if llm_issues:
        parts.append("LLM review: " + ", ".join(_counter_from_values(llm_issues).keys()))
    ai_reasons = _ai_review(item).get("reasons") or []
    if ai_reasons:
        parts.append("AI flavor: " + ", ".join(map(str, ai_reasons)))
    return "; ".join(parts) or "no machine issue surfaced"


def _format_counter(counter: Counter[str]) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- {key}: {value}" for key, value in counter.most_common()]


def _closure_cluster_lines(summary: dict[str, Any]) -> list[str]:
    stats = summary.get("closure_cluster_stats") if isinstance(summary.get("closure_cluster_stats"), dict) else {}
    clusters = stats.get("clusters") if isinstance(stats.get("clusters"), list) else []
    lines = []
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        count = int(cluster.get("count") or 0)
        if count or cluster.get("warning"):
            lines.append(
                f"- {cluster.get('cluster_name') or cluster.get('name') or 'unknown'}: "
                f"{count}, warning={cluster.get('warning')}"
            )
    return lines or ["- none"]


def _business_stats_lines(summary: dict[str, Any]) -> list[str]:
    stats = summary.get("business_usability_stats")
    if not isinstance(stats, dict) or not stats:
        return ["- none"]
    return [f"- `{key}`: `{value}`" for key, value in sorted(stats.items())]


def _tier_groups(items: list[dict[str, Any]]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for item in items:
        tier = str(item.get("business_usability_tier") or "unset")
        groups.setdefault(tier, []).append(_item_no(item))
    return groups


def _snapshot(item: dict[str, Any]) -> dict[str, Any]:
    snapshot = item.get("generation_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _rendered_prompt(item: dict[str, Any]) -> str:
    return str(_snapshot(item).get("rendered_prompt") or "").strip()


def _select_prompt_item(items: list[dict[str, Any]], prompt_item_no: int | None) -> dict[str, Any] | None:
    if not items:
        return None
    if prompt_item_no is not None:
        matched = next((item for item in items if _item_no(item) == prompt_item_no), None)
        if matched:
            return matched
    candidates = [item for item in items if item.get("status") == "generated" and _rendered_prompt(item)]
    if not candidates:
        candidates = [item for item in items if _rendered_prompt(item)]
    if not candidates:
        candidates = [item for item in items if item.get("status") == "generated"]
    if not candidates:
        candidates = items
    return random.SystemRandom().choice(candidates)


def write_preview(
    report: dict[str, Any],
    *,
    source_json_path: Path,
    full_report_path: Path | None,
    prompt_path: Path,
    output_path: Path,
    manual_reviewed: bool = False,
) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    rows = _items(report)
    machine_pass = [
        _item_no(item)
        for item in rows
        if item.get("status") == "generated" and item.get("hard_pass") is True
    ]
    machine_manual = [
        _item_no(item)
        for item in rows
        if item.get("status") != "generated"
        or item.get("hard_pass") is not True
        or item.get("rewrite_required") is True
    ]
    direct_pass = [no for no in machine_pass if _route(next(item for item in rows if _item_no(item) == no)) == "direct"]
    post_pass = [
        no for no in machine_pass if _route(next(item for item in rows if _item_no(item) == no)) == "post-rewrite"
    ]
    tier_groups = _tier_groups(rows)
    quality = _quality_counters(rows)
    manual_note = (
        "manual business review completed outside this script"
        if manual_reviewed
        else "not manually reviewed by this script; use item text below for business review"
    )

    lines = [
        f"# PPL batch {report.get('batch_id')} preview",
        "",
        f"- source start JSON: `{source_json_path}`",
        f"- source full report JSON: `{full_report_path or 'not fetched'}`",
        f"- sampled rendered prompt: `{prompt_path}`",
        f"- batch_id: `{report.get('batch_id')}`",
        f"- batch_code: `{report.get('batch_code')}`",
        f"- asset_key: `{report.get('asset_key')}`",
        f"- requested/total: {summary.get('total_count', report.get('count'))}",
        f"- raw generated count: {summary.get('generated_count')}",
        f"- failed count: {summary.get('failed_count')}",
        f"- machine final pass: {len(machine_pass)}/{len(rows)}, items: {machine_pass}",
        f"- machine rewrite/manual-needed: {len(machine_manual)}/{len(rows)}, items: {machine_manual}",
        f"- direct pass without post-rewrite: {len(direct_pass)}/{len(rows)}, items: {direct_pass}",
        f"- pass after post-rewrite: {len(post_pass)}/{len(rows)}, items: {post_pass}",
        f"- manual business usable: {manual_note}",
        f"- model business tiers: {json.dumps(tier_groups, ensure_ascii=False)}",
        f"- max pairwise similarity 2gram Jaccard: {summary.get('max_pairwise_jaccard_2gram')}",
        f"- similarity warning count: {summary.get('similarity_warning_count')}",
        "",
        "## Business Usability Stats",
        "",
        *_business_stats_lines(summary),
        "",
        "## Closure Cluster Warnings",
        "",
        *_closure_cluster_lines(summary),
        "",
        "## Phrase Guard Issue Counts",
        "",
        *_format_counter(quality["phrase_guard"]),
        "",
        "## LLM Review Issue Counts",
        "",
        *_format_counter(quality["llm_review"]),
        "",
        "## AI Flavor Issue Counts",
        "",
        *_format_counter(quality["ai_flavor"]),
        "",
        "## Assessment Note",
        "",
        "- This file is an automatic delivery preview. It separates machine final pass from business usability; the latter still needs human reading before selecting mother-pool samples.",
        "",
        "## Items",
        "",
    ]
    for item in rows:
        lines.extend(
            [
                f"### {_item_no(item)}. {item.get('title') or '(no title)'}",
                "",
                f"- machine: status={item.get('status')}, final_pass={item.get('hard_pass')}, rewrite_required={item.get('rewrite_required')}",
                f"- route: {_route(item)}",
                f"- model business tier: {item.get('business_usability_tier') or 'unset'}",
                f"- model business reason: {item.get('business_usability_reason') or 'unset'}",
                f"- issue summary: {_machine_issue_summary(item)}",
                "",
                item.get("body") or item.get("error_message") or "",
                "",
            ]
        )
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "machine_final_pass_items": machine_pass,
        "machine_manual_needed_items": machine_manual,
        "direct_pass_items": direct_pass,
        "post_rewrite_pass_items": post_pass,
        "model_business_tiers": tier_groups,
    }


def write_prompt(report: dict[str, Any], *, output_path: Path, prompt_item_no: int | None) -> dict[str, Any]:
    rows = _items(report)
    item = _select_prompt_item(rows, prompt_item_no)
    prompt = _rendered_prompt(item or {})
    lines = [
        f"# PPL batch {report.get('batch_id')} item {_item_no(item or {})} rendered prompt",
        "",
        f"- batch_id: `{report.get('batch_id')}`",
        f"- batch_code: `{report.get('batch_code')}`",
        f"- item_no: `{_item_no(item or {})}`",
        f"- title: {(item or {}).get('title')}",
        "",
        "## rendered_prompt",
        "",
        "```text",
        prompt or "NO_RENDERED_PROMPT_FOUND",
        "```",
    ]
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "prompt_item_no": _item_no(item or {}),
        "prompt_found": bool(prompt),
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    model_config = _json_arg(args.model_config_json, expected_type=dict)
    rotation = _json_arg(args.model_config_rotation_json, expected_type=list)
    return _compact_dict(
        {
            "profile_code": args.profile_code,
            "keyword_asset_key": args.keyword_asset_key,
            "quality_guard_profile_key": args.quality_guard_profile_key,
            "business_rule": args.business_rule,
            "rule_id": args.rule_id,
            "source_row_no": args.source_row_no,
            "draft_corpus": args.draft_corpus,
            "draft_rule_id": args.draft_rule_id,
            "draft_source_row_no": args.draft_source_row_no,
            "count": args.count,
            "articles_per_prompt": args.articles_per_prompt,
            "executor_code": args.executor_code,
            "model_config": model_config,
            "model_config_rotation": rotation or [],
            "created_by": args.created_by,
        }
    )


def print_profiles(base_url: str) -> None:
    try:
        response = _request_json(base_url, "GET", f"{API_PREFIX}/ppl-runs/profiles", timeout=30)
    except ApiError as exc:
        if exc.status == 404:
            raise SystemExit(
                "Local 5100 is reachable, but /ppl-runs/profiles is 404. "
                "Restart the 5100 uvicorn service so it loads the new PPL endpoints."
            ) from exc
        raise
    print(json.dumps(response, ensure_ascii=False, indent=2))


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(args)
    if args.no_run:
        return {"mode": "no_run", "payload": payload}

    try:
        _request_json(args.base_url, "GET", f"{API_PREFIX}/ppl-runs/profiles", timeout=30)
    except ApiError as exc:
        if exc.status == 404:
            raise SystemExit(
                "Local 5100 is reachable, but /ppl-runs/profiles is 404. "
                "Restart the 5100 uvicorn service so it loads the new PPL endpoints."
            ) from exc
        raise

    started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    profile_slug = _slug(args.profile_code)
    response = _request_json(args.base_url, "POST", f"{API_PREFIX}/ppl-runs/start", payload)
    data = _response_data(response)
    batch_id = data.get("batch_id")
    batch_code = data.get("batch_code")

    raw_path = output_dir / f"{started_at}_{profile_slug}_start_response.json"
    raw_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")

    report = data.get("report") if isinstance(data.get("report"), dict) else {}
    full_report_path = None
    if batch_id is not None:
        full_response = _request_json(
            args.base_url,
            "GET",
            f"{API_PREFIX}/batches/{batch_id}/report?full=true",
            timeout=120,
        )
        full_report_path = output_dir / f"{started_at}_{profile_slug}_batch{batch_id}_report_full.json"
        full_report_path.write_text(json.dumps(full_response, ensure_ascii=False, indent=2), encoding="utf-8")
        full_data = _response_data(full_response)
        if isinstance(full_data, dict):
            report = full_data

    item_for_name = _select_prompt_item(_items(report), args.prompt_item_no)
    prompt_item_no = _item_no(item_for_name or {})
    prompt_path = output_dir / f"{started_at}_{profile_slug}_batch{batch_id}_item{prompt_item_no}_rendered_prompt.md"
    prompt_meta = write_prompt(report, output_path=prompt_path, prompt_item_no=prompt_item_no)
    preview_path = output_dir / f"{started_at}_{profile_slug}_batch{batch_id}_preview.md"
    preview_meta = write_preview(
        report,
        source_json_path=raw_path,
        full_report_path=full_report_path,
        prompt_path=prompt_path,
        output_path=preview_path,
    )

    return {
        "mode": "started",
        "profile_code": args.profile_code,
        "batch_id": batch_id,
        "batch_code": batch_code,
        "raw_response_json": str(raw_path),
        "full_report_json": str(full_report_path) if full_report_path else None,
        "preview_md": str(preview_path),
        "prompt_md": str(prompt_path),
        **prompt_meta,
        **preview_meta,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a configured content-generation PPL profile through local MAGA service.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--profile-code", help="Profile code or alias, for example royal, wangyue, a2_post, a2_comment.")
    parser.add_argument("--count", type=int)
    parser.add_argument("--articles-per-prompt", type=int, choices=(1, 2))
    parser.add_argument("--created-by", default="codex-ppl-run")
    parser.add_argument("--executor-code")
    parser.add_argument("--keyword-asset-key")
    parser.add_argument("--quality-guard-profile-key")
    parser.add_argument("--business-rule")
    parser.add_argument("--rule-id")
    parser.add_argument("--source-row-no", type=int)
    parser.add_argument("--draft-corpus")
    parser.add_argument("--draft-rule-id")
    parser.add_argument("--draft-source-row-no", type=int)
    parser.add_argument("--model-config-json", help="JSON object, or @path to a JSON object.")
    parser.add_argument("--model-config-rotation-json", help="JSON list, or @path to a JSON list.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--prompt-item-no", type=int)
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--no-run", action="store_true", help="Print the request payload without starting a batch.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_profiles:
        print_profiles(args.base_url)
        return 0
    if not args.profile_code:
        parser.error("--profile-code is required unless --list-profiles is used")
    try:
        result = run(args)
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
