from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.database import get_db_context
from app.models.maga_assets import AssetRegistry


async def main() -> None:
    async with get_db_context() as db:
        result = await db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_key == "a2_reiyu_ugc_post_rules_v1",
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        asset = result.scalar_one()
        items = list((asset.content_json or {}).get("items") or [])
        print(json.dumps({
            "id": asset.id,
            "version": asset.version_no,
            "display_name": asset.display_name,
            "items": [
                {
                    "source_row_no": item.get("source_row_no"),
                    "item_id": item.get("item_id"),
                    "slot_code": item.get("slot_code"),
                    "name": item.get("name") or item.get("label") or item.get("title"),
                    "content": item,
                }
                for item in items
            ],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
