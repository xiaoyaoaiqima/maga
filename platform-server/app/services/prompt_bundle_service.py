"""Build immutable prompt bundle snapshots for executor generation inputs."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetRegistry
from app.models.prompt_optimizer import PromptAsset, PromptVersion
from app.services.asset_import_service import WORKER_STATIC_ASSET_SOURCE_NAME


PROMPT_BUNDLE_SCHEMA_VERSION = "1"
XHS_WRITER_PROMPT_PREFIX = "xhs_writer."


class PromptBundleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_xhs_writer_prompt_bundle_snapshot(self) -> dict[str, Any]:
        """Build a self-contained snapshot of MAGA-managed xhs-writer prompts.

        The bundle carries the current prompt contents and static expert corpus
        assets used by maga-worker. Executors can later consume this snapshot
        without depending on local workspace files or additional MAGA reads.
        """
        prompts = await self._current_prompt_versions()
        assets = await self._active_static_assets()
        bundle = {
            "schema_version": PROMPT_BUNDLE_SCHEMA_VERSION,
            "source": "maga_prompt_bundle",
            "prompt_prefix": XHS_WRITER_PROMPT_PREFIX,
            "prompts": {
                prompt.name: {
                    "prompt_id": prompt.id,
                    "version_id": version.id,
                    "version_no": version.version_no,
                    "prompt_type": prompt.prompt_type,
                    "tags": prompt.tags or [],
                    "content": version.content,
                }
                for prompt, version in prompts
            },
            "assets": {
                f"{asset.asset_type}:{asset.asset_key}": {
                    "asset_id": asset.id,
                    "asset_type": asset.asset_type,
                    "asset_key": asset.asset_key,
                    "version_no": asset.version_no,
                    "asset_stage": asset.asset_stage,
                    "source_hash": asset.source_hash,
                    "content_json": asset.content_json,
                }
                for asset in assets
            },
        }
        bundle["summary"] = {
            "prompt_count": len(bundle["prompts"]),
            "asset_count": len(bundle["assets"]),
            "bundle_hash": _bundle_hash(bundle),
        }
        return bundle

    async def _current_prompt_versions(self) -> list[tuple[PromptAsset, PromptVersion]]:
        result = await self.db.execute(
            select(PromptAsset, PromptVersion)
            .join(PromptVersion, PromptVersion.id == PromptAsset.current_version_id)
            .where(
                PromptAsset.is_deleted == 0,
                PromptAsset.name.like(f"{XHS_WRITER_PROMPT_PREFIX}%"),
            )
            .order_by(PromptAsset.name)
        )
        return list(result.all())

    async def _active_static_assets(self) -> list[AssetRegistry]:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.source_name == WORKER_STATIC_ASSET_SOURCE_NAME,
                AssetRegistry.status == "active",
            )
            .order_by(AssetRegistry.asset_type, AssetRegistry.asset_key, AssetRegistry.version_no.desc())
        )
        return list(result.scalars().all())


def _bundle_hash(bundle: dict[str, Any]) -> str:
    hash_input = {
        "schema_version": bundle.get("schema_version"),
        "prompts": {
            name: {
                "prompt_id": item.get("prompt_id"),
                "version_id": item.get("version_id"),
                "version_no": item.get("version_no"),
                "content_sha256": hashlib.sha256(str(item.get("content") or "").encode("utf-8")).hexdigest(),
            }
            for name, item in sorted((bundle.get("prompts") or {}).items())
        },
        "assets": {
            key: {
                "asset_id": item.get("asset_id"),
                "version_no": item.get("version_no"),
                "source_hash": item.get("source_hash"),
            }
            for key, item in sorted((bundle.get("assets") or {}).items())
        },
    }
    data = json.dumps(hash_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
