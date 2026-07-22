from __future__ import annotations

import json
import random
import re
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_positive_path_routing_20260722")
REPORT_PATH = OUTPUT_DIR / "batch779_path_routing_report.json"
MANIFEST_PATH = OUTPUT_DIR / "batch779_plan_manifest.json"
CANDIDATE_PATH = OUTPUT_DIR / "a2礼遇_v17单变量_正向词按认可路径分流.csv"
BASELINE_REVIEW = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_v17_title_hard_drop_20260721/"
    "batch768_v17标题硬淘汰验证_10篇预览.md"
)

HUMAN = {
    1: ("usable", "老客体验、宝宝状态和推荐关系成立；标题加权20，未超过上限。"),
    2: ("usable", "信息认可只落在活动、每批检测和品牌评价，没有补亲身喂养结果。"),
    3: ("usable", "积分活动与老客体验成立；长肉和转奶两段略满，但没有事实或路径冲突。"),
    4: ("fix", "虚构已经兑换到小玩意儿；信息认可路径又补了‘自家娃喝着也好、继续囤’。"),
    5: ("usable", "老客礼、每批检测、长肉和冲泡体验承接完整。"),
    6: ("fix", "信息认可路径的参加原因直接塞入转奶失败、绿💩和回归经历，和本条路径冲突。"),
    7: ("usable", "多重福利、检测和老客使用感受清楚；疾病效果按当前业务反馈不判错。"),
    8: ("fix", "信息认可路径本身干净，但活动素材只说多重福利，正文自行新增‘积分翻倍’。"),
    9: ("usable", "3罐换小车车事实正确，老客冲泡与宝宝接受体验承接自然。"),
    10: ("usable", "信息认可只从集罐、每批检测和品牌感受收口，没有补使用结果。"),
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


def item_section(item: dict, path: str) -> list[str]:
    item_no = int(item["item_no"])
    status, reason = HUMAN[item_no]
    return [
        f"### {MARKER[status]} item {item_no}｜{LABEL[status]}｜{item.get('title') or ''}",
        "",
        f"路径：{'老客使用感受' if path == 'old_customer' else '信息了解后的认可'}",
        f"判断：{reason}",
        f"标题加权：{weighted_title_length(str(item.get('title') or ''))}",
        "",
        str(item.get("body") or "（无正文）"),
        "",
    ]


def main() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    report = payload["report"]
    items = {int(item["item_no"]): item for item in report["items"]}
    plans = {int(item["item_no"]): item for item in manifest["items"]}

    human_counts = {"usable": 0, "watch": 0, "fix": 0}
    human_items = {"usable": [], "watch": [], "fix": []}
    for item_no, (status, _) in HUMAN.items():
        human_counts[status] += 1
        human_items[status].append(item_no)

    llm_rewrite_items = []
    deterministic_only_items = []
    untouched_items = []
    for item_no, item in items.items():
        capabilities = [stage.get("capability") for stage in item.get("trace_stage_calls") or []]
        if "content.rewrite" in capabilities:
            llm_rewrite_items.append(item_no)
        elif item.get("rewrite_reason"):
            deterministic_only_items.append(item_no)
        else:
            untouched_items.append(item_no)

    information_items = [item_no for item_no, plan in plans.items() if plan["path"] == "information"]
    information_positive_leaks = []
    information_output_usage_leaks = [4, 6]
    information_clean_items = [item_no for item_no in information_items if item_no not in information_output_usage_leaks]

    prompt_candidates = [
        item
        for item in report["items"]
        if (item.get("generation_snapshot") or {}).get("rendered_prompt")
    ]
    sample = random.SystemRandom().choice(prompt_candidates)
    prompt_path = OUTPUT_DIR / f"batch779_正向词按认可路径分流_随机完整Prompt_item{sample['item_no']}.md"
    prompt_path.write_text(
        "\n".join(
            [
                "# a2礼遇｜正向词按认可路径分流｜随机完整 Prompt",
                "",
                "- batch_id: 779",
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
        "# a2礼遇｜正向词按认可路径分流｜10篇单变量回测",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "方向有效，但暂不替换正式v17。信息认可路径的5条正向词全部来自品牌、活动和检测感受，宝宝状态/产品体验词串入为0；正文中仍有2条被其他上游槽位带回老客经历。人工可用7/10，与v17基线持平，没有证明整体质量提升。本轮只验证了路由；参加原因适配和正向词数量上限必须分成后续两个单变量，不能一起改。",
        "",
        "## 关键指标",
        "",
        f"- 发起/正文产出：10/10；生成失败：{summary['failed_count']}。",
        f"- 机器最终通过：{summary['hard_pass_count']}/10；禁词最终残留：{summary['forbidden_hit_count']}。",
        f"- LLM直出未调用content.rewrite：{10 - len(llm_rewrite_items)}/10；LLM content.rewrite：{len(llm_rewrite_items)}次，item {llm_rewrite_items}。",
        f"- 完全未触发后处理：{len(untouched_items)}/10，item {untouched_items}；仅确定性替换：{len(deterministic_only_items)}/10，item {deterministic_only_items}。",
        f"- 最大2-gram相似度：{summary['max_pairwise_jaccard_2gram']}；相似度告警：{summary['similarity_warning_count']}。",
        f"- 人工可用：{human_counts['usable']}/10，item {human_items['usable']}；需修：{human_counts['fix']}/10，item {human_items['fix']}。",
        f"- 信息认可路径：5条；正向词错误路由0条；最终正文仍出现亲身使用经历2条，item {information_output_usage_leaks}；路径干净3条，item {information_clean_items}。",
        "- 参考基线v17 batch768：机器最终通过7/10、人工可用7/10、LLM rewrite 0次。",
        "",
        "## 候选变化",
        "",
        "只改正向表达素材的路由，其他列和模型配置锁死：",
        "",
        "- 老客使用感受：完整保留并抽取原始CSV的12行语料，不压缩、不改写。",
        "- 信息了解后的认可：只从原始语料抽取以下3组原词，共26个词，没有新增词：",
        "  - 妈妈心理：安心、放心、踏实、靠谱、值得信赖、心里有底、有保障、有底气、经得起研究、经得起比较、让人放心。",
        "  - 妈妈心理：品控在线、品质在线、质量稳定、标准高、细节到位、做得认真、诚意满满、透明放心、让人信服、经得起考验。",
        "  - 妈妈心理：值得推荐、良心品牌、口碑在线、实力在线、表现稳定。",
        "- 资产校验：16条业务规则，8条老客路径、8条信息路径；非正向表达列差异为0。",
        "- 额外发现：现有写法仍要求‘正向表达只挑和本篇体验贴合的一两个自然带入’，它会直接限制正文里的正向词数量；本轮为保持单变量没有改这句话。",
        "",
        "## 重点看",
        "",
    ]
    for item_no in human_items["fix"] + human_items["watch"]:
        lines.extend(item_section(items[item_no], plans[item_no]["path"]))
    lines.extend(["## 其他产出", ""])
    for item_no in human_items["usable"]:
        lines.extend(item_section(items[item_no], plans[item_no]["path"]))
    lines.extend(
        [
            "## 调试信息",
            "",
            "- batch_id: 779",
            "- candidate asset_id: 1978 / v22 / archived candidate",
            "- production asset: 1972 / v17 / active production",
            f"- candidate CSV: `{CANDIDATE_PATH}`",
            f"- JSON report: `{REPORT_PATH}`",
            f"- plan manifest: `{MANIFEST_PATH}`",
            f"- rendered prompt: `{prompt_path}`",
            f"- v17 baseline review: `{BASELINE_REVIEW}`",
            "",
        ]
    )
    preview_path = OUTPUT_DIR / "a2礼遇_正向词按认可路径分流_10篇回测预览.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")

    metrics_path = OUTPUT_DIR / "a2礼遇_正向词按认可路径分流_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "batch_id": 779,
                "machine_summary": summary,
                "human_counts": human_counts,
                "human_items": human_items,
                "llm_rewrite_items": llm_rewrite_items,
                "deterministic_only_items": deterministic_only_items,
                "untouched_items": untouched_items,
                "information_items": information_items,
                "information_positive_leaks": information_positive_leaks,
                "information_output_usage_leaks": information_output_usage_leaks,
                "information_clean_items": information_clean_items,
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
                "human_usable": human_counts["usable"],
                "human_fix": human_counts["fix"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
