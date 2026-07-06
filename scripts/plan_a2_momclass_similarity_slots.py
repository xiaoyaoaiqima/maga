#!/usr/bin/env python3
"""Plan diverse A2 mom-class slot combinations without generating posts."""

from __future__ import annotations

import argparse
import csv
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POOL = (
    REPO_ROOT
    / "outputs/a2_mom_class_ugc_20260705/a2_momclass_similarity_replacement_pool_v3_strict_usable_20260705.csv"
)
DEFAULT_OUTPUT_PREFIX = (
    REPO_ROOT
    / "outputs/a2_mom_class_ugc_20260705/a2_momclass_slot_diversity_plan_v1_count30"
)

PLAN_SLOTS = [
    "叙事大纲",
    "标题表达",
    "活动入口",
    "原始动机",
    "现场动作",
    "现场氛围",
    "现场社交",
    "课堂转场",
    "段落转场",
    "产品卖点表达",
    "检测表达",
    "待产包/礼遇",
    "收尾表达",
    "语气颗粒",
]

MANDATORY_SLOTS = [
    "叙事大纲",
    "活动入口",
    "原始动机",
    "课堂转场",
    "产品卖点表达",
    "检测表达",
    "待产包/礼遇",
]

OPTIONAL_SLOT_PROBABILITY = {
    "标题表达": 0.65,
    "现场动作": 0.55,
    "现场氛围": 0.12,
    "现场社交": 0.35,
    "段落转场": 0.35,
    "收尾表达": 0.45,
    "语气颗粒": 0.16,
}

SIMILARITY_SLOTS = [slot for slot in PLAN_SLOTS if slot != "叙事大纲"]


def normalize(text: str) -> str:
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text or "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？、～~—｜|+：:；;（）()“”\"\\[\\]【】,.!?]", "", text)
    return text.lower()


def ngrams(text: str, n: int = 3) -> Counter[str]:
    value = normalize(text)
    return Counter(value[i : i + n] for i in range(max(0, len(value) - n + 1)))


def cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def load_pool(path: Path, priority: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if priority and row.get("priority") != priority:
                continue
            grouped[row["slot_bucket"]].append(row)
    missing = [slot for slot in MANDATORY_SLOTS if not grouped.get(slot)]
    if missing:
        raise ValueError(f"missing mandatory slot buckets: {', '.join(missing)}")
    return grouped


def candidate_text(row: dict[str, str] | None) -> str:
    if not row:
        return ""
    return row.get("candidate_expression", "")


def plan_text(plan: dict[str, dict[str, str] | None]) -> str:
    parts = []
    for slot in SIMILARITY_SLOTS:
        text = candidate_text(plan.get(slot))
        if text:
            parts.append(text)
    return "\n".join(parts)


def max_similarity(plans: list[dict[str, dict[str, str] | None]]) -> tuple[float, tuple[int, int] | None]:
    vectors = [ngrams(plan_text(plan)) for plan in plans]
    best = 0.0
    pair = None
    for i, left in enumerate(vectors):
        for j in range(i + 1, len(vectors)):
            score = cosine(left, vectors[j])
            if score > best:
                best = score
                pair = (i + 1, j + 1)
    return round(best, 3), pair


def pick_unique(
    rng: random.Random,
    rows: list[dict[str, str]],
    used_exact: set[str],
    preferred_sub_bucket: str | None = None,
) -> dict[str, str]:
    candidates = rows
    if preferred_sub_bucket:
        preferred = [row for row in rows if row.get("sub_bucket") == preferred_sub_bucket]
        if preferred:
            candidates = preferred
    fresh = [row for row in candidates if row["candidate_expression"] not in used_exact]
    if not fresh:
        fresh = [row for row in rows if row["candidate_expression"] not in used_exact] or rows
    row = rng.choice(fresh)
    used_exact.add(row["candidate_expression"])
    return row


def choose_product_sub_bucket(index: int, count: int) -> str | None:
    # A2 remains the dominant卖点, but not every item uses the same protein sentence.
    a2_cutoff = max(1, round(count * 0.5))
    if index <= a2_cutoff:
        return "A2型蛋白"
    return None


def choose_detection_sub_bucket(index: int) -> str:
    cycle = ["报告入口", "每批检测", "三方报告", "60+项质检", "蜡样标准轻对比"]
    return cycle[(index - 1) % len(cycle)]


def build_once(
    grouped: dict[str, list[dict[str, str]]],
    count: int,
    seed: int,
) -> list[dict[str, dict[str, str] | None]]:
    rng = random.Random(seed)
    used_exact: dict[str, set[str]] = defaultdict(set)
    plans: list[dict[str, dict[str, str] | None]] = []

    for index in range(1, count + 1):
        plan: dict[str, dict[str, str] | None] = {}
        for slot in PLAN_SLOTS:
            if slot in OPTIONAL_SLOT_PROBABILITY and rng.random() > OPTIONAL_SLOT_PROBABILITY[slot]:
                plan[slot] = None
                continue
            if slot not in grouped:
                plan[slot] = None
                continue
            if slot in OPTIONAL_SLOT_PROBABILITY and len(used_exact[slot]) >= len(grouped[slot]):
                plan[slot] = None
                continue

            preferred = None
            if slot == "产品卖点表达":
                preferred = choose_product_sub_bucket(index, count)
            elif slot == "检测表达":
                preferred = choose_detection_sub_bucket(index)

            plan[slot] = pick_unique(rng, grouped[slot], used_exact[slot], preferred)
        plans.append(plan)

    return plans


def find_plan(
    grouped: dict[str, list[dict[str, str]]],
    count: int,
    seed: int,
    target: float,
    attempts: int,
) -> tuple[list[dict[str, dict[str, str] | None]], float, tuple[int, int] | None, int]:
    best_plans: list[dict[str, dict[str, str] | None]] = []
    best_score = 1.0
    best_pair = None
    best_attempt = 0
    for attempt in range(attempts):
        plans = build_once(grouped, count, seed + attempt)
        score, pair = max_similarity(plans)
        if score < best_score:
            best_plans = plans
            best_score = score
            best_pair = pair
            best_attempt = attempt + 1
        if score <= target:
            return plans, score, pair, attempt + 1
    return best_plans, best_score, best_pair, best_attempt


def write_csv(path: Path, plans: list[dict[str, dict[str, str] | None]], batch_id: str) -> None:
    fieldnames = [
        "batch_id",
        "item_no",
        *[f"{slot}_sub_bucket" for slot in PLAN_SLOTS],
        *[f"{slot}_expression" for slot in PLAN_SLOTS],
        *[f"{slot}_source" for slot in PLAN_SLOTS],
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item_no, plan in enumerate(plans, 1):
            row = {"batch_id": batch_id, "item_no": item_no}
            for slot in PLAN_SLOTS:
                picked = plan.get(slot)
                row[f"{slot}_sub_bucket"] = picked.get("sub_bucket", "") if picked else ""
                row[f"{slot}_expression"] = picked.get("candidate_expression", "") if picked else ""
                row[f"{slot}_source"] = (
                    f"{picked.get('source_file', '')} {picked.get('source_ref', '')}" if picked else ""
                )
            writer.writerow(row)


def write_preview(
    path: Path,
    plans: list[dict[str, dict[str, str] | None]],
    batch_id: str,
    score: float,
    pair: tuple[int, int] | None,
    attempt: int,
    target: float,
) -> None:
    exact_counter = Counter()
    sub_bucket_counter = Counter()
    for plan in plans:
        for slot, picked in plan.items():
            if not picked:
                continue
            exact_counter[(slot, picked["candidate_expression"])] += 1
            sub_bucket_counter[(slot, picked.get("sub_bucket", ""))] += 1

    repeated = [(slot, expr, count) for (slot, expr), count in exact_counter.items() if count > 1]
    repeated.sort(key=lambda item: (-item[2], item[0], item[1]))

    lines = [
        "# a2妈妈班 slot diversity plan",
        "",
        f"- batch_id: `{batch_id}`",
        f"- count: {len(plans)}",
        f"- target max similarity: {target}",
        f"- planned max similarity: **{score}** pair {pair}",
        f"- selected attempt: {attempt}",
        f"- exact expression repeats: {len(repeated)}",
        "",
        "## Sub-Bucket Distribution",
        "",
    ]
    for slot in PLAN_SLOTS:
        slot_counts = [(sub, count) for (slot_name, sub), count in sub_bucket_counter.items() if slot_name == slot]
        if not slot_counts:
            continue
        lines.append(f"### {slot}")
        for sub, count in sorted(slot_counts, key=lambda item: (-item[1], item[0])):
            lines.append(f"- {sub or '未分桶'}: {count}")
        lines.append("")

    lines.append("## Exact Repeats")
    if repeated:
        for slot, expr, count in repeated[:50]:
            lines.append(f"- {slot} x{count}: {expr}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Plans")
    for item_no, plan in enumerate(plans, 1):
        lines.append(f"### Item {item_no}")
        for slot in PLAN_SLOTS:
            picked = plan.get(slot)
            if not picked:
                continue
            lines.append(f"- **{slot}** `{picked.get('sub_bucket', '')}`: {picked['candidate_expression']}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--batch-id", default="a2_momclass_slot_diversity_plan_v1")
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260705)
    parser.add_argument("--target", type=float, default=0.3)
    parser.add_argument("--attempts", type=int, default=200)
    parser.add_argument("--priority", default="A")
    args = parser.parse_args()

    grouped = load_pool(args.pool, args.priority)
    plans, score, pair, attempt = find_plan(
        grouped=grouped,
        count=args.count,
        seed=args.seed,
        target=args.target,
        attempts=args.attempts,
    )

    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_prefix.with_suffix(".csv")
    preview_path = args.output_prefix.with_name(args.output_prefix.name + "_preview.md")
    write_csv(csv_path, plans, args.batch_id)
    write_preview(preview_path, plans, args.batch_id, score, pair, attempt, args.target)

    print(f"planned {len(plans)} slot plans")
    print(f"max_similarity={score} pair={pair} attempt={attempt}")
    print(f"csv={csv_path}")
    print(f"preview={preview_path}")


if __name__ == "__main__":
    main()
