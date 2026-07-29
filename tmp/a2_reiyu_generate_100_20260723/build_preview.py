from __future__ import annotations

import json
from pathlib import Path


BATCH_ID = 832
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_generate_100_can_20260723")
REPORT_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_full_report.json"
PREVIEW_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_100篇集罐批次预览.md"
PROMPT_PATH = OUTPUT_DIR / f"batch{BATCH_ID}_随机完整Prompt_item57.md"

MANUAL_NEEDS_FIX = {
    11: "把活动前家里快喝完的一箱奶粉接到集罐上，仍有旧库存参与暗示。",
    46: "照抄了“经营跟用户之间的信任感”式业务语料，口吻不自然。",
    92: "照抄了“经营跟用户之间的信任感”式业务语料，口吻不自然。",
}


def guard_reason(item: dict) -> str:
    if item["item_no"] in MANUAL_NEEDS_FIX:
        return MANUAL_NEEDS_FIX[item["item_no"]]
    quality = item.get("quality") or {}
    for key in (
        "a2_reiyu_old_can_guard",
        "a2_reiyu_batch_detection_guard",
        "a2_reiyu_text_guard",
        "a2_reiyu_forbidden_terms_guard",
    ):
        payload = quality.get(key)
        if isinstance(payload, dict) and payload.get("pass") is False and payload.get("reason"):
            return str(payload["reason"])
    return str(
        item.get("rewrite_reason")
        or item.get("business_usability_reason")
        or item.get("error_message")
        or "未通过本轮严格审核。"
    )


def category(item: dict) -> str:
    snapshot = item.get("generation_snapshot") or {}
    rule = (snapshot.get("business_rule") or {}).get("business_rule") or ""
    return "12罐" if "12罐" in rule else "其他罐"


def article_section(marker: str, label: str, item: dict, reason: str | None = None) -> list[str]:
    lines = [f"### {marker} item {item['item_no']}｜{label}｜{item.get('title') or '无标题'}", ""]
    if reason:
        lines.extend([f"问题：{reason}", ""])
    lines.extend([str(item.get("body") or "（无正文）"), ""])
    return lines


def main() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    items = report["items"]
    usable = [
        item
        for item in items
        if item.get("status") == "generated"
        and item.get("business_usability_tier") == "direct_pool"
        and item.get("hard_pass") is True
        and item.get("body")
        and item["item_no"] not in MANUAL_NEEDS_FIX
    ]
    watch = [item for item in items if item.get("business_usability_tier") == "watch"]
    needs_fix = [item for item in items if item not in usable and item not in watch]

    usable_nos = [item["item_no"] for item in usable]
    watch_nos = [item["item_no"] for item in watch]
    needs_fix_nos = [item["item_no"] for item in needs_fix]
    summary = report["summary"]

    lines = [
        "# A2礼遇集罐100篇批次预览",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## 结论",
        "",
        "本批完成100次生成；严格机审与人工复核后62篇可直接入库，7篇待复核，31篇需修或淘汰。本轮不补跑。",
        "",
        "## 关键指标",
        "",
        "- 请求/尝试生成：100",
        "- 原始生成：100；生成接口失败：0",
        "- 报告状态：generated 99；failed 1。item 23 因标题加权长度超过20被置为 failed，但正文保留在全量文件中",
        "- 直接通过：65",
        "- 后链路改写通过：0。本批采用 generate_only，未执行自动改写",
        f"- 机器最终通过：{summary['hard_pass_count']}。其中 item 87 的业务档位为 hold_out，已人工排除",
        f"- 当前规则确定性复审：65/65；人工业务可用：{len(usable)}",
        f"- 禁词命中文章：{summary['forbidden_hit_count']}",
        f"- 最大两两2-gram Jaccard：{summary['max_pairwise_jaccard_2gram']}；相似度预警：{summary['similarity_warning_count']}",
        f"- 人工可用 item：{', '.join(map(str, usable_nos))}",
        f"- 待复核 item：{', '.join(map(str, watch_nos))}",
        f"- 需修/淘汰 item：{', '.join(map(str, needs_fix_nos))}",
        f"- 金标审核不可用 item：{', '.join(map(str, watch_nos))}",
        "",
        "## 本批素材范围",
        "",
        "仅使用 production asset 2005 / v39 的集罐业务素材 source_row_no 9-16：3罐小车车、6罐自行车、12罐奶粉、18罐婴儿车。",
        "",
        "## 重点看",
        "",
    ]

    for item in needs_fix:
        marker = "⛔" if item.get("status") == "failed" else "💣"
        lines.extend(article_section(marker, "需修/淘汰", item, guard_reason(item)))

    for item in watch:
        lines.extend(
            article_section(
                "👀",
                "待复核",
                item,
                "金标语义审核本轮返回不可用结果，按规则不能自动进入直接可用池。",
            )
        )

    lines.extend(["## 其他产出", ""])
    for item in usable:
        lines.extend(article_section("✅", f"可用｜{category(item)}", item))

    lines.extend(
        [
            "## 调试信息",
            "",
            f"- batch_id：{BATCH_ID}",
            "- production asset：2005 / v39",
            "- draft_id：无，本批直接使用 production 限定素材生成",
            f"- 完整报告：`{REPORT_PATH}`",
            f"- 全量CSV：`{OUTPUT_DIR / f'batch{BATCH_ID}_100篇全量.csv'}`",
            f"- 人工复核可用CSV：`{OUTPUT_DIR / f'batch{BATCH_ID}_人工复核可用62篇.csv'}`",
            f"- 随机完整Prompt：`{PROMPT_PATH}`",
            "",
        ]
    )
    PREVIEW_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "preview_path": str(PREVIEW_PATH),
                "usable": len(usable),
                "watch": len(watch),
                "needs_fix": len(needs_fix),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
