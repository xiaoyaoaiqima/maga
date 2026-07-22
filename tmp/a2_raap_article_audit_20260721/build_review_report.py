#!/usr/bin/env python3
"""Build the human-calibrated review report for the duplicated RAAP A2 export."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path("/Users/luxifa/maga")
TMP_DIR = ROOT / "tmp/a2_raap_article_audit_20260721"
OUTPUT_DIR = ROOT / "outputs/a2_raap_article_audit_20260721"
REVIEW_PATH = TMP_DIR / "llm_review.json"
SIMILARITY_PATH = TMP_DIR / "similarity_analysis.json"

HOLD_OUT = {
    6: ("activity_mechanism_error", "把12罐档位写成小车车或奶粉二选一。"),
    22: ("old_can_eligibility_error", "用活动前家里尚未喝完的几罐规划本次集罐，暗示旧购买可参加。"),
    31: ("activity_mechanism_error", "把12罐档位写成兑换小车车或自行车。"),
    32: ("old_can_eligibility_error", "明确写家里已经攒了几个，直接能用于本次活动。"),
    66: ("source_stacking", "邻居告知活动后又去门店确认，同一活动发现链叠加两个来源。"),
    77: ("source_stacking", "邻居阿姨和闺蜜同时成为本次活动发现来源。"),
    82: ("old_can_eligibility_error", "用活动前家里已囤数量计算离集罐目标不远。"),
    101: ("source_stacking", "邻居宝妈、闺蜜、门店三个来源叠加。"),
    102: ("activity_mechanism_error", "把小车车、婴儿车写成抽奖奖品。"),
    104: ("activity_mechanism_error", "明确写12罐档位可选小车车或整罐奶粉。"),
    145: ("source_stacking", "邻居、闺蜜、导购三个来源叠加。"),
    150: ("old_can_eligibility_error", "把家里已有罐子收好用于本次开攒。"),
    164: ("source_stacking", "邻居告知后又去门店问导购，同一活动链叠加来源。"),
    182: ("activity_mechanism_error", "明确写12罐可兑换小车车或奶粉。"),
}

LIGHT_FIX_GROUPS = {
    "main_activity_drift": {
        "rows": {35, 111},
        "reason": "上下文槽位是集罐12罐换奶粉，但正文完全改写成抽奖/老客回馈，事实可成立但主内容方向偏移。",
    },
    "deterministic_replace": {
        "rows": {13, 35, 37, 137, 149, 162, 184},
        "reason": "仍含正式规范化词：便便或眼睛，应分别规范为💩、👀。",
    },
    "model_rewrite_term": {
        "rows": {8, 62},
        "reason": "出现顺手，按正式后链路规则交给qwen-plus结合上下文改写。",
    },
    "can_accumulation_surface": {
        "rows": {88, 122, 137, 151, 197},
        "reason": "出现罐子攒起来/把罐子攒起来，与正式的攒罐子禁用边界同义，需要改成直接说集罐。",
    },
    "detection_page_navigation": {
        "rows": {155, 160},
        "reason": "写成翻到页面才看到每批检测，需删除翻页承接，保留页面提到检测即可。",
    },
    "unclear_abbreviation": {
        "rows": {21, 133, 138, 199},
        "reason": "用FL代指福利，表达像字段缩写，不适合作为直接交付正文。",
    },
    "title_content_mismatch": {
        "rows": {173},
        "reason": "标题写抢到了吗，正文没有抢、中奖或稀缺逻辑，标题和正文关系不自然。",
    },
}


def weighted_title_length(title: str) -> int:
    emoji_re = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
    total = 0
    for char in re.sub(r"\s+", "", title):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if emoji_re.fullmatch(char) else 1
    return total


def evidence_for(item: dict, code: str) -> str:
    body = str(item.get("body") or "")
    patterns = {
        "activity_mechanism_error": r"[^。！\n]{0,20}12罐[^。！\n]{0,60}(?:小车车|自行车|婴儿车|抽奖)[^。！\n]{0,30}|[^。！\n]{0,30}(?:小车车|自行车|婴儿车)[^。！\n]{0,50}12罐[^。！\n]{0,20}",
        "old_can_eligibility_error": r"[^。！\n]{0,25}(?:家里还有几罐|家里正好攒了|家里囤的量|家里的罐子)[^。！\n]{0,50}",
        "source_stacking": r"[^。！\n]{0,100}(?:邻居|闺蜜|导购|门店)[^。！\n]{0,100}",
    }
    match = re.search(patterns.get(code, r"$^"), body)
    if match:
        return match.group(0).strip()[:180]
    return body.replace("\n", " ")[:180]


def main() -> None:
    items = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    similarity = json.loads(SIMILARITY_PATH.read_text(encoding="utf-8"))
    by_row = {int(item["excel_row"]): item for item in items}

    light_reasons: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for code, group in LIGHT_FIX_GROUPS.items():
        for row in group["rows"]:
            if row not in HOLD_OUT:
                light_reasons[row].append((code, group["reason"]))

    hold_rows = sorted(HOLD_OUT)
    light_rows = sorted(light_reasons)
    direct_rows = sorted(set(by_row) - set(hold_rows) - set(light_rows))
    title_over_20 = sorted(row for row, item in by_row.items() if weighted_title_length(str(item["title"])) > 20)

    machine_counts: dict[str, int] = defaultdict(int)
    machine_errors = []
    machine_hold_rows = []
    for item in items:
        if item.get("error"):
            machine_errors.append(int(item["excel_row"]))
            continue
        tier = str((item.get("review") or {}).get("business_usability_tier") or "unknown")
        machine_counts[tier] += 1
        if tier == "hold_out":
            machine_hold_rows.append(int(item["excel_row"]))

    issue_rows = []
    for row in hold_rows:
        item = by_row[row]
        code, reason = HOLD_OUT[row]
        issue_rows.append(
            {
                "excel_row": row,
                "id": item["id"],
                "content_id": item["content_id"],
                "title": item["title"],
                "tier": "hold_out",
                "issue_codes": code,
                "reason": reason,
                "evidence": evidence_for(item, code),
            }
        )
    for row in light_rows:
        item = by_row[row]
        codes = [code for code, _ in light_reasons[row]]
        reasons = [reason for _, reason in light_reasons[row]]
        issue_rows.append(
            {
                "excel_row": row,
                "id": item["id"],
                "content_id": item["content_id"],
                "title": item["title"],
                "tier": "light_fix_usable",
                "issue_codes": ";".join(codes),
                "reason": "；".join(reasons),
                "evidence": str(item["body"]).replace("\n", " ")[:220],
            }
        )
    issue_rows.sort(key=lambda item: (0 if item["tier"] == "hold_out" else 1, item["excel_row"]))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "A2礼遇_RAAP文章池_问题明细.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["excel_row", "id", "content_id", "title", "tier", "issue_codes", "reason", "evidence"],
        )
        writer.writeheader()
        writer.writerows(issue_rows)

    lines = [
        "# A2礼遇｜RAAP文章池200篇审查报告",
        "",
        "## 结论",
        "",
        f"两份Excel是字节完全一致的副本，实际只需审查同一批200篇。按最新口径复核后：原文直接可用 {len(direct_rows)}篇，轻修可用 {len(light_rows)}篇，暂不入池 {len(hold_rows)}篇。轻修已全部完成，最终导出可用文章186篇。",
        "",
        "本批集罐主事实总体稳定，但仍存在12罐奖品串档、旧购买罐参与、多个了解来源叠加，以及RAAP没有执行完整后链路规范化的问题。",
        "",
        "## 核心统计",
        "",
        f"- 总文章：200；上下文活动内容全部为`集罐礼-12罐兑1罐`",
        f"- 人工直接可用：{len(direct_rows)}/200",
        f"- 人工轻修可用：{len(light_rows)}/200，Excel行号：{', '.join(map(str, light_rows))}",
        f"- 人工暂不入池：{len(hold_rows)}/200，Excel行号：{', '.join(map(str, hold_rows))}",
        "- `puq/pyq`按运营最新反馈直接放行，视为朋友圈的可用替代表达；`🆓`是免费的规范表达",
        "- P0奖品/机制错误：5篇，Excel行号：6、31、102、104、182",
        "- 旧购买罐参与：4篇，Excel行号：22、32、82、150",
        "- 多来源叠加：5篇，Excel行号：66、77、101、145、164",
        f"- 标题加权明显超过20：{len(title_over_20)}篇，Excel行号：{', '.join(map(str, title_over_20)) or '无'}；仅作生成约束观察，不计业务判错",
        f"- 完全重复正文：0；重复标题1组，Excel行号118、194",
        f"- 最大两两2-gram相似度：{similarity['maxPairwiseJaccard2gram']}；≥0.35相似对：{similarity['pairCountAtOrAbove035']}，整批没有明显整篇复制",
        "",
        "## 暂不入池明细",
        "",
        "| Excel行号 | Content ID | 标题 | 问题 | 证据 |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for row in hold_rows:
        item = by_row[row]
        code, reason = HOLD_OUT[row]
        evidence = evidence_for(item, code).replace("|", "｜").replace("\n", " ")
        lines.append(f"| {row} | {item['content_id']} | {item['title']} | {reason} | {evidence} |")

    lines.extend(["", "## 暂不入池全文", ""])
    for row in hold_rows:
        item = by_row[row]
        code, reason = HOLD_OUT[row]
        lines.extend(
            [
                f"### 行{row}｜{item['title']}",
                "",
                f"问题：{code}｜{reason}",
                "",
                str(item["body"]),
                "",
            ]
        )

    lines.extend(["## 轻修问题分组", ""])
    for code, group in LIGHT_FIX_GROUPS.items():
        rows = sorted(row for row in group["rows"] if row not in HOLD_OUT)
        if not rows:
            continue
        lines.extend(
            [
                f"### {code}｜{len(rows)}篇",
                "",
                group["reason"],
                "",
                f"Excel行号：{', '.join(map(str, rows))}",
                "",
            ]
        )

    lines.extend(
        [
            "## 模型审核与人工校准",
            "",
            f"- a2专属模型审核：direct_pool {machine_counts.get('direct_pool', 0)}篇、hold_out {machine_counts.get('hold_out', 0)}篇、最终仍无法解析 {len(machine_errors)}篇。",
            f"- 模型hold_out行号：{', '.join(map(str, sorted(machine_hold_rows)))}；异常行号：{', '.join(map(str, machine_errors))}",
            "- 第20行是模型误判：先正确写12罐换1罐奶粉，后面泛提小车车，按已确认的‘正确档位后泛提其他档位奖品可通过’放行。",
            "- 第35、111行不属于奖品机制硬错，但偏离本篇`集罐12罐换奶粉`槽位，人工改判为轻修。",
            "- 第17行模型多次未返回JSON，人工复核为可直接使用；`至高2499元好礼`属于已放行命名。",
            "- 模型漏掉了第22、66、82、101、104、164行的旧罐、来源叠加或12罐奖品串档，后链路金标仍需补这批case。",
            "",
            "## 批量表达观察",
            "",
            f"- `闭眼入不踩雷`：{similarity['phraseCounts']['闭眼入不踩雷']}篇",
            f"- `继续回购`：{similarity['phraseCounts']['继续回购']}篇",
            f"- `值得囤`：{similarity['phraseCounts']['值得囤']}篇",
            f"- `长肉`：{similarity['phraseCounts']['长肉']}篇",
            f"- `扫罐底码`：{similarity['phraseCounts']['扫罐底码']}篇",
            "",
            "这些不是单篇硬错，且整篇相似度不高；但收口和产品体验词簇频率较高，大批量投放时建议做配额控制，不要新增成禁词。",
            "",
            "## 文件关系",
            "",
            "- `文章池导出_2026-07-21.xlsx`与`文章池导出_2026-07-21 (1).xlsx`的SHA-256均为`e76a1c54f23fb6a2b984d3dff3b2a2c45f071d14c31fdfb0790032e9c84dcecc`。",
            "- 两份文件行号完全一致；本报告行号可用于任意一份文件。",
            "",
        ]
    )

    report_path = OUTPUT_DIR / "A2礼遇_RAAP文章池_200篇审查报告.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "direct_pool": len(direct_rows),
                "light_fix_usable": len(light_rows),
                "hold_out": len(hold_rows),
                "report_path": str(report_path),
                "csv_path": str(csv_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
