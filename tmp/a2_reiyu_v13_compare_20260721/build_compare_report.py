#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import random
import re
from pathlib import Path
from statistics import mean, median


ROOT = Path("/Users/luxifa/maga")
OUTPUT_DIR = ROOT / "outputs/a2_reiyu_v13_compare_20260721"
BATCH_ID = 756
DETAILS_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_details.json"
REPORT_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_report.json"
BASELINE_PATH = ROOT / "outputs/a2_reiyu_followup_audit_20260721/A2礼遇_合并可用492篇.csv"

MANUAL = {
    1: ("fix", "把‘看品质溯源信息’写成抽奖参与方式，溯源信息与抽奖机制被错误绑定；该错误来自源槽位。"),
    2: ("fix", "同item 1，把看品质溯源信息写成抽奖入口；该错误来自源槽位。"),
    3: ("usable", "积分累积兑换会员礼的归属正确，活动、检测和老客感受关系成立。"),
    4: ("fix", "无素材支撑地扩写‘买好几罐就够换东西’，虚构了积分兑换门槛，删去即可。"),
    5: ("usable", "老客回归礼、小听粉、每批检测和长期使用感受衔接正常。"),
    6: ("fix", "标题和结尾写成自己已去领、本次已领小听粉，素材只支撑‘可以领取’，属于虚构领礼经历。"),
    7: ("watch", "业务事实基本正确，但机器后链路仍标记未收敛；正文的产品话术也和item 1、3、5、9高度同源。"),
    8: ("watch", "机制正确，但‘这个动作/品质更透明/消费者被重视’呈现明显槽位翻译感。"),
    9: ("fix", "写‘家里刚好买了好几罐，参与起来毫无压力’，暗示活动前已购买罐可直接参加本次集罐。"),
    10: ("watch", "机制和档位正确，但‘yyds/这做事够认真/品质更透明’偏短促总结腔，真人细节偏少。"),
}

MARKERS = {"fix": "💣", "watch": "⚠️", "usable": "✅"}
LABELS = {"fix": "需修", "watch": "重点看", "usable": "可用"}
PHRASES = [
    "看看品质溯源信息就能抽奖",
    "纯A2蛋白对新生宝宝",
    "这个动作",
    "愿意推荐给闺蜜",
    "品质也更透明",
]


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def grams(text: str, n: int = 2) -> set[str]:
    value = compact(text)
    return {value[index : index + n] for index in range(max(0, len(value) - n + 1))}


def jaccard(left: str, right: str) -> float:
    left_grams = grams(left)
    right_grams = grams(right)
    union = left_grams | right_grams
    return len(left_grams & right_grams) / len(union) if union else 0.0


def max_pairwise(items: list[str]) -> float:
    value = 0.0
    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            value = max(value, jaccard(items[left], items[right]))
    return value


def main() -> None:
    items = json.loads(DETAILS_PATH.read_text(encoding="utf-8"))
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))["data"]
    with BASELINE_PATH.open(encoding="utf-8-sig", newline="") as handle:
        baseline = list(csv.DictReader(handle))

    new_bodies = [item["body"] for item in items]
    old_bodies = [item["正文"] for item in baseline]
    rng = random.Random(20260721)
    sampled_maxes = [max_pairwise(rng.sample(old_bodies, 10)) for _ in range(200)]
    nearest_to_old = [max(jaccard(body, old) for old in old_bodies) for body in new_bodies]
    baseline_hidden = [
        (index, row)
        for index, row in enumerate(baseline, start=2)
        if "看看品质溯源信息就能抽奖" in row["正文"]
    ]

    groups = {key: [] for key in ("fix", "watch", "usable")}
    for item in items:
        groups[MANUAL[item["item_no"]][0]].append(item["item_no"])

    rewritten_items = [
        item["item_no"]
        for item in report["items"]
        if item.get("rewrite_reason")
    ]
    rewritten_pass = [
        item["item_no"]
        for item in report["items"]
        if item.get("rewrite_reason") and item.get("hard_pass")
    ]
    direct_pass = [
        item["item_no"]
        for item in report["items"]
        if not item.get("rewrite_reason") and item.get("hard_pass")
    ]

    sampled_item = random.SystemRandom().choice([item for item in items if item.get("rendered_prompt")])
    prompt_path = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item{sampled_item['item_no']}.md"
    prompt_path.write_text(
        "\n".join(
            [
                "# a2礼遇 v13完整生成Prompt",
                "",
                f"- batch_id: {BATCH_ID}",
                f"- item_no: {sampled_item['item_no']}",
                f"- title: {sampled_item['title']}",
                f"- business_rule: {sampled_item.get('business_rule') or ''}",
                "",
                "```text",
                sampled_item["rendered_prompt"],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    lines = [
        "# a2礼遇 v13｜batch 756｜10篇与现有492篇质量对比",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "不建议直接转正。v13的生成稳定性和活动类型覆盖不错，但首轮人工直接可用只有2/10；抽奖机制、旧购买罐和虚构经历仍会穿过机器审核。",
        "",
        "## 关键指标",
        "",
        f"- 生成：{report['summary']['generated_count']}/10；失败：{report['summary']['failed_count']}",
        f"- 机器直接通过：{len(direct_pass)}篇，item {direct_pass}；机器改写后通过：{len(rewritten_pass)}篇，item {rewritten_pass}",
        f"- 机器最终通过：{report['summary']['hard_pass_count']}/10；自动处理条目：{rewritten_items}；仍未收敛：{report['summary']['remaining_rewrite_required_count']}",
        f"- 最终违禁词命中：{report['summary']['forbidden_hit_count']}；相似度预警：{report['summary']['similarity_warning_count']}",
        f"- 最大两两2-gram相似度：{report['summary']['max_pairwise_jaccard_2gram']:.4f}",
        f"- 人工可用：{len(groups['usable'])}篇，item {groups['usable']}",
        f"- 人工重点看：{len(groups['watch'])}篇，item {groups['watch']}",
        f"- 人工需修：{len(groups['fix'])}篇，item {groups['fix']}",
        "",
        "## 候选调整",
        "",
        "本轮只评测，没有改正式资产。最小建议差异：",
        "",
        "```diff",
        "- 活动内容：参与方式挺简单，看看品质溯源信息就能参与抽奖，奖品价值非常高……",
        "+ 活动内容：抽奖活动参与起来不复杂，奖品有2w多的新西兰旅游……",
        "+ 审核金标：增加‘查看/浏览/看看溯源信息 + 抽奖入口’语义类错误，不只拦截‘扫罐底码就能抽奖’。",
        "```",
        "",
        "## 与现有492篇对比",
        "",
        "| 维度 | v13本批10篇 | 现有492篇交付池 | 判断 |",
        "| --- | ---: | ---: | --- |",
        f"| 平均正文长度 | {mean(len(compact(body)) for body in new_bodies):.1f} | {mean(len(compact(body)) for body in old_bodies):.1f} | v13更短，更容易变成概括腔 |",
        f"| 10篇内最大相似度 | {max_pairwise(new_bodies):.4f} | 随机10篇中位数 {median(sampled_maxes):.4f} | v13本批模板聚集更明显 |",
        f"| 与492篇的最近相似度 | 平均 {mean(nearest_to_old):.4f}，最高 {max(nearest_to_old):.4f} | - | 没有整篇复制，问题是槽位短语重复 |",
        f"| 溯源信息绑定抽奖 | 2/10 | {len(baseline_hidden)}/492 | v13触发率显著更高，且492篇中仍漏了3篇 |",
        "",
        "高频槽位痕迹：",
        "",
    ]
    for phrase in PHRASES:
        new_count = sum(phrase in body for body in new_bodies)
        old_count = sum(phrase in body for body in old_bodies)
        lines.append(f"- `{phrase}`：v13 {new_count}/10；492篇 {old_count}/492")

    if baseline_hidden:
        lines.extend(
            [
                "",
                "现有492篇中新发现的3篇漏网文章：",
                "",
            ]
        )
        for row_no, row in baseline_hidden:
            content_id = row.get("content_id") or "无content_id"
            lines.append(f"- CSV行{row_no}｜{content_id}｜{row['标题']}")

    lines.extend(["", "## 重点看", ""])
    for label in ("fix", "watch"):
        for item in items:
            item_label, reason = MANUAL[item["item_no"]]
            if item_label != label:
                continue
            lines.extend(
                [
                    f"### {MARKERS[label]} item {item['item_no']}｜{LABELS[label]}｜{item['title']}",
                    "",
                    f"问题：{reason}",
                    "",
                    item["body"],
                    "",
                ]
            )

    lines.extend(["## 其他产出", ""])
    for item in items:
        label, reason = MANUAL[item["item_no"]]
        if label != "usable":
            continue
        lines.extend(
            [
                f"### {MARKERS[label]} item {item['item_no']}｜{LABELS[label]}｜{item['title']}",
                "",
                f"判断：{reason}",
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
            "- asset: a2_reiyu_ugc_post_rules_v1 v13",
            "- draft_id: 无，本次使用正式生产资产",
            f"- report: `{REPORT_PATH}`",
            f"- details/response: `{DETAILS_PATH}`",
            f"- rendered prompt: `{prompt_path}`",
            "",
        ]
    )

    preview_path = OUTPUT_DIR / f"batch{BATCH_ID}_v13_10篇与492篇质量对比.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")

    comparison = {
        "batch_id": BATCH_ID,
        "human": groups,
        "machine_direct_pass_items": direct_pass,
        "machine_rewritten_pass_items": rewritten_pass,
        "machine_rewritten_items": rewritten_items,
        "new_avg_chars": mean(len(compact(body)) for body in new_bodies),
        "baseline_avg_chars": mean(len(compact(body)) for body in old_bodies),
        "new_max_pairwise": max_pairwise(new_bodies),
        "baseline_sample10_max_median": median(sampled_maxes),
        "nearest_baseline_mean": mean(nearest_to_old),
        "nearest_baseline_max": max(nearest_to_old),
        "baseline_hidden_rows": [row_no for row_no, _ in baseline_hidden],
        "preview_path": str(preview_path),
        "prompt_path": str(prompt_path),
    }
    (OUTPUT_DIR / f"batch{BATCH_ID}_comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
