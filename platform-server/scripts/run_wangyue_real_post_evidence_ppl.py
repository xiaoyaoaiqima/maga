#!/usr/bin/env python3
"""Collect Wangyue real-post evidence directly from TikHub.

The command is dry-run by default. With ``--apply`` it calls TikHub through
MAGA's native acquisition service and writes review artifacts only under the
repository ``outputs`` directory. It never writes MAGA assets or databases.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any


PLATFORM_SERVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLATFORM_SERVER_ROOT.parent
OUTPUTS_ROOT = REPO_ROOT / "outputs"
if str(PLATFORM_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(PLATFORM_SERVER_ROOT))

from app.services.real_post_evidence_service import RealPostEvidenceService  # noqa: E402
from app.services.xhs_real_post_acquisition_service import (  # noqa: E402
    DEFAULT_TIKHUB_BASE_URL,
    XhsRealPostAcquisitionService,
    XhsRealPostRecord,
    XhsSearchRequest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 TikHub 直采小红书笔记并生成旺玥真人语料证据文件；默认仅预估调用量。"
    )
    parser.add_argument(
        "--keyword",
        action="append",
        required=True,
        help="搜索词，可重复传入。",
    )
    parser.add_argument("--per-keyword", type=int, default=20, help="每个搜索词最多拉取的笔记数。")
    parser.add_argument("--sort", default="general", help="TikHub 搜索排序。")
    parser.add_argument("--note-type", default="不限", help="TikHub 笔记类型筛选。")
    parser.add_argument("--time-filter", default="不限", help="TikHub 时间筛选。")
    parser.add_argument("--delay-ms", type=int, default=800, help="翻页和详情请求之间的等待毫秒数。")
    parser.add_argument("--detail-concurrency", type=int, default=4, help="详情请求并发数。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="输出目录；必须位于 maga/outputs 下。默认按时间创建独立目录。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正请求 TikHub 并写本地证据文件；不传时只打印调用量预估。",
    )
    return parser


def normalize_keywords(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = re.sub(r"\s+", " ", value).strip()
        if keyword and keyword not in seen:
            seen.add(keyword)
            result.append(keyword)
    if not result:
        raise ValueError("at least one non-empty --keyword is required")
    return result


def validate_positive_args(*, per_keyword: int, delay_ms: int, detail_concurrency: int) -> None:
    if per_keyword <= 0:
        raise ValueError("--per-keyword must be greater than 0")
    if delay_ms < 0:
        raise ValueError("--delay-ms must be 0 or greater")
    if detail_concurrency <= 0:
        raise ValueError("--detail-concurrency must be greater than 0")


def resolve_output_dir(value: Path | None, *, outputs_root: Path = OUTPUTS_ROOT) -> Path:
    root = outputs_root.resolve()
    if value is None:
        value = root / f"wangyue_tikhub_energy_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    elif not value.is_absolute():
        value = REPO_ROOT / value
    resolved = value.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError(f"--output-dir must be a child directory of {root}")
    return resolved


def build_requests(args: argparse.Namespace, keywords: list[str]) -> list[XhsSearchRequest]:
    return [
        XhsSearchRequest(
            keyword=keyword,
            limit=args.per_keyword,
            sort=args.sort,
            note_type=args.note_type,
            time_filter=args.time_filter,
            delay_ms=args.delay_ms,
            detail_concurrency=args.detail_concurrency,
        )
        for keyword in keywords
    ]


def dedupe_records(records: list[XhsRealPostRecord]) -> list[XhsRealPostRecord]:
    seen: set[str] = set()
    result: list[XhsRealPostRecord] = []
    for record in records:
        key = record.note_id or f"{record.title}\n{record.content}".strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def build_acquisition_service() -> XhsRealPostAcquisitionService:
    return XhsRealPostAcquisitionService(base_url=DEFAULT_TIKHUB_BASE_URL)


def write_raw_jsonl(records: list[XhsRealPostRecord], path: Path) -> Path:
    payload = "".join(json.dumps(asdict(record), ensure_ascii=False) + "\n" for record in records)
    path.write_text(payload, encoding="utf-8")
    return path


async def run(
    args: argparse.Namespace,
    *,
    acquisition_service: XhsRealPostAcquisitionService | None = None,
    outputs_root: Path = OUTPUTS_ROOT,
) -> dict[str, Any]:
    keywords = normalize_keywords(args.keyword)
    validate_positive_args(
        per_keyword=args.per_keyword,
        delay_ms=args.delay_ms,
        detail_concurrency=args.detail_concurrency,
    )
    service = acquisition_service or build_acquisition_service()
    estimate = service.estimate_calls(keywords, per_keyword=args.per_keyword)
    base_result: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry_run",
        "provider": "tikhub_direct",
        "keywords": keywords,
        "estimate": estimate,
        "writes_database": False,
        "writes_assets": False,
    }
    if not args.apply:
        return base_result

    records = await service.fetch_keywords(build_requests(args, keywords))
    deduped = dedupe_records(records)
    evidence = RealPostEvidenceService().analyze(deduped)

    output_dir = resolve_output_dir(args.output_dir, outputs_root=outputs_root)
    output_dir.mkdir(parents=True, exist_ok=False)
    raw_path = write_raw_jsonl(deduped, output_dir / "raw_notes.jsonl")
    evidence_csv_path = RealPostEvidenceService().write_csv(evidence, output_dir / "evidence.csv")
    evidence_md_path = RealPostEvidenceService().write_markdown(
        evidence,
        output_dir / "evidence.md",
        source_label="TikHub direct via MAGA",
    )
    result = {
        **base_result,
        "output_dir": str(output_dir),
        "fetched_count": len(records),
        "deduped_count": len(deduped),
        "evidence_stats": evidence.stats,
        "files": {
            "raw_jsonl": str(raw_path),
            "evidence_csv": str(evidence_csv_path),
            "evidence_markdown": str(evidence_md_path),
        },
    }
    summary_path = output_dir / "summary.json"
    result["files"]["summary_json"] = str(summary_path)
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    args = build_parser().parse_args()
    try:
        result = asyncio.run(run(args))
    except (FileExistsError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
