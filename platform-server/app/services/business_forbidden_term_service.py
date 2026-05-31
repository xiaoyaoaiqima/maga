"""Business-owned forbidden terms managed from operator feedback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetRegistry

BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE = "business_forbidden_terms"
DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY = "default_business_forbidden_terms"
BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class BusinessForbiddenTermUpdateResult:
    asset: AssetRegistry | None
    asset_key: str
    added_terms: list[str]
    existing_terms: list[str]
    all_terms: list[str]


class BusinessForbiddenTermService:
    """Persist and read deterministic business forbidden-word lists."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_terms(self, *, asset_key: str | None = None, include_default: bool = True) -> list[str]:
        keys = _asset_keys_for_lookup(asset_key, include_default=include_default)
        terms: list[str] = []
        for key in keys:
            asset = await self._latest_asset(key)
            if asset is None:
                continue
            for term in _terms_from_content(asset.content_json or {}):
                if term not in terms:
                    terms.append(term)
        return terms

    async def add_terms(
        self,
        *,
        asset_key: str | None,
        terms: list[str],
        created_by: str | None,
        source_context: dict[str, Any] | None = None,
    ) -> BusinessForbiddenTermUpdateResult:
        normalized_asset_key = _normalize_asset_key(asset_key)
        normalized_terms = normalize_business_forbidden_terms(terms)
        if not normalized_terms:
            raise ValueError("business forbidden terms cannot be empty")

        current = await self._latest_asset(normalized_asset_key)
        entries = _term_entries_from_content(current.content_json if current else {})
        existing_terms = _terms_from_entries(entries)
        added_terms = [term for term in normalized_terms if term not in existing_terms]
        if not added_terms:
            return BusinessForbiddenTermUpdateResult(
                asset=current,
                asset_key=normalized_asset_key,
                added_terms=[],
                existing_terms=existing_terms,
                all_terms=existing_terms,
            )

        next_entries = [
            *entries,
            *[
                {
                    "term": term,
                    "enabled": True,
                    "source": "content_batch_feedback",
                    "created_by": created_by or "content_batch_workbench",
                    "note": "运营反馈不希望出现",
                    **({"source_context": source_context} if source_context else {}),
                }
                for term in added_terms
            ],
        ]
        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == normalized_asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        content_json = {
            "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
            "asset_type": BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
            "terms": next_entries,
        }
        asset = AssetRegistry(
            asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
            asset_key=normalized_asset_key,
            display_name=f"{normalized_asset_key} 业务违禁词",
            version_no=await self._next_asset_version(normalized_asset_key),
            status="active",
            asset_stage="production",
            source_name="content_batch_feedback",
            content_json=content_json,
            metadata_json={
                "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
                "term_count": len(_terms_from_entries(next_entries)),
                "added_term_count": len(added_terms),
            },
            created_by=created_by or "content_batch_workbench",
        )
        self.db.add(asset)
        await self.db.flush()
        return BusinessForbiddenTermUpdateResult(
            asset=asset,
            asset_key=normalized_asset_key,
            added_terms=added_terms,
            existing_terms=existing_terms,
            all_terms=_terms_from_entries(next_entries),
        )

    async def _latest_asset(self, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _next_asset_version(self, asset_key: str) -> int:
        result = await self.db.execute(
            select(AssetRegistry.version_no)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
            )
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1


def normalize_business_forbidden_terms(terms: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in terms or []:
        value = str(raw or "").strip()
        if not value:
            continue
        value = " ".join(value.split())
        if len(value) > 100:
            raise ValueError("business forbidden term is too long")
        if value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_asset_key(asset_key: str | None) -> str:
    return (asset_key or DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY).strip() or DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY


def _asset_keys_for_lookup(asset_key: str | None, *, include_default: bool) -> list[str]:
    keys: list[str] = []
    normalized = (asset_key or "").strip()
    if normalized:
        keys.append(normalized)
    if include_default and DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY not in keys:
        keys.append(DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY)
    return keys


def _terms_from_content(content_json: dict[str, Any]) -> list[str]:
    return _terms_from_entries(_term_entries_from_content(content_json))


def _term_entries_from_content(content_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw_terms = (content_json or {}).get("terms")
    if not isinstance(raw_terms, list):
        raw_terms = (content_json or {}).get("items")
    entries: list[dict[str, Any]] = []
    for item in raw_terms or []:
        if isinstance(item, str):
            entries.append({"term": item, "enabled": True})
        elif isinstance(item, dict):
            entries.append(item)
    return entries


def _terms_from_entries(entries: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for entry in entries:
        if entry.get("enabled") is False:
            continue
        value = str(entry.get("term") or entry.get("word") or entry.get("name") or "").strip()
        if value and value not in terms:
            terms.append(value)
    return terms
