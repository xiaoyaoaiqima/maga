"""Delivered comment ledger for exact reuse prevention."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import CommentDeliveryLedger


DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY = "a2_sentiment_comment_activity"
DEFAULT_COMMENT_DELIVERY_LEDGER_SOURCE_TYPE = "local_export"


@dataclass(frozen=True)
class CommentDeliveryLedgerUpsertResult:
    asset_key: str
    imported_rows: int
    skipped_existing_rows: int
    skipped_input_duplicate_rows: int
    total_input_rows: int
    items: list[CommentDeliveryLedger]


class CommentDeliveryLedgerService:
    """Read and write delivered comments using one exact-match normalization."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def normalize_comment(text: str | None) -> str:
        return str(text or "").strip()

    @classmethod
    def hash_comment(cls, normalized: str) -> str:
        return hashlib.sha256(cls.normalize_comment(normalized).encode("utf-8")).hexdigest()

    async def exists_many(
        self,
        *,
        asset_key: str | None,
        comments: list[str],
    ) -> dict[str, CommentDeliveryLedger]:
        normalized_comments = [self.normalize_comment(comment) for comment in comments]
        hashes = [self.hash_comment(comment) for comment in normalized_comments if comment]
        if not hashes:
            return {}
        result = await self.db.execute(
            select(CommentDeliveryLedger).where(
                CommentDeliveryLedger.asset_key == self._asset_key(asset_key),
                CommentDeliveryLedger.comment_hash.in_(set(hashes)),
            )
        )
        return {item.normalized_comment: item for item in result.scalars().all()}

    async def list_entries(
        self,
        *,
        asset_key: str | None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[CommentDeliveryLedger], int]:
        conditions = [CommentDeliveryLedger.asset_key == self._asset_key(asset_key)]
        query_text = self.normalize_comment(q)
        if query_text:
            conditions.append(CommentDeliveryLedger.comment_text.contains(query_text))
        total_result = await self.db.execute(
            select(func.count()).select_from(CommentDeliveryLedger).where(*conditions)
        )
        result = await self.db.execute(
            select(CommentDeliveryLedger)
            .where(*conditions)
            .order_by(CommentDeliveryLedger.delivered_at.desc(), CommentDeliveryLedger.id.desc())
            .offset(max(offset, 0))
            .limit(max(1, min(limit, 500)))
        )
        return list(result.scalars().all()), int(total_result.scalar() or 0)

    async def upsert_many(
        self,
        *,
        asset_key: str | None,
        entries: list[dict[str, Any]],
        source_type: str,
        source_uri: str | None = None,
        delivered_by: str | None = None,
    ) -> CommentDeliveryLedgerUpsertResult:
        normalized_asset_key = self._asset_key(asset_key)
        prepared: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        skipped_input_duplicate_rows = 0
        for entry in entries:
            comment_text = str(entry.get("comment_text") or entry.get("comment") or "").strip()
            normalized = self.normalize_comment(comment_text)
            if not normalized:
                continue
            comment_hash = self.hash_comment(normalized)
            if comment_hash in seen_hashes:
                skipped_input_duplicate_rows += 1
                continue
            seen_hashes.add(comment_hash)
            prepared.append(
                {
                    "category": str(entry.get("category") or "").strip() or None,
                    "comment_text": comment_text,
                    "normalized_comment": normalized,
                    "comment_hash": comment_hash,
                    "source_uri": str(entry.get("source_uri") or source_uri or "").strip() or None,
                    "batch_id": _optional_int(entry.get("batch_id")),
                    "item_id": _optional_int(entry.get("item_id")),
                    "metadata_json": entry.get("metadata_json") if isinstance(entry.get("metadata_json"), dict) else None,
                }
            )
        if not prepared:
            return CommentDeliveryLedgerUpsertResult(
                asset_key=normalized_asset_key,
                imported_rows=0,
                skipped_existing_rows=0,
                skipped_input_duplicate_rows=skipped_input_duplicate_rows,
                total_input_rows=len(entries),
                items=[],
            )

        existing = await self.exists_many(
            asset_key=normalized_asset_key,
            comments=[entry["normalized_comment"] for entry in prepared],
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        created_items: list[CommentDeliveryLedger] = []
        skipped_existing_rows = 0
        for entry in prepared:
            if entry["normalized_comment"] in existing:
                skipped_existing_rows += 1
                continue
            item = CommentDeliveryLedger(
                asset_key=normalized_asset_key,
                category=entry["category"],
                comment_text=entry["comment_text"],
                normalized_comment=entry["normalized_comment"],
                comment_hash=entry["comment_hash"],
                source_type=str(source_type or DEFAULT_COMMENT_DELIVERY_LEDGER_SOURCE_TYPE).strip()
                or DEFAULT_COMMENT_DELIVERY_LEDGER_SOURCE_TYPE,
                source_uri=entry["source_uri"],
                batch_id=entry["batch_id"],
                item_id=entry["item_id"],
                delivered_by=delivered_by,
                delivered_at=now,
                metadata_json=entry["metadata_json"],
            )
            self.db.add(item)
            created_items.append(item)
        await self.db.flush()
        return CommentDeliveryLedgerUpsertResult(
            asset_key=normalized_asset_key,
            imported_rows=len(created_items),
            skipped_existing_rows=skipped_existing_rows,
            skipped_input_duplicate_rows=skipped_input_duplicate_rows,
            total_input_rows=len(entries),
            items=created_items,
        )

    @staticmethod
    def _asset_key(asset_key: str | None) -> str:
        return str(asset_key or DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY).strip() or DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY


def ledger_entry_to_dict(entry: CommentDeliveryLedger) -> dict[str, Any]:
    return {
        "id": entry.id,
        "asset_key": entry.asset_key,
        "category": entry.category or "",
        "comment_text": entry.comment_text,
        "normalized_comment": entry.normalized_comment,
        "comment_hash": entry.comment_hash,
        "source_type": entry.source_type,
        "source_uri": entry.source_uri or "",
        "batch_id": entry.batch_id,
        "item_id": entry.item_id,
        "delivered_by": entry.delivered_by or "",
        "delivered_at": _format_datetime(entry.delivered_at),
    }


def _optional_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_datetime(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""
