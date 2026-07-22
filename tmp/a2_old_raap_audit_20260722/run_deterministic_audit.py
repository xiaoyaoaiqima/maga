#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import regex

from app.core.database import async_session_factory
from app.services.a2_reiyu_old_can_guard_service import (
    A2_REIYU_ARTICLE_ASSET_KEY,
    review_a2_reiyu_old_can_eligibility,
)
from app.services.forbidden_term_review_service import ForbiddenTermReviewService


ROOT = Path("/Users/luxifa/maga/tmp/a2_old_raap_audit_20260722")
INPUT = ROOT / "extracted_workbooks.json"
OUTPUT = ROOT / "deterministic_audit.json"

SENTENCE_SPLIT = re.compile(r"[\n。！？!?；;]+")
PRIZES = {
    3: ("小车车", "小车"),
    6: ("自行车",),
    12: ("奶粉", "正装", "产品"),
    18: ("婴儿车",),
}
ALL_COLLECT_PRIZES = tuple(dict.fromkeys(term for terms in PRIZES.values() for term in terms))
LOTTERY_PRIZES = ("旅游基金", "新西兰旅游", "金手链", "金手串", "夏凉被")
FABRICATED_REWARD = re.compile(
    r"(?:已经|成功|真的|刚|终于|这就|都)?(?:抽中|中奖|兑到|换到|拿到|领到|兑换到|收到)"
    r"[^，。；\n]{0,22}(?:旅游|基金|手链|手串|凉被|小车|自行车|奶粉|婴儿车|奖品|礼品)"
    r"|(?:娃|宝宝|孩子)[^，。；\n]{0,16}(?:拿到|收到|骑上|玩上)[^，。；\n]{0,16}(?:小车|自行车|婴儿车|奖品|礼品)"
)
INSTRUCTION_LEAK = re.compile(
    r"a2礼遇｜|本篇素材|内容方向|认可依据|产品体验原话|推荐态度原话|夸夸a2|"
    r"(?:正文|标题)[:：]|卖点|痛点|输出格式|提示词"
)
EXPLICIT_INSTRUCTION_LEAK = re.compile(
    r"(?:不对|不能写|这里要|提示词|本篇素材|输出格式|正文[:：]|标题[:：])"
)
OLD_ACTIVITY_NAMING = re.compile(r"这个活动(?:叫|名称是)|活动名称是|活动叫|叫会员礼遇活动")
BOTTOM_CODE_ENTRY = re.compile(
    r"扫罐底码[^，。；\n]{0,22}(?:抽奖|中奖|集罐|兑换|积分)|"
    r"(?:抽奖|中奖|集罐|兑换|积分)[^，。；\n]{0,22}扫罐底码"
)
POINTS_WRONG = re.compile(
    r"(?:积分|攒分)[^，。；\n]{0,18}(?:换|兑|兑换)[^，。；\n]{0,18}"
    r"(?:小车车|小车|自行车|奶粉|婴儿车|旅游基金|新西兰旅游|金手链|金手串|夏凉被)"
)
COLLECT_TO_POINTS = re.compile(r"集罐[^，。；\n]{0,16}(?:换|兑|兑换)[^，。；\n]{0,8}积分")
COLD_WATER = re.compile(r"冷水[^，。；\n]{0,10}(?:冲|泡)|(?:冲|泡)[^，。；\n]{0,10}冷水")
FIRST_TRY = re.compile(r"一直想(?:买|囤|试)|第一次(?:买|喝|尝试)|准备(?:第一次|开始)(?:喝|买|试)|刚开始喝")
LONG_TERM = re.compile(r"一直喝|喝了(?:几个月|半年|一年|好久)|长期喝|继续回购|从出生|没换过|老客|老粉|一直回购")
NO_SWITCH = re.compile(r"从出生[^，。；\n]{0,18}(?:一直喝|没换过)|一直[^，。；\n]{0,10}没换过")
SWITCHING = re.compile(r"转奶|换奶|换过[^，。；\n]{0,12}(?:品牌|奶粉)|换回来|转回来")
MULTI_SOURCE = re.compile(
    r"(?:闺蜜|朋友|同事|邻居|导购|店员|宝爸|宝妈群|妈妈群|官号|刷到)"
    r"[^。！？\n]{0,70}(?:又|还|同时|后来)"
    r"[^。！？\n]{0,20}(?:闺蜜|朋友|同事|邻居|导购|店员|宝爸|宝妈群|妈妈群|官号|刷到)"
)
OLD_CAN_EXTRA = re.compile(
    r"(?:把|将)?家里[^，。；\n]{0,8}(?:的)?罐子[^，。；\n]{0,8}(?:攒|存|留)起来|"
    r"(?:以前|之前|早先)[^，。；\n]{0,16}(?:罐子|罐)[^，。；\n]{0,16}(?:集罐|扫码|兑换|参加)|"
    r"罐子攒起来[^，。；\n]{0,20}(?:换|兑|集罐)"
)


def weighted_title_length(text: str) -> int:
    total = 0
    for grapheme in regex.findall(r"\X", text or ""):
        total += 2 if regex.search(r"\p{Extended_Pictographic}", grapheme) else 1
    return total


def context_of(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def add_hit(hits: list[dict[str, Any]], code: str, severity: str, evidence: str, reason: str) -> None:
    key = (code, evidence)
    if any((item["code"], item["evidence"]) == key for item in hits):
        return
    hits.append({"code": code, "severity": severity, "evidence": evidence, "reason": reason})


def mechanism_hits(title: str, body: str) -> list[dict[str, Any]]:
    text = f"{title}\n{body}"
    hits: list[dict[str, Any]] = []

    title_len = weighted_title_length(title)
    if title_len > 20:
        add_hit(hits, "title_too_long", "reject", f"标题加权长度 {title_len}", "审核上限为20，超过后直接淘汰。")
    if "a2至初" not in text:
        add_hit(hits, "missing_required_keyword", "reject", title or body[:40], "全文缺少必带关键词a2至初。")

    for code, pattern, severity, reason in (
        ("instruction_leakage", EXPLICIT_INSTRUCTION_LEAK, "reject", "出现明确的提示词、自我纠错或输出字段泄漏。"),
        ("bottom_code_activity_entry", BOTTOM_CODE_ENTRY, "reject", "把罐底码写成活动参加、抽奖或兑换入口。"),
        ("points_redeem_prize", POINTS_WRONG, "reject", "把集罐或抽奖奖品错误写成积分兑换。"),
        ("collect_can_redeem_points", COLLECT_TO_POINTS, "reject", "把集罐错误写成兑换积分。"),
        ("fabricated_reward_experience", FABRICATED_REWARD, "reject", "素材未提供已中奖或已兑换经历，却写成已经拿到奖品。"),
        ("activity_naming_explanation", OLD_ACTIVITY_NAMING, "light_fix", "直接解释活动叫什么，改成自然说发现a2上了活动。"),
        ("cold_water_preparation", COLD_WATER, "light_fix", "冷水冲调属于明确生活常识问题。"),
    ):
        match = pattern.search(text)
        if match:
            add_hit(hits, code, severity, match.group(0), reason)

    if FIRST_TRY.search(text) and LONG_TERM.search(text):
        add_hit(hits, "identity_conflict", "reject", "首次/一直想尝试 与 长期喝/回购 同篇出现", "消费者身份前后冲突。")
    if NO_SWITCH.search(text) and SWITCHING.search(text):
        add_hit(hits, "switching_conflict", "reject", "从出生没换过 与 转奶/换奶 同篇出现", "使用时间线明确冲突。")
    source_match = MULTI_SOURCE.search(text)
    if source_match:
        add_hit(hits, "source_stacking_watch", "watch", source_match.group(0), "可能把多个来源叠加成同一次发现，需要人工确认。")

    old_can_extra = OLD_CAN_EXTRA.search(text)
    if old_can_extra:
        add_hit(hits, "old_can_eligibility_error", "reject", old_can_extra.group(0), "把家中已有罐子与本次集罐或兑换连接。")

    soft_instruction = INSTRUCTION_LEAK.search(text)
    if soft_instruction and not EXPLICIT_INSTRUCTION_LEAK.search(text):
        add_hit(hits, "template_phrase_watch", "watch", soft_instruction.group(0), "可能是素材标签回声，也可能是自然口语，需要结合整句判断。")

    for sentence in filter(None, (item.strip() for item in SENTENCE_SPLIT.split(text))):
        for count, correct_terms in PRIZES.items():
            count_match = re.search(rf"(?:集|攒|凑|满|买)?\s*{count}\s*罐", sentence)
            if not count_match:
                continue
            tail = sentence[count_match.end() : count_match.end() + 34]
            relation = re.search(r"(?:就|还|直接|可以|能)?\s*(?:换|兑|兑换|得|领|拿)", tail)
            if not relation:
                continue
            prize_tail = tail[relation.end() :]
            first_correct = min((prize_tail.find(term) for term in correct_terms if term in prize_tail), default=10_000)
            wrong_candidates: list[tuple[int, str]] = []
            for other_count, other_terms in PRIZES.items():
                if other_count == count:
                    continue
                for term in other_terms:
                    pos = prize_tail.find(term)
                    if pos >= 0:
                        wrong_candidates.append((pos, term))
            if not wrong_candidates:
                continue
            wrong_pos, wrong_term = min(wrong_candidates)
            if wrong_pos < first_correct:
                add_hit(
                    hits,
                    "wrong_can_count_prize_mapping",
                    "reject",
                    sentence,
                    f"{count}罐档位被直接对应到{wrong_term}。",
                )
            elif any(cue in prize_tail[: wrong_pos + len(wrong_term)] for cue in ("还能换", "还可换", "另外换", "再换")):
                add_hit(
                    hits,
                    "can_count_prize_wording_ambiguous",
                    "light_fix",
                    sentence,
                    f"正确写出{count}罐档位后，又像是在同一档位追加{wrong_term}。",
                )
        if "积分" in sentence and any(term in sentence for term in ALL_COLLECT_PRIZES + LOTTERY_PRIZES):
            if any(cue in sentence for cue in ("换", "兑", "兑换", "能领", "可领")):
                add_hit(hits, "points_prize_context_watch", "watch", sentence, "积分与具体奖品同句，需要确认是否串换机制。")

    return hits


async def main() -> None:
    workbooks = json.loads(INPUT.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    body_rows: dict[str, list[str]] = defaultdict(list)
    title_rows: dict[str, list[str]] = defaultdict(list)

    async with async_session_factory() as db:
        forbidden = ForbiddenTermReviewService(db)
        for file_index, workbook in enumerate(workbooks, start=1):
            rows = workbook["sheets"][0]["values"][1:]
            for index, row in enumerate(rows, start=2):
                article_id, content_id, title, body, context_raw, status, is_test, created_at = row
                title = str(title or "")
                body = str(body or "")
                row_ref = f"文件{file_index}-第{index}行"
                body_rows[body].append(row_ref)
                title_rows[title].append(row_ref)
                context = context_of(context_raw)
                hits = mechanism_hits(title, body)

                old_can = review_a2_reiyu_old_can_eligibility(
                    title=title,
                    body=body,
                    plan={"asset_key": A2_REIYU_ARTICLE_ASSET_KEY},
                )
                for evidence in old_can.hits:
                    add_hit(hits, "old_can_eligibility_error", "reject", evidence, "把活动前家中已有库存与本次集罐资格连接。")

                audit = await forbidden.audit_text(
                    asset_key=A2_REIYU_ARTICLE_ASSET_KEY,
                    title=title,
                    body=body,
                )
                for term in audit.hits:
                    enforcement = audit.enforcements.get(term) or "rewrite"
                    severity = "reject" if enforcement in {"hard_ban", "block_only"} else "light_fix"
                    add_hit(
                        hits,
                        "forbidden_term",
                        severity,
                        term,
                        audit.term_reasons.get(term) or f"当前生产策略命中：{enforcement}",
                    )

                results.append({
                    "file_index": file_index,
                    "input_path": workbook["inputPath"],
                    "source_row": index,
                    "row_ref": row_ref,
                    "id": article_id,
                    "content_id": content_id,
                    "title": title,
                    "body": body,
                    "context": context,
                    "status": status,
                    "is_test": is_test,
                    "created_at": created_at,
                    "title_weighted_length": weighted_title_length(title),
                    "hits": hits,
                })

    duplicates = {
        "body_groups": [{"rows": rows, "body": body} for body, rows in body_rows.items() if body and len(rows) > 1],
        "title_groups": [{"rows": rows, "title": title} for title, rows in title_rows.items() if title and len(rows) > 1],
    }
    severity_counts = Counter()
    code_counts = Counter()
    for item in results:
        for hit in item["hits"]:
            severity_counts[hit["severity"]] += 1
            code_counts[hit["code"]] += 1
    payload = {
        "total": len(results),
        "files": Counter(item["file_index"] for item in results),
        "rows_with_hits": sum(bool(item["hits"]) for item in results),
        "severity_counts": severity_counts,
        "code_counts": code_counts,
        "duplicates": duplicates,
        "results": results,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    print(json.dumps({
        "total": payload["total"],
        "rows_with_hits": payload["rows_with_hits"],
        "severity_counts": dict(severity_counts),
        "code_counts": dict(code_counts),
        "duplicate_body_groups": len(duplicates["body_groups"]),
        "duplicate_title_groups": len(duplicates["title_groups"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
