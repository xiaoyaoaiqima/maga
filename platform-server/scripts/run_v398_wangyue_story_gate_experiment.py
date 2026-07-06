#!/usr/bin/env python3
"""Local Wangyue two-stage story planner experiment.

This does not replace the production content.generate path. It tests whether
planning a single story spine before writing reduces slot-stitching.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

import run_v380_wangyue_row18_distributed_variants_batch as helper


SOURCE_ASSET_KEY = "wangyue_v395_targeted_row_tuning_article_rules"
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence")
EXPERIMENT_ID = "v398_story_gate"

FORBIDDEN_TERMS = [
    "🍼",
    "厌奶",
    "体质",
    "肠胃",
    "脾胃",
    "天然",
    "儿保",
    "抵抗力",
    "宝宝",
    "宝妈",
    "自护力",
    "底气",
    "源乳",
    "初乳",
    "换季",
    "流感",
    "春游",
    "秋游",
]

DIRECT_CAUSE_PATTERNS = [
    r"旺玥.{0,12}(让|使|带来|导致|改善|提升)",
    r"(因为|靠|多亏).{0,12}旺玥",
    r"(对眼睛|对脑子|专注提升|起作用|有帮助)",
]

SEASON_ENV_PATTERNS = [
    r"天气变化.{0,12}(没|不|挺|状态|精神|蔫|折腾)",
    r"周围.{0,12}(倒|请假|咳|中招)",
    r"班里.{0,12}(倒|请假|咳|中招)",
]


@dataclass
class ModelConfig:
    api_key: str
    base_url: str
    model: str
    timeout: int = 120


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL") or None)
    parser.add_argument("--seed", type=int, default=397)
    args = parser.parse_args()

    random.seed(args.seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = helper._connect(args.database_url)
    try:
        rows = _load_rows(conn, SOURCE_ASSET_KEY)
        model_config = _load_model_config(conn, args.model)
    finally:
        conn.close()

    selected = rows[: args.count]
    batch_code = f"{EXPERIMENT_ID}_{int(time.time())}"
    response_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_response.json"
    preview_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_preview.md"
    prompt_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_item1_rendered_prompt.md"
    plan_csv_path = OUTPUT_DIR / f"{EXPERIMENT_ID}_plans.csv"

    items: list[dict[str, Any]] = []
    prompt_sample = ""
    for index, row in enumerate(selected, start=1):
        plan_prompt = _build_plan_prompt(row, index)
        plan = _call_json(model_config, system=PLANNER_SYSTEM, user=plan_prompt, max_tokens=1500, temperature=0.55)
        plan_valid, plan_issues = _validate_plan(plan)
        if not plan_valid:
            retry_prompt = (
                f"{plan_prompt}\n\n上一版主线问题：{'; '.join(plan_issues)}\n"
                "请只修主线，不要扩成更完整的种草链。"
            )
            plan = _call_json(model_config, system=PLANNER_SYSTEM, user=retry_prompt, max_tokens=1500, temperature=0.45)
            plan_valid, plan_issues = _validate_plan(plan)

        writer_prompt = ""
        if plan_valid:
            writer_prompt = _build_writer_prompt(row, plan, plan_valid=plan_valid, plan_issues=plan_issues)
            article = _call_json(model_config, system=WRITER_SYSTEM, user=writer_prompt, max_tokens=1800, temperature=0.75)
            title = _clean_text(article.get("title"))
            body = _clean_text(article.get("body"))
            quality = _local_quality(title, body, plan)
        else:
            title = ""
            body = ""
            quality = {
                "hard_pass": False,
                "flags": ["plan_gate_failed"],
                "forbidden_hits": [],
                "business_tier": "plan_rejected",
                "business_reason": "主线规划未通过，未进入正文写作",
            }
        item = {
            "item_no": index,
            "source_row_no": row.get("source_row_no") or row.get("item_no") or index,
            "title": title,
            "body": body,
            "plan": plan,
            "plan_valid": plan_valid,
            "plan_issues": plan_issues,
            "hard_pass": quality["hard_pass"],
            "rewrite_required": not quality["hard_pass"],
            "business_usability_tier": quality["business_tier"],
            "business_usability_reason": quality["business_reason"],
            "quality_flags": quality["flags"],
            "forbidden_hits": quality["forbidden_hits"],
        }
        items.append(item)
        if index == 1:
            prompt_sample = _format_prompt_sample(plan_prompt, writer_prompt, plan)

    summary = _summary(items)
    response = {
        "experiment_id": EXPERIMENT_ID,
        "batch_id": "local_v398",
        "batch_code": batch_code,
        "source_asset": SOURCE_ASSET_KEY,
        "model": model_config.model,
        "items": items,
        "report": {"summary": summary},
    }
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_path.write_text(prompt_sample, encoding="utf-8")
    _write_plan_csv(plan_csv_path, items)
    _write_preview(preview_path, response_path, prompt_path, plan_csv_path, response)

    print(json.dumps({
        "response_path": str(response_path),
        "preview_path": str(preview_path),
        "prompt_path": str(prompt_path),
        "plan_csv_path": str(plan_csv_path),
        "summary": summary,
    }, ensure_ascii=False, indent=2))


def _load_rows(conn, asset_key: str) -> list[dict[str, Any]]:
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
        raise RuntimeError(f"missing active asset: {asset_key}")
    content = helper._json_value(row["content_json"])
    items = [item for item in content.get("items") or [] if isinstance(item, dict)]
    return sorted(items, key=lambda item: int(item.get("source_row_no") or item.get("item_no") or 0))


def _load_model_config(conn, model_override: str | None) -> ModelConfig:
    with conn.cursor() as cur:
        cur.execute(
            """
            select provider_code, api_key, base_url, default_model, timeout
            from llm_provider_config
            where enabled=1 and is_deleted=0 and api_key is not null and api_key <> ''
            order by priority desc, id asc
            limit 1
            """
        )
        provider = cur.fetchone()
    if provider:
        return ModelConfig(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            model=model_override or provider.get("default_model") or "deepseek-v4-flash",
            timeout=int(provider.get("timeout") or 120),
        )
    api_key = os.getenv("AIHUBMIX_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("missing LLM api key")
    return ModelConfig(
        api_key=api_key,
        base_url=os.getenv("AIHUBMIX_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://aihubmix.com/v1",
        model=model_override or "deepseek-v4-flash",
    )


def _chat_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _call_json(config: ModelConfig, *, system: str, user: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    payload = {
        "model": config.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=config.timeout) as client:
        response = client.post(
            _chat_url(config.base_url),
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"]
    return _parse_json_object(raw)


PLANNER_SYSTEM = """你是小红书母婴UGC内容的主线规划器。
你不写正文，只规划一条能自然成立的发帖主线。
目标是：真实妈妈发帖里自然带旺玥，有正向种草力，但不是素材清单。
输出 JSON，字段只能是：
posting_motive, life_entry, product_permission, product_role, single_selling_point, positive_evidence, ending_stop, avoid_links, self_check。
要求：
- 只允许一条主线，一个生活触发，一个产品判断，一个自家观察。
- 强种草可以正面，但不要把旺玥写成万能答案。
- 成分可以出现，但不要直接写成导致孩子变化的原因。
- 不写换季、流感、春游、秋游、公共疾病环境或当前季节。
- 不用安心、省心、放心、踏实、心里有底当结尾逻辑。
"""


WRITER_SYSTEM = """你是小红书妈妈UGC写手。
你只能根据给定主线写标题和正文，不重新规划新事实。
输出 JSON，字段只能是 title 和 body。
写法要求：
- 正文自然出现旺玥，产品价值要写到位。
- 像妈妈顺手发帖，不像广告 brief。
- 允许具体生活细节，但只能服务同一条主线。
- 不写禁词，不写当前季节/公共疾病大环境。
- 不写孩子自己泡奶粉、奶瓶、便携袋、水杯侧袋。
- 标题不超过20字，emoji算2字。
"""


def _build_plan_prompt(row: dict[str, Any], index: int) -> str:
    payload = _row_payload(row, index)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt(row: dict[str, Any], plan: dict[str, Any], *, plan_valid: bool, plan_issues: list[str]) -> str:
    payload = {
        "product_fact": "旺玥是给3岁以上孩子的儿童奶粉；不要写成低龄、断奶、辅食或三段场景。",
        "source_row": _row_payload(row, int(row.get("source_row_no") or row.get("item_no") or 0)),
        "approved_story_plan": plan,
        "plan_gate": {"valid": plan_valid, "issues": plan_issues},
        "writer_task": "把 approved_story_plan 写成一篇 120-180 字左右的小红书妈妈UGC正向种草笔记。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _row_payload(row: dict[str, Any], index: int) -> dict[str, Any]:
    keys = [
        "source_row_no",
        "post_type",
        "painpoint",
        "selling_point",
        "selling_description",
        "story_spine",
        "corpus",
        "scene_motive_bucket",
    ]
    payload = {key: row.get(key) for key in keys if row.get(key)}
    payload["item_index"] = index
    return payload


def _validate_plan(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    story_text = json.dumps({
        key: plan.get(key)
        for key in (
            "posting_motive",
            "life_entry",
            "product_permission",
            "product_role",
            "single_selling_point",
            "positive_evidence",
            "ending_stop",
        )
    }, ensure_ascii=False)
    issues: list[str] = []
    required = [
        "posting_motive",
        "life_entry",
        "product_permission",
        "product_role",
        "single_selling_point",
        "positive_evidence",
        "ending_stop",
        "avoid_links",
    ]
    for key in required:
        if not str(plan.get(key) or "").strip():
            issues.append(f"missing:{key}")
    if hits := _hits(story_text, FORBIDDEN_TERMS):
        issues.append(f"forbidden:{','.join(hits)}")
    if _pattern_hits(story_text, DIRECT_CAUSE_PATTERNS):
        issues.append("direct_causality")
    if _pattern_hits(story_text, SEASON_ENV_PATTERNS):
        issues.append("season_or_environment_anchor")
    if any(word in story_text for word in ("安心", "省心", "放心", "踏实", "心里有底")):
        issues.append("closure_shortcut")
    return not issues, issues


def _local_quality(title: str, body: str, plan: dict[str, Any]) -> dict[str, Any]:
    text = f"{title}\n{body}"
    flags: list[str] = []
    forbidden_hits = _hits(text, FORBIDDEN_TERMS)
    if forbidden_hits:
        flags.append("forbidden")
    if "旺玥" not in text:
        flags.append("missing_product")
    if len(title) > 20:
        flags.append("title_too_long")
    if _pattern_hits(text, DIRECT_CAUSE_PATTERNS):
        flags.append("direct_causality")
    if _pattern_hits(text, SEASON_ENV_PATTERNS):
        flags.append("season_or_environment_anchor")
    if any(word in text[-36:] for word in ("安心", "省心", "放心", "踏实", "心里有底")):
        flags.append("formulaic_closure")
    if any(word in text for word in ("奶瓶", "自己泡", "书包侧袋", "水杯侧袋", "便携")):
        flags.append("product_action_or_carrier_risk")
    hard_pass = not flags
    return {
        "hard_pass": hard_pass,
        "flags": flags,
        "forbidden_hits": forbidden_hits,
        "business_tier": "direct_pool" if hard_pass else "needs_manual_review",
        "business_reason": "本地架构实验粗审通过" if hard_pass else "；".join(flags),
    }


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    generated = [item for item in items if item.get("body")]
    hard_pass = [item["item_no"] for item in generated if item.get("hard_pass")]
    rewrite = [item["item_no"] for item in generated if not item.get("hard_pass")]
    plan_valid = [item["item_no"] for item in generated if item.get("plan_valid")]
    return {
        "total_count": len(items),
        "generated_count": len(generated),
        "failed_count": len(items) - len(generated),
        "machine_final_pass_count": len(hard_pass),
        "machine_final_pass_items": hard_pass,
        "machine_needs_review_count": len(rewrite),
        "machine_needs_review_items": rewrite,
        "plan_valid_count": len(plan_valid),
        "plan_valid_items": plan_valid,
        "max_pairwise_jaccard_2gram": _max_pairwise_jaccard([item.get("body") or "" for item in generated]),
        "closure_hit_count": _closure_hit_count(generated),
        "forbidden_hit_count": sum(len(item.get("forbidden_hits") or []) for item in generated),
        "business_usability_stats": {
            "counts": {
                "direct_pool": len(hard_pass),
                "needs_manual_review": len(rewrite),
            },
            "item_nos_by_tier": {
                "direct_pool": hard_pass,
                "needs_manual_review": rewrite,
            },
        },
    }


def _write_plan_csv(path: Path, items: list[dict[str, Any]]) -> None:
    fields = [
        "item_no",
        "source_row_no",
        "plan_valid",
        "plan_issues",
        "posting_motive",
        "life_entry",
        "product_permission",
        "product_role",
        "single_selling_point",
        "positive_evidence",
        "ending_stop",
        "title",
        "body",
        "quality_flags",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in items:
            plan = item.get("plan") or {}
            writer.writerow({
                "item_no": item.get("item_no"),
                "source_row_no": item.get("source_row_no"),
                "plan_valid": item.get("plan_valid"),
                "plan_issues": ",".join(item.get("plan_issues") or []),
                "posting_motive": plan.get("posting_motive"),
                "life_entry": plan.get("life_entry"),
                "product_permission": plan.get("product_permission"),
                "product_role": plan.get("product_role"),
                "single_selling_point": plan.get("single_selling_point"),
                "positive_evidence": plan.get("positive_evidence"),
                "ending_stop": plan.get("ending_stop"),
                "title": item.get("title"),
                "body": item.get("body"),
                "quality_flags": ",".join(item.get("quality_flags") or []),
            })


def _write_preview(path: Path, response_path: Path, prompt_path: Path, plan_csv_path: Path, response: dict[str, Any]) -> None:
    summary = response["report"]["summary"]
    lines = [
        "# v398 story-gate architecture experiment preview",
        "",
        f"- source JSON: `{response_path}`",
        f"- sampled rendered prompt: `{prompt_path}`",
        f"- plan CSV: `{plan_csv_path}`",
        f"- source asset: `{response['source_asset']}`",
        f"- batch_id: `{response['batch_id']}`",
        f"- batch_code: `{response['batch_code']}`",
        "",
        "## Metrics",
        "",
        f"- total count: {summary['total_count']}",
        f"- generated count: {summary['generated_count']}",
        f"- failed count: {summary['failed_count']}",
        f"- local machine pass: {summary['machine_final_pass_count']} / {summary['generated_count']} -> {summary['machine_final_pass_items']}",
        f"- local needs review: {summary['machine_needs_review_count']} -> {summary['machine_needs_review_items']}",
        f"- plan valid: {summary['plan_valid_count']} / {summary['generated_count']} -> {summary['plan_valid_items']}",
        f"- max pairwise similarity: {summary['max_pairwise_jaccard_2gram']}",
        f"- forbidden hit count: {summary['forbidden_hit_count']}",
        f"- closure hit count: {summary['closure_hit_count']}",
        "",
        "## First-Principles Assessment",
        "",
        "这一版验证架构假设：先生成可审核主线，主线通过才写正文；主线不通过直接拒绝，不让 writer 带病写作。",
        "本地粗审不是生产审核，重点看 hard gate 是否能把槽位拼接和错误因果挡在正文前。",
        "",
        "## Items",
        "",
    ]
    for item in response["items"]:
        plan = item.get("plan") or {}
        lines.extend([
            f"### {item['item_no']}. {item.get('title') or ''}",
            "",
            f"- source_row_no: `{item.get('source_row_no')}`",
            f"- plan valid: `{item.get('plan_valid')}`; issues: `{', '.join(item.get('plan_issues') or [])}`",
            f"- local machine pass: `{item.get('hard_pass')}`; flags: `{', '.join(item.get('quality_flags') or [])}`",
            f"- posting motive: {plan.get('posting_motive') or ''}",
            f"- life entry: {plan.get('life_entry') or ''}",
            f"- product role: {plan.get('product_role') or ''}",
            f"- positive evidence: {plan.get('positive_evidence') or ''}",
            "",
            item.get("body") or "",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _format_prompt_sample(plan_prompt: str, writer_prompt: str, plan: dict[str, Any]) -> str:
    return "\n".join([
        "# v398 story-gate item1 rendered prompt",
        "",
        "## Planner System",
        "",
        "```text",
        PLANNER_SYSTEM,
        "```",
        "",
        "## Planner User",
        "",
        "```json",
        plan_prompt,
        "```",
        "",
        "## Planner Output",
        "",
        "```json",
        json.dumps(plan, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Writer System",
        "",
        "```text",
        WRITER_SYSTEM,
        "```",
        "",
        "## Writer User",
        "",
        "```json",
        writer_prompt,
        "```",
        "",
    ])


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model response is not a JSON object")
    return value


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and term in text]


def _pattern_hits(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text)]


def _max_pairwise_jaccard(bodies: list[str]) -> float:
    max_score = 0.0
    for index, left in enumerate(bodies):
        for right in bodies[index + 1 :]:
            max_score = max(max_score, _jaccard_2gram(left, right))
    return round(max_score, 4)


def _jaccard_2gram(left: str, right: str) -> float:
    def grams(text: str) -> set[str]:
        compact = re.sub(r"\s+", "", text)
        return {compact[i : i + 2] for i in range(max(0, len(compact) - 1))}

    left_set = grams(left)
    right_set = grams(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _closure_hit_count(items: list[dict[str, Any]]) -> int:
    phrases = ["安心", "省心", "放心", "踏实", "心里有底", "继续喝", "回购", "续上", "没选错", "选对"]
    count = 0
    for item in items:
        closing = (item.get("body") or "")[-40:]
        if any(phrase in closing for phrase in phrases):
            count += 1
    return count


if __name__ == "__main__":
    main()
