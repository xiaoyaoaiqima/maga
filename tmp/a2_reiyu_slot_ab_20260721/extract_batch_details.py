import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_slot_ab_20260721")
BATCHES = {"current": 716, "original": 717}


async def main() -> None:
    async with async_session_factory() as session:
        for name, batch_id in BATCHES.items():
            items = list(
                (
                    await session.execute(
                        select(ContentBatchItem)
                        .where(ContentBatchItem.batch_id == batch_id)
                        .order_by(ContentBatchItem.item_no)
                    )
                )
                .scalars()
                .all()
            )
            payload = []
            for item in items:
                plan = dict(item.plan_json or {})
                unified = dict(plan.get("unified_generation") or {})
                payload.append(
                    {
                        "item_id": item.id,
                        "item_no": item.item_no,
                        "title": item.title or "",
                        "body": item.body or "",
                        "quality": item.quality_json or {},
                        "business_rule": plan.get("business_rule"),
                        "rule_id": plan.get("rule_id"),
                        "source_row_no": plan.get("source_row_no"),
                        "variation_slots": plan.get("variation_slots") or [],
                        "rendered_prompt": unified.get("rendered_prompt") or "",
                        "model_config": unified.get("model_config") or plan.get("model_config") or {},
                    }
                )
            path = OUTPUT_DIR / f"{name}_batch_details.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(name, batch_id, len(payload), path)


if __name__ == "__main__":
    asyncio.run(main())
