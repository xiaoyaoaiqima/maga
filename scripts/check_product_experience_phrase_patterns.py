#!/usr/bin/env python3
"""Mark repeated phrase patterns in 产品使用体验 generation reports.

This is a QA marker, not a rewriting tool. It flags batch-level repetition
such as "选奶纠结 -> 贵 -> 孩子愿意喝 -> 省心/踏实" so operators can review
whether generated product-experience posts sound like one author.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SKELETON_PARTS: dict[str, list[str]] = {
    "selection_process": [
        "纠结",
        "犹豫",
        "做功课",
        "翻成分表",
        "看成分表",
        "对比",
        "看评价",
        "问朋友",
        "问店员",
        "选奶",
        "换奶",
    ],
    "price": [
        "贵",
        "不便宜",
        "价格",
        "肉疼",
        "趁活动",
        "不是便宜",
        "不算便宜",
        "小贵",
    ],
    "kid_acceptance": [
        "愿意喝",
        "不排斥",
        "不抗拒",
        "接受",
        "能接受",
        "喝完",
        "咕咚",
        "顺口",
        "口味",
        "主动要喝",
    ],
    "ai_closure": [
        "省心",
        "踏实",
        "固定",
        "固定下来",
        "这事先这么放着",
        "不用临时凑",
        "不用额外想",
        "心里有数",
        "好执行",
        "省得",
        "先这样",
        "继续喝着",
    ],
}

AI_PHRASES = [
    "省心",
    "踏实",
    "固定下来",
    "这事先这么放着",
    "不用每天临时凑",
    "不用临时凑",
    "不用额外想一堆",
    "不用额外想",
    "孩子愿意喝就好执行",
    "早上冲得快",
    "价格不算友好",
    "心里有数",
    "没那么焦虑",
    "流程",
    "放进日常",
    "固定在日常",
]

STRONG_REAL_PHRASES = [
    "没再半夜闹腾",
    "不容易中招",
    "精力恢复得快",
    "一直挺稳",
    "可能跟每天那杯旺玥有关系",
    "可能跟每天那杯有关系",
    "坐不住",
    "坐不久",
    "精神头明显不如上午",
    "正餐吃少也不怕",
    "接触杂了也不容易中招",
    "请病假少",
    "少请假",
    "长个",
    "窜个",
    "抵抗力",
]

HARD_RISK_PHRASES = [
    "保证长高",
    "一定长高",
    "喝了就不生病",
    "不生病了",
    "再也不生病",
    "提高免疫力",
    "增强免疫力",
    "免疫力提高",
    "治疗",
    "改善乳糖不耐受",
    "乳糖不耐受好转",
    "专注力提升",
    "专注力变好",
]

MONITORED_PHRASES = sorted(
    {
        phrase
        for phrases in SKELETON_PARTS.values()
        for phrase in phrases
    }
    | set(AI_PHRASES)
    | {
        "老母亲",
        "不踩坑",
        "安排上",
        "喝了一阵",
        "喝了几个月",
        "旺玥和4段",
    },
    key=len,
    reverse=True,
)


@dataclass
class BatchContext:
    source_file: str
    batch_id: str
    batch_code: str
    product_topic: str


@dataclass
class ItemQa:
    row: dict[str, str]
    monitored_hits: set[str]
    complete_skeleton_hit: bool
    hard_risk_count: int
    strong_real_count: int
    ai_phrase_count: int


def load_report(path: Path) -> tuple[BatchContext, list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        items = data.get("items")
        if not isinstance(items, list):
            raise ValueError(f"{path} does not contain data.items")
        context = BatchContext(
            source_file=str(path),
            batch_id=str(data.get("batch_id") or ""),
            batch_code=str(data.get("batch_code") or ""),
            product_topic=str(data.get("product_topic") or ""),
        )
        return context, items
    if isinstance(data, list):
        context = BatchContext(str(path), "", "", "")
        return context, data
    raise ValueError(f"{path} is not a supported batch report JSON")


def compact_hits(text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if phrase and phrase in text]


def skeleton_hits(text: str) -> dict[str, list[str]]:
    return {
        part: compact_hits(text, phrases)
        for part, phrases in SKELETON_PARTS.items()
        if compact_hits(text, phrases)
    }


def extract_business_fields(item: dict[str, Any]) -> dict[str, str]:
    snapshot = item.get("generation_snapshot") if isinstance(item.get("generation_snapshot"), dict) else {}
    business_rule = snapshot.get("business_rule") if isinstance(snapshot.get("business_rule"), dict) else {}
    corpus = str(business_rule.get("corpus") or "")
    fields = {
        "product_experience": str(business_rule.get("product_experience") or ""),
        "rule_id": str(business_rule.get("rule_id") or ""),
        "rule_asset_version": str(business_rule.get("rule_asset_version") or ""),
        "source_row_no": str(business_rule.get("source_row_no") or ""),
        "painpoint": "",
        "scene": str(item.get("scene_type") or ""),
        "selling_direction": "",
    }

    patterns = {
        "painpoint": r"痛点词：([^；。\n]+)",
        "scene": r"场景：([^；。\n]+)",
        "selling_direction": r"卖点方向：([^；。\n]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, corpus)
        if match:
            fields[key] = match.group(1).strip()
    return fields


def make_item_qa(context: BatchContext, item: dict[str, Any]) -> ItemQa:
    title = str(item.get("title") or "")
    body = str(item.get("body") or item.get("body_preview") or "")
    text = f"{title}\n{body}"
    skeleton = skeleton_hits(body)
    skeleton_parts = sorted(skeleton)
    complete_skeleton_hit = len(skeleton_parts) >= 3
    ai_hits = compact_hits(body, AI_PHRASES)
    strong_real_hits = compact_hits(body, STRONG_REAL_PHRASES)
    hard_risk_hits = compact_hits(body, HARD_RISK_PHRASES)
    monitored_hits = set(compact_hits(body, MONITORED_PHRASES))
    business = extract_business_fields(item)
    phrase_score = (
        len(skeleton_parts) * 20
        + len(ai_hits) * 8
        + (20 if complete_skeleton_hit else 0)
        + len(hard_risk_hits) * 100
        + min(len(strong_real_hits), 2) * 2
    )
    if hard_risk_hits:
        qa_label = "hard_risk"
    elif complete_skeleton_hit:
        qa_label = "complete_skeleton_review"
    elif ai_hits:
        qa_label = "ai_phrase_review"
    elif strong_real_hits:
        qa_label = "strong_real_keep_review"
    else:
        qa_label = "ok"

    notes: list[str] = []
    if complete_skeleton_hit:
        notes.append("命中3类以上选奶-价格-接受-收口骨架")
    if set(skeleton_parts) == set(SKELETON_PARTS):
        notes.append("完整4段骨架")
    if hard_risk_hits:
        notes.append("硬风险词需人工处理")
    if strong_real_hits and not hard_risk_hits:
        notes.append("真人强表达，先标记不拦截")

    row = {
        "source_file": context.source_file,
        "batch_id": context.batch_id,
        "batch_code": context.batch_code,
        "item_no": str(item.get("item_no") or ""),
        "item_id": str(item.get("item_id") or ""),
        "title": title,
        "body": body,
        "body_chars": str(item.get("body_chars") or len(body)),
        "product_topic": context.product_topic,
        "product_experience": business["product_experience"],
        "painpoint": business["painpoint"],
        "scene": business["scene"],
        "selling_direction": business["selling_direction"],
        "rule_id": business["rule_id"],
        "rule_asset_version": business["rule_asset_version"],
        "source_row_no": business["source_row_no"],
        "complete_skeleton_hit": "yes" if complete_skeleton_hit else "no",
        "skeleton_part_count": str(len(skeleton_parts)),
        "skeleton_parts": ";".join(skeleton_parts),
        "skeleton_hits": json.dumps(skeleton, ensure_ascii=False, sort_keys=True),
        "ai_phrase_hits": ";".join(ai_hits),
        "price_expression_hits": ";".join(skeleton.get("price", [])),
        "strong_real_expression_hits": ";".join(strong_real_hits),
        "hard_risk_hits": ";".join(hard_risk_hits),
        "overfreq_phrase_hits": "",
        "phrase_score": str(phrase_score),
        "qa_label": qa_label,
        "notes": "；".join(notes),
    }
    return ItemQa(
        row=row,
        monitored_hits=monitored_hits,
        complete_skeleton_hit=complete_skeleton_hit,
        hard_risk_count=len(hard_risk_hits),
        strong_real_count=len(strong_real_hits),
        ai_phrase_count=len(ai_hits),
    )


def batch_key(item: ItemQa) -> str:
    return item.row["batch_id"] or Path(item.row["source_file"]).stem


def apply_overfrequency(items: list[ItemQa], ratio: float, min_count: int) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in items:
        counts.update(item.monitored_hits)

    by_batch: dict[str, list[ItemQa]] = defaultdict(list)
    for item in items:
        by_batch[batch_key(item)].append(item)

    for batch_items in by_batch.values():
        batch_counts: Counter[str] = Counter()
        for item in batch_items:
            batch_counts.update(item.monitored_hits)
        threshold = max(min_count, math.floor(len(batch_items) * ratio) + 1)
        overfreq = Counter({phrase: count for phrase, count in batch_counts.items() if count >= threshold})
        for item in batch_items:
            hits = sorted((phrase for phrase in item.monitored_hits if phrase in overfreq), key=lambda p: (-overfreq[p], p))
            item.row["overfreq_phrase_hits"] = ";".join(f"{phrase}({overfreq[phrase]}/{len(batch_items)})" for phrase in hits)
            if hits:
                item.row["notes"] = "；".join(filter(None, [item.row["notes"], "批次超频词"]))
    return counts


def write_csv(path: Path, items: list[ItemQa]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_file",
        "batch_id",
        "batch_code",
        "item_no",
        "item_id",
        "title",
        "body",
        "body_chars",
        "product_topic",
        "product_experience",
        "painpoint",
        "scene",
        "selling_direction",
        "rule_id",
        "rule_asset_version",
        "source_row_no",
        "complete_skeleton_hit",
        "skeleton_part_count",
        "skeleton_parts",
        "skeleton_hits",
        "ai_phrase_hits",
        "price_expression_hits",
        "strong_real_expression_hits",
        "hard_risk_hits",
        "overfreq_phrase_hits",
        "phrase_score",
        "qa_label",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(item.row)


def print_summary(items: list[ItemQa], phrase_counts: Counter[str]) -> None:
    by_batch: dict[str, list[ItemQa]] = defaultdict(list)
    for item in items:
        by_batch[batch_key(item)].append(item)

    print(f"items={len(items)}")
    for batch_id, batch_items in by_batch.items():
        complete = sum(item.complete_skeleton_hit for item in batch_items)
        ai_rows = sum(item.ai_phrase_count > 0 for item in batch_items)
        hard = sum(item.hard_risk_count > 0 for item in batch_items)
        strong = sum(item.strong_real_count > 0 for item in batch_items)
        print(
            "batch="
            f"{batch_id} items={len(batch_items)} "
            f"complete_skeleton={complete} "
            f"ai_phrase_rows={ai_rows} "
            f"strong_real_rows={strong} "
            f"hard_risk_rows={hard}"
        )

    print("top_phrase_frequencies:")
    for phrase, count in phrase_counts.most_common(20):
        print(f"  {phrase}: {count}/{len(items)}")


def default_output_path(inputs: list[Path]) -> Path:
    if len(inputs) == 1:
        return inputs[0].with_name(f"phrase_qa_{inputs[0].stem}.csv")
    parent = inputs[0].parent
    return parent / "phrase_qa_comparison.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="batch_report JSON file(s)")
    parser.add_argument("--output", "-o", type=Path, help="CSV output path")
    parser.add_argument("--overfreq-ratio", type=float, default=0.20, help="row ratio for batch phrase over-frequency")
    parser.add_argument("--overfreq-min-count", type=int, default=4, help="minimum rows for batch phrase over-frequency")
    args = parser.parse_args()

    qa_items: list[ItemQa] = []
    for report in args.reports:
        context, items = load_report(report)
        qa_items.extend(make_item_qa(context, item) for item in items)

    phrase_counts = apply_overfrequency(qa_items, args.overfreq_ratio, args.overfreq_min_count)
    output = args.output or default_output_path(args.reports)
    write_csv(output, qa_items)
    print_summary(qa_items, phrase_counts)
    print(f"wrote={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
