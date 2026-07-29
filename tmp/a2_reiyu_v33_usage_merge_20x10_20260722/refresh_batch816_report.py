"""Replay deterministic a2 guards and refresh the compact report for batch 816."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.core.database import async_session_factory
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_report_service import ContentBatchReportService


BATCH_ID = 816
REPORT_PATH = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_v33_usage_merge_audit_v7_20260722/batch816_report.json"
)


async def main() -> None:
    async with async_session_factory() as db:
        service = ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
        )
        job = await service._require_job(BATCH_ID)
        await service._review_a2_reiyu_text_items(BATCH_ID, job)
        await service._review_a2_reiyu_batch_detection_items(BATCH_ID, job)
        await service._review_a2_reiyu_old_can_items(BATCH_ID, job)
        await db.commit()
        db.expire_all()
        report = (await ContentBatchReportService(db).get_batch_report(BATCH_ID)).model_dump(mode="json")

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"batch_id": BATCH_ID, "report_path": str(REPORT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
