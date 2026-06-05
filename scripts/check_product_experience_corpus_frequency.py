#!/usr/bin/env python3
"""Check 产品使用体验 reference-material frequency.

The gate is intentionally strict for reusable time words, life-scene words,
and scene combinations. Core topic semantics are not grouped broadly here:
for example, a 便便问题 row may naturally talk about 拉的状态, but repeated
surface phrases such as 纸尿裤 or 纸尿裤+小硬粒 should stay under the cap.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = REPO_ROOT / "关键词语料" / "产品使用体验_子关键词导出.csv"

TIME_TERMS = [
    "刚喝不久",
    "转奶第2周",
    "喝了十几天",
    "尝试了一周多",
    "才喝半个月",
    "刚转过来没几天",
    "喝了不到10天",
    "这两周下来",
    "转源悦第3个月",
    "差不多两个月整",
    "喝了60多天",
    "近两个月",
    "近两个月看下来",
    "喝到第三个月",
    "喝了大半年",
    "半年真实反馈",
    "喝了180多天",
    "第6个月打卡",
    "喝了小半年",
    "持续喝中",
    "持续喝着",
    "喝了有一段时间",
    "这段时间下来",
    "喝了一段时间",
    "这些日子",
    "这一小段时间",
    "喝了有些天",
    "这几个月下来",
    "从第一次喝到现在",
    "不到俩月",
    "喝了几个月",
    "三四个月左右",
    "快小半年",
    "第5个月打卡",
    "一直喝着",
    "喝了挺久",
    "刚喝不到俩星期",
]

LIFE_TERMS = [
    "纸尿裤",
    "尿不湿",
    "喝奶",
    "辅食",
    "睡前",
    "晚上",
    "嗯嗯",
    "出门",
    "称重",
    "玩具",
    "白天",
    "抱起来",
    "趴",
    "有点肉",
    "便便",
    "吃饭",
    "脸上",
    "哄",
    "奶这一顿",
    "喝这一顿",
    "米糊",
    "小碗饭",
    "吃的东西",
    "饭菜",
    "临睡那顿",
    "睡觉前那顿",
    "快睡那顿",
    "夜里",
    "臭臭",
    "拉出来的状态",
    "带出去",
    "外出",
    "上称",
    "布书",
]

TERM_LIMIT_OVERRIDES = {
    # Exact `纸尿裤` was still too visible at the generic 5% cap.
    "纸尿裤": 3,
}

BANNED_PHRASES = [
    "猜来猜去",
    "围着这事儿猜",
    "围着这事猜",
    "围着厕所这事猜",
    "围绕纸尿裤、嗯嗯频率、软硬",
]

COMBO_PATTERNS = [
    r"洗澡.*小腿",
    r"小腿.*称重",
    r"洗澡.*称重",
    r"纸尿裤.*嗯嗯",
    r"纸尿裤.*小硬粒",
    r"纸尿裤.*好收拾",
    r"睡前.*220ml",
    r"睡前.*追着",
    r"出门.*睡醒",
    r"出门.*玩具",
    r"辅食.*奶",
    r"玩具.*分心",
    r"抱起来.*实在",
    r"喝奶.*跑神",
    r"米糊.*奶",
    r"吃的东西.*奶",
    r"临睡那顿.*220ml",
    r"睡觉前那顿.*220ml",
    r"快睡那顿.*220ml",
    r"尿不湿.*拉",
]


@dataclass
class Reference:
    row_no: int
    key: str
    text: str


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        content = "".join(line for line in f if not line.lstrip("\ufeff").startswith("#"))
    return list(csv.DictReader(io.StringIO(content)))


def extract_references(rows: list[dict[str, str]]) -> list[Reference]:
    refs: list[Reference] = []
    for row_no, row in enumerate(rows, 1):
        in_ref = False
        for line in row["语料"].splitlines():
            s = line.strip()
            if s == "可参考素材：":
                in_ref = True
                continue
            if in_ref and s.startswith("注意："):
                in_ref = False
            if in_ref and s.startswith("- "):
                refs.append(Reference(row_no, row["产品使用体验"], s[2:].strip()))
    return refs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", nargs="?", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--ratio", type=float, default=0.05)
    parser.add_argument("--show-ok", action="store_true")
    args = parser.parse_args()

    rows = read_rows(args.csv_path)
    refs = extract_references(rows)
    limit = math.floor(len(refs) * args.ratio)
    failures: list[tuple[str, str, int]] = []

    print(f"refs={len(refs)} ratio={args.ratio:.2%} strict_limit={limit}")

    for term in TIME_TERMS + LIFE_TERMS:
        count = sum(term in ref.text for ref in refs)
        term_limit = TERM_LIMIT_OVERRIDES.get(term, limit)
        block_count = sum(term in row["语料"] for row in rows) if term in TERM_LIMIT_OVERRIDES else count
        if count > term_limit or block_count > term_limit:
            failures.append(("term", f"{term} (refs {count}, blocks {block_count}, limit {term_limit})", max(count, block_count)))
        elif args.show_ok and count:
            print(f"OK term {count:>3}/{term_limit:<3} {term}")

    for pattern in COMBO_PATTERNS:
        regex = re.compile(pattern)
        count = sum(bool(regex.search(ref.text)) for ref in refs)
        if count > limit:
            failures.append(("combo", pattern, count))
        elif args.show_ok and count:
            print(f"OK combo {count:>3} {pattern}")

    for phrase in BANNED_PHRASES:
        ref_count = sum(phrase in ref.text for ref in refs)
        block_count = sum(phrase in row["语料"] for row in rows)
        if ref_count or block_count:
            failures.append(("banned", f"{phrase} (refs {ref_count}, blocks {block_count})", ref_count + block_count))

    if failures:
        for kind, name, count in failures:
            print(f"FAIL {kind} {count:>3} > {limit}: {name}")
        return 1

    print("OK: all monitored terms and combinations are within the strict cap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
