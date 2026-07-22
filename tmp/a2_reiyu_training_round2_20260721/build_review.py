#!/usr/bin/env python3
"""Build the second A2 reiyu v11 training preview and stability comparison."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path


BATCH_ID = 746
BASELINE_BATCH_ID = 731
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_training_round2_20260721")
INITIAL_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_match_review_20260721")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")

INITIAL_ISSUES = {
    1: "标题写成自己抽到旅游大奖，形成中奖经历。",
    2: "用活动页面承接每批检测；后链路连续两轮改写仍未去掉。",
    3: "出现‘顺手’；后链路连续两轮改写仍写回同类连接词。",
    4: "标题‘积分随便换’夸大积分兑换边界。",
    5: "开头泄漏内容方向原句，并写活动页里看到检测。",
    6: "写活动那页提到检测，未被现有页面上下文规则识别。",
    9: "编造已经换到小车车、宝宝拿到手玩耍的经历。",
    10: "把购买好几罐直接写成兑换资格，并从活动信息承接检测。",
}
DIRECT_ITEMS = [7, 8]
REVISED_ITEMS = [1, 2, 3, 4, 5, 6, 9, 10]
DETERMINISTIC_ITEMS = [1, 3, 5, 7, 9]
SEMANTIC_REWRITE_ITEMS = [2, 3, 4, 5, 10]
MACHINE_POSTPROCESS_PASS_ITEMS = [1, 4, 5, 7, 9, 10]
MACHINE_UNRESOLVED_ITEMS = [2, 3]


def title_weighted_length(title: str) -> int:
    total = 0
    for char in re.sub(r"\s+", "", title.strip()):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if EMOJI_RE.fullmatch(char) else 1
    return total


def write_random_prompt(items: list[dict]) -> Path:
    item = random.SystemRandom().choice([item for item in items if item.get("rendered_prompt")])
    path = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item{item['item_no']}.md"
    path.write_text(
        "\n".join(
            [
                "# A2礼遇v11第二批稳定性训练｜随机完整Prompt",
                "",
                f"- batch_id: {BATCH_ID}",
                f"- item_no: {item['item_no']}",
                f"- title: {item['title']}",
                f"- business_rule: {item.get('business_rule') or ''}",
                "",
                "```text",
                item["rendered_prompt"],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def main() -> None:
    initial_report_path = INITIAL_DIR / f"batch{BATCH_ID}_report.json"
    initial_details_path = INITIAL_DIR / f"batch{BATCH_ID}_details.json"
    final_report_path = OUTPUT_DIR / f"batch{BATCH_ID}_report.json"
    final_details_path = OUTPUT_DIR / f"batch{BATCH_ID}_details.json"

    initial_report = json.loads(initial_report_path.read_text(encoding="utf-8"))["data"]
    initial_items = json.loads(initial_details_path.read_text(encoding="utf-8"))
    final_report = json.loads(final_report_path.read_text(encoding="utf-8"))["data"]
    final_items = json.loads(final_details_path.read_text(encoding="utf-8"))
    final_by_no = {item["item_no"]: item for item in final_items}
    prompt_path = write_random_prompt(final_items)

    raw_content_count = sum(
        bool((item.get("title") or "").strip() and (item.get("body") or "").strip())
        for item in initial_items
    )
    title_pass = sum(title_weighted_length(item["title"]) <= 20 for item in final_items)

    lines = [
        "# A2礼遇v11第二批稳定性训练｜10篇预览",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "v11第二批首轮稳定性未提升：10次调用均产出完整正文，但2篇在生成后语义改写阶段失败；人工首审仅2篇直接可用。修改后10篇可交付，仍只能证明L3人机协同可用。",
        "",
        "## 关键指标",
        "",
        f"- 发起生成：10；产出完整标题和正文：{raw_content_count}/10",
        f"- 系统最终状态：机器通过 {initial_report['summary']['hard_pass_count']}/10；后链路未解决 {len(MACHINE_UNRESOLVED_ITEMS)}/10，item {MACHINE_UNRESOLVED_ITEMS}",
        f"- 机器直接通过：2篇，item [6, 8]；机器后处理后通过：{len(MACHINE_POSTPROCESS_PASS_ITEMS)}篇，item {MACHINE_POSTPROCESS_PASS_ITEMS}",
        f"- 确定性规范化：{len(DETERMINISTIC_ITEMS)}篇，item {DETERMINISTIC_ITEMS}",
        f"- 模型语义改写：{len(SEMANTIC_REWRITE_ITEMS)}篇，item {SEMANTIC_REWRITE_ITEMS}",
        f"- 人工首审直接可用：{len(DIRECT_ITEMS)}/10，item {DIRECT_ITEMS}",
        f"- 人工要求修改：{len(REVISED_ITEMS)}/10，item {REVISED_ITEMS}",
        "- 修改后最终可用：10/10；正式禁词最终命中：0",
        f"- 标题审核口径合格：{title_pass}/10，按中文1、emoji2、上限20计算",
        f"- 最大两两2-gram相似度：{initial_report['summary']['max_pairwise_jaccard_2gram']}；相似度预警：{initial_report['summary']['similarity_warning_count']}",
        "",
        "## 候选变化",
        "",
        "- 本轮没有修改v11业务资产、原始槽位或禁词资产，只验证同一版本第二批稳定性。",
        "- 工作台仅补充：有完整标题和正文的failed条目可以进入request_revision和Qwen自动改写；空内容失败仍不可改写。",
        "",
        "## 重点看",
        "",
    ]

    for item_no in REVISED_ITEMS:
        item = final_by_no[item_no]
        lines.extend(
            [
                f"### ✅ item {item_no}｜改写后可用｜{item['title']}",
                "",
                f"首轮问题：{INITIAL_ISSUES[item_no]}",
                "",
                item["body"],
                "",
            ]
        )

    lines.extend(["## 其他产出", ""])
    for item_no in DIRECT_ITEMS:
        item = final_by_no[item_no]
        lines.extend(
            [
                f"### ✅ item {item_no}｜首轮直接可用｜{item['title']}",
                "",
                item["body"],
                "",
            ]
        )

    lines.extend(
        [
            "## 调试信息",
            "",
            f"- batch_id: {BATCH_ID}",
            f"- batch_code: {final_report['batch_code']}",
            f"- initial report: `{initial_report_path}`",
            f"- initial details: `{initial_details_path}`",
            f"- final report: `{final_report_path}`",
            f"- final details: `{final_details_path}`",
            f"- rendered prompt: `{prompt_path}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / f"batch{BATCH_ID}_A2礼遇v11第二批稳定性训练_10篇预览.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")

    comparison_path = OUTPUT_DIR / "a2礼遇_v11_两批稳定性对比.md"
    comparison_path.write_text(
        "\n".join(
            [
                "# A2礼遇v11｜两批稳定性对比",
                "",
                "## 结论",
                "",
                "v11尚未形成稳定的首轮直接可用能力。第二批人工直过率从30%降到20%，并新增20%的机器后链路未解决率。当前主要瓶颈不是确定性词面规范化，而是原始内容方向与检测页面边界冲突、语义改写服从度不足，以及中奖或兑换亲历缺少机器事实审核。",
                "",
                "| 指标 | 第一批 batch 731 | 第二批 batch 746 |",
                "| --- | ---: | ---: |",
                "| 发起生成 | 10 | 10 |",
                "| 产出完整正文 | 10 | 10 |",
                "| 机器最终通过 | 10 | 8 |",
                "| 机器后链路未解决 | 0 | 2 |",
                "| 人工首审直接可用 | 3 | 2 |",
                "| 人工要求修改 | 7 | 8 |",
                "| 修改后最终可用 | 10 | 10 |",
                "| 最大2-gram相似度 | 0.3346 | 0.2687 |",
                "",
                "## 下一轮应先解决",
                "",
                "1. 原始内容方向中仍有‘活动页面中讲了每批检测’等冲突语料；先列出问题原文，由运营确认后再改原始语料，不做压缩替换。",
                "2. Qwen对‘活动页面/顺手’连续改写仍会写回同类词，需要调整审核改写指令或增加改写后排除词校验。",
                "3. ‘自己抽到大奖’‘已经换到小车车’应进入活动事实审核，但不直接升级成全局字符串硬禁词。",
                "4. ‘积分随便换’‘买好几罐就有兑换资格’属于机制扩写，应增加活动类型一致性审核。",
                "",
                "## 文件",
                "",
                f"- 第二批预览：`{preview_path}`",
                f"- 第二批完整Prompt：`{prompt_path}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "preview_path": str(preview_path),
                "prompt_path": str(prompt_path),
                "comparison_path": str(comparison_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
