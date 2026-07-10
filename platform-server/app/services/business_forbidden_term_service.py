"""Business-owned forbidden terms managed from operator feedback."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetRegistry

BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE = "business_forbidden_terms"
DEFAULT_BUSINESS_FORBIDDEN_TERMS_ASSET_KEY = "default_business_forbidden_terms"
BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION = "1"
A2_SENTIMENT_COMMENT_ASSET_KEY = "a2_sentiment_comment_activity"
A2_SENTIMENT_COMMENT_SEED_TERMS = (
    {
        "term": "小程序",
        "reason": "小红书不能出现微信生态的词",
        "enabled": True,
        "replacement": "",
        "source": "operator_rule",
        "created_by": "ops",
    },
    {
        "term": "0.03",
        "reason": "业务新要求：暂不露出蜡样/蜡毒检测的明确数值",
        "enabled": True,
        "replacement": "",
        "source": "operator_rule",
        "created_by": "ops",
    },
    {
        "term": "60+",
        "reason": "业务新要求：暂不露出检测报告/检测项目的明确数量",
        "enabled": True,
        "replacement": "",
        "source": "operator_rule",
        "created_by": "ops",
    },
    {
        "term": "60多项",
        "reason": "业务新要求：暂不露出检测报告/检测项目的明确数量",
        "enabled": True,
        "replacement": "",
        "source": "operator_rule",
        "created_by": "ops",
    },
)
A2_SENTIMENT_COMMENT_SEED_TERM = A2_SENTIMENT_COMMENT_SEED_TERMS[0]


@dataclass(frozen=True)
class BusinessForbiddenTermUpdateResult:
    asset: AssetRegistry | None
    asset_key: str
    added_terms: list[str]
    updated_terms: list[str]
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
            try:
                asset = await self._latest_asset(key)
            except SQLAlchemyError:
                continue
            if asset is None:
                continue
            for term in _terms_from_content(asset.content_json or {}):
                if term not in terms:
                    terms.append(term)
        return terms

    async def list_entries(
        self,
        *,
        asset_key: str | None = None,
        include_default: bool = True,
    ) -> list[dict[str, Any]]:
        keys = _asset_keys_for_lookup(asset_key, include_default=include_default)
        entries: list[dict[str, Any]] = []
        seen_terms: set[str] = set()
        for key in keys:
            try:
                asset = await self._latest_asset(key)
            except SQLAlchemyError:
                continue
            if asset is None:
                continue
            for entry in _term_entries_from_content(asset.content_json or {}):
                normalized = _normalized_entry(entry, fallback_asset_key=key)
                term = _term_from_entry(normalized)
                if not term or term in seen_terms:
                    continue
                seen_terms.add(term)
                entries.append(normalized)
        return entries

    async def list_replacements(self, *, asset_key: str | None = None, include_default: bool = True) -> dict[str, str]:
        keys = _asset_keys_for_lookup(asset_key, include_default=include_default)
        replacements: dict[str, str] = {}
        for key in keys:
            try:
                asset = await self._latest_asset(key)
            except SQLAlchemyError:
                continue
            if asset is None:
                continue
            for entry in _term_entries_from_content(asset.content_json or {}):
                if entry.get("enabled") is False:
                    continue
                term = _term_from_entry(entry)
                replacement = _replacement_from_entry(entry)
                if term and replacement and term not in replacements:
                    replacements[term] = replacement
        return replacements

    async def add_terms(
        self,
        *,
        asset_key: str | None,
        terms: list[str],
        created_by: str | None,
        source_context: dict[str, Any] | None = None,
    ) -> BusinessForbiddenTermUpdateResult:
        entries = [
            {
                "term": term,
                "source": "content_batch_feedback",
                "reason": "运营反馈不希望出现",
            }
            for term in normalize_business_forbidden_terms(terms)
        ]
        return await self.upsert_entries(
            asset_key=asset_key,
            entries=entries,
            created_by=created_by or "content_batch_workbench",
            source_context=source_context,
        )

    async def upsert_entries(
        self,
        *,
        asset_key: str | None,
        entries: list[dict[str, Any]],
        created_by: str | None,
        source_context: dict[str, Any] | None = None,
    ) -> BusinessForbiddenTermUpdateResult:
        normalized_asset_key = _normalize_asset_key(asset_key)
        normalized_new_entries = normalize_business_forbidden_term_entries(entries)
        if not normalized_new_entries:
            raise ValueError("business forbidden terms cannot be empty")

        current = await self._latest_asset(normalized_asset_key)
        entries = _term_entries_from_content(current.content_json if current else {})
        existing_terms = _terms_from_entries(entries)
        next_entries = [_normalized_entry(entry, fallback_asset_key=normalized_asset_key) for entry in entries]
        added_terms: list[str] = []
        updated_terms: list[str] = []
        now = _now_iso()

        for new_entry in normalized_new_entries:
            term = _term_from_entry(new_entry)
            match_index = next(
                (idx for idx, entry in enumerate(next_entries) if _term_from_entry(entry) == term),
                None,
            )
            entry_patch = {
                "term": term,
                "enabled": bool(new_entry.get("enabled", True)),
                "source": str(new_entry.get("source") or "operator_rule").strip() or "operator_rule",
                "created_by": created_by or str(new_entry.get("created_by") or "content_batch_workbench"),
                "reason": str(new_entry.get("reason") or new_entry.get("note") or "运营反馈不希望出现").strip(),
                "replacement": str(new_entry.get("replacement") or "").strip(),
                **({"source_context": source_context} if source_context else {}),
            }
            if match_index is None:
                next_entries.append(
                    {
                        **entry_patch,
                        "created_at": str(new_entry.get("created_at") or now),
                    }
                )
                added_terms.append(term)
            else:
                existing = dict(next_entries[match_index])
                update_patch = {
                    key: value
                    for key, value in entry_patch.items()
                    if key != "created_by" and value not in (None, "")
                }
                next_entries[match_index] = {
                    **existing,
                    **update_patch,
                    "enabled": entry_patch["enabled"],
                    "created_at": existing.get("created_at") or now,
                    "updated_at": now,
                    "updated_by": created_by or "content_batch_workbench",
                }
                updated_terms.append(term)

        if not added_terms and not updated_terms:
            return BusinessForbiddenTermUpdateResult(
                asset=current,
                asset_key=normalized_asset_key,
                added_terms=[],
                updated_terms=[],
                existing_terms=existing_terms,
                all_terms=existing_terms,
            )

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
                "updated_term_count": len(updated_terms),
            },
            created_by=created_by or "content_batch_workbench",
        )
        self.db.add(asset)
        await self.db.flush()
        return BusinessForbiddenTermUpdateResult(
            asset=asset,
            asset_key=normalized_asset_key,
            added_terms=added_terms,
            updated_terms=updated_terms,
            existing_terms=existing_terms,
            all_terms=_terms_from_entries(next_entries),
        )

    async def set_enabled(
        self,
        *,
        asset_key: str | None,
        term: str,
        enabled: bool,
        created_by: str | None,
    ) -> BusinessForbiddenTermUpdateResult:
        normalized_asset_key = _normalize_asset_key(asset_key)
        normalized_terms = normalize_business_forbidden_terms([term])
        if not normalized_terms:
            raise ValueError("business forbidden term cannot be empty")
        current = await self._latest_asset(normalized_asset_key)
        if current is None:
            raise ValueError("business forbidden terms asset not found")
        entries = [
            _normalized_entry(entry, fallback_asset_key=normalized_asset_key)
            for entry in _term_entries_from_content(current.content_json)
        ]
        existing_terms = _terms_from_entries(entries)
        target = normalized_terms[0]
        updated_terms: list[str] = []
        now = _now_iso()
        for entry in entries:
            if _term_from_entry(entry) == target:
                entry["enabled"] = enabled
                entry["updated_at"] = now
                entry["updated_by"] = created_by or "content_batch_workbench"
                updated_terms.append(target)
                break
        if not updated_terms:
            raise ValueError("business forbidden term not found")
        asset = await self._replace_asset(
            normalized_asset_key,
            entries,
            created_by=created_by or "content_batch_workbench",
            source_name="business_forbidden_terms_status",
            added_term_count=0,
            updated_term_count=1,
        )
        return BusinessForbiddenTermUpdateResult(
            asset=asset,
            asset_key=normalized_asset_key,
            added_terms=[],
            updated_terms=updated_terms,
            existing_terms=existing_terms,
            all_terms=_terms_from_entries(entries),
        )

    async def _replace_asset(
        self,
        asset_key: str,
        entries: list[dict[str, Any]],
        *,
        created_by: str,
        source_name: str,
        added_term_count: int,
        updated_term_count: int,
    ) -> AssetRegistry:
        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        asset = AssetRegistry(
            asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
            asset_key=asset_key,
            display_name=f"{asset_key} 业务违禁词",
            version_no=await self._next_asset_version(asset_key),
            status="active",
            asset_stage="production",
            source_name=source_name,
            content_json={
                "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
                "asset_type": BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                "terms": entries,
            },
            metadata_json={
                "schema_version": BUSINESS_FORBIDDEN_TERMS_SCHEMA_VERSION,
                "term_count": len(_terms_from_entries(entries)),
                "added_term_count": added_term_count,
                "updated_term_count": updated_term_count,
            },
            created_by=created_by,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

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


def normalize_business_forbidden_term_entries(entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_terms: set[str] = set()
    for raw in entries or []:
        if not isinstance(raw, dict):
            continue
        terms = normalize_business_forbidden_terms([_term_from_entry(raw)])
        if not terms:
            continue
        term = terms[0]
        if term in seen_terms:
            continue
        reason = str(raw.get("reason") or raw.get("note") or "").strip()
        if len(reason) > 1000:
            raise ValueError("business forbidden term reason is too long")
        replacement = str(raw.get("replacement") or raw.get("rewrite_to") or raw.get("replace_with") or "").strip()
        if len(replacement) > 100:
            raise ValueError("business forbidden term replacement is too long")
        normalized.append(
            {
                **raw,
                "term": term,
                "reason": reason,
                "replacement": replacement,
                "enabled": raw.get("enabled") is not False,
            }
        )
        seen_terms.add(term)
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


def _normalized_entry(entry: dict[str, Any], *, fallback_asset_key: str | None = None) -> dict[str, Any]:
    term = _term_from_entry(entry)
    return {
        "term": term,
        "reason": str(entry.get("reason") or entry.get("note") or "").strip(),
        "enabled": entry.get("enabled") is not False,
        "created_at": str(entry.get("created_at") or ""),
        "created_by": str(entry.get("created_by") or "").strip(),
        "updated_at": str(entry.get("updated_at") or ""),
        "updated_by": str(entry.get("updated_by") or "").strip(),
        "replacement": _replacement_from_entry(entry),
        "source": str(entry.get("source") or "").strip(),
        "asset_key": str(entry.get("asset_key") or fallback_asset_key or "").strip(),
        **({"source_context": entry.get("source_context")} if entry.get("source_context") is not None else {}),
    }


def _terms_from_entries(entries: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for entry in entries:
        if entry.get("enabled") is False:
            continue
        value = _term_from_entry(entry)
        if value and value not in terms:
            terms.append(value)
    return terms


def _term_from_entry(entry: dict[str, Any]) -> str:
    return str(entry.get("term") or entry.get("word") or entry.get("name") or "").strip()


def _replacement_from_entry(entry: dict[str, Any]) -> str:
    return str(
        entry.get("replacement")
        or entry.get("rewrite_to")
        or entry.get("replace_with")
        or entry.get("suggested_replacement")
        or ""
    ).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
