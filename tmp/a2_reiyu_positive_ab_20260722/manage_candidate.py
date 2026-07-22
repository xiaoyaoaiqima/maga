import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.models.maga_assets import AssetRegistry
from app.services.business_rule_asset_types import ARTICLE_BUSINESS_RULE_ASSET_TYPES
from app.services.product_experience_rule_service import import_product_experience_rule_set


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
PRODUCTION_ASSET_ID = 1972


async def import_candidate(csv_path: Path, label: str) -> None:
    async with async_session_factory() as session:
        production = await session.get(AssetRegistry, PRODUCTION_ASSET_ID)
        if production is None or production.asset_key != ASSET_KEY:
            raise RuntimeError("v17 production asset 1972 not found")
        result = await import_product_experience_rule_set(
            session,
            csv_path.read_bytes(),
            source_name=csv_path.name,
            asset_key=ASSET_KEY,
            display_name="a2礼遇UGC分享贴业务规则",
            created_by=f"codex-a2-reiyu-positive-ab-{label}",
        )
        candidate = await session.get(AssetRegistry, result.asset_id)
        # Planner only reads active production-stage assets. The candidate is
        # promoted temporarily for its isolated batch, then archived as
        # candidate by the restore action.
        candidate.asset_stage = "production"
        candidate.content_json = {
            **(candidate.content_json or {}),
            "variation_slot_selection_mode": "batch_item_cycle",
        }
        candidate.metadata_json = {
            **(candidate.metadata_json or {}),
            "variation_slot_selection_mode": "batch_item_cycle",
            "experiment": "positive_words_single_variable_ab",
            "experiment_arm": label,
            "production_baseline_asset_id": PRODUCTION_ASSET_ID,
        }
        await session.commit()
        print(
            json.dumps(
                {
                    "action": "import",
                    "label": label,
                    "asset_id": candidate.id,
                    "version_no": candidate.version_no,
                    "status": candidate.status,
                    "stage": candidate.asset_stage,
                    "rule_count": result.rule_count,
                },
                ensure_ascii=False,
            )
        )


async def restore_production() -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type.in_(ARTICLE_BUSINESS_RULE_ASSET_TYPES),
                AssetRegistry.asset_key == ASSET_KEY,
                AssetRegistry.id != PRODUCTION_ASSET_ID,
                AssetRegistry.status == "active",
            )
            .values(status="archived", asset_stage="candidate")
        )
        production = await session.get(AssetRegistry, PRODUCTION_ASSET_ID)
        if production is None:
            raise RuntimeError("v17 production asset 1972 not found")
        production.status = "active"
        production.asset_stage = "production"
        await session.commit()
        assets = list(
            (
                await session.execute(
                    select(AssetRegistry)
                    .where(
                        AssetRegistry.asset_type.in_(ARTICLE_BUSINESS_RULE_ASSET_TYPES),
                        AssetRegistry.asset_key == ASSET_KEY,
                    )
                    .order_by(AssetRegistry.version_no.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )
        print(
            json.dumps(
                {
                    "action": "restore",
                    "assets": [
                        {
                            "asset_id": asset.id,
                            "version_no": asset.version_no,
                            "status": asset.status,
                            "stage": asset.asset_stage,
                        }
                        for asset in assets
                    ],
                },
                ensure_ascii=False,
            )
        )


async def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("csv_path", type=Path)
    import_parser.add_argument("label")
    subparsers.add_parser("restore")
    args = parser.parse_args()
    if args.action == "import":
        await import_candidate(args.csv_path, args.label)
    else:
        await restore_production()


if __name__ == "__main__":
    asyncio.run(main())
