"""Extract review candidates for Wangyue real-user prompt layers from operator UGC CSV."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.real_user_example_pool_service import (  # noqa: E402
    infer_real_user_risk_tags,
    infer_real_user_tags,
    _clean_text,
    _normalize_for_match,
    _short_hash,
)


BLOCK_TERMS = (
    "乳糖不耐受",
    "无乳糖",
    "乳糖酶",
    "金领冠",
    "爱他美",
    "长到",
    "185",
    "13岁",
    "14岁",
    "3周岁",
    "三周岁",
    "4段",
    "三段",
    "3段",
    "一段",
    "二段",
    "新生儿",
    "宝宝",
    "宝妈",
    "奶瓶",
    "自己冲",
    "自己泡",
    "塞书包",
    "路上喝",
    "攻略",
    "推荐",
    "哪里买",
    "在哪买",
    "评论区",
)

OPENING_TERMS = ("当妈后", "选奶", "对比", "纠结", "又开", "喝了", "刚开始", "之前")
ENDING_TERMS = ("值了", "没毛病", "没缺点", "先喝", "试试看", "不打算换", "给点建议", "纠结不出来")
TEXTURE_TERMS = ("贵", "嫌贵", "纠结", "头疼", "不懂", "全都不喝", "不喝", "好喝", "放心", "肉疼", "比不来")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract Wangyue UGC layer candidates for manual review.")
    parser.add_argument("csv_path", help="Operator-collected Wangyue UGC CSV.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    candidates, stats = extract_candidates(Path(args.csv_path).expanduser())
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "suggested_layer",
                "prompt_text",
                "reason",
                "title",
                "source_field",
                "row_no",
                "tags",
                "risk_tags",
                "dedupe_hash",
            ],
        )
        writer.writeheader()
        writer.writerows(candidates)
    print({"candidate_count": len(candidates), "stats": dict(stats), "output": str(output_path)})


def extract_candidates(csv_path: Path) -> tuple[list[dict[str, Any]], Counter[str]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats: Counter[str] = Counter()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row_no, row in enumerate(csv.DictReader(f), 1):
            stats["read_rows"] += 1
            title = _clean_text(row.get("标题"), limit=80)
            body = _clean_text(row.get("正文"), limit=500)
            for text, source_field in _fragments(title, body):
                stats["fragment_seen"] += 1
                normalized = _normalize_for_match(text)
                if normalized in seen:
                    stats["duplicate"] += 1
                    continue
                seen.add(normalized)
                if _blocked(text):
                    stats["blocked"] += 1
                    continue
                layer, reason = _suggest_layer(text)
                if not layer:
                    stats["unclassified"] += 1
                    continue
                match_text = f"{title} {body}"
                risk_tags = infer_real_user_risk_tags(match_text, source_type="note")
                if {"竞品品牌", "产品动作风险"} & set(risk_tags):
                    stats["source_risk_blocked"] += 1
                    continue
                candidates.append(
                    {
                        "suggested_layer": layer,
                        "prompt_text": text,
                        "reason": reason,
                        "title": title,
                        "source_field": source_field,
                        "row_no": row_no,
                        "tags": "；".join(infer_real_user_tags(match_text)),
                        "risk_tags": "；".join(risk_tags),
                        "dedupe_hash": _short_hash("wangyue_ugc_layer", layer, text),
                    }
                )
                stats[f"kept:{layer}"] += 1
    return candidates, stats


def _fragments(title: str, body: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if title and title != "/":
        result.append((title, "title"))
    for sentence in re.split(r"[\n\r]+|(?<=[。！？!?；;])", body):
        sentence = sentence.strip(" \t，,。！？!?；;、")
        if not sentence:
            continue
        clauses = [
            clause.strip(" \t，,。！？!?；;、")
            for clause in re.split(r"[，,、；;]", sentence)
            if clause.strip(" \t，,。！？!?；;、")
        ]
        for item in [sentence, *clauses]:
            if 4 <= len(item) <= 42:
                result.append((item, "body_fragment"))
    return result


def _blocked(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(_normalize_for_match(term) in normalized for term in BLOCK_TERMS)


def _suggest_layer(text: str) -> tuple[str, str]:
    normalized = _normalize_for_match(text)
    if any(_normalize_for_match(term) in normalized for term in ENDING_TERMS):
        return "ending", "ending_term"
    if any(_normalize_for_match(term) in normalized for term in TEXTURE_TERMS):
        return "texture", "texture_term"
    if any(_normalize_for_match(term) in normalized for term in OPENING_TERMS):
        return "opening_texture", "opening_term"
    return "", ""


if __name__ == "__main__":
    main()
