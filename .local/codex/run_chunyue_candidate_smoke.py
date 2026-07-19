#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "platform-server"
sys.path.insert(0, str(SERVER))

from app.services.executor_invocation_service import DirectLLMInvocationClient  # noqa: E402
from app.services.forbidden_term_review_service import find_forbidden_hits  # noqa: E402
from app.services.product_experience_rule_service import _row_to_rule_item  # noqa: E402
from app.services.unified_content_generation_service import _layered_article_prompt  # noqa: E402


EXTRA_RISK_TERMS = [
    "欧盟认证有机牧场",
    "少生病",
    "少跑医院",
    "恢复更快",
    "预防",
    "治疗",
    "流感",
    "自护力",
    "免疫力",
    "保证有效",
    "HMO",
    "OPN",
    "DHA",
    "乳磷脂",
]

EXPRESSION_SEGMENT_SEPARATOR = re.compile(r"[，。！？；、：,.!?;:\\n]+")


def expression_content_preserved(expression: str, body: str) -> bool:
    segments = [
        segment.strip()
        for segment in EXPRESSION_SEGMENT_SEPARATOR.split(str(expression or ""))
        if segment.strip()
    ]
    if not segments:
        return False
    cursor = 0
    for segment in segments:
        position = str(body or "").find(segment, cursor)
        if position < 0:
            return False
        cursor = position + len(segment)
    return True


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_rules(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rules = [_row_to_rule_item(row, index) for index, row in enumerate(rows, start=1)]
    return [rule for rule in rules if rule is not None]


def read_expressions(path: Path) -> dict[str, list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for source_row_no, row in enumerate(rows, start=1):
        group = str(row.get("卖点表达") or row.get("卖点") or "").strip()
        expression = str(row.get("语料") or "").strip()
        if not group or not expression:
            continue
        grouped.setdefault(group, []).append(
            {"expression": expression, "source_row_no": source_row_no}
        )
    return grouped


async def generate_one(
    index: int,
    rule: dict[str, Any],
    expression_pool: dict[str, list[dict[str, Any]]],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    rule = dict(rule)
    group = str(rule.get("selling_painpoint_group") or "").strip()
    candidates = expression_pool.get(group) or []
    selected_expression = candidates[(max(1, index) - 1) % len(candidates)] if candidates else None
    if selected_expression:
        rule["selling_painpoint_expression"] = selected_expression["expression"]
    rendered_prompt = _layered_article_prompt(
        rule,
        selected_keywords=[],
        output_format="只输出 JSON 对象，字段只能包含 title 和 body。",
    )
    input_payload = {
        "schema_version": "1",
        "capability": "content.generate",
        "content_type": "article",
        "output_fields": ["title", "body"],
        "business_rule": rule,
        "selected_keywords": [],
        "model_config": {
            "provider_code": "aihubmix",
            "model_code": "deepseek-v4-flash",
            "temperature": 0.86,
            "max_tokens": 900,
            "timeout": 120,
            "system_prompt": "你是中文小红书母婴帖子生成器。严格按提示输出 JSON，不解释过程。",
        },
        "rendered_prompt": rendered_prompt,
    }
    envelope = {
        "stage_call_id": f"chunyue-smoke-{index}-{uuid.uuid4().hex[:8]}",
        "capability": "content.generate",
        "input": input_payload,
    }
    async with semaphore:
        result = await DirectLLMInvocationClient().invoke(
            invoke_url="llm://direct/content",
            envelope=envelope,
        )
    output = result.output or {}
    title = str(output.get("title") or "").strip()
    body = str(output.get("body") or "").strip()
    text = f"{title}\n{body}".strip()
    selected_expression_text = str(
        selected_expression["expression"] if selected_expression else ""
    )
    expression_exactly_used = bool(
        selected_expression_text and selected_expression_text in body
    )
    expression_preserved = expression_content_preserved(
        selected_expression_text,
        body,
    )
    formal_hits = find_forbidden_hits(text)
    source_expression = selected_expression_text.lower()
    unsupported_expansion_hits = [
        term
        for term in EXTRA_RISK_TERMS
        if term.lower() in text.lower() and term.lower() not in source_expression
    ]
    return {
        "item_no": index,
        "rule_id": rule.get("rule_id"),
        "business_rule": rule.get("business_rule"),
        "selling_painpoint_group": group,
        "selling_painpoint_expression": (
            selected_expression_text or None
        ),
        "selling_painpoint_expression_source_row_no": (
            selected_expression["source_row_no"] if selected_expression else None
        ),
        "status": result.status,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "title": title,
        "body": body,
        "rendered_prompt": rendered_prompt,
        "prompt_length": len(rendered_prompt),
        "expression_exactly_used": expression_exactly_used,
        "expression_content_preserved": expression_preserved,
        "formal_forbidden_hits": formal_hits,
        "unsupported_expansion_hits": unsupported_expansion_hits,
        "runtime_result": output.get("runtime_result") or {},
        "stats": result.stats or {},
    }


def bigrams(text: str) -> set[str]:
    compact = "".join(str(text or "").split())
    return {compact[i : i + 2] for i in range(max(0, len(compact) - 1))}


def max_similarity(items: list[dict[str, Any]]) -> tuple[float, list[int]]:
    best = 0.0
    best_pair: list[int] = []
    for i, left in enumerate(items):
        left_set = bigrams(left.get("body") or "")
        for right in items[i + 1 :]:
            right_set = bigrams(right.get("body") or "")
            union = left_set | right_set
            score = len(left_set & right_set) / len(union) if union else 0.0
            if score > best:
                best = score
                best_pair = [int(left["item_no"]), int(right["item_no"])]
    return round(best, 4), best_pair


async def run(args: argparse.Namespace) -> dict[str, Any]:
    rules = read_rules(args.rules)[: args.limit]
    expression_pool = read_expressions(args.expressions)
    batch_id = f"draft-chunyue-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output_dir = args.output_dir / batch_id
    output_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(args.concurrency)
    items = await asyncio.gather(
        *(
            generate_one(index, rule, expression_pool, semaphore)
            for index, rule in enumerate(rules, start=1)
        )
    )
    generated = [
        item
        for item in items
        if item["status"] in {"completed", "succeeded"} and item["body"]
    ]
    machine_passed = [
        item
        for item in generated
        if item["expression_content_preserved"]
        and not item["formal_forbidden_hits"]
        and not item["unsupported_expansion_hits"]
    ]
    similarity, pair = max_similarity(generated)
    report = {
        "batch_id": batch_id,
        "mode": "draft_candidate_content_generate",
        "rules_path": str(args.rules),
        "expression_pool_path": str(args.expressions),
        "model_code": "deepseek-v4-flash",
        "requested_count": len(rules),
        "generated_count": len(generated),
        "failed_count": len(rules) - len(generated),
        "formal_forbidden_hit_items": [
            item["item_no"] for item in items if item["formal_forbidden_hits"]
        ],
        "unsupported_expansion_hit_items": [
            item["item_no"] for item in items if item["unsupported_expansion_hits"]
        ],
        "expression_exactly_used_count": sum(
            1 for item in generated if item["expression_exactly_used"]
        ),
        "expression_not_exactly_used_items": [
            item["item_no"] for item in generated if not item["expression_exactly_used"]
        ],
        "expression_content_preserved_count": sum(
            1 for item in generated if item["expression_content_preserved"]
        ),
        "expression_content_not_preserved_items": [
            item["item_no"]
            for item in generated
            if not item["expression_content_preserved"]
        ],
        "machine_final_pass_count": len(machine_passed),
        "machine_final_pass_items": [item["item_no"] for item in machine_passed],
        "max_pairwise_jaccard_2gram": similarity,
        "max_similarity_pair": pair,
        "items": items,
    }
    report_path = output_dir / "raw_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**{k: v for k, v in report.items() if k != "items"}, "report_path": str(report_path)}, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "outputs/chunyue_migration/20260718_chunyue_painpoint_sellingpoint_rules_v2.csv",
    )
    parser.add_argument(
        "--expressions",
        type=Path,
        default=ROOT / "outputs/chunyue_migration/20260718_chunyue_selling_painpoint_expression_pool_v2.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/chunyue_migration/smoke_runs",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
