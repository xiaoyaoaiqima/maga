#!/usr/bin/env python3
"""Mark-only storyline consistency audit for Wangyue batch response JSON files."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


HELPER_PATH = Path("/Users/luxifa/maga/platform-server/scripts/run_v380_wangyue_row18_distributed_variants_batch.py")
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence")


def _load_helper():
    spec = importlib.util.spec_from_file_location("wangyue_batch_helper", HELPER_PATH)
    helper = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(helper)
    return helper


ENTRY_PATTERNS: dict[str, list[str]] = {
    "meal_table": ["饭桌", "吃饭", "饭菜", "青椒", "牛肉", "筷子", "晚饭", "早餐"],
    "comparison": ["对比", "选奶", "挑", "看了好几款", "最后选", "定了", "拿定主意"],
    "replenish": ["补货", "又补", "下单", "见底", "快见底", "顺手带上", "订单"],
    "home_inventory": ["整理", "常备", "清单", "柜子", "衣柜", "收拾", "翻到", "家里一直有"],
    "asked_or_comment": ["被朋友问", "问起", "随口", "说了一句", "冒一句", "我爸", "我妈", "队友"],
    "photo_or_record": ["相册", "手机", "记录", "笔记", "回头看", "回看"],
    "activity_after": ["出去", "小区", "跑", "活动", "体育课", "回来", "放学", "接回来"],
    "quiet_task": ["拼图", "写作业", "积木", "乐高", "绘本", "安静", "坐得住"],
}

PRODUCT_REASON_PATTERNS: dict[str, list[str]] = {
    "protection_ingredients": ["乳铁蛋白", "HMO", "保护力"],
    "basic_nutrition": ["基础营养", "关键营养", "多种营养", "多种维生素", "营养比较全", "营养都有"],
    "minerals": ["钙铁锌"],
    "eye_brain": ["DHA", "燕窝酸", "眼脑"],
    "taste_acceptance": ["清淡", "奶香", "接受", "顺口", "痛快", "没拒绝", "愿意喝"],
    "routine_fit": ["日常", "长期", "常备", "一直喝", "继续买", "继续留"],
}

EVIDENCE_PATTERNS: dict[str, list[str]] = {
    "energy_state": ["精神", "精力", "不蔫", "神气", "状态", "有劲", "接着忙活", "活力"],
    "eating": ["吃得香", "吃饭", "饭也吃", "胃口", "饭量"],
    "attention": ["拼图", "写作业", "坐得住", "专注", "三分钟热度", "自己坐"],
    "growth": ["窜", "裤脚", "短了一截", "够到", "长", "阶段变化"],
    "disease_or_environment": ["咳", "感冒", "发烧", "不舒服", "请假", "传染", "中招", "小状况", "没受影响"],
    "acceptance": ["喝得", "喝完", "端着杯子", "接过杯子", "咕咚", "不拒绝", "顺口"],
}

RISK_PATTERNS: dict[str, list[str]] = {
    "protection_disease_contrast": [
        "邻居家孩子咳",
        "别人.*咳",
        "小朋友.*咳",
        "请假",
        "传染",
        "中招",
        "没受影响",
        "小状况.*少",
    ],
    "protection_environment_anchor": [
        "天气变化.*(没|不|挺|状态|精神|蔫)",
        "外面.*活动多.*(没|不|状态|精神)",
    ],
    "fixed_usage": [
        "每天冲",
        "每天.*一杯",
        "早上.*一杯",
        "日常冲一杯",
        "正餐.*一杯",
        "一杯.*(补|额外补)",
        "早晚",
        "早餐搭子",
    ],
    "direct_product_causality": [
        "大概跟.*旺玥有关",
        "可能跟.*旺玥有关",
        "估计跟.*旺玥",
        "大概.*起了点作用",
        "可能.*起了点作用",
        "它就是能续上",
        "旺玥.{0,12}(让|使|带来|变得)",
        "旺玥.*没白喝",
        "喝到现在.*状态",
    ],
    "summary_tone": [
        "没走偏",
        "没白折腾",
        "没白",
        "心里挺稳",
        "挺踏实",
        "更有数",
        "刚刚好",
        "这题",
    ],
    "fallback_logic": [
        "底子铺好",
        "兜底",
        "托底",
        "营养有地方补",
        "不费心再想别的",
        "不用我额外再补",
        "不用.*额外补",
        "至少.*有个稳",
        "算有谱",
    ],
    "brief_translation_tone": [
        "有存在感",
        "这块",
        "对路",
        "接住",
    ],
    "typo_or_broken": [
        "孩子得挺",
        "喝了.*，得挺",
    ],
    "product_fact_number_review": [
        "30多种",
        "三十多种",
    ],
}


def _matches(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text):
            hits.append(pattern)
    return hits


def _family_hits(text: str, families: dict[str, list[str]]) -> dict[str, list[str]]:
    return {name: hits for name, patterns in families.items() if (hits := _matches(text, patterns))}


def _load_asset_rows(asset_key: str | None, database_url: str | None) -> dict[int, dict[str, Any]]:
    if not asset_key:
        return {}
    helper = _load_helper()
    conn = helper._connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select content_json
                from asset_registry
                where asset_key=%s and asset_stage='production' and status='active'
                order by version_no desc, id desc
                limit 1
                """,
                (asset_key,),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError(f"missing active article asset: {asset_key}")
        content = helper._json_value(row["content_json"])
        result: dict[int, dict[str, Any]] = {}
        for item in content.get("items") or []:
            row_no = int(item.get("source_row_no") or item.get("item_no") or 0)
            if row_no:
                result[row_no] = item
        return result
    finally:
        conn.close()


def _severity(flags: list[str], entry_count: int, reason_count: int, evidence_count: int) -> str:
    hard_flags = {
        "protection_disease_contrast",
        "protection_environment_anchor",
        "fixed_usage",
        "direct_product_causality",
    }
    if hard_flags.intersection(flags):
        return "needs_fix"
    if entry_count >= 4 or reason_count >= 4 or evidence_count >= 4:
        return "review"
    if flags:
        return "review"
    return "ok"


def _analyze_item(item: dict[str, Any], rule: dict[str, Any] | None) -> dict[str, Any]:
    title = str(item.get("title") or "")
    body = str(item.get("body") or "")
    text = f"{title}\n{body}"
    entry_hits = _family_hits(text, ENTRY_PATTERNS)
    reason_hits = _family_hits(text, PRODUCT_REASON_PATTERNS)
    evidence_hits = _family_hits(text, EVIDENCE_PATTERNS)

    risk_hits = _family_hits(text, RISK_PATTERNS)
    flags = sorted(risk_hits)
    protection_context = any(
        marker in text
        for marker in ("乳铁蛋白", "HMO", "保护力")
    ) or any(
        marker in str((rule or {}).get(key) or "")
        for key in ("painpoint", "selling_point", "selling_description", "story_spine")
        for marker in ("保护", "乳铁蛋白", "HMO")
    )
    if protection_context and evidence_hits.get("disease_or_environment") and "protection_disease_contrast" not in flags:
        flags.append("protection_disease_contrast")

    entry_count = len(entry_hits)
    reason_count = len(reason_hits)
    evidence_count = len(evidence_hits)
    severity = _severity(flags, entry_count, reason_count, evidence_count)
    return {
        "item_no": item.get("item_no"),
        "title": title,
        "machine_hard_pass": item.get("hard_pass"),
        "machine_rewrite_required": item.get("rewrite_required"),
        "business_usability_tier": item.get("business_usability_tier"),
        "post_type": (rule or {}).get("post_type") or "",
        "painpoint": (rule or {}).get("painpoint") or "",
        "selling_point": (rule or {}).get("selling_point") or "",
        "entry_family_count": entry_count,
        "entry_families": ",".join(sorted(entry_hits)),
        "product_reason_count": reason_count,
        "product_reason_families": ",".join(sorted(reason_hits)),
        "evidence_count": evidence_count,
        "evidence_families": ",".join(sorted(evidence_hits)),
        "flags": ",".join(flags),
        "severity": severity,
        "body": body,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "item_no",
        "title",
        "severity",
        "flags",
        "entry_family_count",
        "entry_families",
        "product_reason_count",
        "product_reason_families",
        "evidence_count",
        "evidence_families",
        "machine_hard_pass",
        "machine_rewrite_required",
        "business_usability_tier",
        "post_type",
        "painpoint",
        "selling_point",
        "body",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_md(path: Path, *, response_path: Path, asset_key: str | None, rows: list[dict[str, Any]]) -> None:
    counts = Counter(row["severity"] for row in rows)
    flag_counts: Counter[str] = Counter()
    for row in rows:
        for flag in str(row["flags"] or "").split(","):
            if flag:
                flag_counts[flag] += 1
    lines = [
        "# Wangyue Storyline Consistency Audit",
        "",
        f"- source JSON: `{response_path}`",
        f"- asset_key: `{asset_key or ''}`",
        f"- total: {len(rows)}",
        f"- severity counts: `{dict(counts)}`",
        f"- flag counts: `{dict(flag_counts)}`",
        "",
        "## Method",
        "",
        "本报告是本地 mark-only 粗筛，不调用 LLM，不改写正文。它用规则把人工反复指出的问题显性化：多入口、多产品理由、多效果证明、保护力疾病对照、固定喝法、直接因果、总结腔和兜底逻辑。",
        "",
        "## Items Needing Review",
        "",
    ]
    risky = [row for row in rows if row["severity"] != "ok"]
    if not risky:
        lines.append("No review items detected.")
    for row in risky:
        lines.extend(
            [
                f"### {row['item_no']}. {row['title']}",
                "",
                f"- severity: `{row['severity']}`",
                f"- flags: `{row['flags']}`",
                f"- entry families ({row['entry_family_count']}): `{row['entry_families']}`",
                f"- product reason families ({row['product_reason_count']}): `{row['product_reason_families']}`",
                f"- evidence families ({row['evidence_count']}): `{row['evidence_families']}`",
                f"- machine hard pass: `{row['machine_hard_pass']}`; machine rewrite: `{row['machine_rewrite_required']}`; business tier: `{row['business_usability_tier']}`",
                "",
                str(row["body"]),
                "",
            ]
        )
    lines.extend(["## All Items", ""])
    for row in rows:
        lines.append(
            f"- {row['item_no']}. {row['title']} -> {row['severity']} | flags={row['flags'] or '-'} | "
            f"entry={row['entry_family_count']} reason={row['product_reason_count']} evidence={row['evidence_count']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("response_json", type=Path)
    parser.add_argument("--asset-key", default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--out-prefix", default=None)
    args = parser.parse_args()

    data = json.loads(args.response_json.read_text(encoding="utf-8"))
    items = data.get("data", {}).get("report", {}).get("items") or []
    rules = _load_asset_rows(args.asset_key, args.database_url)
    rows = [_analyze_item(item, rules.get(int(item.get("item_no") or 0))) for item in items]

    prefix = args.out_prefix
    if not prefix:
        stem = args.response_json.stem.replace("_response", "")
        prefix = str(OUTPUT_DIR / f"{stem}_storyline_consistency")
    csv_path = Path(f"{prefix}.csv")
    md_path = Path(f"{prefix}.md")
    _write_csv(csv_path, rows)
    _write_md(md_path, response_path=args.response_json, asset_key=args.asset_key, rows=rows)
    print(json.dumps({
        "csv_path": str(csv_path),
        "md_path": str(md_path),
        "severity_counts": dict(Counter(row["severity"] for row in rows)),
        "flag_counts": dict(Counter(flag for row in rows for flag in str(row["flags"] or "").split(",") if flag)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
