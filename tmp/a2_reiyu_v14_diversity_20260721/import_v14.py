import asyncio
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.maga_assets import AssetRegistry
from app.services.product_experience_rule_service import import_product_experience_rule_set


CSV_PATH = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_v18_concise_prompt_20260721/"
    "a2礼遇UGC分享贴_v18精简生成要求.csv"
)
ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"


async def main() -> None:
    async with async_session_factory() as session:
        result = await import_product_experience_rule_set(
            session,
            CSV_PATH.read_bytes(),
            source_name=CSV_PATH.name,
            asset_key=ASSET_KEY,
            display_name="a2礼遇UGC分享贴业务规则",
            created_by="codex-a2-reiyu-concise-prompt-v18",
        )
        asset = (
            await session.execute(select(AssetRegistry).where(AssetRegistry.id == result.asset_id))
        ).scalar_one()
        asset.content_json = {
            **(asset.content_json or {}),
            "variation_slot_selection_mode": "batch_item_cycle",
        }
        asset.metadata_json = {
            **(asset.metadata_json or {}),
            "variation_slot_selection_mode": "batch_item_cycle",
        }
        await session.commit()
        print(
            {
                "asset_id": result.asset_id,
                "asset_key": result.asset_key,
                "version_no": asset.version_no,
                "rule_count": result.rule_count,
                "variation_slot_selection_mode": asset.content_json.get(
                    "variation_slot_selection_mode"
                ),
                "warnings": result.warnings,
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
