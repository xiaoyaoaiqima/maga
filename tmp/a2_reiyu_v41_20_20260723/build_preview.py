from __future__ import annotations

import csv
import json
from pathlib import Path


BATCH_ID = 833
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v41_20_20260723")
REPORT_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_full_report.json"
PREVIEW_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_v41_20篇人工审核预览.md"
USABLE_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_人工可用13篇.csv"
PROMPT_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item17.md"

USABLE = {1, 2, 3, 6, 7, 9, 13, 14, 15, 17, 18, 19, 20}
ISSUES = {
    4: "出现“顺手攒罐子”，既命中替换词，也容易联想到旧罐参与。",
    5: "“免费”需按现有后链路替换规则处理。",
    8: "出现“顺手”，需后链路改写。",
    10: "“朋友圈”需替换成puq或pyq。",
    11: "标题把宝宝长肉卖点前置，且正文仍有解释腔，需要改写后再用。",
    12: "出现正式硬禁表达“囤了好几罐”，并构成活动前库存参与暗示。",
    16: "出现“攒罐子”，按当前规则直接拦截。",
}


def section(marker: str, label: str, item: dict, reason: str | None = None) -> list[str]:
    lines = [f"### {marker} item {item['item_no']}｜{label}｜{item.get('title') or '无标题'}", ""]
    if reason:
        lines.extend([f"问题：{reason}", ""])
    lines.extend([item.get("body") or "（无正文）", ""])
    return lines


def main() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    items = report["items"]
    summary = report["summary"]
    usable = [item for item in items if item["item_no"] in USABLE]
    needs_fix = [item for item in items if item["item_no"] not in USABLE]

    lines = [
        "# A2礼遇 v41｜集罐20篇生成与人工审核",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "v41两项修复有效：旧库存新表达没有漏过机审，旧业务腔没有再生成。本批13篇可用，7篇需处理。",
        "",
        "## 关键指标",
        "",
        "- 请求/尝试：20；原始生成：20；生成失败：0",
        "- 严格审核直接通过：16；后链路改写通过：0，本批使用generate_only",
        f"- 机器最终通过：{summary['hard_pass_count']}；人工可用：{len(usable)}",
        f"- 禁词命中文章：{summary['forbidden_hit_count']}",
        f"- 最大两两2-gram Jaccard：{summary['max_pairwise_jaccard_2gram']}；相似度预警：{summary['similarity_warning_count']}",
        "- 人工可用 item：1, 2, 3, 6, 7, 9, 13, 14, 15, 17, 18, 19, 20",
        "- 人工观察 item：无",
        "- 需修 item：4, 5, 8, 10, 11, 12, 16",
        "",
        "## 本轮变化",
        "",
        "- 旧库存机审新增“家里快喝完一箱＋攒/集罐”语义；本批未出现漏网样本。",
        "- `brand_feeling_008` 已改为“看完对a2又多了点信任🤝”。",
        "- 原有反照抄规则改为：偏书面或业务总结的槽位原话必须转成宝妈自然口语，未额外叠加重复规则。",
        "- 本批旧表达“经营跟用户之间的信任感”命中0次。",
        "",
        "## 重点看",
        "",
    ]
    for item in needs_fix:
        lines.extend(section("💣", "需修", item, ISSUES[item["item_no"]]))
    lines.extend(["## 其他产出", ""])
    for item in usable:
        lines.extend(section("✅", "可用", item))
    lines.extend(
        [
            "## 调试信息",
            "",
            f"- batch_id：{BATCH_ID}",
            "- production asset：2007 / v41",
            "- draft_id：无",
            f"- JSON报告：`{REPORT_PATH}`",
            f"- 人工可用CSV：`{USABLE_PATH}`",
            f"- 随机完整Prompt：`{PROMPT_PATH}`",
            "",
        ]
    )
    PREVIEW_PATH.write_text("\n".join(lines), encoding="utf-8")

    with USABLE_PATH.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["content_id", "标题", "正文", "分类"])
        writer.writeheader()
        for item in usable:
            rule = str(
                ((item.get("generation_snapshot") or {}).get("business_rule") or {}).get(
                    "business_rule"
                )
                or ""
            )
            writer.writerow(
                {
                    "content_id": f"batch-{BATCH_ID}-item-{item['item_no']}",
                    "标题": item.get("title") or "",
                    "正文": item.get("body") or "",
                    "分类": "12罐" if "12罐" in rule else "其他罐",
                }
            )
    print(
        json.dumps(
            {
                "preview": str(PREVIEW_PATH),
                "usable_csv": str(USABLE_PATH),
                "usable": len(usable),
                "needs_fix": len(needs_fix),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
