from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.services.product_experience_phrase_guard_service import (
    review_product_experience_phrase,
)


ROOT = Path("/Users/luxifa/maga")
INVENTORY_PATH = ROOT / "local_data/a2_reiyu_delivery/article_inventory.sqlite3"
OUTPUT_DIR = (
    ROOT
    / "outputs/0705_wangyue_product_relation_evidence"
    / "20260727_wangyue_machine_only_pool_review"
)
ASSET_KEY = "wangyue_v3_core_storyline_article_rules"


def load_inventory_rows() -> list[dict[str, object]]:
    conn = sqlite3.connect(INVENTORY_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            i.id AS inventory_id,
            i.content_id,
            i.title,
            i.body,
            i.review_status,
            s.metadata_json
        FROM article_inventory i
        JOIN article_inventory_source s ON s.id = (
            SELECT MAX(s2.id)
            FROM article_inventory_source s2
            WHERE s2.article_id = i.id
              AND s2.source_type = 'maga_batch_sync'
        )
        WHERE i.asset_key = ?
          AND i.usable = 1
          AND i.delivered_count = 0
          AND i.review_status = 'machine_exportable'
        ORDER BY i.id
        """,
        (ASSET_KEY,),
    ).fetchall()
    conn.close()
    result: list[dict[str, object]] = []
    for row in rows:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        result.append(
            {
                "inventory_id": int(row["inventory_id"]),
                "content_id": str(row["content_id"]),
                "title": str(row["title"]),
                "body": str(row["body"]),
                "review_status": str(row["review_status"]),
                "batch_id": int(metadata.get("batch_id") or 0),
                "item_id": int(metadata.get("item_id") or 0),
                "rule_asset_version": int(metadata.get("rule_asset_version") or 0),
                "category": str(metadata.get("分类") or ""),
                "context_list": str(metadata.get("上下文变量(context_list)") or ""),
            }
        )
    return result


async def enrich(rows: list[dict[str, object]]) -> None:
    item_ids = [int(row["item_id"]) for row in rows if int(row["item_id"])]
    async with async_session_factory() as db:
        item_result = await db.execute(
            select(ContentBatchItem).where(ContentBatchItem.id.in_(item_ids))
        )
        items = {int(item.id): item for item in item_result.scalars().all()}
        batch_ids = sorted({int(item.batch_id) for item in items.values()})
        job_result = await db.execute(
            select(ContentBatchJob).where(ContentBatchJob.id.in_(batch_ids))
        )
        jobs = {int(job.id): job for job in job_result.scalars().all()}

    for ordinal, row in enumerate(rows, start=1):
        item = items.get(int(row["item_id"]))
        if item is None:
            row["item_missing"] = True
            row["ordinal"] = ordinal
            continue
        plan = dict(item.plan_json or {})
        review = review_product_experience_phrase(
            title=str(row["title"]),
            body=str(row["body"]),
            plan=plan,
        )
        job = jobs.get(int(item.batch_id))
        row.update(
            {
                "ordinal": ordinal,
                "item_no": int(item.item_no),
                "batch_code": str(job.batch_code or "") if job else "",
                "plan_json": plan,
                "current_phrase_guard": review.model_dump(),
                "rendered_prompt": str(
                    ((plan.get("unified_generation") or {}).get("rendered_prompt") or "")
                ),
            }
        )


def write_outputs(rows: list[dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "20260727_wangyue_machine_only_150_review_packet.json"
    md_path = OUTPUT_DIR / "20260727_wangyue_machine_only_150_review_packet.md"
    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 旺玥未导出库存｜仅机审 150 篇复核包",
        "",
        "本文件按本地文章池顺序列出标题、正文、来源批次和当前确定性审核信号。",
        "确定性信号只辅助人工复核，不自动代表文章不可用。",
        "",
    ]
    for row in rows:
        guard = dict(row.get("current_phrase_guard") or {})
        reasons = list(guard.get("reasons") or [])
        lines.extend(
            [
                (
                    f"## {row['ordinal']}. inventory {row['inventory_id']}｜"
                    f"batch {row['batch_id']} item {row.get('item_no', '?')}｜v{row['rule_asset_version']}"
                ),
                "",
                f"- 内容方向：{row['category']}",
                f"- 当前确定性信号：{', '.join(reasons) if reasons else '无'}",
                f"- 标题：{row['title']}",
                "",
                str(row["body"]),
                "",
            ]
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "count": len(rows),
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "missing_items": sum(bool(row.get("item_missing")) for row in rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def main() -> None:
    rows = load_inventory_rows()
    await enrich(rows)
    write_outputs(rows)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
