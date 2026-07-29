from __future__ import annotations

import asyncio
import csv
import json
import random
from io import StringIO
from pathlib import Path

from app.core.database import get_db_context
from app.services.content_batch_report_service import (
    ContentBatchReportService,
    _article_pool_export_items,
    _build_article_pool_csv,
)


BATCH_ID = 832
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_generate_100_can_20260723")


async def main() -> None:
    async with get_db_context() as db:
        report = await ContentBatchReportService(db).get_batch_report(
            BATCH_ID,
            include_details=True,
        )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"batch{BATCH_ID}_full_report.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    exportable = _article_pool_export_items(report.items)
    article_pool_path = OUTPUT_DIR / f"batch{BATCH_ID}_machine_direct_pool.csv"
    article_pool_path.write_bytes(_build_article_pool_csv(report))

    prompt_item = random.Random(20260723).choice(exportable or report.items)
    snapshot = prompt_item.generation_snapshot or {}
    prompt_path = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item{prompt_item.item_no}.md"
    prompt_path.write_text(
        "\n".join(
            [
                "# A2礼遇集罐100篇随机完整Prompt",
                "",
                f"- batch_id: {BATCH_ID}",
                f"- item_no: {prompt_item.item_no}",
                f"- title: {prompt_item.title or ''}",
                "",
                "## 完整生文 Prompt",
                "",
                str(snapshot.get("rendered_prompt") or ""),
                "",
            ]
        ),
        encoding="utf-8",
    )

    raw_csv = StringIO(newline="")
    writer = csv.DictWriter(
        raw_csv,
        fieldnames=["item_no", "content_id", "标题", "正文", "分类", "机器审核档位"],
    )
    writer.writeheader()
    for item in report.items:
        snapshot = item.generation_snapshot or {}
        business_rule = str((snapshot.get("business_rule") or {}).get("business_rule") or "")
        if "12罐" in business_rule:
            category = "12罐"
        elif "集罐" in business_rule:
            category = "其他罐"
        else:
            category = "其他"
        writer.writerow(
            {
                "item_no": item.item_no,
                "content_id": f"batch-{BATCH_ID}-item-{item.item_no}",
                "标题": item.title or "",
                "正文": item.body or "",
                "分类": category,
                "机器审核档位": item.business_usability_tier or "",
            }
        )
    raw_path = OUTPUT_DIR / f"batch{BATCH_ID}_100篇全量.csv"
    raw_path.write_text(raw_csv.getvalue(), encoding="utf-8-sig")

    summary = {
        "batch_id": BATCH_ID,
        "batch_code": report.batch_code,
        "asset_id": 2005,
        "asset_version": 39,
        "source_rows": list(range(9, 17)),
        "attempted": 100,
        "raw_generated": report.summary.generated_count,
        "generation_failed": report.summary.failed_count,
        "machine_final_pass": report.summary.hard_pass_count,
        "machine_direct_pool_csv_rows": len(exportable),
        "max_pairwise_jaccard_2gram": report.summary.max_pairwise_jaccard_2gram,
        "similarity_warning_count": report.summary.similarity_warning_count,
        "forbidden_hit_count": report.summary.forbidden_hit_count,
        "report_path": str(report_path),
        "raw_path": str(raw_path),
        "article_pool_path": str(article_pool_path),
        "prompt_path": str(prompt_path),
    }
    (OUTPUT_DIR / f"batch{BATCH_ID}_run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
