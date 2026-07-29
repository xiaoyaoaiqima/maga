from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem


async def main() -> None:
    async with async_session_factory() as db:
        items = (
            await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id.in_([873, 874]))
                .order_by(ContentBatchItem.batch_id, ContentBatchItem.item_no)
            )
        ).scalars()
        rows = []
        for item in items:
            quality = dict(item.quality_json or {})
            report = dict(quality.get("review_report") or {})
            judge = dict(report.get("product_experience_llm_review") or {})
            guard_keys = (
                "a2_reiyu_text_guard",
                "a2_reiyu_batch_detection_guard",
                "a2_reiyu_old_can_guard",
                "a2_reiyu_forbidden_terms_guard",
            )
            failed_guards = {
                key: report.get(key)
                for key in guard_keys
                if isinstance(report.get(key), dict)
                and report[key].get("pass") is not True
            }
            if (
                failed_guards
                or judge.get("business_usability_tier") == "hold_out"
                or (item.batch_id, item.item_no) == (873, 14)
            ):
                rows.append(
                    {
                        "batch_id": item.batch_id,
                        "item_no": item.item_no,
                        "title": item.title,
                        "body": item.body,
                        "hard_pass": quality.get("hard_pass"),
                        "tier": judge.get("business_usability_tier"),
                        "reason": judge.get("business_usability_reason"),
                        "issues": judge.get("issues"),
                        "failed_guards": failed_guards,
                        "top_level_forbidden_guard": quality.get("a2_reiyu_forbidden_terms_guard"),
                    }
                )
        print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
