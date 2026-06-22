"""Extract clean real-user title-shape candidates from XHS note exports.

This is a dry-run utility. It does not write MAGA assets; it creates a review CSV
so we can decide whether a title-shape pool is clean enough before enabling it in
generation prompts.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.real_user_example_pool_service import (  # noqa: E402
    MAX_TEXT_CHARS,
    MAX_TITLE_CHARS,
    infer_real_user_risk_tags,
    infer_real_user_tags,
    _clean_text,
    _normalize_for_match,
    _short_hash,
    _title_shape_block_reason,
    _title_shape_source_block_reason,
)


DEFAULT_EXPORT_DIRS = [
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_150746",
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_165055_wangyue_100_notes",
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_165252_wangyue_100_notes",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract dry-run title-shape candidates from XHS exports.")
    parser.add_argument(
        "export_dirs",
        nargs="*",
        default=[],
        help="Directories containing xhs_notes_full.csv. Defaults to current Wangyue/XHS exports.",
    )
    parser.add_argument("--output", required=True, help="Output CSV path for candidate review.")
    parser.add_argument("--limit", type=int, default=300, help="Maximum candidates to write.")
    parser.add_argument("--json-summary", help="Optional JSON summary output path.")
    parser.add_argument(
        "--notes-csv",
        action="append",
        default=[],
        help="Additional generic note CSV path. Useful for operator-collected UGC files.",
    )
    parser.add_argument("--title-field", default="标题", help="Title field for --notes-csv files.")
    parser.add_argument("--content-field", default="正文", help="Content field for --notes-csv files.")
    parser.add_argument("--url-field", default="链接", help="URL/link field for --notes-csv files.")
    parser.add_argument(
        "--include-rejected",
        action="store_true",
        help="Include rejected candidates with block_reason for manual review.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    export_dirs = args.export_dirs or ([] if args.notes_csv else DEFAULT_EXPORT_DIRS)
    candidates, summary = extract_candidates(
        [Path(item).expanduser() for item in export_dirs],
        generic_csv_paths=[Path(item).expanduser() for item in args.notes_csv],
        title_field=args.title_field,
        content_field=args.content_field,
        url_field=args.url_field,
        include_rejected=args.include_rejected,
        limit=args.limit,
    )
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "candidate_text",
                "candidate_source",
                "title",
                "source_keyword",
                "tags",
                "risk_tags",
                "note_id",
                "url",
                "dedupe_hash",
                "source_dir",
                "block_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(candidates)
    if args.json_summary:
        summary_path = Path(args.json_summary).expanduser()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "output": str(output_path)}, ensure_ascii=False, indent=2))


def extract_candidates(
    export_dirs: list[Path],
    *,
    generic_csv_paths: list[Path] | None = None,
    title_field: str = "标题",
    content_field: str = "正文",
    url_field: str = "链接",
    include_rejected: bool = False,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    stats: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for export_dir in export_dirs:
        notes_path = export_dir / "xhs_notes_full.csv"
        if not notes_path.exists():
            stats["missing_notes_file"] += 1
            continue
        with notes_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                stats["read_notes"] += 1
                for candidate_text, candidate_source in _row_candidates(row):
                    stats[f"candidate_seen:{candidate_source}"] += 1
                    reason = _candidate_block_reason(row, candidate_text)
                    if reason:
                        reason_counts[reason] += 1
                        if include_rejected:
                            candidates.append(
                                _candidate_row(row, candidate_text, candidate_source, export_dir=export_dir, block_reason=reason)
                            )
                        continue
                    normalized = _normalize_for_match(candidate_text)
                    if normalized in seen_texts:
                        stats["duplicate_candidate"] += 1
                        continue
                    seen_texts.add(normalized)
                    candidates.append(_candidate_row(row, candidate_text, candidate_source, export_dir=export_dir))
                    stats[f"candidate_kept:{candidate_source}"] += 1
                    if len(candidates) >= limit:
                        return candidates, _summary(stats, reason_counts, candidates)
    for csv_path in generic_csv_paths or []:
        if not csv_path.exists():
            stats["missing_generic_csv"] += 1
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                stats["read_generic_notes"] += 1
                normalized_row = {
                    "title": row.get(title_field),
                    "content": row.get(content_field),
                    "source_keyword": row.get("高频讨论") or row.get("source_keyword"),
                    "note_id": row.get("note_id") or row.get("序号"),
                    "note_url": row.get(url_field),
                }
                for candidate_text, candidate_source in _row_candidates(normalized_row):
                    stats[f"candidate_seen:{candidate_source}"] += 1
                    reason = _candidate_block_reason(normalized_row, candidate_text)
                    if reason:
                        reason_counts[reason] += 1
                        if include_rejected:
                            candidates.append(
                                _candidate_row(
                                    normalized_row,
                                    candidate_text,
                                    candidate_source,
                                    export_dir=csv_path.parent,
                                    block_reason=reason,
                                )
                            )
                        continue
                    normalized = _normalize_for_match(candidate_text)
                    if normalized in seen_texts:
                        stats["duplicate_candidate"] += 1
                        continue
                    seen_texts.add(normalized)
                    candidates.append(
                        _candidate_row(normalized_row, candidate_text, candidate_source, export_dir=csv_path.parent)
                    )
                    stats[f"candidate_kept:{candidate_source}"] += 1
                    if len(candidates) >= limit:
                        return candidates, _summary(stats, reason_counts, candidates)
    return candidates, _summary(stats, reason_counts, candidates)


def _row_candidates(row: dict[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    title = _clean_text(row.get("title"), limit=MAX_TITLE_CHARS)
    if title:
        result.append((title, "title"))
    text = _clean_text(row.get("content"), limit=MAX_TEXT_CHARS)
    for fragment in _opening_fragments(text):
        result.append((fragment, "opening_fragment"))
    return result


def _opening_fragments(text: str) -> list[str]:
    fragments: list[str] = []
    sentences = [
        item.strip(" \t，,。！？!?；;、")
        for item in re.split(r"[\n\r]+|(?<=[。！？!?；;])", text)
        if item.strip(" \t，,。！？!?；;、")
    ][:2]
    for sentence in sentences:
        clauses = [
            item.strip(" \t，,。！？!?；;、")
            for item in re.split(r"[，,；;]", sentence)
            if item.strip(" \t，,。！？!?；;、")
        ]
        for item in [sentence, *clauses]:
            if 4 <= len(re.sub(r"\s+", "", item)) <= 24:
                fragments.append(item)
    return list(dict.fromkeys(fragments))


def _candidate_block_reason(row: dict[str, Any], candidate_text: str) -> str:
    title_reason = _title_shape_block_reason(candidate_text, exclude_terms=[])
    if title_reason:
        return f"title:{title_reason}"
    source_item = _source_item(row)
    source_reason = _title_shape_source_block_reason(source_item, exclude_terms=[])
    if source_reason:
        return f"source:{source_reason}"
    return ""


def _source_item(row: dict[str, Any]) -> dict[str, Any]:
    title = _clean_text(row.get("title"), limit=MAX_TITLE_CHARS)
    text = _clean_text(row.get("content"), limit=MAX_TEXT_CHARS)
    source_keyword = _clean_text(row.get("source_keyword") or row.get("search_keywords"), limit=MAX_TITLE_CHARS)
    match_text = f"{title} {text} {source_keyword}"
    return {
        "source_type": "note",
        "text": text,
        "prompt_text": text,
        "title": title,
        "source_keyword": source_keyword,
        "tags": infer_real_user_tags(match_text),
        "risk_tags": infer_real_user_risk_tags(match_text, source_type="note"),
    }


def _candidate_row(
    row: dict[str, Any],
    candidate_text: str,
    candidate_source: str,
    *,
    export_dir: Path,
    block_reason: str = "",
) -> dict[str, Any]:
    source_item = _source_item(row)
    return {
        "candidate_text": candidate_text,
        "candidate_source": candidate_source,
        "title": source_item["title"],
        "source_keyword": source_item["source_keyword"],
        "tags": "；".join(source_item["tags"]),
        "risk_tags": "；".join(source_item["risk_tags"]),
        "note_id": str(row.get("note_id") or "").strip(),
        "url": str(row.get("note_url") or "").strip(),
        "dedupe_hash": _short_hash("title_shape", candidate_text),
        "source_dir": export_dir.name,
        "block_reason": block_reason,
    }


def _summary(
    stats: Counter[str],
    reason_counts: Counter[str],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "stats": dict(stats),
        "block_reason_top": dict(reason_counts.most_common(20)),
        "candidate_count": len(candidates),
        "accepted_count": sum(1 for item in candidates if not item.get("block_reason")),
        "rejected_count": sum(1 for item in candidates if item.get("block_reason")),
        "candidate_source_counts": dict(Counter(item["candidate_source"] for item in candidates)),
        "tag_counts": dict(
            Counter(tag for item in candidates if not item.get("block_reason") for tag in item.get("tags", "").split("；") if tag)
        ),
        "sample": [item["candidate_text"] for item in candidates[:30]],
    }


if __name__ == "__main__":
    main()
