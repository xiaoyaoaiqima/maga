#!/usr/bin/env python3
"""Render simple A2 mom-class prompts from a fixed story skeleton and random slots."""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLOT_CSV = REPO_ROOT / "关键词语料" / "a2妈妈班简单骨架真人表达槽位_20260705.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "outputs" / "a2_mom_class_ugc_20260705" / "simple_skeleton_rendered_prompts"

SLOT_ORDER = [
    "活动入口",
    "原始动机",
    "A2蛋白表达",
    "检测表达",
    "品牌好感反应",
    "待产包表达",
    "收尾",
]


def read_slots(path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            grouped[row["slot_name"]].append(row)
    missing = [slot for slot in SLOT_ORDER if not grouped.get(slot)]
    if missing:
        raise ValueError(f"missing slot groups: {', '.join(missing)}")
    return grouped


def render_prompt(index: int, picks: dict[str, dict[str, str]]) -> str:
    slot_lines = "\n".join(
        f"- {slot}: {picks[slot]['expression']}"
        for slot in SLOT_ORDER
    )
    risk_lines = "\n".join(
        f"- {slot}: {picks[slot]['risk_note']}"
        for slot in SLOT_ORDER
        if picks[slot].get("risk_note")
    )
    return f"""# A2 门店妈妈班简单骨架 item {index}

## 本篇抽到的真人表达槽位

{slot_lines}

## 本篇槽位风险提醒

{risk_lines}

## 固定叙事骨架

只写一件事，顺序不能乱：

1. 妈妈因为“活动入口”去参加 a2 妈妈班。
2. 用“原始动机”解释她为什么会认真听。
3. 老师讲到 a2 奶粉优点，用“A2蛋白表达”自然带出 A2型蛋白质/母R同型/亲和好吸收。
4. 老师或工作人员再讲检测，用“检测表达”带出每批检测/罐底码/对应批次报告。
5. 用“品牌好感反应”写妈妈对 a2 品牌和品质印象变好。
6. 写现场待产包/新客礼盒，用“待产包表达”承接现场收获。
7. 用“收尾”轻轻结束。

## 硬边界

- 不写买待产包、购买待产包、入手待产包、花钱买礼盒。
- 不写免费领、领取、送、薅、划算、超值。
- 不写宝宝已经出生后的使用效果。
- 不写母乳，写母R。
- A2型蛋白质只承接亲和、好吸收、小肚肚适应。
- 品质安心只能由检测、报告、罐底码、对应批次、奶源等证据承接。
- 待产包只承接现场收获、东西全、备产能用、喜欢、省心。

## 生成任务

请写 1 篇小红书 UGC 风格帖子。

输出格式：

标题：
正文：

要求：标题自然包含“待产包”或“新生儿奶粉”其一；正文自然换行，像真实妈妈随手分享；不要广告腔，不要按卖点顺序机械罗列。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-csv", type=Path, default=DEFAULT_SLOT_CSV)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260705)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    grouped = read_slots(args.slot_csv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    choices_path = args.out_dir / "slot_choices.csv"
    with choices_path.open("w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["item_no", *SLOT_ORDER]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(1, args.count + 1):
            picks = {slot: rng.choice(grouped[slot]) for slot in SLOT_ORDER}
            prompt = render_prompt(index, picks)
            (args.out_dir / f"item{index}_rendered_prompt.md").write_text(prompt, encoding="utf-8")
            writer.writerow(
                {
                    "item_no": index,
                    **{slot: picks[slot]["expression"] for slot in SLOT_ORDER},
                }
            )

    print(f"rendered {args.count} prompts -> {args.out_dir}")
    print(f"slot choices -> {choices_path}")


if __name__ == "__main__":
    main()
