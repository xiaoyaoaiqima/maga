from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.database import get_db_context
from app.services.content_batch_report_service import ContentBatchReportService, _build_article_pool_csv


OUTPUT = Path("/Users/luxifa/maga/tmp/a2_reiyu_delivery_inventory_20260723/batch827_usable.csv")


async def main() -> None:
    async with get_db_context() as db:
        report = await ContentBatchReportService(db).get_batch_report(827, include_details=True)
        OUTPUT.write_bytes(_build_article_pool_csv(report))


if __name__ == "__main__":
    asyncio.run(main())
