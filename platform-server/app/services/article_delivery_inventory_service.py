"""Persistent article inventory and delivery ledger for repeatable CSV delivery."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

A2_REIYU_ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
WANGYUE_ASSET_KEY = "wangyue_v3_core_storyline_article_rules"
DEFAULT_A2_REIYU_INVENTORY_PATH = (
    Path(__file__).resolve().parents[3]
    / "local_data/a2_reiyu_delivery/article_inventory.sqlite3"
)
DEFAULT_ARTICLE_INVENTORY_PATH = DEFAULT_A2_REIYU_INVENTORY_PATH

_TITLE_COLUMNS = ("标题", "title")
_BODY_COLUMNS = ("正文", "body", "content")
_CONTENT_ID_COLUMNS = ("content_id", "Content ID", "ID", "id")
_CATEGORY_COLUMNS = ("分类", "category")
_CONTEXT_COLUMNS = ("上下文变量(context_list)", "context_list")


@dataclass(frozen=True)
class InventoryImportResult:
    input_rows: int
    accepted_rows: int
    inserted_articles: int
    duplicate_articles: int
    skipped_rows: int


@dataclass(frozen=True)
class DeliveryExportResult:
    delivery_code: str
    output_path: str
    total_count: int
    can_collection_count: int
    other_count: int
    committed: bool


@dataclass(frozen=True)
class InventoryAuditApplyResult:
    input_rows: int
    matched_articles: int
    usable_articles: int
    withheld_articles: int


class ArticleDeliveryInventoryService:
    """SQLite-backed content registry with source provenance and delivery events."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_ARTICLE_INVENTORY_PATH,
        *,
        asset_key: str = A2_REIYU_ASSET_KEY,
    ):
        self.db_path = Path(db_path).expanduser().resolve()
        self.asset_key = str(asset_key).strip()
        if not self.asset_key:
            raise ValueError("asset_key must not be empty")

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS article_inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_key TEXT NOT NULL,
                    content_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    body_hash TEXT NOT NULL,
                    category_group TEXT NOT NULL,
                    category TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    usable INTEGER NOT NULL DEFAULT 1,
                    delivered_count INTEGER NOT NULL DEFAULT 0,
                    first_delivered_at TEXT,
                    last_delivered_at TEXT,
                    create_time TEXT NOT NULL,
                    update_time TEXT NOT NULL,
                    UNIQUE(asset_key, body_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_article_inventory_delivery
                    ON article_inventory(asset_key, usable, delivered_count, category_group);

                CREATE TABLE IF NOT EXISTS article_inventory_source (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    source_row INTEGER NOT NULL,
                    source_content_id TEXT,
                    review_status TEXT NOT NULL,
                    metadata_json TEXT,
                    create_time TEXT NOT NULL,
                    UNIQUE(article_id, source_uri, source_row),
                    FOREIGN KEY(article_id) REFERENCES article_inventory(id)
                );

                CREATE TABLE IF NOT EXISTS article_delivery_batch (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivery_code TEXT NOT NULL UNIQUE,
                    asset_key TEXT NOT NULL,
                    target_count INTEGER NOT NULL,
                    can_collection_count INTEGER NOT NULL,
                    other_count INTEGER NOT NULL,
                    output_uri TEXT,
                    status TEXT NOT NULL,
                    create_time TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS article_delivery_batch_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivery_batch_id INTEGER NOT NULL,
                    article_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    UNIQUE(delivery_batch_id, article_id),
                    FOREIGN KEY(delivery_batch_id) REFERENCES article_delivery_batch(id),
                    FOREIGN KEY(article_id) REFERENCES article_inventory(id)
                );
                """
            )
            self._repair_duplicate_content_ids(conn)
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_article_inventory_asset_content_id
                ON article_inventory(asset_key, content_id)
                """
            )

    def import_csv(
        self,
        input_path: Path | str,
        *,
        source_type: str,
        default_review_status: str,
        allowed_review_tiers: Iterable[str] | None = None,
        mark_delivered_code: str | None = None,
        existing_only: bool = False,
        source_uri_override: str | None = None,
        source_row_column: str | None = None,
    ) -> InventoryImportResult:
        self.initialize()
        source_path = Path(input_path).expanduser().resolve()
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

        allowed_tiers = set(allowed_review_tiers or ())
        accepted: list[tuple[int, Mapping[str, Any], str, str, str, str, str, str]] = []
        skipped = 0
        for csv_row, row in enumerate(rows, start=2):
            source_row = _source_row(row, source_row_column, csv_row)
            title = _first_value(row, _TITLE_COLUMNS).strip()
            body = _first_value(row, _BODY_COLUMNS).strip()
            if not title or not body:
                skipped += 1
                continue
            row_tier = str(row.get("审核档位") or "").strip()
            if allowed_tiers and row_tier not in allowed_tiers:
                skipped += 1
                continue
            review_status = row_tier or default_review_status
            category_group, category = self._classify_article(row)
            body_hash = hash_article_body(body)
            content_id = _first_value(row, _CONTENT_ID_COLUMNS).strip()
            if not content_id:
                content_id = f"{self._auto_content_id_prefix()}-{body_hash[:16]}"
            accepted.append(
                (
                    source_row,
                    row,
                    title,
                    body,
                    content_id,
                    review_status,
                    category_group,
                    category,
                )
            )

        inserted = 0
        duplicates = 0
        article_ids: list[int] = []
        now = _now()
        with self._connect() as conn:
            for (
                source_row,
                row,
                title,
                body,
                content_id,
                review_status,
                category_group,
                category,
            ) in accepted:
                body_hash = hash_article_body(body)
                existing = conn.execute(
                    """
                    SELECT id, content_id, category_group, review_status
                    FROM article_inventory
                    WHERE asset_key = ? AND body_hash = ?
                    """,
                    (self.asset_key, body_hash),
                ).fetchone()
                if existing is None:
                    if existing_only:
                        skipped += 1
                        continue
                    content_id = self._unique_content_id(conn, content_id, body_hash)
                    cursor = conn.execute(
                        """
                        INSERT INTO article_inventory (
                            asset_key, content_id, title, body, body_hash, category_group,
                            category, review_status, usable, create_time, update_time
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            self.asset_key,
                            content_id,
                            title,
                            body,
                            body_hash,
                            category_group,
                            category,
                            review_status,
                            now,
                            now,
                        ),
                    )
                    article_id = int(cursor.lastrowid)
                    inserted += 1
                else:
                    article_id = int(existing["id"])
                    duplicates += 1
                    auto_prefix = f"{self._auto_content_id_prefix()}-"
                    if str(existing["content_id"]).startswith(
                        auto_prefix
                    ) and not content_id.startswith(auto_prefix):
                        content_id = self._unique_content_id(
                            conn,
                            content_id,
                            body_hash,
                            exclude_article_id=article_id,
                        )
                        conn.execute(
                            "UPDATE article_inventory SET content_id = ?, update_time = ? WHERE id = ?",
                            (content_id, now, article_id),
                        )
                    if (
                        category_group == "can_collection"
                        and existing["category_group"] != category_group
                    ):
                        conn.execute(
                            """
                            UPDATE article_inventory
                            SET category_group = ?, category = ?, update_time = ?
                            WHERE id = ?
                            """,
                            (category_group, category, now, article_id),
                        )
                    if _is_approved_review_status(review_status) and not str(
                        existing["review_status"]
                    ).startswith("current_audit:"):
                        conn.execute(
                            """
                            UPDATE article_inventory
                            SET usable = 1, review_status = ?, update_time = ?
                            WHERE id = ?
                            """,
                            (review_status, now, article_id),
                        )
                article_ids.append(article_id)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO article_inventory_source (
                        article_id, source_type, source_uri, source_row, source_content_id,
                        review_status, metadata_json, create_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article_id,
                        source_type,
                        source_uri_override or str(source_path),
                        source_row,
                        content_id,
                        review_status,
                        json.dumps(_source_metadata(row), ensure_ascii=False),
                        now,
                    ),
                )
            if mark_delivered_code and article_ids:
                self._record_delivery(
                    conn,
                    delivery_code=mark_delivered_code,
                    article_ids=list(dict.fromkeys(article_ids)),
                    output_uri=source_uri_override or str(source_path),
                    status="historical_delivered",
                )

        return InventoryImportResult(
            input_rows=len(rows),
            accepted_rows=len(accepted),
            inserted_articles=inserted,
            duplicate_articles=duplicates,
            skipped_rows=skipped,
        )

    def export_delivery(
        self,
        output_path: Path | str,
        *,
        count: int,
        can_ratio: float | None,
        delivery_code: str,
        seed: int = 20260723,
        commit: bool = False,
        allow_reuse: bool = False,
    ) -> DeliveryExportResult:
        if count <= 0:
            raise ValueError("count must be positive")
        if can_ratio is not None and not 0 <= can_ratio <= 1:
            raise ValueError("can_ratio must be between 0 and 1")
        self.initialize()
        with self._connect() as conn:
            if self.asset_key == A2_REIYU_ASSET_KEY:
                effective_can_ratio = 0.7 if can_ratio is None else can_ratio
                can_count = round(count * effective_can_ratio)
                other_count = count - can_count
                selected_can = self._select_articles(
                    conn,
                    category_group="can_collection",
                    count=can_count,
                    seed=seed,
                    allow_reuse=allow_reuse,
                )
                selected_other = self._select_articles(
                    conn,
                    category_group="other",
                    count=other_count,
                    seed=seed + 1,
                    allow_reuse=allow_reuse,
                )
                if len(selected_can) != can_count or len(selected_other) != other_count:
                    raise ValueError(
                        "insufficient inventory: "
                        f"need can={can_count}, other={other_count}; "
                        f"available can={len(selected_can)}, other={len(selected_other)}"
                    )
                selected = [*selected_can, *selected_other]
                random.Random(seed + 2).shuffle(selected)
            else:
                can_count = 0
                other_count = count
                selected = self._select_articles(
                    conn,
                    category_group=None,
                    count=count,
                    seed=seed,
                    allow_reuse=allow_reuse,
                )
                if len(selected) != count:
                    raise ValueError(
                        f"insufficient inventory: need={count}; available={len(selected)}"
                    )
            target = Path(output_path).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8-sig", newline="") as handle:
                fieldnames = (
                    ["content_id", "标题", "正文", "分类"]
                    if self.asset_key == A2_REIYU_ASSET_KEY
                    else ["标题", "正文", "上下文变量(context_list)"]
                )
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row in selected:
                    if self.asset_key == A2_REIYU_ASSET_KEY:
                        writer.writerow(
                            {
                                "content_id": row["content_id"],
                                "标题": row["title"],
                                "正文": row["body"],
                                "分类": row["category"],
                            }
                        )
                    else:
                        writer.writerow(
                            {
                                "标题": row["title"],
                                "正文": row["body"],
                                "上下文变量(context_list)": self._article_context_list(
                                    conn,
                                    int(row["id"]),
                                ),
                            }
                        )
            if commit:
                self._record_delivery(
                    conn,
                    delivery_code=delivery_code,
                    article_ids=[int(row["id"]) for row in selected],
                    output_uri=str(target),
                    status="delivered",
                )
        return DeliveryExportResult(
            delivery_code=delivery_code,
            output_path=str(target),
            total_count=count,
            can_collection_count=can_count,
            other_count=other_count,
            committed=commit,
        )

    def export_inventory_snapshot(
        self,
        output_path: Path | str,
        *,
        never_delivered_only: bool = False,
    ) -> int:
        self.initialize()
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            delivery_clause = " AND delivered_count = 0" if never_delivered_only else ""
            rows = conn.execute(
                f"""
                SELECT content_id, title, body, category, review_status, delivered_count
                FROM article_inventory
                WHERE asset_key = ? AND usable = 1
                {delivery_clause}
                ORDER BY id
                """,
                (self.asset_key,),
            ).fetchall()
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "content_id",
                    "标题",
                    "正文",
                    "分类",
                    "审核状态",
                    "已交付次数",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "content_id": row["content_id"],
                        "标题": row["title"],
                        "正文": row["body"],
                        "分类": row["category"],
                        "审核状态": row["review_status"],
                        "已交付次数": row["delivered_count"],
                    }
                )
        return len(rows)

    def export_unseen_csv(self, input_path: Path | str, output_path: Path | str) -> int:
        """Write only bodies that are not already present in the inventory."""
        self.initialize()
        source = Path(input_path).expanduser().resolve()
        target = Path(output_path).expanduser().resolve()
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        with self._connect() as conn:
            known_hashes = {
                str(row["body_hash"])
                for row in conn.execute(
                    "SELECT body_hash FROM article_inventory WHERE asset_key = ?",
                    (self.asset_key,),
                )
            }
        unseen = [
            row
            for row in rows
            if hash_article_body(_first_value(row, _BODY_COLUMNS)) not in known_hashes
        ]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unseen)
        return len(unseen)

    def apply_audit_csv(
        self,
        input_path: Path | str,
        *,
        usable_tiers: Iterable[str] = ("direct_pool",),
    ) -> InventoryAuditApplyResult:
        """Apply current audit decisions to matching inventory bodies."""
        self.initialize()
        source = Path(input_path).expanduser().resolve()
        allowed = set(usable_tiers)
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        matched = 0
        usable = 0
        withheld = 0
        now = _now()
        with self._connect() as conn:
            for row in rows:
                body = _first_value(row, _BODY_COLUMNS)
                tier = str(row.get("审核档位") or "").strip()
                if not body or not tier:
                    continue
                article = conn.execute(
                    "SELECT id FROM article_inventory WHERE asset_key = ? AND body_hash = ?",
                    (self.asset_key, hash_article_body(body)),
                ).fetchone()
                if article is None:
                    continue
                is_usable = tier in allowed
                conn.execute(
                    """
                    UPDATE article_inventory
                    SET usable = ?, review_status = ?, update_time = ?
                    WHERE id = ?
                    """,
                    (
                        1 if is_usable else 0,
                        f"current_audit:{tier}",
                        now,
                        int(article["id"]),
                    ),
                )
                matched += 1
                usable += int(is_usable)
                withheld += int(not is_usable)
        return InventoryAuditApplyResult(
            input_rows=len(rows),
            matched_articles=matched,
            usable_articles=usable,
            withheld_articles=withheld,
        )

    def stats(self) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT category_group, category, delivered_count, COUNT(*) AS count
                FROM article_inventory
                WHERE asset_key = ? AND usable = 1
                GROUP BY category_group, category, delivered_count
                """,
                (self.asset_key,),
            ).fetchall()
        total = sum(int(row["count"]) for row in rows)
        never_delivered = sum(
            int(row["count"]) for row in rows if int(row["delivered_count"]) == 0
        )
        return {
            "asset_key": self.asset_key,
            "db_path": str(self.db_path),
            "total_usable": total,
            "never_delivered": never_delivered,
            "by_category": _count_rows(rows, only_never_delivered=False),
            "available_by_category": _count_rows(rows, only_never_delivered=True),
        }

    def _select_articles(
        self,
        conn: sqlite3.Connection,
        *,
        category_group: str | None,
        count: int,
        seed: int,
        allow_reuse: bool,
    ) -> list[sqlite3.Row]:
        if count == 0:
            return []
        clauses = ["asset_key = ?", "usable = 1"]
        params: list[Any] = [self.asset_key]
        if category_group is not None:
            clauses.append("category_group = ?")
            params.append(category_group)
        if not allow_reuse:
            clauses.append("delivered_count = 0")
        rows = conn.execute(
            f"SELECT * FROM article_inventory WHERE {' AND '.join(clauses)}",
            params,
        ).fetchall()
        random.Random(seed).shuffle(rows)
        rows.sort(key=lambda row: int(row["delivered_count"]))
        return rows[:count]

    def _repair_duplicate_content_ids(self, conn: sqlite3.Connection) -> None:
        duplicate_ids = conn.execute(
            """
            SELECT asset_key, content_id
            FROM article_inventory
            GROUP BY asset_key, content_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for duplicate in duplicate_ids:
            rows = conn.execute(
                """
                SELECT id, body_hash
                FROM article_inventory
                WHERE asset_key = ? AND content_id = ?
                ORDER BY id
                """,
                (duplicate["asset_key"], duplicate["content_id"]),
            ).fetchall()
            for row in rows[1:]:
                unique_id = self._unique_content_id(
                    conn,
                    str(duplicate["content_id"]),
                    str(row["body_hash"]),
                    exclude_article_id=int(row["id"]),
                )
                conn.execute(
                    "UPDATE article_inventory SET content_id = ?, update_time = ? WHERE id = ?",
                    (unique_id, _now(), int(row["id"])),
                )

    def _unique_content_id(
        self,
        conn: sqlite3.Connection,
        content_id: str,
        body_hash: str,
        *,
        exclude_article_id: int | None = None,
    ) -> str:
        candidate = content_id
        suffix_size = 8
        while True:
            clauses = ["asset_key = ?", "content_id = ?"]
            params: list[Any] = [self.asset_key, candidate]
            if exclude_article_id is not None:
                clauses.append("id != ?")
                params.append(exclude_article_id)
            existing = conn.execute(
                f"SELECT 1 FROM article_inventory WHERE {' AND '.join(clauses)} LIMIT 1",
                params,
            ).fetchone()
            if existing is None:
                return candidate
            candidate = f"{content_id}-{body_hash[:suffix_size]}"
            suffix_size += 2

    def _record_delivery(
        self,
        conn: sqlite3.Connection,
        *,
        delivery_code: str,
        article_ids: list[int],
        output_uri: str,
        status: str,
    ) -> None:
        existing = conn.execute(
            "SELECT id FROM article_delivery_batch WHERE delivery_code = ?",
            (delivery_code,),
        ).fetchone()
        if existing is not None:
            raise ValueError(f"delivery_code already exists: {delivery_code}")
        placeholders = ",".join("?" for _ in article_ids)
        counts = conn.execute(
            f"""
            SELECT category_group, COUNT(*) AS count
            FROM article_inventory
            WHERE id IN ({placeholders})
            GROUP BY category_group
            """,
            article_ids,
        ).fetchall()
        category_counts = {row["category_group"]: int(row["count"]) for row in counts}
        now = _now()
        cursor = conn.execute(
            """
            INSERT INTO article_delivery_batch (
                delivery_code, asset_key, target_count, can_collection_count,
                other_count, output_uri, status, create_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delivery_code,
                self.asset_key,
                len(article_ids),
                category_counts.get("can_collection", 0),
                len(article_ids) - category_counts.get("can_collection", 0),
                output_uri,
                status,
                now,
            ),
        )
        delivery_batch_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO article_delivery_batch_item (delivery_batch_id, article_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (delivery_batch_id, article_id, position)
                for position, article_id in enumerate(article_ids, 1)
            ],
        )
        conn.execute(
            f"""
            UPDATE article_inventory
            SET delivered_count = delivered_count + 1,
                first_delivered_at = COALESCE(first_delivered_at, ?),
                last_delivered_at = ?,
                update_time = ?
            WHERE id IN ({placeholders})
            """,
            [now, now, now, *article_ids],
        )

    def record_historical_delivery(
        self,
        *,
        delivery_code: str,
        bodies: Iterable[str],
        output_uri: str,
    ) -> int:
        """Mark matching inventory bodies delivered; repeated syncs are idempotent."""
        self.initialize()
        hashes = list(
            dict.fromkeys(
                hash_article_body(body) for body in bodies if str(body or "").strip()
            )
        )
        if not hashes:
            return 0
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM article_delivery_batch WHERE delivery_code = ?",
                (delivery_code,),
            ).fetchone():
                return 0
            placeholders = ",".join("?" for _ in hashes)
            article_ids = [
                int(row["id"])
                for row in conn.execute(
                    f"SELECT id FROM article_inventory WHERE asset_key = ? AND body_hash IN ({placeholders})",
                    [self.asset_key, *hashes],
                ).fetchall()
            ]
            if not article_ids:
                return 0
            self._record_delivery(
                conn,
                delivery_code=delivery_code,
                article_ids=article_ids,
                output_uri=output_uri,
                status="historical_delivered",
            )
            return len(article_ids)

    def replace_usable_bodies(
        self,
        bodies: Iterable[str],
        *,
        review_status: str,
    ) -> int:
        """Make one asset's usable set exactly match the supplied body set."""
        self.initialize()
        hashes = list(
            dict.fromkeys(
                hash_article_body(body) for body in bodies if str(body or "").strip()
            )
        )
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE article_inventory
                SET usable = 0, review_status = ?, update_time = ?
                WHERE asset_key = ? AND review_status NOT LIKE 'current_audit:%'
                """,
                ("excluded_by_current_sync", now, self.asset_key),
            )
            if not hashes:
                return 0
            placeholders = ",".join("?" for _ in hashes)
            cursor = conn.execute(
                f"""
                UPDATE article_inventory
                SET usable = 1, review_status = ?, update_time = ?
                WHERE asset_key = ?
                  AND body_hash IN ({placeholders})
                  AND review_status NOT LIKE 'current_audit:%'
                """,
                [review_status, now, self.asset_key, *hashes],
            )
            return int(cursor.rowcount)

    def _classify_article(self, row: Mapping[str, Any]) -> tuple[str, str]:
        if self.asset_key == A2_REIYU_ASSET_KEY:
            return classify_a2_reiyu_article(row)
        category = _first_value(row, _CATEGORY_COLUMNS).strip() or "未分类"
        return "all", category

    def _auto_content_id_prefix(self) -> str:
        if self.asset_key == A2_REIYU_ASSET_KEY:
            return "a2-reiyu"
        if self.asset_key == WANGYUE_ASSET_KEY:
            return "wangyue"
        return (
            re.sub(r"[^0-9A-Za-z]+", "-", self.asset_key).strip("-").lower()
            or "article"
        )

    def _article_context_list(self, conn: sqlite3.Connection, article_id: int) -> str:
        source = conn.execute(
            """
            SELECT metadata_json
            FROM article_inventory_source
            WHERE article_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (article_id,),
        ).fetchone()
        if source is None or not source["metadata_json"]:
            return "{}"
        try:
            metadata = json.loads(source["metadata_json"])
        except (TypeError, json.JSONDecodeError):
            return "{}"
        context = (
            metadata.get("上下文变量(context_list)")
            or metadata.get("context_list")
            or {}
        )
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except json.JSONDecodeError:
                return context
        return json.dumps(
            context if isinstance(context, dict) else {}, ensure_ascii=False
        )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def classify_a2_reiyu_article(row: Mapping[str, Any]) -> tuple[str, str]:
    raw_category = _first_value(row, _CATEGORY_COLUMNS).strip()
    activity = ""
    raw_context = _first_value(row, _CONTEXT_COLUMNS).strip()
    if raw_context:
        try:
            context = json.loads(raw_context)
        except json.JSONDecodeError:
            context = {}
        if isinstance(context, dict):
            activity = " ".join(
                str(context.get(key) or "")
                for key in ("活动内容", "本条主活动", "业务规则")
            ).strip()
    anchor = raw_category or activity
    if "12罐" in anchor:
        return "can_collection", "12罐"
    if "集罐" in anchor or "其他罐" in anchor:
        return "can_collection", "其他罐"
    return "other", "其他"


def hash_article_body(body: str | None) -> str:
    normalized = re.sub(r"\s+", "", str(body or "")).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _first_value(row: Mapping[str, Any], names: Iterable[str]) -> str:
    for name in names:
        if name in row:
            return str(row.get(name) or "")
    return ""


def _source_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {*_TITLE_COLUMNS, *_BODY_COLUMNS} and value not in (None, "")
    }


def _source_row(row: Mapping[str, Any], column: str | None, fallback: int) -> int:
    if not column:
        return fallback
    try:
        return int(row.get(column) or fallback)
    except (TypeError, ValueError):
        return fallback


def _is_approved_review_status(review_status: str) -> bool:
    return review_status in {
        "direct_pool",
        "approved_manual",
        "strict_reviewed",
        "machine_exportable",
    }


def _count_rows(
    rows: list[sqlite3.Row], *, only_never_delivered: bool
) -> dict[str, int]:
    result = {"12罐": 0, "其他罐": 0, "其他": 0}
    for row in rows:
        if only_never_delivered and int(row["delivered_count"]) != 0:
            continue
        result[str(row["category"])] = result.get(str(row["category"]), 0) + int(
            row["count"]
        )
    return result


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
