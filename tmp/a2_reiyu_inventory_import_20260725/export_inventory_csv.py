from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem
from app.services.a2_reiyu_csv_audit_service import a2_reiyu_title_weighted_len


OUTPUT = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_inventory_import_20260725/"
    "A2礼遇_新增可用198篇_20260725.csv"
)


def category_for_source_row(source_row_no: int) -> str:
    if source_row_no in {13, 14}:
        return "12罐"
    if source_row_no in {9, 10, 11, 12, 15, 16}:
        return "其他罐"
    if source_row_no in set(range(1, 9)):
        return "其他"
    raise ValueError(f"unexpected source row: {source_row_no}")


async def main() -> None:
    async with async_session_factory() as db:
        items = list(
            (
                await db.execute(
                    select(ContentBatchItem)
                    .where(ContentBatchItem.batch_id.in_([873, 874]))
                    .order_by(ContentBatchItem.batch_id, ContentBatchItem.item_no)
                )
            ).scalars()
        )

    rows = []
    excluded = []
    bodies = set()
    for item in items:
        quality = dict(item.quality_json or {})
        report = dict(quality.get("review_report") or {})
        judge = dict(report.get("product_experience_llm_review") or {})
        weighted_len = a2_reiyu_title_weighted_len(item.title or "")
        if weighted_len > 20:
            excluded.append((item.batch_id, item.item_no, weighted_len))
            continue
        if quality.get("hard_pass") is not True:
            raise ValueError(f"not hard pass: batch={item.batch_id} item={item.item_no}")
        if judge.get("business_usability_tier") != "direct_pool":
            raise ValueError(
                f"not direct_pool: batch={item.batch_id} item={item.item_no} "
                f"tier={judge.get('business_usability_tier')}"
            )
        body = str(item.body or "").strip()
        if not body or body in bodies:
            raise ValueError(f"empty or duplicate body: batch={item.batch_id} item={item.item_no}")
        bodies.add(body)
        source_row_no = int((item.plan_json or {}).get("source_row_no") or 0)
        rows.append(
            {
                "content_id": f"a2-reiyu-b{item.batch_id}-i{item.item_no:03d}",
                "标题": str(item.title or "").strip(),
                "正文": body,
                "分类": category_for_source_row(source_row_no),
                "审核档位": "direct_pool",
            }
        )

    if [(batch_id, item_no) for batch_id, item_no, _ in excluded] != [(873, 60), (874, 79)]:
        raise ValueError(f"unexpected title exclusions: {excluded}")
    if len(rows) != 198:
        raise ValueError(f"expected 198 rows, got {len(rows)}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["content_id", "标题", "正文", "分类", "审核档位"],
        )
        writer.writeheader()
        writer.writerows(rows)

    counts = {category: sum(row["分类"] == category for row in rows) for category in ("12罐", "其他罐", "其他")}
    print({"output": str(OUTPUT), "rows": len(rows), "counts": counts, "excluded": excluded})


if __name__ == "__main__":
    asyncio.run(main())
