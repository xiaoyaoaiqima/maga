#!/usr/bin/env python3
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


EVAL_DIR = Path("/Users/luxifa/maga/platform-server/evals")
CASES = {
    "A2RY-AM-012": "hold_out",
    "A2RY-AM-013": "hold_out",
    "A2RY-AM-014": "hold_out",
    "A2RY-AM-015": "hold_out",
    "A2RY-AM-016": "light_fix_usable",
    "A2RY-NC-003": "direct_pool",
    "A2RY-NC-004": "light_fix_usable",
    "A2RY-CL-001": "light_fix_usable",
}


def load_cases() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in (
        EVAL_DIR / "a2_reiyu_review_gold_v1_activity_mechanism.json",
        EVAL_DIR / "a2_reiyu_review_gold_v1_narrative_consistency.json",
        EVAL_DIR / "a2_reiyu_review_gold_v1_common_logic.json",
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload["items"]:
            code = item["meta"]["case_code"]
            if code in CASES:
                items.append(item)
    return items


async def main() -> None:
    plan = {
        "asset_key": A2_REIYU_ARTICLE_ASSET_KEY,
        "business_rule": "a2礼遇｜人工确认金标回归验证",
        "activity_material": [
            "积分只能兑换会员礼",
            "集罐标准为3罐小车车、6罐自行车、12罐奶粉、18罐婴儿车",
        ],
        "variation_slots": [],
    }
    results = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:5100", timeout=120) as client:
        for item in load_cases():
            code = item["meta"]["case_code"]
            review = None
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    response = await client.post(
                        "/api/v1/content-agent/prompt-debug/run",
                        json={
                            "prompt": _user_prompt(
                                title=item["title"],
                                body=item["content"],
                                plan=plan,
                                phrase_review=None,
                            ),
                            "system_prompt": _A2_REIYU_SYSTEM_PROMPT,
                            "model_code": "deepseek-v4-flash",
                            "temperature": 0.0,
                            "max_tokens": 1200,
                        },
                    )
                    response.raise_for_status()
                    data = response.json().get("data") or {}
                    if not data.get("success"):
                        raise RuntimeError(data.get("error_message") or f"{code} failed")
                    review = parse_product_experience_llm_review(str(data.get("content") or ""))
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 3:
                        await asyncio.sleep(0.5 * attempt)
            if review is None:
                raise last_error or RuntimeError(f"{code} failed")
            actual = review.business_usability_tier
            results.append(
                {
                    "case_code": code,
                    "expected": CASES[code],
                    "actual": actual,
                    "issues": [issue.code for issue in review.issues],
                    "match": actual == CASES[code],
                }
            )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    mismatches = [item for item in results if not item["match"]]
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
