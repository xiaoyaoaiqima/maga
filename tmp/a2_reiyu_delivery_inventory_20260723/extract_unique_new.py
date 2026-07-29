from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path


KNOWN_SOURCES = [
    Path("/Users/luxifa/maga/outputs/a2_reiyu_audit_20260720_csv_v4/a2礼遇_300篇_集罐70_其他30.csv"),
    Path("/Users/luxifa/maga/outputs/a2_raap_article_audit_20260721/A2礼遇_RAAP文章池_最终可用186篇.csv"),
    Path("/Users/luxifa/maga/outputs/a2_reiyu_followup_audit_20260721/A2礼遇_新200篇_审核后可用198篇.csv"),
    Path("/Users/luxifa/maga/outputs/a2_reiyu_followup_audit_20260721/A2礼遇_剩余301篇_清理后可用294篇.csv"),
    Path("/Users/luxifa/maga/outputs/a2_old_raap_audit_20260722/A2礼遇_老RAAP两批合并可用393篇.csv"),
]
INPUT = Path("/Users/luxifa/Downloads/PG UGC正向词调整后模型 - 礼遇生文备用 (2).csv")
OUTPUT = Path("/Users/luxifa/maga/tmp/a2_reiyu_delivery_inventory_20260723/source_384_unique_new.csv")


def digest(body: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", "", body or "").strip().encode()).hexdigest()


def body(row: dict[str, str]) -> str:
    return row.get("正文") or row.get("body") or row.get("content") or ""


known_hashes = set()
for path in KNOWN_SOURCES:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        known_hashes.update(digest(body(row)) for row in csv.DictReader(handle))

with INPUT.open("r", encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    fieldnames = [name for name in reader.fieldnames or [] if name]
    rows = [row for row in reader if digest(body(row)) not in known_hashes]

with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

print(len(rows))
