from __future__ import annotations

import argparse
import asyncio
import copy
import json

from sqlalchemy import func, select, update

from app.core.database import async_session_factory
from app.models.maga_assets import AssetRegistry


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
ASSET_TYPE = "article_business_rule_set"
EXPECTED_PRODUCTION_ID = 2005
EXPECTED_PRODUCTION_VERSION = 39

OLD_ATOM = "真的有在用心经营跟用户之间的信任感🤝"
NEW_ATOM = "看完对a2又多了点信任🤝"
OLD_BOUNDARY = "不要照抄槽位素材，要换成自然大白话；不要解释活动叫什么名字。"
NEW_BOUNDARY = (
    "槽位素材只提供意思；如果原话偏书面或像业务总结，改成宝妈会说的自然口语，"
    "不能照抄。不要解释活动叫什么名字。"
)


def patch_content(content_json: dict) -> tuple[dict, dict]:
    content = copy.deepcopy(content_json)
    atom_changes = 0
    boundary_changes = 0
    for item in content.get("items") or []:
        for slot in item.get("variation_slots") or []:
            for option in slot.get("options") or []:
                if not isinstance(option, dict):
                    continue
                if option.get("id") == "brand_feeling_008":
                    if option.get("text") != OLD_ATOM:
                        raise RuntimeError("brand_feeling_008 changed since review")
                    option["text"] = NEW_ATOM
                    atom_changes += 1
        boundaries = list(item.get("hard_boundaries") or [])
        matches = [index for index, value in enumerate(boundaries) if value == OLD_BOUNDARY]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one anti-copy boundary in rule {item.get('rule_id')}, got {len(matches)}"
            )
        boundaries[matches[0]] = NEW_BOUNDARY
        item["hard_boundaries"] = boundaries
        boundary_changes += 1
    if atom_changes != 8:
        raise RuntimeError(f"expected 8 brand atom changes, got {atom_changes}")
    if boundary_changes != 16:
        raise RuntimeError(f"expected 16 boundary changes, got {boundary_changes}")
    return content, {"atom_changes": atom_changes, "boundary_changes": boundary_changes}


def validate_content(content: dict) -> dict:
    raw = json.dumps(content, ensure_ascii=False)
    result = {
        "old_atom_hits": raw.count(OLD_ATOM),
        "new_atom_hits": raw.count(NEW_ATOM),
        "old_boundary_hits": raw.count(OLD_BOUNDARY),
        "new_boundary_hits": raw.count(NEW_BOUNDARY),
    }
    if result != {
        "old_atom_hits": 0,
        "new_atom_hits": 8,
        "old_boundary_hits": 0,
        "new_boundary_hits": 16,
    }:
        raise RuntimeError(f"candidate validation failed: {result}")
    return result


async def next_version(db) -> int:
    value = await db.scalar(
        select(func.max(AssetRegistry.version_no)).where(
            AssetRegistry.asset_type == ASSET_TYPE,
            AssetRegistry.asset_key == ASSET_KEY,
        )
    )
    return int(value or 0) + 1


async def create_candidate() -> None:
    async with async_session_factory() as db:
        production = (
            await db.execute(
                select(AssetRegistry).where(
                    AssetRegistry.id == EXPECTED_PRODUCTION_ID,
                    AssetRegistry.version_no == EXPECTED_PRODUCTION_VERSION,
                    AssetRegistry.asset_key == ASSET_KEY,
                    AssetRegistry.asset_stage == "production",
                    AssetRegistry.status == "active",
                )
            )
        ).scalar_one()
        content, changes = patch_content(production.content_json or {})
        validation = validate_content(content)
        await db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == ASSET_TYPE,
                AssetRegistry.asset_key == ASSET_KEY,
                AssetRegistry.asset_stage == "candidate",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        candidate = AssetRegistry(
            asset_type=ASSET_TYPE,
            asset_key=ASSET_KEY,
            display_name=production.display_name,
            version_no=await next_version(db),
            status="active",
            asset_stage="candidate",
            source_name="asset_registry:2005:v39:colloquial-source-and-old-stock-audit",
            source_uri=production.source_uri,
            source_hash=None,
            content_json=content,
            metadata_json={
                **(production.metadata_json or {}),
                "base_asset_id": production.id,
                "base_version_no": production.version_no,
                "brand_feeling_008_before": OLD_ATOM,
                "brand_feeling_008_after": NEW_ATOM,
                "anti_copy_boundary_before": OLD_BOUNDARY,
                "anti_copy_boundary_after": NEW_BOUNDARY,
            },
            created_by="codex-a2-reiyu-colloquial-source-fix",
        )
        db.add(candidate)
        await db.flush()
        payload = {
            "action": "candidate",
            "asset_id": candidate.id,
            "version_no": candidate.version_no,
            **changes,
            **validation,
        }
        await db.commit()
        print(json.dumps(payload, ensure_ascii=False, indent=2))


async def publish() -> None:
    async with async_session_factory() as db:
        candidate = (
            await db.execute(
                select(AssetRegistry)
                .where(
                    AssetRegistry.asset_type == ASSET_TYPE,
                    AssetRegistry.asset_key == ASSET_KEY,
                    AssetRegistry.asset_stage == "candidate",
                    AssetRegistry.status == "active",
                )
                .order_by(AssetRegistry.version_no.desc())
                .limit(1)
            )
        ).scalar_one()
        validation = validate_content(candidate.content_json or {})
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
            version_no=await next_version(db),
            status="active",
            asset_stage="production",
            source_name=f"promoted:asset_registry:{candidate.id}:v{candidate.version_no}",
            source_uri=candidate.source_uri,
            source_hash=None,
            content_json=copy.deepcopy(candidate.content_json or {}),
            metadata_json={
                **(candidate.metadata_json or {}),
                "promoted_candidate_asset_id": candidate.id,
                "promoted_candidate_version_no": candidate.version_no,
            },
            created_by="codex-a2-reiyu-colloquial-source-publish",
        )
        db.add(production)
        await db.flush()
        payload = {
            "action": "publish",
            "asset_id": production.id,
            "version_no": production.version_no,
            **validation,
        }
        await db.commit()
        print(json.dumps(payload, ensure_ascii=False, indent=2))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("candidate", "publish"))
    args = parser.parse_args()
    if args.action == "candidate":
        await create_candidate()
    else:
        await publish()


if __name__ == "__main__":
    asyncio.run(main())
