#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import re
import statistics
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARMS = {
    "A_core_only": "A｜无风格语料",
    "B_shared_real_lines": "B｜共享真人原句",
    "C_surface_signatures": "C｜共享纯句面特征",
}
ROUNDS = ("round_1", "round_2", "round_3")
BLIND_SEED = 20260729
BATCH_LABELS = ("K", "M", "R")

STRATEGIES = {
    "S01": "短反应｜线上随眼看到｜一句即时反应，不展开动作",
    "S02": "库存观察｜线上连续几次看到可买｜只写自己的观察",
    "S03": "自己补到｜家里快喝完｜只写补到一罐",
    "S04": "少折腾｜以前反复确认｜现在省事一些",
    "S05": "不用刻意囤｜回应别人囤货｜按需要再买",
    "S06": "接楼回复｜别人说现在有货｜承接后补一个小观察",
    "S07": "长期留意｜老用户偶尔关注｜顺口写观察习惯",
    "S08": "前后对比｜以前较难买、现在容易些｜不绝对化",
    "S09": "短反应｜家人或朋友带回消息｜不追加行动链",
    "S10": "库存观察｜日常逛商超时看到｜不推断供货趋势",
}


def normalized(text: str) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9+]", "", text).lower()


def ngrams(text: str, size: int = 2) -> set[str]:
    value = normalized(text)
    if len(value) < size:
        return {value} if value else set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def jaccard(left: str, right: str) -> float:
    left_set = ngrams(left)
    right_set = ngrams(right)
    if not left_set and not right_set:
        return 1.0
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def longest_common_substring(left: str, right: str) -> str:
    a = normalized(left)
    b = normalized(right)
    if not a or not b:
        return ""
    table = [0] * (len(b) + 1)
    best_length = 0
    best_end = 0
    for i, left_char in enumerate(a, 1):
        previous = 0
        for j, right_char in enumerate(b, 1):
            current = table[j]
            if left_char == right_char:
                table[j] = previous + 1
                if table[j] > best_length:
                    best_length = table[j]
                    best_end = i
            else:
                table[j] = 0
            previous = current
    return a[best_end - best_length : best_end]


def load_batch(round_name: str, arm: str) -> list[dict[str, str]]:
    payload = json.loads(
        (ROOT / round_name / arm / "run_1.json").read_text(encoding="utf-8")
    )
    items = payload["raw_output"]["items"]
    expected = [f"S{index:02d}" for index in range(1, 11)]
    actual = [str(item.get("strategy_id") or "").strip() for item in items]
    if actual != expected:
        raise ValueError(f"{round_name}/{arm}: strategy mismatch: {actual}")
    return items


def source_lines() -> list[dict[str, str]]:
    payload = json.loads((ROOT / "style_sources.json").read_text(encoding="utf-8"))
    return payload["items"]


def source_overlap(comment: str, sources: list[dict[str, str]]) -> dict[str, object]:
    candidates = []
    for source in sources:
        candidates.append(
            {
                "style_ref_id": source["style_ref_id"],
                "source_text": source["text"],
                "jaccard_2gram": round(jaccard(comment, source["text"]), 4),
                "longest_common_substring": longest_common_substring(comment, source["text"]),
            }
        )
    candidates.sort(
        key=lambda item: (
            item["jaccard_2gram"],
            len(str(item["longest_common_substring"])),
        ),
        reverse=True,
    )
    return candidates[0]


def diagnostic_hits(comment: str) -> list[str]:
    checks = {
        "english_word": r"[A-Za-z]{2,}",
        "xhs_emoji_token": r"\[[^\]]+R\]",
        "laughter": r"哈哈",
        "repeated_punctuation": r"[!?！？]{2,}",
        "source_specific_word": r"cool|音效|学到|捧场|拱手|衔接|丝滑|可爱|听劝",
    }
    return [name for name, pattern in checks.items() if re.search(pattern, comment, re.I)]


def batch_metrics(
    items: list[dict[str, str]], sources: list[dict[str, str]]
) -> dict[str, object]:
    pair_scores = [
        {
            "left": left["strategy_id"],
            "right": right["strategy_id"],
            "score": round(jaccard(left["comment"], right["comment"]), 4),
        }
        for left, right in combinations(items, 2)
    ]
    pair_scores.sort(key=lambda item: item["score"], reverse=True)
    comments = [item["comment"] for item in items]
    lengths = [len(comment) for comment in comments]
    overlaps = [
        {
            "strategy_id": item["strategy_id"],
            "comment": item["comment"],
            **source_overlap(item["comment"], sources),
        }
        for item in items
    ]
    return {
        "count": len(items),
        "unique_count": len(set(comments)),
        "average_length": round(statistics.mean(lengths), 2),
        "length_stdev": round(statistics.pstdev(lengths), 2),
        "min_length": min(lengths),
        "max_length": max(lengths),
        "max_pairwise_jaccard_2gram": pair_scores[0]["score"] if pair_scores else 0.0,
        "closest_pair": pair_scores[0] if pair_scores else None,
        "response_mode_count": len({item["response_mode"] for item in items}),
        "life_entry_count": len({item["life_entry"] for item in items}),
        "source_overlap": overlaps,
        "max_source_overlap": max(
            (float(item["jaccard_2gram"]) for item in overlaps), default=0.0
        ),
        "diagnostic_hits": [
            {
                "strategy_id": item["strategy_id"],
                "comment": item["comment"],
                "hits": diagnostic_hits(item["comment"]),
            }
            for item in items
            if diagnostic_hits(item["comment"])
        ],
    }


def aggregate_metrics(metrics: dict[str, dict[str, dict[str, object]]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for arm in ARMS:
        rows = [metrics[round_name][arm] for round_name in ROUNDS]
        result[arm] = {
            "batch_count": len(rows),
            "mean_average_length": round(
                statistics.mean(float(row["average_length"]) for row in rows), 2
            ),
            "mean_length_stdev": round(
                statistics.mean(float(row["length_stdev"]) for row in rows), 2
            ),
            "mean_max_pairwise_jaccard_2gram": round(
                statistics.mean(
                    float(row["max_pairwise_jaccard_2gram"]) for row in rows
                ),
                4,
            ),
            "max_source_overlap_across_batches": max(
                float(row["max_source_overlap"]) for row in rows
            ),
            "diagnostic_hit_count": sum(
                len(row["diagnostic_hits"]) for row in rows
            ),
        }
    return result


def write_revealed(
    batches: dict[str, dict[str, list[dict[str, str]]]],
    metrics: dict[str, dict[str, dict[str, object]]],
) -> None:
    lines = [
        "# A2 有货评论风格语料实验 v2｜揭盲结果",
        "",
        "每个条件运行 3 个整批样本；每批都是一次调用生成 10 条。",
        "",
    ]
    for round_name in ROUNDS:
        lines.extend([f"## {round_name}", ""])
        for arm, label in ARMS.items():
            metric = metrics[round_name][arm]
            lines.extend(
                [
                    f"### {label}",
                    "",
                    (
                        f"- 最大组内2-gram相似度：{metric['max_pairwise_jaccard_2gram']}；"
                        f"最相似：{metric['closest_pair']['left']} / {metric['closest_pair']['right']}；"
                        f"平均长度：{metric['average_length']}；长度标准差：{metric['length_stdev']}。"
                    ),
                    "",
                    "| ID | 回应模式 | 生活入口 | 评论 |",
                    "|---|---|---|---|",
                ]
            )
            for item in batches[round_name][arm]:
                lines.append(
                    f"| {item['strategy_id']} | {item['response_mode']} | "
                    f"{item['life_entry']} | {item['comment'].replace('|', '｜')} |"
                )
            lines.append("")
    (ROOT / "revealed_preview.md").write_text("\n".join(lines), encoding="utf-8")


def write_blind_reviews(
    batches: dict[str, dict[str, list[dict[str, str]]]]
) -> None:
    randomizer = random.Random(BLIND_SEED)
    mapping: list[dict[str, object]] = []
    taste_lines = [
        "# A2 有货评论风格实验 v2｜匿名整批 taste 盲评",
        "",
        "每个匿名批次都来自一次模型调用，包含完整 10 条。请把每批当成一个生产组合判断，不展示条件、策略编号或生成顺序。",
        "",
        "每批填写：`像不同的人在说话 1-5`、`自然顺口 1-5`、`通过/边缘/不通过`、最相似两条、最想保留三条。每轮最后强制排序三个批次。",
        "",
    ]
    business_lines = [
        "# A2 有货评论风格实验 v2｜匿名业务复核",
        "",
        "这份表展示每条固定内容策略，但仍隐藏风格条件。单条判断：`直接可用 / 局部改写 / 整句重写`。主问题：`新增事实或身份 / 策略漂移 / 近抄语料 / 动作过多 / 同骨架 / 语感不顺`。",
        "",
    ]

    for round_index, round_name in enumerate(ROUNDS, 1):
        arms = list(ARMS)
        randomizer.shuffle(arms)
        taste_lines.extend([f"## 复现实验 {round_index}", ""])
        business_lines.extend([f"## 复现实验 {round_index}", ""])
        round_labels: list[str] = []
        for label_code, arm in zip(BATCH_LABELS, arms):
            batch_label = f"R{round_index}-{label_code}"
            round_labels.append(batch_label)
            shuffled_items = list(batches[round_name][arm])
            randomizer.shuffle(shuffled_items)
            taste_lines.extend(
                [
                    f"### 批次 {batch_label}",
                    "",
                    "| 条目 | 评论 |",
                    "|---|---|",
                ]
            )
            business_lines.extend(
                [
                    f"### 批次 {batch_label}",
                    "",
                    "| 条目 | 固定内容策略 | 评论 | 判断 | 主问题 |",
                    "|---|---|---|---|---|",
                ]
            )
            item_mapping = []
            for item_index, item in enumerate(shuffled_items, 1):
                blind_id = f"{batch_label}-{item_index:02d}"
                safe_comment = item["comment"].replace("|", "｜")
                taste_lines.append(f"| {blind_id} | {safe_comment} |")
                business_lines.append(
                    f"| {blind_id} | {STRATEGIES[item['strategy_id']]} | "
                    f"{safe_comment} |  |  |"
                )
                item_mapping.append(
                    {
                        "blind_id": blind_id,
                        "strategy_id": item["strategy_id"],
                        "comment": item["comment"],
                    }
                )
            taste_lines.extend(
                [
                    "",
                    "- 像不同的人在说话（1-5）：",
                    "- 自然顺口（1-5）：",
                    "- 整组：通过 / 边缘 / 不通过",
                    "- 最相似的两条：",
                    "- 最想保留的三条：",
                    "",
                ]
            )
            business_lines.append("")
            mapping.append(
                {
                    "round": round_name,
                    "batch_label": batch_label,
                    "arm": arm,
                    "arm_label": ARMS[arm],
                    "items": item_mapping,
                }
            )
        taste_lines.extend(
            [
                f"- 本轮强制排序（最好 -> 最弱）：{' / '.join(round_labels)}",
                "",
            ]
        )

    (ROOT / "blind_taste_review.md").write_text(
        "\n".join(taste_lines), encoding="utf-8"
    )
    (ROOT / "blind_business_review.md").write_text(
        "\n".join(business_lines), encoding="utf-8"
    )
    (ROOT / "blind_mapping.json").write_text(
        json.dumps({"seed": BLIND_SEED, "batches": mapping}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    sources = source_lines()
    batches = {
        round_name: {
            arm: load_batch(round_name, arm)
            for arm in ARMS
        }
        for round_name in ROUNDS
    }
    metrics = {
        round_name: {
            arm: batch_metrics(batches[round_name][arm], sources)
            for arm in ARMS
        }
        for round_name in ROUNDS
    }
    metrics["aggregate"] = aggregate_metrics(metrics)
    (ROOT / "machine_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_revealed(batches, metrics)
    write_blind_reviews(batches)


if __name__ == "__main__":
    main()
