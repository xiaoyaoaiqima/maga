from __future__ import annotations

import asyncio
import json

from sqlalchemy import func, select

from app.core.database import get_db_context
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.services.business_forbidden_term_service import A2_REIYU_UGC_POST_ASSET_KEY


async def main() -> None:
    async with get_db_context() as db:
        total = await db.execute(
            select(func.count())
            .select_from(ContentBatchItem)
            .join(ContentBatchJob, ContentBatchJob.id == ContentBatchItem.batch_id)
            .where(ContentBatchJob.asset_key == A2_REIYU_UGC_POST_ASSET_KEY)
        )
        rows = await db.execute(
            select(
                ContentBatchJob.id,
                ContentBatchJob.batch_code,
                ContentBatchJob.status,
                ContentBatchJob.count,
                ContentBatchJob.strategy_json,
                func.count(ContentBatchItem.id).label("item_count"),
                func.sum(ContentBatchItem.status == "generated").label("generated_count"),
                func.max(ContentBatchJob.create_time).label("create_time"),
            )
            .join(ContentBatchItem, ContentBatchItem.batch_id == ContentBatchJob.id, isouter=True)
            .where(ContentBatchJob.asset_key == A2_REIYU_UGC_POST_ASSET_KEY)
            .group_by(ContentBatchJob.id)
            .order_by(ContentBatchJob.id.desc())
            .limit(30)
        )
        print(json.dumps({
            "total_items": int(total.scalar() or 0),
            "latest_batches": [
                {
                    "id": row.id,
                    "batch_code": row.batch_code,
                    "status": row.status,
                    "count": row.count,
                    "item_count": int(row.item_count or 0),
                    "generated_count": int(row.generated_count or 0),
                    "strategy_json": row.strategy_json,
                    "create_time": str(row.create_time or ""),
                }
                for row in rows
            ],
        }, ensure_ascii=False, indent=2))

        status_rows = await db.execute(
            select(ContentBatchItem.batch_id, ContentBatchItem.status, func.count())
            .where(ContentBatchItem.batch_id.in_([825, 827]))
            .group_by(ContentBatchItem.batch_id, ContentBatchItem.status)
            .order_by(ContentBatchItem.batch_id, ContentBatchItem.status)
        )
        print(json.dumps({"statuses": [list(row) for row in status_rows]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
