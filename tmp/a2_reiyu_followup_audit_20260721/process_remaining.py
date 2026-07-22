#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
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
INPUT_PATH = WORK_DIR / "remaining_301.json"
FORBIDDEN_PATH = Path("/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/forbidden_terms_response.json")
REWRITE_CACHE_PATH = WORK_DIR / "remaining_rewrite_cache.json"
OUTPUT_PATH = WORK_DIR / "remaining_processed.json"
BASE_URL = "http://127.0.0.1:5100"

HARD_DELETE_ROWS = {47, 272, 315, 318, 414, 487, 523}
RECLASSIFIED_LIGHT_ROWS = {86, 627, 718}
RECLASSIFIED_PASS_ROWS = {524, 591}
FORCE_REWRITE_ROWS = {327, 396}


def records_from_matrix(matrix: list[list[Any]]) -> list[dict[str, Any]]:
    headers = [str(value or "") for value in matrix[0]]
    return [
        {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
        for row in matrix[1:]
    ]


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


def apply_replacements(value: str, replacements: dict[str, str]) -> str:
    text = value
    for term in sorted(replacements, key=len, reverse=True):
        text = text.replace(term, replacements[term])
    return text


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


def needs_model_rewrite(record: dict[str, Any], source_row: int) -> bool:
    if source_row == 350:
        return False
    if source_row in RECLASSIFIED_LIGHT_ROWS:
        return True
    issue_type = str(record.get("问题类型") or "")
    return any(marker in issue_type for marker in ("报名", "顺手", "顺便", "instruction_leakage", "soft_rewrite_terms"))


def rewrite_instruction(record: dict[str, Any], source_row: int) -> str:
    if source_row == 86:
        return "把‘冷水一冲就化开’改成不新增具体水温的正常冲泡表达，例如‘冲泡时很快就化开’，其他内容不改。"
    if source_row == 627:
        return "删除‘奶粉喝完了罐子存着就行’这类存空罐说法，直接自然写参加集罐可以换奶粉；不要新增旧罐、新罐或参与资格事实。"
    if source_row == 718:
        return "标题写两年、正文写大半年有冲突。以正文‘大半年’为准，只修改标题中的时长，正文尽量不动。"
    issue_type = str(record.get("问题类型") or "")
    if "instruction_leakage" in issue_type:
        return "删除‘夸夸a2、必须夸夸、删掉、啊呸’等写作指令或生成痕迹，把相关句子改成自然消费者表达。"
    if "soft_rewrite_terms" in issue_type:
        return "删除或自然改写攒罐、罐子攒起来等容易暗示空罐或旧罐的表达，直接说参加集罐；同时去掉明显AI连接词。"
    if "报名" in issue_type:
        return "活动无需报名，删除或自然改写‘报名’相关说法，保留原活动来源和参加动作。"
    if "顺手" in issue_type:
        return "自然改写‘顺手’，不要机械删除造成病句；保留原活动事实和语气。"
    if "顺便" in issue_type:
        return "自然改写‘顺便’，不要机械删除造成病句；保留原活动事实和语气。"
    return "只做最小必要修改，解决审核问题，不新增任何活动、奖品、来源或使用经历。"


def build_plan(category: str) -> dict[str, Any]:
    if category == "12罐":
        business_rule = "a2礼遇｜集罐12罐兑换1罐奶粉"
    elif category == "其他罐":
        business_rule = "a2礼遇｜其他集罐档位"
    else:
        business_rule = "a2礼遇｜抽奖、积分、老客回馈或多重福利"
    return {
        "asset_key": A2_REIYU_ARTICLE_ASSET_KEY,
        "business_rule": business_rule,
        "activity_material": [
            "集罐标准为3罐小车车、6罐自行车、12罐奶粉、18罐婴儿车",
            "抽奖奖品可写旅游基金或新西兰旅游、金手链或金手串、夏凉被",
            "积分只能累计兑换会员礼",
        ],
        "variation_slots": [{"slot_code": "审核分类", "slot_name": "审核分类", "value": category}],
    }


async def main() -> None:
    matrix = json.loads(INPUT_PATH.read_text(encoding="utf-8"))["values"]
    records = records_from_matrix(matrix)
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
    cached: dict[str, dict[str, str]] = {}
    if REWRITE_CACHE_PATH.exists():
        cached = json.loads(REWRITE_CACHE_PATH.read_text(encoding="utf-8"))

    processed: list[dict[str, Any]] = []
    rewrite_targets: list[dict[str, Any]] = []
    for record in records:
        source_row = int(record["原始行号"])
        if source_row in HARD_DELETE_ROWS:
            processed.append({**record, "source_row": source_row, "final_status": "deleted_hard", "was_rewritten": False})
            continue
        title = apply_replacements(str(record.get("标题") or ""), replacements)
        body = apply_replacements(str(record.get("正文") or ""), replacements)
        if source_row == 350:
            body = body.replace("顺便拿点权益多香啊", "有活动权益当然也想参加")
            body = body.replace("顺手领点权益多香啊", "有活动权益当然也想参加")
        original_light = record.get("审核结论") == "需轻修" or source_row in RECLASSIFIED_LIGHT_ROWS
        item = {
            **record,
            "source_row": source_row,
            "title": title,
            "body": body,
            "category": str(record.get("审核分类") or "其他"),
            "original_light": original_light,
            "was_rewritten": title != str(record.get("标题") or "") or body != str(record.get("正文") or ""),
        }
        if source_row in RECLASSIFIED_PASS_ROWS:
            item["original_light"] = False
        if item["original_light"] and needs_model_rewrite(record, source_row):
            rewrite_targets.append(item)
        processed.append(item)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=150) as client:
        semaphore = asyncio.Semaphore(8)

        async def rewrite_one(item: dict[str, Any]) -> None:
            key = str(item["source_row"])
            if key in cached and int(item["source_row"]) not in FORCE_REWRITE_ROWS:
                item["title"] = cached[key]["title"]
                item["body"] = cached[key]["body"]
                item["was_rewritten"] = True
                return
            system_prompt = "\n".join(
                [
                    "你是a2礼遇UGC后链路编辑，只做最小必要修改。",
                    "必须保留原人物、发现来源、活动机制、奖品归属、每批检测信息和产品体验。",
                    "不得新增中奖、兑换成功、领奖、旧罐参与、参与资格、奖品或新的了解来源。",
                    "改写结果不得出现‘报名、顺手、顺口、顺便’，也不得用这些词互相替换。",
                    "puq、pyq、🆓可以保留，a2和a2至初中的a必须小写。",
                    "只输出JSON：{\"title\":\"...\",\"body\":\"...\"}。",
                ]
            )
            payload = {
                "instruction": rewrite_instruction(item, int(item["source_row"])),
                "title": item["title"],
                "body": item["body"],
            }
            async with semaphore:
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
                        item["title"] = title
                        item["body"] = body
                        item["was_rewritten"] = True
                        cached[key] = {"title": title, "body": body}
                        return
                    except Exception as exc:
                        last_error = exc
                        if attempt < 3:
                            await asyncio.sleep(0.5 * attempt)
                raise last_error or RuntimeError("rewrite failed")

        await asyncio.gather(*(rewrite_one(item) for item in rewrite_targets))
        REWRITE_CACHE_PATH.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding="utf-8")

        review_targets = [item for item in processed if item.get("original_light") and item.get("final_status") != "deleted_hard"]
        review_semaphore = asyncio.Semaphore(12)

        async def review_one(item: dict[str, Any]) -> None:
            plan = build_plan(str(item["category"]))
            prompt = _user_prompt(title=item["title"], body=item["body"], plan=plan, phrase_review=None)
            async with review_semaphore:
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
                        item["review"] = parse_product_experience_llm_review(str(data.get("content") or "")).model_dump()
                        item["review_error"] = None
                        return
                    except Exception as exc:
                        last_error = exc
                        if attempt < 3:
                            await asyncio.sleep(0.5 * attempt)
                item["review"] = None
                item["review_error"] = f"{type(last_error).__name__}: {last_error}"

        await asyncio.gather(*(review_one(item) for item in review_targets))

    for item in processed:
        if item.get("final_status") == "deleted_hard":
            continue
        text = f"{item.get('title') or ''}\n{item.get('body') or ''}"
        item["formal_hits"] = [
            {
                "term": entry.get("term"),
                "enforcement": entry.get("enforcement"),
            }
            for entry in entries
            if entry_matches(text, entry)
        ]
        if item.get("review_error"):
            item["final_status"] = "review_error"
        elif item.get("review") and item["review"].get("business_usability_tier") == "hold_out":
            item["final_status"] = "hold_out_after_rewrite"
        elif item["formal_hits"]:
            item["final_status"] = "residual_forbidden"
        else:
            item["final_status"] = "usable"

    OUTPUT_PATH.write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8")
    counts: dict[str, int] = {}
    for item in processed:
        status = str(item.get("final_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({
        "total": len(processed),
        "rewrite_targets": len(rewrite_targets),
        "light_review_targets": sum(1 for item in processed if item.get("original_light")),
        "status_counts": counts,
        "output_path": str(OUTPUT_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
