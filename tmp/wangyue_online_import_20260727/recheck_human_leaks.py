from __future__ import annotations

import json
from pathlib import Path

from app.services.content_batch_execution_service import (
    _production_blocking_product_experience_phrase_hits,
)
from app.services.product_experience_phrase_guard_service import (
    review_product_experience_phrase,
)


REPORT = Path(
    "/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence/"
    "20260727_wangyue_v92_production_100_online/"
    "20260727_124057_wangyue_batch876_report_full.json"
)
ITEM_NOS = {1, 2, 8, 12, 20, 21, 24, 27, 28, 39, 42, 45, 61, 68, 86, 90, 92}


payload = json.loads(REPORT.read_text(encoding="utf-8"))["data"]
results = []
for item in payload["items"]:
    if int(item["item_no"]) not in ITEM_NOS:
        continue
    snapshot = item.get("generation_snapshot") or {}
    plan = snapshot.get("business_rule") or {}
    review = review_product_experience_phrase(
        title=str(item.get("title") or ""),
        body=str(item.get("body") or ""),
        plan=plan,
    )
    blocking_hits = _production_blocking_product_experience_phrase_hits(review)
    results.append(
        {
            "item_no": item["item_no"],
            "title": item.get("title"),
            "current_guard_pass": review.pass_,
            "current_guard_reasons": review.reasons,
            "current_production_blocking_hits": blocking_hits,
            "child_self_brewing_hits": review.child_self_brewing_hits,
            "logic_drift_hits": review.wangyue_article_logic_drift_hits,
            "ingredient_benefit_mismatch_hits": review.ingredient_benefit_mismatch_hits,
        }
    )

print(json.dumps(results, ensure_ascii=False, indent=2))
