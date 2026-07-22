from __future__ import annotations

import json
import random
import re
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_title_under_19_20260722")
REPORT_PATH = OUTPUT_DIR / "batch786_reward_completion_cleanup_report.json"
MANIFEST_PATH = OUTPUT_DIR / "batch786_plan_manifest.json"
CANDIDATE_PATH = OUTPUT_DIR / "a2礼遇_G标题少于19字.csv"

HUMAN = {
    1: ("usable", "标题加权13，活动、检测与老客使用感受承接成立。"),
    2: ("usable", "标题加权20，审核口径允许；少于19字只用于生成时帮助模型收短标题。"),
    3: ("usable", "标题加权11，积分、检测和老客体验关系成立。"),
    4: ("usable", "标题加权9，标题正文贴合，活动与品牌认可自然。"),
    5: ("usable", "标题加权12，只写可以领取小听粉，没有虚构自己已领取。"),
    6: ("usable", "标题加权12，老客回归礼和每批检测承接成立。"),
    7: ("usable", "标题加权17，多重福利、检测与长期使用体验成立。"),
    8: ("usable", "标题加权9，多重福利信息清楚，没有来源叠加。"),
    9: ("fix", "标题加权12，但‘正好家里囤了好几罐’容易暗示活动前已有罐子可参加集罐，需要从源头去掉。"),
    10: ("usable", "标题加权13，集罐、每批检测和品牌认可逻辑成立。"),
}

MARKER = {"usable": "✅", "watch": "⚠️", "fix": "💣"}
LABEL = {"usable": "可用", "watch": "重点看", "fix": "需修"}
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def weighted_title_length(title: str) -> int:
    total = 0
    for char in re.sub(r"\s+", "", title):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if EMOJI_RE.fullmatch(char) else 1
    return total


def item_section(item: dict) -> list[str]:
    item_no = int(item["item_no"])
    status, reason = HUMAN[item_no]
    return [
        f"### {MARKER[status]} item {item_no}｜{LABEL[status]}｜{item.get('title') or ''}",
        "",
        f"判断：{reason}",
        f"标题加权：{weighted_title_length(str(item.get('title') or ''))}",
        "",
        str(item.get("body") or "（无正文）"),
        "",
    ]


def main() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    report = payload["report"]
    items = {int(item["item_no"]): item for item in report["items"]}

    human_items = {status: [] for status in MARKER}
    for item_no, (status, _) in HUMAN.items():
        human_items[status].append(item_no)

    llm_rewrite_items = []
    deterministic_only_items = []
    direct_items = []
    for item_no, item in items.items():
        capabilities = [stage.get("capability") for stage in item.get("trace_stage_calls") or []]
        if "content.rewrite" in capabilities:
            llm_rewrite_items.append(item_no)
        elif item.get("rewrite_reason") and item.get("hard_pass"):
            deterministic_only_items.append(item_no)
        elif item.get("hard_pass"):
            direct_items.append(item_no)

    title_lengths = {
        item_no: weighted_title_length(str(item.get("title") or ""))
        for item_no, item in items.items()
    }
    under_19 = [item_no for item_no, length in title_lengths.items() if length < 19]
    at_or_over_19 = [item_no for item_no, length in title_lengths.items() if length >= 19]
    over_20 = [item_no for item_no, length in title_lengths.items() if length > 20]

    prompt_candidates = [
        items[item_no]
        for item_no in human_items["usable"]
        if (items[item_no].get("generation_snapshot") or {}).get("rendered_prompt")
    ]
    sample = random.SystemRandom().choice(prompt_candidates)
    prompt_path = OUTPUT_DIR / f"batch786_G标题少于19字_随机完整Prompt_item{sample['item_no']}.md"
    prompt_path.write_text(
        "\n".join(
            [
                "# a2礼遇｜G标题少于19字｜随机完整 Prompt",
                "",
                "- batch_id: 786",
                f"- item_no: {sample['item_no']}",
                f"- title: {sample.get('title') or ''}",
                "",
                "```text",
                sample["generation_snapshot"]["rendered_prompt"],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary = report["summary"]
    avg_title = round(sum(title_lengths.values()) / len(title_lengths), 1)
    lines = [
        "# a2礼遇｜标题少于19字｜10篇单变量回测",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "新增标题约束有效，可以保留在候选中，但暂不替换正式v17。标题少于19字从F版的6/10提升到9/10，平均加权长度从17.4降到12.8，本轮没有标题超过20被淘汰。item 2为20字，按审核口径正常可用；少于19字只用于生成时帮助模型收短标题。",
        "",
        "## 关键指标",
        "",
        f"- 发起/正文产出：10/10；生成失败：{summary['failed_count']}。",
        f"- 标题少于19字：{len(under_19)}/10，item {under_19}；生成到20字但审核可用：item {at_or_over_19}。",
        f"- 标题加权平均长度：{avg_title}；超过20：{len(over_20)}篇。",
        f"- 机器直接通过：{len(direct_items)}/10，item {direct_items}。",
        f"- 确定性处理后通过：{len(deterministic_only_items)}/10，item {deterministic_only_items}；LLM content.rewrite：{len(llm_rewrite_items)}篇。",
        f"- 机器最终通过：{summary['hard_pass_count']}/10；禁词最终残留：{summary['forbidden_hit_count']}。",
        f"- 最大2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度告警：{summary['similarity_warning_count']}。",
        f"- 人工可用：{len(human_items['usable'])}/10，item {human_items['usable']}；重点看：{human_items['watch']}；需修：{human_items['fix']}。",
        "",
        "## 候选变化",
        "",
        "只在F版16条业务规则的生成要求中新增一条，其他活动内容、了解途径、参加原因、认可表达、正向词和硬边界不变：",
        "",
        "- 新增：标题按中文、字母、数字各1字、emoji算2字，必须少于19字。",
        "- 审核口径不变：20字允许，只有标题加权超过20才直接淘汰。",
        "- 后链路新增业务硬ban：囤了好几罐。该词不写入生文Prompt，由机器审核直接拦截；对batch 786 item 9复核已命中。",
        "",
        "## 重点看",
        "",
    ]
    for item_no in human_items["fix"] + human_items["watch"]:
        lines.extend(item_section(items[item_no]))
    lines.extend(["## 其他产出", ""])
    for item_no in human_items["usable"]:
        lines.extend(item_section(items[item_no]))
    lines.extend(
        [
            "## 调试信息",
            "",
            "- batch_id: 786",
            "- candidate asset_id: 1985 / v27 / archived candidate",
            "- baseline F batch_id: 785；asset_id: 1984 / v26 / archived candidate",
            "- production asset: 1972 / v17 / active production",
            f"- candidate CSV: `{CANDIDATE_PATH}`",
            f"- JSON report: `{REPORT_PATH}`",
            f"- plan manifest: `{MANIFEST_PATH}`",
            f"- rendered prompt: `{prompt_path}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / "a2礼遇_G标题少于19字_10篇回测预览.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")
    metrics_path = OUTPUT_DIR / "a2礼遇_G标题少于19字_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "batch_id": 786,
                "machine_summary": summary,
                "title_lengths": title_lengths,
                "under_19_items": under_19,
                "at_or_over_19_items": at_or_over_19,
                "over_20_items": over_20,
                "direct_items": direct_items,
                "llm_rewrite_items": llm_rewrite_items,
                "deterministic_only_items": deterministic_only_items,
                "human_items": human_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "preview": str(preview_path),
                "prompt": str(prompt_path),
                "metrics": str(metrics_path),
                "sample_item": sample["item_no"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
