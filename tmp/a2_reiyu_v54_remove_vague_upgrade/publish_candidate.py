from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from app.core.database import async_session_factory
from app.models.maga_assets import AssetRegistry


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
ASSET_TYPE = "article_business_rule_set"
CANDIDATE_ID = 2022
TARGET = "这次升级会员体系确实比以前用心了"


def count_target(value: object) -> int:
    if isinstance(value, dict):
        return sum(count_target(child) for child in value.values())
    if isinstance(value, list):
        return sum(count_target(child) for child in value)
    return int(value == TARGET)


async def main() -> None:
    async with async_session_factory() as db:
        candidate = await db.get(AssetRegistry, CANDIDATE_ID)
        if (
            candidate is None
            or candidate.asset_type != ASSET_TYPE
            or candidate.asset_key != ASSET_KEY
            or candidate.asset_stage != "candidate"
            or candidate.status != "active"
        ):
            raise RuntimeError("expected active v54 candidate asset 2022")
        if count_target(candidate.content_json or {}) != 0:
            raise RuntimeError("removed activity-content option still exists")

        previous = (
            await db.execute(
                select(AssetRegistry).where(
                    AssetRegistry.asset_type == ASSET_TYPE,
                    AssetRegistry.asset_key == ASSET_KEY,
                    AssetRegistry.asset_stage == "production",
                    AssetRegistry.status == "active",
                )
            )
        ).scalar_one()
        next_version = int(
            (
                await db.execute(
                    select(func.max(AssetRegistry.version_no)).where(
                        AssetRegistry.asset_type == ASSET_TYPE,
                        AssetRegistry.asset_key == ASSET_KEY,
                    )
                )
            ).scalar_one()
            or 0
        ) + 1

        await db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == ASSET_TYPE,
                AssetRegistry.asset_key == ASSET_KEY,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        candidate.status = "archived"
        production = AssetRegistry(
            asset_type=ASSET_TYPE,
            asset_key=ASSET_KEY,
            display_name=candidate.display_name,
            version_no=next_version,
            status="active",
            asset_stage="production",
            source_name=f"promoted:asset_registry:{candidate.id}:v{candidate.version_no}",
            source_uri=f"asset_registry://{candidate.id}",
            source_hash=candidate.source_hash,
            content_json=copy.deepcopy(candidate.content_json or {}),
            metadata_json={
                **(candidate.metadata_json or {}),
                "asset_stage": "production",
                "previous_production_asset_id": previous.id,
                "previous_production_version_no": previous.version_no,
                "promoted_candidate_asset_id": candidate.id,
                "promoted_candidate_version_no": candidate.version_no,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "promoted_by": "codex",
            },
            created_by="codex-a2-reiyu-v54-publish",
        )
        db.add(production)
        await db.flush()
        result = {
            "previous_production_asset_id": previous.id,
            "previous_production_version": previous.version_no,
            "candidate_asset_id": candidate.id,
            "candidate_version": candidate.version_no,
            "production_asset_id": production.id,
            "production_version": production.version_no,
            "remaining_target_count": count_target(production.content_json or {}),
        }
        await db.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
