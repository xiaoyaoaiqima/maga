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
CANDIDATE_ID = 2024
REMOVED_OPTIONS = {
    "会员体系升级，用户权益也上来了",
    "会员积分啥的就是给长期囤货的人准备的，挺划得来",
    "才注意到a2至初的会员体系，原来每次下单都能累计积分，还能换各种礼品",
    "积分可以换礼品，这种特别适合我这种长期回购的用户",
    "积分系统挺友好的，换的东西也实用",
    "之前还觉得活动就是抽个奖而已，发现真的是福利叠加",
    "多层福利叠加，感觉每一笔消费都更有价值了",
    "多重福利一起上，a2这次是真的很舍得🎁",
    "多重福利叠加起来真的很香✌️",
    "抽奖、集罐礼、老客回馈都有，多重福利真的用心了",
    "本来以为就一个活动，结果发现福利层层叠加，越看越觉得划算😂",
    "罐子能换、抽奖也能参与，这种组合活动很实在了呀😊",
    "集罐、抽奖、回馈礼都有，叠加起来真的很香",
}


def count_removed(value: object) -> int:
    if isinstance(value, dict):
        return sum(count_removed(child) for child in value.values())
    if isinstance(value, list):
        return sum(count_removed(child) for child in value)
    return int(isinstance(value, str) and value in REMOVED_OPTIONS)


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
            raise RuntimeError("expected active v56 candidate asset 2024")
        if count_removed(candidate.content_json or {}) != 0:
            raise RuntimeError("vague activity-content options still exist")

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
            created_by="codex-a2-reiyu-v56-publish",
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
            "remaining_vague_option_count": count_removed(production.content_json or {}),
        }
        await db.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
