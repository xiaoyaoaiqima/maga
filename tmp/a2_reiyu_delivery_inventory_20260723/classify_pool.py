from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


SOURCES = [
    ("delivered_300", Path("/Users/luxifa/maga/outputs/a2_reiyu_audit_20260720_csv_v4/a2礼遇_300篇_集罐70_其他30.csv")),
    ("usable", Path("/Users/luxifa/maga/outputs/a2_raap_article_audit_20260721/A2礼遇_RAAP文章池_最终可用186篇.csv")),
    ("usable", Path("/Users/luxifa/maga/outputs/a2_reiyu_followup_audit_20260721/A2礼遇_新200篇_审核后可用198篇.csv")),
    ("usable", Path("/Users/luxifa/maga/outputs/a2_reiyu_followup_audit_20260721/A2礼遇_剩余301篇_清理后可用294篇.csv")),
    ("usable", Path("/Users/luxifa/maga/outputs/a2_old_raap_audit_20260722/A2礼遇_老RAAP两批合并可用393篇.csv")),
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip()


def category(row: dict[str, str]) -> str:
    raw = (row.get("分类") or row.get("category") or "").strip()
    activity = ""
    if not raw:
        try:
            context = json.loads(row.get("上下文变量(context_list)") or "{}")
        except json.JSONDecodeError:
            context = {}
        if isinstance(context, dict):
            activity = str(context.get("活动内容") or "")
    text = raw or activity
    if "12罐" in text:
        return "12罐"
    if "集罐" in text or "其他罐" in text:
        return "其他罐"
    return "其他"


def main() -> None:
    articles = {}
    delivered_hashes = set()
    for source_type, path in SOURCES:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                body = row.get("正文") or row.get("body") or row.get("content") or ""
                digest = hashlib.sha256(normalize(body).encode()).hexdigest()
                articles.setdefault(digest, category(row))
                if source_type == "delivered_300":
                    delivered_hashes.add(digest)
    total = Counter(articles.values())
    available = Counter(category for digest, category in articles.items() if digest not in delivered_hashes)
    print(json.dumps({
        "unique_total": len(articles),
        "delivered_known": len(delivered_hashes),
        "available_unique": len(articles) - len(delivered_hashes),
        "total_categories": total,
        "available_categories": available,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
