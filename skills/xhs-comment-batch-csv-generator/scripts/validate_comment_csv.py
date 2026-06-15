#!/usr/bin/env python3
"""Validate two-column XHS comment batch CSV files."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


REQUIRED_FIELDS = ["大类", "评论内容"]


def parse_category(raw: str) -> tuple[str, int]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("category must be NAME=COUNT")
    name, count = raw.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("category name cannot be empty")
    try:
        expected = int(count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("category count must be an integer") from exc
    return name, expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--expected-total", type=int)
    parser.add_argument("--category", action="append", default=[], type=parse_category)
    parser.add_argument("--forbidden", action="append", default=[])
    args = parser.parse_args()

    with args.csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []

    errors: list[str] = []
    if fields != REQUIRED_FIELDS:
        errors.append(f"fields expected {REQUIRED_FIELDS}, got {fields}")
    if args.expected_total is not None and len(rows) != args.expected_total:
        errors.append(f"row count expected {args.expected_total}, got {len(rows)}")

    category_counts = Counter(row.get("大类", "") for row in rows)
    expected_categories = dict(args.category)
    for name, expected in expected_categories.items():
        actual = category_counts.get(name, 0)
        if actual != expected:
            errors.append(f"category {name} expected {expected}, got {actual}")
    bad_categories = sorted(set(category_counts) - set(expected_categories)) if expected_categories else []
    if bad_categories:
        errors.append(f"unexpected categories: {bad_categories}")

    empty_rows = [
        index + 2
        for index, row in enumerate(rows)
        if not str(row.get("大类") or "").strip() or not str(row.get("评论内容") or "").strip()
    ]
    if empty_rows:
        errors.append(f"empty category/comment rows: {empty_rows[:20]}")

    duplicate_comments = [text for text, count in Counter(row.get("评论内容", "") for row in rows).items() if count > 1]
    if duplicate_comments:
        errors.append(f"duplicate comments: {duplicate_comments[:20]}")

    forbidden_terms = [term.strip() for term in args.forbidden if term.strip()]
    forbidden_hits = [
        (index + 2, term, row.get("评论内容", ""))
        for index, row in enumerate(rows)
        for term in forbidden_terms
        if term in row.get("评论内容", "")
    ]
    if forbidden_hits:
        errors.append(f"forbidden hits: {forbidden_hits[:20]}")

    print(f"rows={len(rows)}")
    print(f"categories={dict(category_counts)}")
    print(f"duplicates={len(duplicate_comments)}")
    print(f"forbidden_hits={len(forbidden_hits)}")
    if errors:
        print("status=FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("status=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
