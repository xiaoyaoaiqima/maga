#!/usr/bin/env python3
"""Run a narrow common-logic audit on clean A2 reiyu candidates."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx


SCAN_PATH = Path("/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/deterministic_scan.json")
BUSINESS_REVIEW_PATH = Path("/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/llm_review.json")
FORBIDDEN_PATH = Path("/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/forbidden_terms_response.json")
OUTPUT_PATH = Path("/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/common_logic_review.json")
BASE_URL = "http://127.0.0.1:5100"
CONCURRENCY = int(os.environ.get("CONCURRENCY", "16"))
MAX_ATTEMPTS = 4

SYSTEM_PROMPT = """你只审核a2礼遇UGC里明确的通用逻辑、时序、身份和生活常识冲突，不审核文风，也不重复做活动机制审核。

只在不修改就明显自相矛盾或事实不成立时判 reject：
1. 前文说第一次购买、一直想尝试或还没喝过，后文却说已经喝了几个月、一直回购。
2. 明确说从出生一直喝且从未换过，后文又说转奶、换过其他品牌再换回来。
3. 同一人物、同一时间线出现明显无法同时成立的先后关系。
4. 出现明确违反奶粉正常使用常识的做法，例如强调用冷水冲调奶粉。
5. 一次发现经历同时堆叠三个以上互不相干的来源，或一句话里人物关系明显混乱。

以下全部放行，不要判问题：
- 疾病、换季、抵抗力、少跑医院等医疗或效果表达。
- 活动页面、页面里、页面上提到a2至初每批都有检测；仔细看了下；扫罐底码查检测或溯源报告。
- puq、pyq、🆓、吃奶粉、强推荐、别错过、值得试试、活动很香。
- 旅游基金、新西兰旅游、金手链或金手串、夏凉被等自然奖品叫法；2w、两万、万元。
- 标题和正文字数、广告感、总结感、措辞强弱、产品功效是否夸张。
- 老客第一次参加活动，或一直喝但以前没关注过活动，这不冲突。
- 先写一种来源，后文提到朋友使用感受；只有明确把多个来源叠加成同一次发现才算冲突。

宁可放行边界表达，不要把可以理解的口语当逻辑错误。严格输出JSON，不要Markdown：
{"pass":true,"issues":[],"overall_reason":"无明确通用逻辑冲突"}
或
{"pass":false,"issues":[{"code":"identity_conflict|timeline_conflict|common_sense_error|source_stacking","evidence":"原文片段","reason":"明确冲突原因"}],"overall_reason":"一句话总结"}
"""


def extract_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.I)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        value = json.loads(clean)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(clean[start : end + 1])
        return value if isinstance(value, dict) else {}


def entry_matches(text: str, entry: dict[str, Any]) -> bool:
    term = str(entry.get("term") or "")
    if not term or term not in text or entry.get("enabled") is False:
        return False
    mode = str(entry.get("match_mode") or "literal")
    if mode == "activity_prize_context":
        cues = ("奖品", "礼品", "兑换", "换到", "换个", "换一", "抽奖", "中奖", "集罐", "能领", "可以领", "活动送", "活动有", "福利有")
        return any(term in sentence and any(cue in sentence for cue in cues) for sentence in re.split(r"[\n。！？!?；;]", text))
    if mode == "detection_page_context":
        return any(term in sentence and any(cue in sentence for cue in ("每批", "批批", "检测")) for sentence in re.split(r"[\n。！？!?；;]", text))
    return True


async def main() -> None:
    scan = json.loads(SCAN_PATH.read_text(encoding="utf-8"))
    business_reviews = json.loads(BUSINESS_REVIEW_PATH.read_text(encoding="utf-8"))
    review_by_row = {int(item["source_row"]): item for item in business_reviews}
    forbidden_entries = [
        item
        for item in json.loads(FORBIDDEN_PATH.read_text(encoding="utf-8")).get("data", {}).get("items", [])
        if item.get("enabled") is not False
    ]
    candidates: list[dict[str, Any]] = []
    for item in scan["results"]:
        review = review_by_row.get(int(item["source_row"]), {}).get("review") or {}
        if review.get("business_usability_tier") != "direct_pool":
            continue
        if item.get("hits"):
            continue
        text = f"{item.get('title') or ''}\n{item.get('body') or ''}"
        if any(entry_matches(text, entry) for entry in forbidden_entries):
            continue
        candidates.append(item)

    results_by_row: dict[int, dict[str, Any]] = {}
    if OUTPUT_PATH.exists():
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        results_by_row = {int(item["source_row"]): item for item in previous if item and item.get("source_row")}

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as client:
        semaphore = asyncio.Semaphore(CONCURRENCY)
        lock = asyncio.Lock()
        completed = 0

        async def review_one(item: dict[str, Any]) -> None:
            nonlocal completed
            source_row = int(item["source_row"])
            prompt = json.dumps({"title": item.get("title"), "body": item.get("body")}, ensure_ascii=False)
            payload = None
            error = None
            attempts = 0
            async with semaphore:
                for attempts in range(1, MAX_ATTEMPTS + 1):
                    try:
                        response = await client.post(
                            "/api/v1/content-agent/prompt-debug/run",
                            json={
                                "prompt": prompt,
                                "system_prompt": SYSTEM_PROMPT,
                                "model_code": "deepseek-v4-flash",
                                "temperature": 0.0,
                                "max_tokens": 900,
                            },
                        )
                        response.raise_for_status()
                        data = response.json().get("data") or {}
                        if not data.get("success"):
                            raise RuntimeError(data.get("error_message") or "prompt debug failed")
                        payload = extract_json(str(data.get("content") or ""))
                        if "pass" not in payload:
                            raise ValueError("logic review missing pass")
                        error = None
                        break
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        if attempts < MAX_ATTEMPTS:
                            await asyncio.sleep(0.5 * attempts)
            results_by_row[source_row] = {
                "source_row": source_row,
                "effective_category": item.get("effective_category"),
                "title": item.get("title"),
                "review": payload,
                "attempts": attempts,
                "error": error,
            }
            async with lock:
                completed += 1
                if completed % 10 == 0 or completed == len(pending):
                    print(f"logic reviewed {completed}/{len(pending)}", flush=True)
                    ordered = [results_by_row[int(candidate["source_row"])] for candidate in candidates if int(candidate["source_row"]) in results_by_row]
                    OUTPUT_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")

        pending = [item for item in candidates if int(item["source_row"]) not in results_by_row or results_by_row[int(item["source_row"])].get("error")]
        print(f"pending {len(pending)}/{len(candidates)}", flush=True)
        await asyncio.gather(*(review_one(item) for item in pending))

    ordered = [results_by_row[int(item["source_row"])] for item in candidates]
    OUTPUT_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(1 for item in ordered if item.get("review", {}).get("pass") is True and not item.get("error"))
    rejected = [item for item in ordered if item.get("review", {}).get("pass") is False and not item.get("error")]
    errors = sum(1 for item in ordered if item.get("error"))
    category_pass: dict[str, int] = {}
    for item in ordered:
        if item.get("review", {}).get("pass") is True and not item.get("error"):
            category = str(item.get("effective_category") or "其他")
            category_pass[category] = category_pass.get(category, 0) + 1
    print(json.dumps({"candidates": len(candidates), "passed": passed, "rejected": len(rejected), "errors": errors, "category_pass": category_pass, "rejected_items": rejected}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
