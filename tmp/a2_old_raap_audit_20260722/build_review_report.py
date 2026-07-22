#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path("/Users/luxifa/maga")
SCAN_PATH = ROOT / "tmp/a2_old_raap_audit_20260722/deterministic_audit.json"
OUTPUT_DIR = ROOT / "outputs/a2_old_raap_audit_20260722"
MD_PATH = OUTPUT_DIR / "A2礼遇_老RAAP两批审查.md"
JSON_PATH = OUTPUT_DIR / "A2礼遇_老RAAP两批审查结果.json"

REJECTS = {
    (1, 3): ("old_can_eligibility_error", "“正好家里罐子攒着，果断参加”明确把家中已有罐子用于本次活动。"),
    (1, 140): ("old_can_eligibility_error", "“赶紧把家里罐子攒起来”明确指向活动前家中已有罐子。"),
    (2, 42): ("old_can_eligibility_error", "“算算家里罐子够不够”把家中现有罐子与本次兑换资格连接。"),
    (2, 78): ("instruction_leakage", "正文出现“顺手（不对，不能写顺手）”，属于模型自我纠错和提示词泄漏。"),
    (2, 97): ("wrong_can_count_prize_mapping", "“集12罐能换小车车或者奶粉”把12罐档位错误对应到小车车；小车车应为3罐档位。"),
    (2, 111): ("old_can_eligibility_error", "“把家里存的那几罐码扫了”明确使用活动前库存参加。"),
    (2, 198): ("old_can_eligibility_error", "“把家里平时喝的罐子集起来就行”明确暗示旧罐可参加。"),
}

EXTRA_LIGHT = {
    (1, 24): ("can_count_prize_wording_ambiguous", "12罐换奶粉后紧接“还能换小车车”，容易理解为同一档位追加奖品。"),
    (1, 69): ("can_count_prize_wording_ambiguous", "12罐换奶粉后紧接“还能换小车车”，档位归属不清。"),
    (1, 136): ("can_count_prize_wording_ambiguous", "“买12罐到手13罐，还能换小车车或者婴儿车”像是12罐可继续选其他档位奖品。"),
    (1, 185): ("can_count_prize_wording_ambiguous", "12罐换奶粉后写“还能换小车车、婴儿车”，需要拆成其他档位泛提。"),
    (2, 140): ("can_count_prize_wording_ambiguous", "“买12罐……这些可以选”容易理解为12罐可在多个奖品中任选。"),
    (1, 131): ("old_can_wording_risk", "“罐子攒起来能换东西”没有明确旧罐，但容易诱发旧罐联想，改成直接说参加集罐。"),
    (1, 163): ("old_can_wording_risk", "“罐子攒起来能换礼品”没有明确旧罐，但建议去掉存罐动作。"),
    (2, 68): ("old_can_wording_risk", "“罐子攒起来可以换礼品”建议改为直接介绍集罐档位。"),
    (1, 67): ("core_activity_detail_missing", "槽位是12罐兑1罐，正文只写小车车，遗漏本篇主活动档位。"),
    (1, 158): ("core_activity_detail_missing", "槽位是12罐兑1罐，正文只泛写小车车或奶粉，没有12罐档位。"),
    (1, 187): ("core_activity_detail_missing", "槽位是12罐兑1罐，正文只写集罐换一罐，没有具体12罐。"),
    (2, 3): ("core_activity_detail_missing", "槽位是12罐兑1罐，正文只讲抽奖与回馈，未写12罐集罐。"),
    (2, 20): ("core_activity_detail_missing", "槽位是12罐兑1罐，正文只泛写集罐兑奶粉和小车车；“抽奖拿到”也建议改成“抽奖有”。"),
    (2, 31): ("core_activity_detail_missing", "槽位是12罐兑1罐，正文未写集罐档位；另有“从女儿童年小麻杆”病句。"),
    (2, 67): ("core_activity_detail_missing", "槽位是12罐兑1罐，正文只讲抽奖和回馈，遗漏主活动。"),
    (2, 155): ("core_activity_detail_missing", "槽位是12罐兑1罐，正文只写集罐兑一罐，没有12罐档位。"),
    (1, 124): ("typo", "“收到导发消息”存在明显错字，应改为导购发消息。"),
    (2, 58): ("malformed_activity_expression", "“12集1兑换一罐”表达残缺，应改为“集12罐兑换1罐”。"),
    (1, 190): ("keyword_format", "正文写成“a2 至初”，需要合并为完整关键词“a2至初”。"),
    (1, 33): ("identity_timeline_ambiguous", "“从出生就喝a2至初”与“转奶的时候”并列，时间线容易冲突。"),
    (1, 144): ("identity_timeline_ambiguous", "“从出生就喝它”与“转奶顺利”并列，建议只保留一种经历。"),
    (2, 84): ("identity_timeline_ambiguous", "“从出生就喝这个”与“当初转奶”并列，时间线含糊。"),
    (2, 189): ("identity_timeline_ambiguous", "“从出生就喝它”与“转奶顺利”并列，建议改清楚。"),
}

TERM_FIXES = {
    "便便": "替换为💩",
    "顺便": "按上下文自然改写，不能机械替换",
    "顺手": "按上下文自然改写；若伴随自我纠错则直接淘汰",
    "眼睛": "替换为👀",
    "失败": "按负面语境自然改写",
    "肠胃": "替换为肚肚",
    "报名": "删除报名表述，活动无需报名",
}


def main() -> None:
    scan = json.loads(SCAN_PATH.read_text(encoding="utf-8"))
    rows = {(item["file_index"], item["source_row"]): item for item in scan["results"]}
    light: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)

    for key, item in rows.items():
        for hit in item["hits"]:
            if hit["code"] != "forbidden_term" or key in REJECTS:
                continue
            term = hit["evidence"]
            light[key].append({
                "code": "production_rewrite_term",
                "evidence": term,
                "reason": TERM_FIXES.get(term, "按当前production规则轻修"),
            })

    for key, (code, reason) in EXTRA_LIGHT.items():
        if key not in REJECTS:
            light[key].append({"code": code, "evidence": "", "reason": reason})

    review_rows = []
    for key, item in rows.items():
        if key in REJECTS:
            code, reason = REJECTS[key]
            tier = "明确问题"
            issues = [{"code": code, "reason": reason}]
        elif key in light:
            tier = "轻修可用"
            issues = light[key]
        else:
            tier = "可直接使用"
            issues = []
        review_rows.append({
            "file_index": item["file_index"],
            "source_row": item["source_row"],
            "row_ref": item["row_ref"],
            "content_id": item["content_id"],
            "title": item["title"],
            "tier": tier,
            "issues": issues,
        })

    counts = defaultdict(lambda: defaultdict(int))
    for item in review_rows:
        counts[item["file_index"]][item["tier"]] += 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps({"counts": counts, "rows": review_rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# A2礼遇老RAAP两批审查",
        "",
        "审查范围：两份工作簿各200篇，共400篇。未修改原文件，未调用外部模型API。",
        "",
        "## 结论",
        "",
        "| 文件 | 明确问题 | 轻修可用 | 可直接使用 |",
        "|---|---:|---:|---:|",
        f"| 文件1：文章池导出_2026-07-22.xlsx | {counts[1]['明确问题']} | {counts[1]['轻修可用']} | {counts[1]['可直接使用']} |",
        f"| 文件2：文章池导出_2026-07-22 (1).xlsx | {counts[2]['明确问题']} | {counts[2]['轻修可用']} | {counts[2]['可直接使用']} |",
        f"| 合计 | {sum(counts[i]['明确问题'] for i in (1, 2))} | {sum(counts[i]['轻修可用'] for i in (1, 2))} | {sum(counts[i]['可直接使用'] for i in (1, 2))} |",
        "",
        "标题加权长度没有超过20字的；正文无完全重复。存在4组重复标题，作为批次多样性提醒，不按单篇错误淘汰。",
        "",
        "## 7篇明确有问题",
        "",
    ]
    for key in sorted(REJECTS):
        item = rows[key]
        code, reason = REJECTS[key]
        lines.extend([
            f"### {item['row_ref']}｜{item['content_id']}｜{item['title']}",
            "",
            f"- 问题：`{code}`",
            f"- 原因：{reason}",
            "",
        ])

    lines.extend(["## 轻修项", "", "### 当前production词面改写", ""])
    grouped_terms: dict[str, list[str]] = defaultdict(list)
    for key, issues in light.items():
        for issue in issues:
            if issue["code"] == "production_rewrite_term":
                grouped_terms[issue["evidence"]].append(rows[key]["row_ref"])
    for term, refs in sorted(grouped_terms.items(), key=lambda item: (-len(item[1]), item[0])):
        lines.append(f"- `{term}`：{len(refs)}篇；{TERM_FIXES.get(term, '按上下文轻修')}。行号：{'、'.join(refs)}")

    lines.extend(["", "### 其他事实、逻辑和表达轻修", ""])
    for key in sorted(EXTRA_LIGHT):
        if key in REJECTS:
            continue
        item = rows[key]
        code, reason = EXTRA_LIGHT[key]
        lines.append(f"- {item['row_ref']}｜{item['content_id']}｜`{code}`：{reason}")

    lines.extend(["", "## 多样性提醒", ""])
    for group in scan["duplicates"]["title_groups"]:
        lines.append(f"- 标题“{group['title']}”重复：{'、'.join(group['rows'])}")

    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "markdown": str(MD_PATH),
        "json": str(JSON_PATH),
        "counts": {str(k): dict(v) for k, v in counts.items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
