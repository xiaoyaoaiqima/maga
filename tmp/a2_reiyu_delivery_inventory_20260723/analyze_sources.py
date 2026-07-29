from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


SOURCES = [
    Path("/Users/luxifa/maga/outputs/a2_reiyu_audit_20260720_csv_v4/a2礼遇_300篇_集罐70_其他30.csv"),
    Path("/Users/luxifa/maga/outputs/a2_raap_article_audit_20260721/A2礼遇_RAAP文章池_最终可用186篇.csv"),
    Path("/Users/luxifa/maga/outputs/a2_reiyu_followup_audit_20260721/A2礼遇_新200篇_审核后可用198篇.csv"),
    Path("/Users/luxifa/maga/outputs/a2_reiyu_followup_audit_20260721/A2礼遇_剩余301篇_清理后可用294篇.csv"),
    Path("/Users/luxifa/maga/outputs/a2_old_raap_audit_20260722/A2礼遇_老RAAP两批合并可用393篇.csv"),
    Path("/Users/luxifa/Downloads/PG UGC正向词调整后模型 - 礼遇生文备用 (2).csv"),
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip()


def main() -> None:
    seen = {}
    source_summary = []
    for path in SOURCES:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        categories = Counter((row.get("分类") or row.get("category") or "").strip() for row in rows)
        context_keys = Counter()
        context_activity_samples = []
        for row in rows:
            raw_context = row.get("上下文变量(context_list)") or ""
            if not raw_context:
                continue
            try:
                context = json.loads(raw_context)
            except json.JSONDecodeError:
                continue
            if isinstance(context, dict):
                context_keys.update(context)
                if len(context_activity_samples) < 3:
                    context_activity_samples.append(context)
        duplicates = 0
        for index, row in enumerate(rows, start=2):
            body = row.get("正文") or row.get("body") or row.get("content") or ""
            digest = hashlib.sha256(normalize(body).encode()).hexdigest()
            if digest in seen:
                duplicates += 1
            else:
                seen[digest] = (str(path), index)
        source_summary.append({
            "path": str(path),
            "rows": len(rows),
            "duplicates_against_prior_sources": duplicates,
            "headers": list(rows[0]) if rows else [],
            "categories": categories,
            "context_keys": context_keys,
            "context_samples": context_activity_samples,
        })
    print(json.dumps({"sources": source_summary, "unique_bodies": len(seen)}, ensure_ascii=False, indent=2, default=dict))


if __name__ == "__main__":
    main()
