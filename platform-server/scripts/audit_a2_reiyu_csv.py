"""Audit one external a2 礼遇 CSV with the production gold-review chain."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.a2_reiyu_csv_audit_service import (  # noqa: E402
    audit_a2_reiyu_csv_file,
    audit_a2_reiyu_csv_file_strict,
    load_active_a2_reiyu_business_entries,
    load_active_a2_reiyu_review_plan,
)


async def _load_active_audit_context():
    from app.core.database import get_db_context

    async with get_db_context() as db:
        return (
            await load_active_a2_reiyu_business_entries(db),
            await load_active_a2_reiyu_review_plan(db),
        )


async def _run_strict_audit(input_path, output_path, *, concurrency: int):
    business_entries, review_plan = await _load_active_audit_context()
    return await audit_a2_reiyu_csv_file_strict(
        input_path,
        output_path,
        business_entries=business_entries,
        review_plan=review_plan,
        concurrency=concurrency,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="使用production Guard + 金标Judge审核a2礼遇CSV。")
    parser.add_argument("input_csv", type=Path, help="待审核CSV")
    parser.add_argument("--output", type=Path, help="输出CSV；默认为原文件同目录的 *_a2审核.csv")
    parser.add_argument("--concurrency", type=int, default=10, help="金标语义审核并发数，默10")
    parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="只跑确定性Guard，用于调试；正式CSV审核不应使用",
    )
    args = parser.parse_args()

    input_path = args.input_csv.expanduser().resolve()
    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else input_path.with_name(f"{input_path.stem}_a2审核.csv")
    )
    if args.deterministic_only:
        business_entries, _ = asyncio.run(_load_active_audit_context())
        summary = audit_a2_reiyu_csv_file(
            input_path,
            output_path,
            business_entries=business_entries,
        )
    else:
        summary = asyncio.run(
            _run_strict_audit(input_path, output_path, concurrency=args.concurrency)
        )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
