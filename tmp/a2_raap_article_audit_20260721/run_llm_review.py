#!/usr/bin/env python3
"""Run the production A2 reiyu business-usability judge over a RAAP article export."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.services.product_experience_llm_review_service import (
    A2_REIYU_ARTICLE_ASSET_KEY,
    _A2_REIYU_SYSTEM_PROMPT,
    _user_prompt,
    parse_product_experience_llm_review,
)


INPUT_PATH = Path("/Users/luxifa/maga/tmp/a2_raap_article_audit_20260721/extracted_workbooks.json")
OUTPUT_PATH = Path("/Users/luxifa/maga/tmp/a2_raap_article_audit_20260721/llm_review.json")
CONCURRENCY = 10
BASE_URL = "http://127.0.0.1:5100"
MAX_ATTEMPTS = 4


def build_plan(context: dict[str, Any]) -> dict[str, Any]:
    motive = str(context.get("动机") or "")
    path = "老客使用感受" if motive == "老客型" else "消费者活动分享"
    variation_slots = [
        {"slot_code": key, "slot_name": key, "value": value}
        for key, value in context.items()
    ]
    return {
        "asset_key": A2_REIYU_ARTICLE_ASSET_KEY,
        "business_rule": f"a2礼遇｜集罐12罐换奶粉｜{path}",
        "post_type": "a2礼遇",
        "activity_material": ["集罐12罐兑换1罐奶粉"],
        "variation_slots": variation_slots,
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
    workbooks = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    rows = workbooks[0]["sheets"][0]["values"][1:]
    semaphore = asyncio.Semaphore(CONCURRENCY)
    if OUTPUT_PATH.exists():
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        results: list[dict[str, Any] | None] = previous if len(previous) == len(rows) else [None] * len(rows)
    else:
        results = [None] * len(rows)
    completed = 0
    lock = asyncio.Lock()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as client:

        async def invoke(title: str, body: str, plan: dict[str, Any]):
            prompt = _user_prompt(
                title=title,
                body=body,
                plan=plan,
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
            return parse_product_experience_llm_review(str(payload.get("content") or ""))

        async def review_one(index: int, row: list[Any]) -> None:
            nonlocal completed
            excel_row = index + 2
            article_id, content_id, title, body, context_text, status, is_test, created_at = row
            try:
                context = json.loads(context_text or "{}")
            except json.JSONDecodeError:
                context = {}
            async with semaphore:
                try:
                    plan = build_plan(context)
                    last_error: Exception | None = None
                    for attempts in range(1, MAX_ATTEMPTS + 1):
                        try:
                            review = await invoke(str(title or ""), str(body or ""), plan)
                            break
                        except Exception as exc:
                            last_error = exc
                            if attempts < MAX_ATTEMPTS:
                                await asyncio.sleep(0.5 * attempts)
                    else:
                        raise last_error or RuntimeError("review failed")
                    review.review_rubric_code = "a2_reiyu_business_usability_v1"
                    review.review_attempts = attempts
                    review_payload = review.model_dump()
                    error = None
                except Exception as exc:  # Preserve row-level failures for human review.
                    review_payload = None
                    error = f"{type(exc).__name__}: {exc}"
            results[index] = {
                "excel_row": excel_row,
                "id": article_id,
                "content_id": content_id,
                "title": title,
                "body": body,
                "context": context,
                "status": status,
                "is_test": is_test,
                "created_at": created_at,
                "review": review_payload,
                "error": error,
            }
            async with lock:
                completed += 1
                if completed % 10 == 0 or completed == len(rows):
                    print(f"reviewed {completed}/{len(rows)}", flush=True)

        pending = [
            (index, row)
            for index, row in enumerate(rows)
            if results[index] is None or results[index].get("error")
        ]
        print(f"pending {len(pending)}/{len(rows)}", flush=True)
        await asyncio.gather(*(review_one(index, row) for index, row in pending))
    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    error_count = 0
    issue_counts: dict[str, int] = {}
    for item in results:
        if not item or item["error"]:
            error_count += 1
            continue
        review = item["review"] or {}
        tier = str(review.get("business_usability_tier") or "unknown")
        counts[tier] = counts.get(tier, 0) + 1
        for issue in review.get("issues") or []:
            code = str(issue.get("code") or "other")
            issue_counts[code] = issue_counts.get(code, 0) + 1
    print(json.dumps({"tier_counts": counts, "error_count": error_count, "issue_counts": issue_counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
