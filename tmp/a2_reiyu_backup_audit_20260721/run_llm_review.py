#!/usr/bin/env python3
"""Audit the A2 reiyu backup CSV through the DB-backed prompt-debug route."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

from app.services.product_experience_llm_review_service import (
    A2_REIYU_ARTICLE_ASSET_KEY,
    _A2_REIYU_SYSTEM_PROMPT,
    _user_prompt,
    parse_product_experience_llm_review,
)


INPUT_PATH = Path("/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/deterministic_scan.json")
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/llm_review.json"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "12"))
LIMIT = int(os.environ.get("LIMIT", "0"))
BASE_URL = "http://127.0.0.1:5100"
MAX_ATTEMPTS = 4


def build_plan(item: dict[str, Any]) -> dict[str, Any]:
    category = str(item.get("effective_category") or "其他")
    if category == "12罐":
        business_rule = "a2礼遇｜集罐12罐兑换1罐奶粉"
        activity_material = ["集12罐兑换1罐奶粉"]
    elif category == "其他罐":
        business_rule = "a2礼遇｜其他集罐档位"
        activity_material = ["集3罐换小车车", "集6罐换自行车", "集18罐换婴儿车"]
    else:
        business_rule = "a2礼遇｜抽奖、积分、老客回馈或多重福利"
        activity_material = [
            "抽奖奖品可写旅游基金或新西兰旅游、金手链或金手串、夏凉被",
            "积分可以累计兑换会员礼，但不能兑换集罐奖品",
            "老客回馈和多重福利可以自然分享",
        ]
    return {
        "asset_key": A2_REIYU_ARTICLE_ASSET_KEY,
        "business_rule": business_rule,
        "post_type": "a2礼遇",
        "activity_material": activity_material,
        "variation_slots": [
            {"slot_code": "源表分类", "slot_name": "源表分类", "value": item.get("source_category") or "未填写"},
            {"slot_code": "审核分类", "slot_name": "审核分类", "value": category},
        ],
        "model_config": {
            "provider_code": "deepseek",
            "model_code": "deepseek-v4-flash",
            "ge_model": "deepseek-v4-flash",
            "ae_model": "deepseek-v4-flash",
            "temperature": 0.1,
            "max_tokens": 1800,
        },
    }


async def main() -> None:
    scan = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    items = scan["results"][:LIMIT] if LIMIT > 0 else scan["results"]
    semaphore = asyncio.Semaphore(CONCURRENCY)
    results_by_row: dict[int, dict[str, Any]] = {}
    if OUTPUT_PATH.exists():
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        results_by_row = {int(item["source_row"]): item for item in previous if item and item.get("source_row")}

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=150) as client:

        async def invoke(item: dict[str, Any]) -> dict[str, Any]:
            prompt = _user_prompt(
                title=str(item.get("title") or ""),
                body=str(item.get("body") or ""),
                plan=build_plan(item),
                phrase_review=None,
            )
            response = await client.post(
                "/api/v1/content-agent/prompt-debug/run",
                json={
                    "prompt": prompt,
                    "system_prompt": _A2_REIYU_SYSTEM_PROMPT,
                    "model_code": "deepseek-v4-flash",
                    "temperature": 0.1,
                    "max_tokens": 1800,
                },
            )
            response.raise_for_status()
            payload = response.json().get("data") or {}
            if not payload.get("success"):
                raise RuntimeError(payload.get("error_message") or "prompt debug failed")
            review = parse_product_experience_llm_review(str(payload.get("content") or ""))
            review.review_rubric_code = "a2_reiyu_business_usability_v1"
            return review.model_dump()

        completed = 0
        lock = asyncio.Lock()

        async def review_one(item: dict[str, Any]) -> None:
            nonlocal completed
            source_row = int(item["source_row"])
            async with semaphore:
                review_payload = None
                error = None
                attempts = 0
                for attempts in range(1, MAX_ATTEMPTS + 1):
                    try:
                        review_payload = await invoke(item)
                        break
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        if attempts < MAX_ATTEMPTS:
                            await asyncio.sleep(0.5 * attempts)
                if review_payload is not None:
                    error = None
            results_by_row[source_row] = {
                "source_row": source_row,
                "title": item.get("title"),
                "body": item.get("body"),
                "source_category": item.get("source_category"),
                "effective_category": item.get("effective_category"),
                "review": review_payload,
                "attempts": attempts,
                "error": error,
            }
            async with lock:
                completed += 1
                if completed % 10 == 0 or completed == len(pending):
                    print(f"reviewed {completed}/{len(pending)}", flush=True)
                    ordered = [results_by_row[int(candidate["source_row"])] for candidate in items if int(candidate["source_row"]) in results_by_row]
                    OUTPUT_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")

        pending = [item for item in items if int(item["source_row"]) not in results_by_row or results_by_row[int(item["source_row"])].get("error")]
        print(f"pending {len(pending)}/{len(items)}", flush=True)
        await asyncio.gather(*(review_one(item) for item in pending))

    ordered = [results_by_row[int(item["source_row"])] for item in items]
    OUTPUT_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    tier_counts: dict[str, int] = {}
    issue_counts: dict[str, int] = {}
    errors = 0
    for item in ordered:
        if item.get("error") or not item.get("review"):
            errors += 1
            continue
        review = item["review"]
        tier = str(review.get("business_usability_tier") or "unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        for issue in review.get("issues") or []:
            code = str(issue.get("code") or "other")
            issue_counts[code] = issue_counts.get(code, 0) + 1
    print(json.dumps({"tier_counts": tier_counts, "issue_counts": issue_counts, "errors": errors, "output_path": str(OUTPUT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
