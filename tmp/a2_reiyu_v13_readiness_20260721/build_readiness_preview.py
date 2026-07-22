#!/usr/bin/env python3
"""Build the A2 reiyu v13 30-item readiness preview and sampled prompt."""

from __future__ import annotations

import json
import random
import re
from itertools import combinations
from pathlib import Path


OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v13_readiness_20260721")
BATCH_IDS = (752, 753, 754)
SIMILARITY_THRESHOLD = 0.35
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")

NEEDS_FIX = {
    (752, 11): "正文照抄内部组合标签“a2礼遇｜集罐6罐换自行车活动”，属于指令/规则标签泄漏。",
}


def title_weighted_length(title: str) -> int:
    total = 0
    for char in re.sub(r"\s+", "", title.strip()):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if EMOJI_RE.fullmatch(char) else 1
    return total


def ngrams(text: str, size: int = 2) -> set[str]:
    normalized = re.sub(r"\s+", "", text)
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[index : index + size] for index in range(len(normalized) - size + 1)}


def jaccard(left: str, right: str) -> float:
    left_set = ngrams(left)
    right_set = ngrams(right)
    if not left_set and not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def load_data() -> tuple[list[dict], dict[int, dict]]:
    items: list[dict] = []
    reports: dict[int, dict] = {}
    for batch_id in BATCH_IDS:
        details = json.loads((OUTPUT_DIR / f"batch{batch_id}_details.json").read_text(encoding="utf-8"))
        report = json.loads((OUTPUT_DIR / f"batch{batch_id}_report.json").read_text(encoding="utf-8"))["data"]
        reports[batch_id] = report
        report_by_no = {item["item_no"]: item for item in report["items"]}
        for item in details:
            merged = dict(item)
            merged["batch_id"] = batch_id
            merged["report_item"] = report_by_no[item["item_no"]]
            items.append(merged)
    return items, reports


def human_review(item: dict) -> tuple[str, str]:
    key = (item["batch_id"], item["item_no"])
    if key in NEEDS_FIX:
        return "needs_fix", NEEDS_FIX[key]
    if "纯A2蛋白对新生宝宝" in item["body"]:
        return "watch", "老客认可原句在本轮高频复现；单篇事实链可用，但批量投放有明显模板聚集。"
    return "usable", "当前人工业务口径下可直接使用。"


def write_prompt(items: list[dict]) -> Path:
    candidates = [item for item in items if item.get("rendered_prompt") and human_review(item)[0] != "needs_fix"]
    item = random.SystemRandom().choice(candidates)
    path = OUTPUT_DIR / f"batch{item['batch_id']}_随机完整Prompt_item{item['item_no']}.md"
    path.write_text(
        "\n".join(
            [
                "# A2礼遇v13就绪度验证｜随机完整Prompt",
                "",
                f"- batch_id: {item['batch_id']}",
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
    items, reports = load_data()
    prompt_path = write_prompt(items)

    generated_count = sum(bool(item.get("title") and item.get("body")) for item in items)
    machine_pass = sum(bool(item["report_item"].get("hard_pass")) for item in items)
    unresolved = [
        (item["batch_id"], item["item_no"])
        for item in items
        if not item["report_item"].get("hard_pass")
    ]
    deterministic = [
        (item["batch_id"], item["item_no"])
        for item in items
        if (item.get("quality") or {}).get("forbidden_terms_review", {}).get("rewrite_method")
        == "deterministic_replace"
    ]
    semantic_rewrite = [
        (item["batch_id"], item["item_no"])
        for item in items
        if (item.get("quality") or {}).get("forbidden_terms_review", {}).get("rewrite_method")
        == "content.rewrite"
    ]
    direct_machine_pass = [
        (item["batch_id"], item["item_no"])
        for item in items
        if item["report_item"].get("hard_pass")
        and (item.get("quality") or {}).get("forbidden_terms_review", {}).get("rewrite_method", "none") == "none"
    ]
    final_forbidden_hits = sum(len(item["report_item"].get("forbidden_hits") or []) for item in items)
    business_direct_pool = [
        (item["batch_id"], item["item_no"])
        for item in items
        if item["report_item"].get("business_usability_tier") == "direct_pool"
    ]

    reviewed = {"usable": [], "watch": [], "needs_fix": []}
    review_reason: dict[tuple[int, int], str] = {}
    for item in items:
        tier, reason = human_review(item)
        key = (item["batch_id"], item["item_no"])
        reviewed[tier].append(key)
        review_reason[key] = reason

    similarities = []
    for left, right in combinations(items, 2):
        score = jaccard(left["body"], right["body"])
        similarities.append((score, (left["batch_id"], left["item_no"]), (right["batch_id"], right["item_no"])))
    similarities.sort(reverse=True)
    max_similarity = similarities[0][0] if similarities else 0.0
    similarity_warnings = [entry for entry in similarities if entry[0] >= SIMILARITY_THRESHOLD]

    rules_covered = {
        int(item.get("source_row_no"))
        for item in items
        if item.get("source_row_no") is not None
    }
    title_over_20 = [
        (item["batch_id"], item["item_no"])
        for item in items
        if title_weighted_length(item["title"]) > 20
    ]
    body_in_prompt_range = sum(200 <= len(item["body"]) <= 250 for item in items)

    body_text = "\n".join(item["body"] for item in items)
    phrase_counts = {
        "至初纯A2蛋白对新生宝宝": body_text.count("至初纯A2蛋白对新生宝宝"),
        "品质也更透明": body_text.count("品质也更透明"),
        "消费者有被重视到": body_text.count("消费者有被重视到"),
        "奶粉要喝，权益当然": body_text.count("奶粉要喝，权益当然"),
    }

    lines = [
        "# A2礼遇v13｜30篇全链路就绪度验证",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "活动机制已稳定，可进入受控小批量；暂不建议直接大规模转正。当前剩余问题是1篇规则标签泄漏、1次审核JSON误卡，以及原始认可/动机语料在跨批次高频照抄。",
        "",
        "## 关键指标",
        "",
        f"- 发起生成：30；完整标题和正文：{generated_count}/30；生成失败：{30 - generated_count}",
        f"- 机器直接通过且未做后处理：{len(direct_machine_pass)}/30，条目 {direct_machine_pass}",
        f"- 确定性规范化后通过：{len(deterministic)}/30，条目 {deterministic}",
        f"- 模型语义改写后通过：{len(semantic_rewrite)}/30，条目 {semantic_rewrite}",
        f"- 机器最终通过：{machine_pass}/30；后链路未解决：{len(unresolved)}/30，条目 {unresolved}",
        f"- A2专属业务审核标记direct_pool：{len(business_direct_pool)}/30；其中误放过batch 752 item 11，另有batch 752 item 6因前序机器误卡而未进入业务审核",
        f"- 正式禁词最终命中：{final_forbidden_hits}",
        f"- 人工单篇可用：{len(reviewed['usable']) + len(reviewed['watch'])}/30；其中无明显观察项 {len(reviewed['usable'])}篇、批量观察 {len(reviewed['watch'])}篇、需修 {len(reviewed['needs_fix'])}篇",
        f"- 人工需修条目：{reviewed['needs_fix']}",
        f"- P0活动机制错误：0；16条业务规则覆盖：{len(rules_covered)}/16",
        f"- 30篇最大两两2-gram相似度：{max_similarity:.4f}；≥{SIMILARITY_THRESHOLD:.2f}的相似对：{len(similarity_warnings)}",
        f"- 生成约束观察：正文200-250字 {body_in_prompt_range}/30；标题按中文1、emoji2加权超过20的条目 {title_over_20}。这两项不计入业务判错。",
        "",
        "## 候选变化",
        "",
        "本轮未继续改资产，只做同一v13、同一DeepSeek配置的稳定性验证。下一轮应分层处理：",
        "",
        f"- 源头语料：`至初纯A2蛋白对新生宝宝...`出现 {phrase_counts['至初纯A2蛋白对新生宝宝']} 次，`奶粉要喝，权益当然...`出现 {phrase_counts['奶粉要喝，权益当然']} 次。保留原始语料，不压缩；补充更多原始老客感受和参加原因，降低单句被整段照抄的概率。",
        f"- 源头语料：`品质也更透明`出现 {phrase_counts['品质也更透明']} 次，`消费者有被重视到`出现 {phrase_counts['消费者有被重视到']} 次。信息了解后的认可路径逻辑已经正确，但原句数量还不够。",
        "- 后链路业务审核：增加对正文出现`a2礼遇｜...`这类内部组合标签的明确识别；这是语义漏判，不建议做全局字符串硬禁。",
        "- 后链路稳定性：对审核器非JSON响应增加一次JSON修复或重试，避免内容本身可用却被误卡。",
        "",
        "## 重点看",
        "",
    ]

    marker_map = {"needs_fix": "💣", "watch": "👀", "usable": "✅"}
    label_map = {"needs_fix": "需修", "watch": "观察", "usable": "可用"}
    ordered_items = sorted(
        items,
        key=lambda item: (
            {"needs_fix": 0, "watch": 1, "usable": 2}[human_review(item)[0]],
            item["batch_id"],
            item["item_no"],
        ),
    )
    for item in ordered_items:
        tier, _ = human_review(item)
        if tier == "usable":
            continue
        key = (item["batch_id"], item["item_no"])
        lines.extend(
            [
                f"### {marker_map[tier]} batch {item['batch_id']} item {item['item_no']}｜{label_map[tier]}｜{item['title']}",
                "",
                f"复核：{review_reason[key]}",
                "",
                item["body"],
                "",
            ]
        )

    lines.extend(["## 其他产出", ""])
    for item in ordered_items:
        tier, _ = human_review(item)
        if tier != "usable":
            continue
        lines.extend(
            [
                f"### ✅ batch {item['batch_id']} item {item['item_no']}｜可用｜{item['title']}",
                "",
                item["body"],
                "",
            ]
        )

    lines.extend(
        [
            "## 调试信息",
            "",
            "- batch_id: 752, 753, 754",
            f"- batch 752 report: `{OUTPUT_DIR / 'batch752_report.json'}`",
            f"- batch 753 report: `{OUTPUT_DIR / 'batch753_report.json'}`",
            f"- batch 754 report: `{OUTPUT_DIR / 'batch754_report.json'}`",
            f"- rendered prompt: `{prompt_path}`",
            "",
        ]
    )

    preview_path = OUTPUT_DIR / "A2礼遇v13_30篇全链路就绪度验证.md"
    preview_path.write_text("\n".join(lines), encoding="utf-8")

    metrics_path = OUTPUT_DIR / "A2礼遇v13_30篇指标.json"
    metrics_path.write_text(
        json.dumps(
            {
                "batch_ids": list(BATCH_IDS),
                "generated_count": generated_count,
                "machine_direct_pass_count": len(direct_machine_pass),
                "deterministic_normalization_count": len(deterministic),
                "semantic_rewrite_count": len(semantic_rewrite),
                "machine_final_pass_count": machine_pass,
                "machine_unresolved_items": unresolved,
                "business_direct_pool_count": len(business_direct_pool),
                "human_clean_usable_items": reviewed["usable"],
                "human_watch_items": reviewed["watch"],
                "human_needs_fix_items": reviewed["needs_fix"],
                "p0_activity_mechanism_error_count": 0,
                "rule_coverage": len(rules_covered),
                "max_pairwise_jaccard_2gram": round(max_similarity, 4),
                "similarity_warning_count": len(similarity_warnings),
                "title_over_weighted_20_items": title_over_20,
                "body_200_250_count": body_in_prompt_range,
                "phrase_counts": phrase_counts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "preview_path": str(preview_path),
                "prompt_path": str(prompt_path),
                "metrics_path": str(metrics_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
