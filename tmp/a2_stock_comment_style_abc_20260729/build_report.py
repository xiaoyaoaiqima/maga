#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import re
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARMS = {
    "A_free": "A｜无风格样本",
    "B_full_examples": "B｜逐条完整真人示例",
    "C_texture": "C｜逐条真人风格纹理",
}
BLIND_SEED = 20260729


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


def load_items(arm: str) -> list[dict[str, str]]:
    payload = json.loads((ROOT / arm / "run_1.json").read_text(encoding="utf-8"))
    return payload["raw_output"]["items"]


def load_full_examples() -> dict[str, str]:
    text = (ROOT / "B_full_examples" / "condition.md").read_text(encoding="utf-8")
    return {
        match.group("strategy_id"): match.group("example")
        for match in re.finditer(
            r"- (?P<strategy_id>S\d{2}) / R\d{2}：`(?P<example>[^`]+)`",
            text,
        )
    }


def arm_metrics(items: list[dict[str, str]]) -> dict[str, object]:
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
    return {
        "count": len(items),
        "unique_count": len(set(comments)),
        "average_length": round(sum(len(comment) for comment in comments) / len(comments), 2),
        "max_pairwise_jaccard_2gram": pair_scores[0]["score"] if pair_scores else 0.0,
        "closest_pair": pair_scores[0] if pair_scores else None,
        "response_mode_count": len({item["response_mode"] for item in items}),
        "life_entry_count": len({item["life_entry"] for item in items}),
    }


def main() -> None:
    all_items = {arm: load_items(arm) for arm in ARMS}
    metrics = {arm: arm_metrics(items) for arm, items in all_items.items()}

    full_examples = load_full_examples()
    full_example_overlap = []
    for item in all_items["B_full_examples"]:
        strategy_id = item["strategy_id"]
        example = full_examples[strategy_id]
        full_example_overlap.append(
            {
                "strategy_id": strategy_id,
                "jaccard_2gram": round(jaccard(item["comment"], example), 4),
                "longest_common_substring": longest_common_substring(item["comment"], example),
                "comment": item["comment"],
                "example": example,
            }
        )
    metrics["B_full_examples"]["source_overlap"] = full_example_overlap

    same_strategy_scores = []
    for strategy_index in range(10):
        entries = {
            arm: all_items[arm][strategy_index]["comment"]
            for arm in ARMS
        }
        same_strategy_scores.append(
            {
                "strategy_id": all_items["A_free"][strategy_index]["strategy_id"],
                "A_vs_B": round(jaccard(entries["A_free"], entries["B_full_examples"]), 4),
                "A_vs_C": round(jaccard(entries["A_free"], entries["C_texture"]), 4),
                "B_vs_C": round(jaccard(entries["B_full_examples"], entries["C_texture"]), 4),
            }
        )
    metrics["same_strategy_cross_arm"] = same_strategy_scores
    (ROOT / "machine_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    revealed_lines = [
        "# A2 有货评论风格语料 A/B/C 结果",
        "",
        "三组都使用同一套固定内容策略；只改变风格语料条件。",
        "",
    ]
    for arm, label in ARMS.items():
        arm_metric = metrics[arm]
        revealed_lines.extend(
            [
                f"## {label}",
                "",
                (
                    f"- 10条唯一数：{arm_metric['unique_count']}；"
                    f"最大2-gram相似度：{arm_metric['max_pairwise_jaccard_2gram']}；"
                    f"最相似：{arm_metric['closest_pair']['left']} / {arm_metric['closest_pair']['right']}；"
                    f"平均字符数：{arm_metric['average_length']}。"
                ),
                "",
                "| ID | 回应模式 | 生活入口 | 评论 |",
                "|---|---|---|---|",
            ]
        )
        for item in all_items[arm]:
            revealed_lines.append(
                f"| {item['strategy_id']} | {item['response_mode']} | {item['life_entry']} | {item['comment'].replace('|', '｜')} |"
            )
        revealed_lines.append("")
    (ROOT / "revealed_preview.md").write_text("\n".join(revealed_lines), encoding="utf-8")

    blind_entries = [
        {
            "arm": arm,
            "strategy_id": item["strategy_id"],
            "comment": item["comment"],
        }
        for arm, items in all_items.items()
        for item in items
    ]
    random.Random(BLIND_SEED).shuffle(blind_entries)
    mapping = []
    blind_lines = [
        "# A2 有货评论风格实验｜匿名盲评",
        "",
        "下面30条来自三种不同风格条件，已打乱，不展示组别。请先只凭 taste 判断。",
        "",
        "单条判断：`直接可用 / 局部改写 / 整句重写`。主问题只选一个：`编造或逻辑 / 动作化 / 同骨架 / 语感不顺`；直接可用时留空。",
        "",
        "| 盲评ID | 评论 | 判断 | 主问题 | 你的改写（可选） |",
        "|---|---|---|---|---|",
    ]
    for index, entry in enumerate(blind_entries, 1):
        blind_id = f"X{index:02d}"
        mapping.append({"blind_id": blind_id, **entry})
        blind_lines.append(
            f"| {blind_id} | {entry['comment'].replace('|', '｜')} |  |  |  |"
        )
    blind_lines.extend(
        [
            "",
            "## 整组判断",
            "",
            "- 整体差异性：通过 / 边缘 / 不通过",
            "- 你认为最像的两条：",
            "- 你最想保留的5条：",
        ]
    )
    (ROOT / "blind_review.md").write_text("\n".join(blind_lines), encoding="utf-8")
    (ROOT / "blind_mapping.json").write_text(
        json.dumps({"seed": BLIND_SEED, "items": mapping}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
