#!/usr/bin/env python3
"""Check duplicate values in the 评论内容 column of a CSV file."""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_CSV = Path("/Users/luxifa/Downloads/安心高品质-评论话术表 - 613给出-去重.csv")
COMMENT_FIELD = "评论内容"
CATEGORY_FIELDS = ("分类", "大类")
DEFAULT_ASSET_KEY = "a2_sentiment_comment_activity"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=DEFAULT_CSV,
        type=Path,
        help=f"CSV file to check, defaults to {DEFAULT_CSV}",
    )
    parser.add_argument(
        "--dedup-output",
        type=Path,
        help="Write a de-duplicated CSV, keeping the first occurrence of each 评论内容.",
    )
    parser.add_argument(
        "--history-csv",
        action="append",
        default=[],
        type=Path,
        help="Historical CSV to exclude by 评论内容. Can be passed more than once.",
    )
    parser.add_argument(
        "--against-ledger",
        action="store_true",
        help="Check whether comments already exist in comment_delivery_ledger.",
    )
    parser.add_argument(
        "--import-ledger",
        action="store_true",
        help="Import non-empty comments into comment_delivery_ledger.",
    )
    parser.add_argument(
        "--asset-key",
        default=DEFAULT_ASSET_KEY,
        help=f"Ledger asset key, defaults to {DEFAULT_ASSET_KEY}.",
    )
    parser.add_argument(
        "--source-uri",
        default=None,
        help="Source URI/path recorded when importing into the ledger.",
    )
    parser.add_argument(
        "--source-type",
        default="csv_import",
        help="Ledger source_type when importing, defaults to csv_import.",
    )
    parser.add_argument(
        "--delivered-by",
        default="csv_script",
        help="Ledger delivered_by when importing, defaults to csv_script.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.csv_path.exists():
        raise SystemExit(f"CSV not found: {args.csv_path}")

    history_comments = _read_history_comments(args.history_csv)
    rows = _read_comment_rows(args.csv_path)
    header = rows["header"]
    csv_rows = rows["rows"]
    comment_rows = rows["comment_rows"]
    empty_rows = rows["empty_rows"]
    dedup_rows = _build_dedup_rows(csv_rows, history_comments) if args.dedup_output else []
    total_rows = rows["total_rows"]
    non_empty_rows = rows["non_empty_rows"]

    duplicate_items = [
        (comment, rows)
        for comment, rows in comment_rows.items()
        if len(rows) > 1
    ]
    history_duplicate_rows = [
        row
        for row in csv_rows
        if row["comment"] and row["comment"] in history_comments
    ]

    print(f"file={args.csv_path}")
    print(f"checked_column={COMMENT_FIELD}")
    print(f"total_rows={total_rows}")
    print(f"non_empty_rows={non_empty_rows}")
    print(f"unique_comments={len(comment_rows)}")
    print(f"empty_rows={len(empty_rows)}")
    print(f"duplicate_comment_groups={len(duplicate_items)}")
    print(f"history_comments={len(history_comments)}")
    print(f"history_duplicate_rows={len(history_duplicate_rows)}")

    if args.dedup_output:
        args.dedup_output.parent.mkdir(parents=True, exist_ok=True)
        with args.dedup_output.open("w", encoding="utf-8-sig", newline="") as output_file:
            writer = csv.writer(output_file)
            writer.writerow(header)
            writer.writerows(dedup_rows)
        print(f"dedup_output={args.dedup_output}")
        print(f"dedup_rows={len(dedup_rows)}")
        print(f"removed_rows={total_rows - len(dedup_rows)}")

    if empty_rows:
        print("\nEmpty 评论内容 rows:")
        print(", ".join(str(row) for row in empty_rows))

    if duplicate_items:
        print("\nDuplicate 评论内容:")
        for comment, rows in duplicate_items:
            print(f"- rows={','.join(str(row) for row in rows)} count={len(rows)} content={comment}")
    if history_duplicate_rows:
        print("\nDuplicate against history CSV:")
        for row in history_duplicate_rows:
            print(f"- row={row['row_no']} content={row['comment']}")
    ledger_duplicate_rows = []
    imported_rows = 0
    skipped_existing_rows = 0
    skipped_input_duplicate_rows = 0
    if args.against_ledger or args.import_ledger:
        ledger_result = asyncio.run(
            _run_ledger_actions(
                args=args,
                csv_rows=csv_rows,
            )
        )
        ledger_duplicate_rows = ledger_result["duplicate_rows"]
        imported_rows = ledger_result["imported_rows"]
        skipped_existing_rows = ledger_result["skipped_existing_rows"]
        skipped_input_duplicate_rows = ledger_result["skipped_input_duplicate_rows"]
        print(f"ledger_duplicate_rows={len(ledger_duplicate_rows)}")
        print(f"imported_rows={imported_rows}")
        print(f"skipped_existing_rows={skipped_existing_rows}")
        print(f"skipped_input_duplicate_rows={skipped_input_duplicate_rows}")
        if ledger_duplicate_rows:
            print("\nDuplicate against comment_delivery_ledger:")
            for item in ledger_duplicate_rows:
                entry = item["ledger_entry"]
                print(
                    f"- row={item['row_no']} ledger_id={entry.get('id')} "
                    f"source={entry.get('source_type')} uri={entry.get('source_uri')} "
                    f"content={item['comment']}"
                )

    if duplicate_items or history_duplicate_rows or ledger_duplicate_rows:
        return 1

    print("\nNo duplicate 评论内容 found.")
    return 0


def _read_history_comments(history_csv_paths: list[Path]) -> set[str]:
    comments: set[str] = set()
    for history_csv_path in history_csv_paths:
        if not history_csv_path.exists():
            raise SystemExit(f"History CSV not found: {history_csv_path}")
        history_rows = _read_comment_rows(history_csv_path)
        for row in history_rows["rows"]:
            if row["comment"]:
                comments.add(row["comment"])
    return comments


def _build_dedup_rows(csv_rows: list[dict[str, Any]], history_comments: set[str]) -> list[list[str]]:
    dedup_rows: list[list[str]] = []
    seen_comments: set[str] = set()
    for row in csv_rows:
        comment = row["comment"]
        if not comment:
            dedup_rows.append(row["row"])
            continue
        # 历史库命中的评论直接排除；其余只保留本文件内第一次出现。
        if comment in history_comments or comment in seen_comments:
            continue
        dedup_rows.append(row["row"])
        seen_comments.add(comment)
    return dedup_rows


def _read_comment_rows(csv_path: Path) -> dict[str, Any]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.reader(csv_file)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit(f"CSV is empty: {csv_path}") from None
        if COMMENT_FIELD not in header:
            raise SystemExit(f"Missing required column {COMMENT_FIELD!r}; fields={header}")
        comment_index = header.index(COMMENT_FIELD)
        category_index = next((header.index(field) for field in CATEGORY_FIELDS if field in header), None)

        # 按 strip 后的评论内容聚合，避免前后空格导致重复漏检；空内容单独统计。
        comment_rows: dict[str, list[int]] = defaultdict(list)
        empty_rows: list[int] = []
        dedup_rows: list[list[str]] = []
        csv_rows: list[dict[str, Any]] = []
        total_rows = 0
        non_empty_rows = 0
        seen_comments: set[str] = set()
        for index, row in enumerate(reader, start=2):
            total_rows += 1
            comment = (row[comment_index] if len(row) > comment_index else "").strip()
            category = (row[category_index] if category_index is not None and len(row) > category_index else "").strip()
            csv_rows.append({"row_no": index, "row": row, "category": category, "comment": comment})
            if not comment:
                empty_rows.append(index)
                dedup_rows.append(row)
                continue
            non_empty_rows += 1
            comment_rows[comment].append(index)
            if comment not in seen_comments:
                dedup_rows.append(row)
            seen_comments.add(comment)
    return {
        "header": header,
        "rows": csv_rows,
        "comment_rows": comment_rows,
        "empty_rows": empty_rows,
        "dedup_rows": dedup_rows,
        "total_rows": total_rows,
        "non_empty_rows": non_empty_rows,
    }


async def _run_ledger_actions(*, args: argparse.Namespace, csv_rows: list[dict[str, Any]]) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    platform_server = repo_root / "platform-server"
    sys.path.insert(0, str(platform_server))

    from app.core.database import async_session_factory  # noqa: PLC0415
    from app.services.comment_delivery_ledger_service import CommentDeliveryLedgerService, ledger_entry_to_dict  # noqa: PLC0415

    non_empty_rows = [row for row in csv_rows if row["comment"]]
    duplicate_rows = []
    imported_rows = 0
    skipped_existing_rows = 0
    skipped_input_duplicate_rows = 0
    async with async_session_factory() as session:
        service = CommentDeliveryLedgerService(session)
        if args.against_ledger:
            existing = await service.exists_many(
                asset_key=args.asset_key,
                comments=[row["comment"] for row in non_empty_rows],
            )
            for row in non_empty_rows:
                entry = existing.get(service.normalize_comment(row["comment"]))
                if entry is not None:
                    duplicate_rows.append(
                        {
                            "row_no": row["row_no"],
                            "comment": row["comment"],
                            "ledger_entry": ledger_entry_to_dict(entry),
                        }
                    )
        if args.import_ledger:
            result = await service.upsert_many(
                asset_key=args.asset_key,
                entries=[
                    {
                        "category": row["category"],
                        "comment_text": row["comment"],
                        "metadata_json": {"csv_row_no": row["row_no"]},
                    }
                    for row in non_empty_rows
                ],
                source_type=args.source_type,
                source_uri=args.source_uri or str(args.csv_path),
                delivered_by=args.delivered_by,
            )
            imported_rows = result.imported_rows
            skipped_existing_rows = result.skipped_existing_rows
            skipped_input_duplicate_rows = result.skipped_input_duplicate_rows
        await session.commit()
    return {
        "duplicate_rows": duplicate_rows,
        "imported_rows": imported_rows,
        "skipped_existing_rows": skipped_existing_rows,
        "skipped_input_duplicate_rows": skipped_input_duplicate_rows,
    }


if __name__ == "__main__":
    raise SystemExit(main())
