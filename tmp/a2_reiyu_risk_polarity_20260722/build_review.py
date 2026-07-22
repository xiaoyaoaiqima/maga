from __future__ import annotations

import json
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_risk_polarity_20260722")
BATCH_ID = 791
NEEDS_FIX = {4}
ISSUES = {
    4: "写了“家里刚囤了一箱、娃天天催我扫码”，仍可能把看到活动前的家庭库存和本次活动连接起来。",
}


def main() -> None:
    details = json.loads((OUTPUT_DIR / f"batch{BATCH_ID}_details.json").read_text(encoding="utf-8"))
    report = json.loads((OUTPUT_DIR / f"batch{BATCH_ID}_report.json").read_text(encoding="utf-8"))["data"]
    summary = report["summary"]

    item5 = next(item for item in details if item["item_no"] == 5)
    prompt_path = OUTPUT_DIR / f"batch{BATCH_ID}_完整Prompt_item5.md"
    prompt_path.write_text(
        "\n".join(
            [
                "# a2礼遇｜踩雷上下文检测回测｜完整生成 Prompt",
                "",
                f"- batch_id：{BATCH_ID}",
                "- item_no：5",
                f"- 标题：{item5['title']}",
                "",
                "```text",
                item5["rendered_prompt"],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    sections = []
    for item in sorted(details, key=lambda value: (value["item_no"] not in NEEDS_FIX, value["item_no"])):
        item_no = item["item_no"]
        marker = "💣" if item_no in NEEDS_FIX else "✅"
        state = "需修" if item_no in NEEDS_FIX else "可用"
        issue = f"\n\n判断：{ISSUES[item_no]}" if item_no in ISSUES else ""
        sections.append(
            f"### {marker} item {item_no}｜{state}｜{item['title']}"
            f"{issue}\n\n{item['body']}"
        )

    preview_path = OUTPUT_DIR / "a2礼遇_踩雷上下文检测_10篇回测预览.md"
    preview_path.write_text(
        "\n\n".join(
            [
                "# a2礼遇｜踩雷上下文检测｜10篇回测",
                "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
                "## 结论\n\n建议采用本次“踩雷”上下文检测修复。正向表达“闭眼入不踩雷”已直接放行，报表也不再误计禁词；但v29仍有老库存叙事，不能因此转正。",
                "## 关键指标\n\n"
                f"- 发起10篇；生成{summary['generated_count']}篇；失败{summary['failed_count']}篇。\n"
                "- 机器直接通过7篇；后链路改写后通过3篇；机器最终通过10/10。\n"
                f"- 最终禁词残留：{summary['forbidden_hit_count']}；最大2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度告警：{summary['similarity_warning_count']}。\n"
                "- 目标验证：item 5“闭眼入不踩雷”直接通过，未触发改写，也未进入禁词统计。\n"
                "- 人工可用：9篇，item [1, 2, 3, 5, 6, 7, 8, 9, 10]；需修：item [4]。",
                "## 候选变化\n\n"
                "- 修改前：正文只要包含“踩雷”，就按字面触发 qwen-plus 改写；改写后仍有该词便判失败。\n"
                "- 修改后：只在句子明确表达踩雷风险时触发改写；“不踩雷、没踩雷”等正向否定表达放行。\n"
                "- 报告层同步复用审核后的最终命中结果，不再二次做纯字符串误判。",
                "## 重点看\n\n" + sections[0],
                "## 其他产出\n\n" + "\n\n".join(sections[1:]),
                "## 调试信息\n\n"
                f"- batch_id：{BATCH_ID}\n"
                "- candidate：asset_id 1989 / v29 / active candidate\n"
                "- production保持：asset_id 1988 / v28 / active production\n"
                f"- JSON报告：`{OUTPUT_DIR / f'batch{BATCH_ID}_report.json'}`\n"
                f"- 生成详情：`{OUTPUT_DIR / f'batch{BATCH_ID}_details.json'}`\n"
                f"- 完整Prompt：`{prompt_path}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"preview": str(preview_path), "prompt": str(prompt_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
