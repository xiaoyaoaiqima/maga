#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from app.services.product_experience_llm_review_service import (
    A2_REIYU_ARTICLE_ASSET_KEY,
    _A2_REIYU_SYSTEM_PROMPT,
    _user_prompt,
    parse_product_experience_llm_review,
)


WORK_DIR = Path("/Users/luxifa/maga/tmp/a2_reiyu_followup_audit_20260721")
INPUT_PATH = WORK_DIR / "new_workbook.json"
FORBIDDEN_PATH = Path("/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/forbidden_terms_response.json")
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", str(WORK_DIR / "new_processed.json")))
CACHE_PATH = Path(os.environ.get("CACHE_PATH", str(WORK_DIR / "new_rewrite_cache.json")))
LIMIT = int(os.environ.get("LIMIT", "0"))
BASE_URL = "http://127.0.0.1:5100"
MANUAL_HARD_ROWS = {51, 54}
MANUAL_PASS_ROWS = {57}
MANUAL_LIGHT_INSTRUCTIONS = {
    20: "不要用‘叫……活动/礼遇’解释活动名称，改成自然说发现a2上了会员礼遇活动，其他内容不改。",
    67: "本篇内容方向是会员体系/积分。把抽奖和抽奖奖品那一段改成会员积分相关分享，只说积分可以积累、兑换会员礼，不要编具体积分礼品；其他内容不改。",
    86: "删除‘虽然没中’这类抽奖结果描述，保持前后自然，其他活动机制不改。",
    120: "不要用‘叫礼遇活动’解释活动名称，改成自然说发现a2上了礼遇活动，其他内容不改。",
    174: "修复‘从大宝到二宝一直没断过’与‘中间试过别的牌子、赶紧换回来’的经历冲突。保留中间换过又换回a2至初的经历，只改第一句，其他内容不改。",
}


def extract_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.I)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        value = json.loads(clean)
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
    sentences = re.split(r"[\n。！？!?；;]", text)
    if mode == "activity_prize_context":
        cues = ("奖品", "礼品", "兑换", "换到", "换个", "换一", "抽奖", "中奖", "集罐", "能领", "可以领", "活动送", "活动有", "福利有")
        return any(term in sentence and any(cue in sentence for cue in cues) for sentence in sentences)
    if mode == "detection_page_context":
        return any(term in sentence and any(cue in sentence for cue in ("每批", "批批", "检测")) for sentence in sentences)
    return True


def formal_hits(text: str, entries: list[dict[str, Any]], enforcement: str | None = None) -> list[dict[str, Any]]:
    return [
        entry
        for entry in entries
        if (enforcement is None or entry.get("enforcement") == enforcement) and entry_matches(text, entry)
    ]


def apply_replacements(value: str, replacements: dict[str, str]) -> str:
    text = value
    for term in sorted(replacements, key=len, reverse=True):
        text = text.replace(term, replacements[term])
    return text.replace("a2蛋白", "A2蛋白").replace("💩💩", "💩").replace("👀👀", "👀")


def parse_context(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def build_plan(item: dict[str, Any]) -> dict[str, Any]:
    activity_type = str(item.get("activity_type") or "其他")
    return {
        "asset_key": A2_REIYU_ARTICLE_ASSET_KEY,
        "business_rule": f"a2礼遇｜{activity_type}",
        "post_type": "a2礼遇",
        "activity_material": [
            "集罐标准为3罐小车车、6罐自行车、12罐奶粉、18罐婴儿车",
            "抽奖奖品可写旅游基金或新西兰旅游、金手链或金手串、夏凉被",
            "积分可以累计兑换会员礼，但不能兑换集罐奖品",
            "旧购买罐不能参加本次活动；不得新增中奖或兑换成功经历",
        ],
        "variation_slots": [
            {"slot_code": "活动内容", "slot_name": "活动内容", "value": activity_type},
        ],
    }


def rewrite_instruction(item: dict[str, Any]) -> str:
    instructions: list[str] = []
    manual_instruction = MANUAL_LIGHT_INSTRUCTIONS.get(int(item["excel_row"]))
    if manual_instruction:
        instructions.append(manual_instruction)
    terms = [str(entry.get("term") or "") for entry in item.get("model_rewrite_hits") or []]
    if terms:
        instructions.append(f"自然改写这些后链路避用表达：{'、'.join(terms)}。不要机械删词造成病句。")
    review = item.get("initial_review") or {}
    for issue in review.get("issues") or []:
        direction = str(issue.get("rewrite_direction") or "").strip()
        if direction:
            instructions.append(direction)
    if not instructions:
        instructions.append("只做最小必要修改，解决局部审核问题。")
    return "\n".join(instructions)


async def call_review(client: httpx.AsyncClient, item: dict[str, Any]) -> dict[str, Any]:
    prompt = _user_prompt(title=item["title"], body=item["body"], plan=build_plan(item), phrase_review=None)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = await client.post(
                "/api/v1/content-agent/prompt-debug/run",
                json={
                    "prompt": prompt,
                    "system_prompt": _A2_REIYU_SYSTEM_PROMPT,
                    "model_code": "deepseek-v4-flash",
                    "temperature": 0.0,
                    "max_tokens": 1800,
                },
            )
            response.raise_for_status()
            data = response.json().get("data") or {}
            if not data.get("success"):
                raise RuntimeError(data.get("error_message") or "review failed")
            return parse_product_experience_llm_review(str(data.get("content") or "")).model_dump()
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(0.5 * attempt)
    raise last_error or RuntimeError("review failed")


async def call_rewrite(client: httpx.AsyncClient, item: dict[str, Any], instruction: str) -> dict[str, str]:
    system_prompt = "\n".join(
        [
            "你是a2礼遇UGC后链路编辑，只做最小必要修改。",
            "必须保留原人物、发现来源、活动类型、活动事实、每批检测信息、使用经历和消费者认可。",
            "不得新增或串换奖品，不得新增中奖、兑换成功、旧罐参与、参与资格或新的了解来源。",
            "活动页面提到每批检测可以保留；puq、pyq、🆓可以保留。",
            "不得出现报名、顺手、顺口、顺便、朋友圈、薅、白嫖、羊毛、攒罐子、攒着罐子。",
            "a2和a2至初中的a必须小写。只输出JSON：{\"title\":\"...\",\"body\":\"...\"}。",
        ]
    )
    payload = {"instruction": instruction, "title": item["title"], "body": item["body"]}
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = await client.post(
                "/api/v1/content-agent/prompt-debug/run",
                json={
                    "prompt": json.dumps(payload, ensure_ascii=False),
                    "system_prompt": system_prompt,
                    "model_code": "qwen-plus",
                    "temperature": 0.15,
                    "max_tokens": 1800,
                },
            )
            response.raise_for_status()
            data = response.json().get("data") or {}
            if not data.get("success"):
                raise RuntimeError(data.get("error_message") or "rewrite failed")
            result = extract_json(str(data.get("content") or ""))
            title = str(result.get("title") or "").strip()
            body = str(result.get("body") or "").strip()
            if not title or not body:
                raise ValueError("rewrite returned empty title/body")
            return {"title": title, "body": body}
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(0.5 * attempt)
    raise last_error or RuntimeError("rewrite failed")


async def main() -> None:
    source = json.loads(INPUT_PATH.read_text(encoding="utf-8"))["sheets"][0]["values"]
    headers = [str(value or "") for value in source[0]]
    rows = source[1 : LIMIT + 1] if LIMIT > 0 else source[1:]
    entries = [
        entry
        for entry in json.loads(FORBIDDEN_PATH.read_text(encoding="utf-8"))["data"]["items"]
        if entry.get("enabled") is not False
    ]
    replacements = {
        str(entry["term"]): str(entry.get("replacement") or "")
        for entry in entries
        if entry.get("enforcement") == "replace" and entry.get("term")
    }
    cache: dict[str, dict[str, str]] = {}
    if CACHE_PATH.exists() and LIMIT == 0:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    previous_by_row: dict[int, dict[str, Any]] = {}
    if OUTPUT_PATH.exists() and LIMIT == 0:
        previous_by_row = {
            int(item["excel_row"]): item
            for item in json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            if item.get("excel_row")
        }

    items: list[dict[str, Any]] = []
    for offset, row in enumerate(rows, start=2):
        record = {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
        context = parse_context(record.get("上下文变量(context_list)"))
        original_title = str(record.get("标题") or "")
        original_body = str(record.get("正文") or "")
        original_text = f"{original_title}\n{original_body}"
        title = apply_replacements(original_title, replacements)
        body = apply_replacements(original_body, replacements)
        normalized_text = f"{title}\n{body}"
        hard_entries = {
            str(entry.get("term")): entry
            for entry in formal_hits(original_text, entries, "hard_ban") + formal_hits(normalized_text, entries, "hard_ban")
        }
        item = {
                **record,
                "excel_row": offset,
                "original_title": original_title,
                "original_body": original_body,
                "title": title,
                "body": body,
                "context": context,
                "activity_type": str(context.get("活动内容") or "其他"),
                "deterministic_changed": title != original_title or body != original_body,
                "hard_formal_hits": list(hard_entries.values()),
                "model_rewrite_hits": formal_hits(normalized_text, entries, "model_rewrite"),
            }
        previous = previous_by_row.get(offset)
        if previous:
            item["initial_review"] = previous.get("initial_review")
            item["initial_review_error"] = previous.get("initial_review_error")
        items.append(item)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=150) as client:
        semaphore = asyncio.Semaphore(12)

        async def review_initial(item: dict[str, Any]) -> None:
            if "initial_review" in item:
                return
            async with semaphore:
                try:
                    item["initial_review"] = await call_review(client, item)
                    item["initial_review_error"] = None
                except Exception as exc:
                    item["initial_review"] = None
                    item["initial_review_error"] = f"{type(exc).__name__}: {exc}"

        await asyncio.gather(*(review_initial(item) for item in items))

        rewrite_targets = [
            item
            for item in items
            if not item["hard_formal_hits"]
            and item["excel_row"] not in MANUAL_HARD_ROWS
            and item["excel_row"] not in MANUAL_PASS_ROWS
            and not item["initial_review_error"]
            and (
                item["excel_row"] in MANUAL_LIGHT_INSTRUCTIONS
                or
                item["model_rewrite_hits"]
                or (item["initial_review"] or {}).get("business_usability_tier") == "light_fix_usable"
            )
        ]
        rewrite_targets.extend(
            item
            for item in items
            if item["excel_row"] in MANUAL_LIGHT_INSTRUCTIONS
            and item["initial_review_error"]
            and item["excel_row"] not in {target["excel_row"] for target in rewrite_targets}
        )
        rewrite_semaphore = asyncio.Semaphore(7)

        async def rewrite_one(item: dict[str, Any]) -> None:
            key = str(item["excel_row"])
            if key in cache:
                result = cache[key]
            else:
                async with rewrite_semaphore:
                    result = await call_rewrite(client, item, rewrite_instruction(item))
                cache[key] = result
            item["title"] = apply_replacements(result["title"], replacements)
            item["body"] = apply_replacements(result["body"], replacements)
            item["was_model_rewritten"] = True

        await asyncio.gather(*(rewrite_one(item) for item in rewrite_targets))
        if LIMIT == 0:
            CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

        async def review_final(item: dict[str, Any]) -> None:
            if not item.get("was_model_rewritten"):
                item["final_review"] = item.get("initial_review")
                item["final_review_error"] = item.get("initial_review_error")
                return
            async with semaphore:
                try:
                    item["final_review"] = await call_review(client, item)
                    item["final_review_error"] = None
                except Exception as exc:
                    item["final_review"] = None
                    item["final_review_error"] = f"{type(exc).__name__}: {exc}"

        await asyncio.gather(*(review_final(item) for item in items))

    for item in items:
        text = f"{item['title']}\n{item['body']}"
        item["residual_formal_hits"] = formal_hits(text, entries)
        review = item.get("final_review") or {}
        if item.get("final_review_error"):
            item["final_status"] = "review_error"
        elif item["excel_row"] in MANUAL_HARD_ROWS:
            item["final_status"] = "hard_problem"
        elif item["excel_row"] in MANUAL_PASS_ROWS:
            item["final_status"] = "usable"
        elif item["hard_formal_hits"]:
            item["final_status"] = "hard_problem"
        elif review.get("business_usability_tier") == "hold_out":
            item["final_status"] = "hard_problem"
        elif item["residual_formal_hits"]:
            item["final_status"] = "residual_problem"
        elif review.get("business_usability_tier") == "light_fix_usable":
            item["final_status"] = "residual_problem"
        else:
            item["final_status"] = "usable"

    OUTPUT_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    status_counts: dict[str, int] = {}
    issue_counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("final_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        for issue in (item.get("final_review") or {}).get("issues") or []:
            code = str(issue.get("code") or "other")
            issue_counts[code] = issue_counts.get(code, 0) + 1
    print(
        json.dumps(
            {
                "total": len(items),
                "rewrite_targets": len(rewrite_targets),
                "status_counts": status_counts,
                "issue_counts": issue_counts,
                "output_path": str(OUTPUT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
