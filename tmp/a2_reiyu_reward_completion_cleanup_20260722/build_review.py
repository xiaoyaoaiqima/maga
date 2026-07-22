from __future__ import annotations

import json
import random
import re
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_reward_completion_cleanup_20260722")
REPORT_PATH = OUTPUT_DIR / "batch785_reward_completion_cleanup_report.json"
MANIFEST_PATH = OUTPUT_DIR / "batch785_plan_manifest.json"
CANDIDATE_PATH = OUTPUT_DIR / "a2礼遇_F强化禁止虚构领奖并删除冗余路径约束.csv"

HUMAN = {
    1: ("usable", "只介绍抽奖奖品，没有写自己中奖或拿到奖品；单一来源和老客体验承接成立。"),
    2: ("usable", "宝妈群是唯一发现来源；抽奖、每批检测和老客认可逻辑自然。"),
    3: ("usable", "积分换礼只写可兑换，没有虚构已兑换；老客产品体验承接成立。"),
    4: ("usable", "闺蜜告知是唯一来源；活动和每批检测后的认可表达成立。"),
    5: ("usable", "只写老客可以领小听粉，没有写自己已领取；长期使用体验成立。"),
    6: ("fix", "没有虚构已领取，但素材只说可以领取小听粉，正文新增‘不用凑单也不用转、直接能领’的参与条件，需要删掉。"),
    7: ("dropped", "正文没有虚构领奖，标题加权23超过20，按现行规则直接淘汰。"),
    8: ("usable", "多重福利、扫罐码累计和每批检测关系清楚，没有叠加多个发现来源。"),
    9: ("usable", "3罐换小车车写成可兑换，没有写自己已经换到；老客体验成立。"),
    10: ("usable", "集罐机制和每批检测成立，没有虚构已兑换，也没有旧罐参与表述。"),
}

MARKER = {"usable": "✅", "watch": "⚠️", "fix": "💣", "dropped": "⛔"}
LABEL = {"usable": "可用", "watch": "重点看", "fix": "需修", "dropped": "标题淘汰"}
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

    prompt_candidates = [
        item
        for item in report["items"]
        if item.get("hard_pass") and (item.get("generation_snapshot") or {}).get("rendered_prompt")
    ]
    sample = random.SystemRandom().choice(prompt_candidates)
    prompt_path = OUTPUT_DIR / f"batch785_F强化领奖边界_随机完整Prompt_item{sample['item_no']}.md"
    prompt_path.write_text(
        "\n".join(
            [
                "# a2礼遇｜F强化禁止虚构领奖｜随机完整 Prompt",
                "",
                "- batch_id: 785",
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
    lines = [
        "# a2礼遇｜禁止虚构领奖并删除冗余路径约束｜10篇回测",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "F版可以保留为下一候选，但暂不替换正式v17。强化后10篇都没有把可领取、可兑换或可抽奖写成自己已经拿到；删除单一了解来源和认可路径硬约束后，也没有出现多个发现来源叠加。人工可用8/10，剩余1篇是新增未提供的领取条件，另1篇因标题超过20直接淘汰。",
        "",
        "## 关键指标",
        "",
        f"- 发起/正文产出：10/9；生成失败或淘汰：{summary['failed_count']}。",
        f"- 机器直接通过：{len(direct_items)}/10，item {direct_items}。",
        f"- 后处理后通过：{len(llm_rewrite_items) + len(deterministic_only_items)}/10；其中 LLM content.rewrite {len(llm_rewrite_items)}篇，item {llm_rewrite_items}；确定性处理 {len(deterministic_only_items)}篇，item {deterministic_only_items}。",
        f"- 机器最终通过：{summary['hard_pass_count']}/10；禁词最终残留：{summary['forbidden_hit_count']}。",
        f"- 最大2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度告警：{summary['similarity_warning_count']}。",
        f"- 人工可用：{len(human_items['usable'])}/10，item {human_items['usable']}；需修：{human_items['fix']}；标题淘汰：{human_items['dropped']}。",
        "- 虚构已兑换、已领取、已中奖或已拿到奖品：0/10。",
        "- 多个活动了解来源叠加成同一次发现经历：0/10。",
        "",
        "## 候选变化",
        "",
        "只改16条业务规则的生成要求，原始活动内容、了解途径、参加原因、认可表达和正向词均未压缩或改写：",
        "",
        "- 新增：标题和正文只能介绍活动可兑换、可领取或可抽取什么；禁止写自己已经领了、领到、收到、拿到、兑到、换到或中奖，也不要虚构任何已经得到奖品的经历。",
        "- 删除：每篇只选择一个活动了解途径，不得把多个了解来源叠加成同一次发现经历。",
        "- 删除：老客了解信息后更认可的专门路径硬约束。",
        "- 第一版E在batch 784仍出现1篇标题写成‘去门店领了个小惊喜’；F版明确覆盖标题和完成态动词后，本轮未再出现。",
        "",
        "## 重点看",
        "",
    ]
    for item_no in human_items["dropped"] + human_items["fix"] + human_items["watch"]:
        lines.extend(item_section(items[item_no]))
    lines.extend(["## 其他产出", ""])
    for item_no in human_items["usable"]:
        lines.extend(item_section(items[item_no]))
    lines.extend(
        [
            "## 调试信息",
            "",
            "- batch_id: 785",
            "- candidate asset_id: 1984 / v26 / archived candidate",
            "- first-pass asset_id: 1983 / v25 / archived candidate; batch_id: 784",
            "- production asset: 1972 / v17 / active production",
            f"- candidate CSV: `{CANDIDATE_PATH}`",
            f"- JSON report: `{REPORT_PATH}`",
            f"- plan manifest: `{MANIFEST_PATH}`",
            f"- rendered prompt: `{prompt_path}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / "a2礼遇_F禁止虚构领奖并删除冗余路径约束_10篇回测预览.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")
    metrics_path = OUTPUT_DIR / "a2礼遇_F禁止虚构领奖并删除冗余路径约束_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "batch_id": 785,
                "machine_summary": summary,
                "direct_items": direct_items,
                "llm_rewrite_items": llm_rewrite_items,
                "deterministic_only_items": deterministic_only_items,
                "human_items": human_items,
                "reward_completion_violations": [],
                "stacked_source_violations": [],
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
