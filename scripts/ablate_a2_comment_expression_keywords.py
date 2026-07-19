#!/usr/bin/env python3
"""Ablate comment expression keyword categories for A2 comment generation."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SCRIPT_DIR = REPO_ROOT / ".local/archive/content-generation-scripts/20260704_ugc_ppl_script_cleanup/scripts"
sys.path.insert(0, str(ARCHIVE_SCRIPT_DIR))

from run_a2_month_center_direction_batch import call_model, load_dotenv  # noqa: E402


DEFAULT_API_BASE = "http://127.0.0.1:5100"
DEFAULT_KEYWORD_ASSET = "default_content_generation_keywords"
DEFAULT_RULE_ASSET = "a2_sentiment_comment_activity"

FORBIDDEN = [
    "缺货",
    "断货",
    "没货",
    "断粮",
    "断档",
    "焦虑",
    "恐慌",
    "小程序",
    "微信",
    "召回",
    "FDA",
    "热线",
    "呕吐毒素",
    "医疗护理",
    "美版",
    "毒奶",
    "假货",
    "保证没问题",
    "绝对安全",
    "无风险",
    # 业务新要求：暂不露出蜡样/蜡毒检测数值和检测报告/检测项目的明确数量。
    "0.03",
    "60+",
    "60多项",
]

AUDIT_ONLY_FORBIDDEN = ["没找到", "找不到", "难买", "心焦", "心急"]

ABLATIONS: dict[str, set[str]] = {
    "baseline": set(),
    "no_perturbation": {"perturbation_rule"},
    "no_persona": {"persona"},
    "no_writing_method": {"writing_method"},
    "no_speaking_style": {"comment_speaking_style"},
    "no_format_control": {"comment_format_control"},
    "no_comment_generation_requirement": {"comment_generation_requirement"},
    "no_comment_writing_instruction": {"comment_writing_instruction"},
    "only_comment_generation_requirement": {
        "comment_writing_instruction",
        "comment_format_control",
    },
    "business_examples_only": {
        "comment_generation_requirement",
        "comment_writing_instruction",
        "comment_format_control",
    },
    "minimal_requirement_only": {
        "perturbation_rule",
        "persona",
        "writing_method",
        "comment_speaking_style",
        "comment_format_control",
    },
    "keep_requirement_format": {
        "perturbation_rule",
        "persona",
        "writing_method",
        "comment_speaking_style",
    },
    "keep_requirement_format_speaking": {
        "perturbation_rule",
        "persona",
        "writing_method",
    },
    "keep_requirement_format_writing": {
        "perturbation_rule",
        "persona",
        "comment_speaking_style",
    },
}

SUBKEYWORD_ABLATIONS: dict[str, set[str]] = {
    "no_comment_micro_reply": {"comment_micro_reply"},
    "no_comment_micro_controls": {"comment_micro_reply"},
    "no_comment_short_clean": {"comment_short_clean"},
    "no_comment_light_emoji": {"comment_light_emoji"},
    "no_comment_two_sentence": {"comment_two_sentence"},
    "no_comment_21_35": {"comment_21_35"},
    "no_comment_21_50": {"comment_21_50"},
    "no_comment_long_controls": {"comment_two_sentence", "comment_21_35", "comment_21_50"},
    "no_natural_comment": {"natural_comment"},
    "no_specific_comment_question": {"specific_comment_question"},
    "no_light_comment_experience": {"light_comment_experience"},
}


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url) as resp:
        return json.load(resp)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def comment_categories(content: dict[str, Any]) -> list[dict[str, Any]]:
    categories = []
    for category in content.get("categories") or []:
        app = category.get("applicable_content_types")
        if isinstance(app, list) and app and "comment" not in {str(item) for item in app}:
            continue
        categories.append(category)
    return categories


def categories_without(content: dict[str, Any], excluded_codes: set[str]) -> list[dict[str, Any]]:
    kept = []
    for category in comment_categories(content):
        code = str(category.get("category_code") or category.get("code") or "").strip()
        if code in excluded_codes:
            continue
        kept.append(category)
    return kept


def categories_for_variant(content: dict[str, Any], variant: str) -> list[dict[str, Any]]:
    categories = categories_without(content, ABLATIONS.get(variant, set()))
    excluded_keywords = SUBKEYWORD_ABLATIONS.get(variant, set())
    if not excluded_keywords:
        return categories
    patched: list[dict[str, Any]] = []
    for category in categories:
        item = copy.deepcopy(category)
        item["sub_keywords"] = [
            keyword
            for keyword in item.get("sub_keywords") or []
            if str(keyword.get("keyword_code") or "").strip() not in excluded_keywords
        ]
        patched.append(item)
    return patched


def selected_rules(items: list[dict[str, Any]], max_rules: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        major = str(item.get("business_rule") or "").split("-", 1)[0]
        buckets[major].append(item)
    preferred = {
        "有货": ["a2_direct_01", "a2_direct_03"],
        "批批检": ["a2_direct_05", "a2_direct_09"],
        "转奶": ["a2_direct_10", "a2_direct_14"],
        "会员权益": ["a2_direct_28", "a2_direct_29"],
    }
    selected: list[dict[str, Any]] = []
    by_id = {str(item.get("rule_id")): item for item in items}
    for ids in preferred.values():
        for rule_id in ids:
            item = by_id.get(rule_id)
            if item:
                selected.append(item)
    if len(selected) < max_rules:
        seen = {id(item) for item in selected}
        for item in items:
            if id(item) not in seen:
                selected.append(item)
            if len(selected) >= max_rules:
                break
    return selected[:max_rules]


def rule_for_prompt(item: dict[str, Any], *, item_no: int) -> dict[str, Any]:
    examples = [str(value).strip() for value in item.get("examples") or [] if str(value).strip()]
    # Mirror comment PPL enough for the experiment: only a few examples enter the prompt.
    return {
        **item,
        "examples": examples[:3],
        "supplements": [],
        "example_pool_count": len(examples),
        "example_sample_count": min(3, len(examples)),
        "selected_example_indices": list(range(min(3, len(examples)))),
        "item_no": item_no,
    }


def parse_comment(raw: str) -> str:
    value = str(raw or "").strip()
    value = re.sub(r"^```(?:json|text)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value).strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, str):
            return parsed.strip()
        if isinstance(parsed, list) and parsed:
            return str(parsed[0]).strip()
        if isinstance(parsed, dict):
            for key in ["comment", "content", "内容", "text"]:
                if parsed.get(key):
                    return str(parsed[key]).strip()
    except json.JSONDecodeError:
        pass
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return ""
    first = re.sub(r"^\s*\d+[、.]\s*", "", lines[0]).strip(" -，,。")
    return first.strip().strip('"').strip("'")


def audit(rule_name: str, text: str, seen: set[str]) -> str:
    if not text:
        return "empty"
    if text in seen:
        return "duplicate"
    if any(term in text for term in FORBIDDEN) or any(term in text for term in AUDIT_ONLY_FORBIDDEN):
        return "forbidden"
    if len(text) < 5 or len(text) > 80:
        return "length"
    if _looks_dangling_fragment(text):
        return "dangling_fragment"
    if any(k in text for k in ["业务规则", "本条要求", "表达扩散语料", "分类", "rule_id", "asset"]):
        return "prompt_leak"
    major = rule_name.split("-", 1)[0]
    if major == "批批检":
        if not any(k in text for k in ["报告", "扫", "码", "批", "检测", "质检", "数据", "蜡样", "入口", "三方"]):
            return "batch_no_anchor"
        if any(k in text for k in ["标准最高", "最安全", "官方保证", "绝对放心"]):
            return "batch_bad_claim"
    if major == "转奶":
        pain_terms = ["不适应", "拉肚子", "厌奶", "胀气", "肠胃", "哭闹", "拉稀", "奶瓣", "绿便", "折腾"]
        bridge_terms = ["a2", "至初", "报告", "扫", "码", "批", "检测", "质检", "慢慢", "先看", "先观察", "转回", "试试"]
        if any(k in text for k in pain_terms) and not any(k in text for k in bridge_terms):
            return "transfer_pain_only"
        if any(k in text for k in ["好了", "改善", "缓解", "治"]):
            return "transfer_effect_claim"
    if major == "会员权益":
        if "a2" not in text and "至初" not in text:
            return "member_no_brand"
        if not any(k in text for k in ["集罐", "积分", "抽奖", "换礼", "礼品", "老客", "会员", "空罐", "活动"]):
            return "member_no_action"
        if any(k in text for k in ["绘本", "玩具", "推车", "滑板车", "纸尿裤", "保温杯", "围兜", "旅行装", "积木"]):
            return "member_gift_out_of_scope"
    return ""


def _looks_dangling_fragment(text: str) -> bool:
    cleaned = str(text or "").strip().rstrip("，,。.!！?？~～")
    dangling_tails = (
        "先拿一",
        "先拿",
        "先试一",
        "先囤一",
        "刚看到a2",
        "a2每批",
    )
    if cleaned.endswith(dangling_tails):
        return True
    if cleaned[-1:] in {"每", "挺", "很", "但", "比", "这", "那"}:
        return True
    if re.search(r"(不是只看几|不只是看几|不光看几)$", cleaned):
        return True
    return False


def prefix_signature(text: str) -> str:
    return re.sub(r"[，。！？~～!?,\s]", "", text)[:6]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--temperature", type=float, default=0.85)
    parser.add_argument("--max-rules", type=int, default=8)
    parser.add_argument(
        "--variants",
        default=",".join(ABLATIONS),
        help="Comma-separated variant names to run.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    load_dotenv(args.dotenv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rule_asset = get_json(f"{args.api_base}/api/v1/assets/comment_business_rule_set/{DEFAULT_RULE_ASSET}")["data"]
    keyword_asset = get_json(f"{args.api_base}/api/v1/assets/content_generation_keywords/{DEFAULT_KEYWORD_ASSET}")["data"]
    keyword_content = keyword_asset["content_json"]
    rules = selected_rules(rule_asset["content_json"]["items"], args.max_rules)

    trace_rows: list[dict[str, Any]] = []
    prompt_rows: list[dict[str, Any]] = []
    variant_names = [name.strip() for name in args.variants.split(",") if name.strip()]
    known_variants = set(ABLATIONS) | set(SUBKEYWORD_ABLATIONS)
    unknown = [name for name in variant_names if name not in known_variants]
    if unknown:
        raise ValueError(f"unknown variants: {', '.join(unknown)}")

    for variant in variant_names:
        seen: set[str] = set()
        categories = categories_for_variant(keyword_content, variant)
        for index, item in enumerate(rules, start=1):
            rule = rule_for_prompt(item, item_no=index)
            preview_payload = {
                "asset_key": DEFAULT_KEYWORD_ASSET,
                "content_type": "comment",
                "item_no": index,
                "output_fields": ["comment"],
                "business_rule": rule,
                "categories": categories,
                "selection_policy": (keyword_content.get("selection_policy") or {}),
            }
            preview = post_json(f"{args.api_base}/api/v1/assets/content-generation-keywords/preview", preview_payload)["data"]
            prompt = preview["rendered_prompt"]
            prompt_path = args.output_dir / f"{variant}_{index:02d}_{item['rule_id']}_prompt.md"
            prompt_path.write_text(prompt, encoding="utf-8")
            prompt_rows.append(
                {
                    "variant": variant,
                    "rule_id": item.get("rule_id"),
                    "business_rule": item.get("business_rule"),
                    "prompt_chars": len(prompt),
                    "prompt_lines": prompt.count("\n") + 1,
                    "selected_keyword_codes": ",".join(
                        str(kw.get("category_code")) for kw in preview.get("selected_keywords") or []
                    ),
                    "selected_keyword_details": ",".join(
                        f"{kw.get('category_code')}:{kw.get('keyword_code')}"
                        for kw in preview.get("selected_keywords") or []
                    ),
                    "prompt_path": str(prompt_path),
                }
            )
            raw = call_model(
                prompt=prompt,
                model=args.model,
                temperature=args.temperature,
                max_tokens=300,
                timeout=120,
                base_url_override=args.base_url,
            )
            comment = parse_comment(raw)
            reason = audit(str(item.get("business_rule") or ""), comment, seen)
            passed = not reason
            if passed:
                seen.add(comment)
            trace_rows.append(
                {
                    "variant": variant,
                    "rule_id": item.get("rule_id"),
                    "business_rule": item.get("business_rule"),
                    "major_category": str(item.get("business_rule") or "").split("-", 1)[0],
                    "comment": comment,
                    "raw": raw,
                    "passed": "是" if passed else "否",
                    "fail_reason": reason,
                    "length": len(comment),
                    "prefix_signature": prefix_signature(comment),
                    "prompt_chars": len(prompt),
                }
            )
            time.sleep(0.2)

    trace_path = args.output_dir / "a2_comment_expression_ablation_trace.csv"
    with trace_path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = [
            "variant",
            "rule_id",
            "business_rule",
            "major_category",
            "comment",
            "raw",
            "passed",
            "fail_reason",
            "length",
            "prefix_signature",
            "prompt_chars",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trace_rows)

    prompt_path = args.output_dir / "a2_comment_expression_ablation_prompts.csv"
    with prompt_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "variant",
                "rule_id",
                "business_rule",
                "prompt_chars",
                "prompt_lines",
                "selected_keyword_codes",
                "selected_keyword_details",
                "prompt_path",
            ],
        )
        writer.writeheader()
        writer.writerows(prompt_rows)

    by_variant = defaultdict(list)
    for row in trace_rows:
        by_variant[row["variant"]].append(row)
    lines = ["# A2 Comment Expression Keyword Ablation", ""]
    for variant, rows in by_variant.items():
        passed = [row for row in rows if row["passed"] == "是"]
        reasons = Counter(row["fail_reason"] for row in rows if row["passed"] != "是")
        prefixes = Counter(row["prefix_signature"] for row in rows)
        avg_len = sum(int(row["length"]) for row in rows) / len(rows)
        avg_prompt = sum(int(row["prompt_chars"]) for row in rows) / len(rows)
        lines.extend(
            [
                f"## {variant}",
                f"- pass: {len(passed)}/{len(rows)} ({len(passed) / len(rows):.1%})",
                f"- avg_len: {avg_len:.1f}",
                f"- avg_prompt_chars: {avg_prompt:.0f}",
                f"- fail_reasons: {dict(reasons)}",
                f"- repeated_prefix_count: {sum(1 for _, count in prefixes.items() if count > 1)}",
                "",
            ]
        )
        for row in rows:
            status = "PASS" if row["passed"] == "是" else f"FAIL:{row['fail_reason']}"
            lines.append(f"- {status} [{row['business_rule']}] {row['comment']}")
        lines.append("")
    report_path = args.output_dir / "a2_comment_expression_ablation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(trace_path)
    print(prompt_path)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
