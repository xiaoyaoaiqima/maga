#!/usr/bin/env python3
"""Local Wangyue v440 two-step product-relation probe.

v439 proved the useful unit is:

product relation stage x proof mechanism

but its inherited three-step chain was slow and still pulled old human-event
gates into relation types such as first try, repurchase, and restock. This
probe keeps the v439 kernel matrix but compresses execution into two LLM calls:

1. relation planner: choose the relation stage, proof mechanism, stop point.
2. writer: write the article from that plan.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any

import run_v405_wangyue_human_event_bridge_experiment as v405


EXPERIMENT_ID = "v440_two_step_relation_probe"
SOURCE_ASSET_KEY = v405.SOURCE_ASSET_KEY
OUTPUT_DIR = v405.OUTPUT_DIR

FORBIDDEN_TERMS = v405.FORBIDDEN_TERMS

KERNELS: list[dict[str, str]] = [
    {
        "product_relation_stage": "熟悉日常使用",
        "proof_mechanism": "孩子动作接受",
        "allowed_selling": "口味温和、接受度、低阻力",
        "boundary": "只讲孩子自然喝、端杯、喝几口、喝完继续做事；不讲保护力、钙铁锌、DHA、成长效果。",
    },
    {
        "product_relation_stage": "初试/新开罐",
        "proof_mechanism": "早期接受",
        "allowed_selling": "口味清淡、不甜、不腥、接受度",
        "boundary": "只停在早期接受，不马上写连着几天主动要、长期复购、少请假或成长变化。",
    },
    {
        "product_relation_stage": "对比选择/做功课",
        "proof_mechanism": "妈妈筛选标准",
        "allowed_selling": "进阶保护力、眼脑营养、整体营养配置中的一个方向",
        "boundary": "只保留一个决定理由，不写成完整测评、参数课、购买教程或竞品攻击。",
    },
    {
        "product_relation_stage": "阶段营养安排",
        "proof_mechanism": "3岁后阶段需求",
        "allowed_selling": "钙铁锌、30+关键营养、DHA/燕窝酸、整体营养",
        "boundary": "写阶段需求和一个产品理由，不写医生建议、体检指标、固定早晚杯数或安心踏实收口。",
    },
    {
        "product_relation_stage": "长期使用/复购",
        "proof_mechanism": "复购动作证明认可",
        "allowed_selling": "状态稳、少请假、精神头、接受度、复购信任中的一个",
        "boundary": "买了/补了/继续买本身是证明；只加一个继续理由，不补完整广告闭环。",
    },
    {
        "product_relation_stage": "状态反馈/效果观察",
        "proof_mechanism": "一个生活观察证明",
        "allowed_selling": "五个痛点之一对应的正向观察",
        "boundary": "一个观察就够；成分只能做支撑，不直接归因神效，不把乳铁蛋白接长肉/跑跳有劲。",
    },
    {
        "product_relation_stage": "补货/库存/快递",
        "proof_mechanism": "购买动作证明长期关系",
        "allowed_selling": "继续买的一个理由、轻卖点或状态观察",
        "boundary": "补货动作是主证明；不要高频见底/半罐，不要强行补对比选择长链路。",
    },
    {
        "product_relation_stage": "求助后反馈",
        "proof_mechanism": "之前纠结后的一个反馈",
        "allowed_selling": "一个选择理由加一个轻反馈",
        "boundary": "回答当初的问题即可，不写测评大全、教学口吻或互动提问收口。",
    },
]

PLAN_SYSTEM = """你是小红书母婴UGC种草内容的关系规划器。
你不写正文。你只决定这篇内容的产品关系阶段、证明机制和停止点。
输出 JSON，字段只能是：
product_relation_stage, proof_mechanism, painpoint, post_intent, life_trigger, product_entry, selling_point_use, positive_evidence, story_spine, stop_point, title_angle, self_check。
要求：
- 旺玥是3岁以上、3-6岁学龄前儿童可喝的4段儿童奶粉。
- 先确定旺玥和妈妈生活的关系，再决定能讲什么卖点；不要把卖点塞进不匹配的生活场景。
- 每篇只有一个主证明机制；不要同时写选择、补货、被问、状态反馈、复购全部出现。
- 可以正面种草，效果证明可以强，但必须符合关系阶段。
- 不写当前季节、公共疾病大环境、换季、流感、春游、秋游。
- 不写宝宝、宝妈、厌奶、体质、肠胃、脾胃、天然、儿保、抵抗力、自护力、底气、源乳、初乳。
- 不写低于3岁的履历，不写奶瓶/盒装/吸管/便携小包/书包侧袋/孩子独立冲泡。
- 不用安心、省心、放心、踏实、心里有底做规划收口。
- 如果 target_kernel 给了关系阶段，优先服从；如果 source_row 明显不适配，可以在同类关系内微调，但必须说明在 self_check。
"""

WRITER_SYSTEM = """你是小红书妈妈UGC写手。
你只能根据 approved_relation_plan 写标题和正文，不重新规划新事实。
输出 JSON，字段只能是 title 和 body。
写法要求：
- 正文写成一条自然妈妈笔记，120-180字左右。
- 旺玥必须自然出现，产品价值要写到位，但只服务 approved_relation_plan 的一个证明机制。
- 不要把 source_row、target_kernel、approved_relation_plan 逐条翻译进正文。
- 不要堆多个入口；如果生活触发、产品理由、效果观察并列不顺，删掉弱的一环。
- 强种草可以直接说好处，但用妈妈语言，不用业务总结腔。
- 不写禁词，不写当前季节/公共疾病大环境。
- 不写奶瓶、盒装/吸管奶、便携小包、书包侧袋、孩子独立冲泡。
- 不用安心、省心、放心、踏实、心里有底收尾。
- 标题不超过20字，emoji算2字；标题不要截正文半句。
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL") or None)
    parser.add_argument("--seed", type=int, default=440)
    args = parser.parse_args()

    random.seed(args.seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = v405.helper._connect(args.database_url)
    try:
        rows = v405._load_rows(conn, SOURCE_ASSET_KEY)
        model_config = v405._load_model_config(conn, args.model)
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
    fallback_prompt_sample = ""
    started = time.time()

    for index, row in enumerate(selected, start=1):
        kernel = KERNELS[(index - 1) % len(KERNELS)]
        plan_prompt = _build_plan_prompt(row, index, kernel)
        plan = v405._call_json_with_retry(
            model_config,
            system=PLAN_SYSTEM,
            user=plan_prompt,
            max_tokens=1500,
            temperature=0.6,
        )
        plan_valid, plan_issues = _validate_plan(plan)
        if not plan_valid:
            retry_prompt = (
                f"{plan_prompt}\n\n上一版关系规划问题：{'; '.join(plan_issues)}\n"
                "请只修关系规划，不要解释；必须输出同一 JSON schema。"
                "不要在 self_check 里复述禁词；不要出现当前季节、换季、流感、春游、秋游；"
                "不要用安心、省心、放心、踏实、心里有底做收口。"
            )
            plan = v405._call_json_with_retry(
                model_config,
                system=PLAN_SYSTEM,
                user=retry_prompt,
                max_tokens=1500,
                temperature=0.3,
            )
            plan_valid, plan_issues = _validate_plan(plan)
        writer_prompt = ""
        title = ""
        body = ""
        if plan_valid:
            writer_prompt = _build_writer_prompt(row, index, kernel, plan)
            article = v405._call_json_with_retry(
                model_config,
                system=WRITER_SYSTEM,
                user=writer_prompt,
                max_tokens=1800,
                temperature=0.75,
            )
            title = _clean_text(article.get("title"))
            body = _clean_text(article.get("body"))

        local = _local_review(title, body, plan, plan_valid, plan_issues)
        item = {
            "item_no": index,
            "source_row_no": row.get("source_row_no") or row.get("item_no") or index,
            "target_kernel": kernel,
            "plan": plan,
            "plan_valid": plan_valid,
            "plan_issues": plan_issues,
            "title": title,
            "body": body,
            "generated": bool(body),
            "machine_final_pass": local["pass"],
            "machine_flags": local["flags"],
            "human_business_usable": local["human_business_usable"],
            "human_business_reason": local["human_business_reason"],
            "forbidden_hits": local["forbidden_hits"],
            "closure_hits": local["closure_hits"],
            "prompt_debug": {
                "plan_prompt": plan_prompt,
                "writer_prompt": writer_prompt,
            },
        }
        items.append(item)

        sample_text = _format_prompt_sample(index, row, kernel, plan_prompt, plan, writer_prompt)
        if not fallback_prompt_sample:
            fallback_prompt_sample = sample_text
        if not prompt_sample and writer_prompt:
            prompt_sample = sample_text

    summary = _summary(items, elapsed_seconds=time.time() - started)
    response = {
        "experiment_id": EXPERIMENT_ID,
        "batch_id": "local_v440",
        "batch_code": batch_code,
        "source_asset": SOURCE_ASSET_KEY,
        "model": model_config.model,
        "items": items,
        "report": {"summary": summary},
    }
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_path.write_text(prompt_sample or fallback_prompt_sample, encoding="utf-8")
    _write_plan_csv(plan_csv_path, items)
    _write_preview(preview_path, response_path, prompt_path, plan_csv_path, response)

    print(json.dumps({
        "response_path": str(response_path),
        "preview_path": str(preview_path),
        "prompt_path": str(prompt_path),
        "plan_csv_path": str(plan_csv_path),
        "summary": summary,
    }, ensure_ascii=False, indent=2))


def _build_plan_prompt(row: dict[str, Any], index: int, kernel: dict[str, str]) -> str:
    payload = {
        "item_index": index,
        "child_context": "3-6岁学龄前孩子；旺玥是3岁以上4段儿童奶粉。",
        "source_row": _row_payload(row, index),
        "target_kernel": kernel,
        "available_kernels": KERNELS,
        "task": "基于 source_row 和 target_kernel，规划一条产品关系阶段清楚、证明机制单一的旺玥UGC种草主线。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_writer_prompt(row: dict[str, Any], index: int, kernel: dict[str, str], plan: dict[str, Any]) -> str:
    payload = {
        "item_index": index,
        "product_fact": "旺玥是3岁以上、3-6岁学龄前儿童可喝的4段儿童奶粉。",
        "source_row": _row_payload(row, index),
        "target_kernel": kernel,
        "approved_relation_plan": plan,
        "writer_task": "写一篇小红书妈妈UGC正向种草笔记，只沿 approved_relation_plan 的一条主线写。",
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
    issues: list[str] = []
    required = [
        "product_relation_stage",
        "proof_mechanism",
        "painpoint",
        "post_intent",
        "life_trigger",
        "product_entry",
        "selling_point_use",
        "positive_evidence",
        "story_spine",
        "stop_point",
        "title_angle",
    ]
    for key in required:
        if not str(plan.get(key) or "").strip():
            issues.append(f"missing:{key}")
    text = _plan_main_text(plan)
    if hits := _hits(text, FORBIDDEN_TERMS):
        issues.append(f"forbidden:{','.join(hits)}")
    if _current_time_anchor(text):
        issues.append("current_time_or_season_anchor")
    if _product_form_error(text):
        issues.append("product_form_error")
    if _under3_context(text):
        issues.append("under3_context")
    if _formulaic_closure(text):
        issues.append("formulaic_closure_in_plan")
    if _too_many_proofs(text):
        issues.append("too_many_proof_points")
    return not issues, sorted(set(issues))


def _local_review(title: str, body: str, plan: dict[str, Any], plan_valid: bool, plan_issues: list[str]) -> dict[str, Any]:
    flags: list[str] = []
    forbidden_hits: list[str] = []
    closure_hits: list[str] = []
    if not plan_valid:
        flags.append("plan_gate_failed")
        flags.extend(plan_issues)
    if not body:
        flags.append("empty_body")
    text = f"{title}\n{body}"
    if "旺玥" not in text:
        flags.append("missing_wangyue")
    forbidden_hits = _hits(text, FORBIDDEN_TERMS)
    if forbidden_hits:
        flags.append("forbidden_terms")
    if _current_time_anchor(text):
        flags.append("current_time_or_season_anchor")
    if _product_form_error(text):
        flags.append("product_form_error")
    if _under3_context(text):
        flags.append("under3_context")
    if len(title) > 20:
        flags.append("title_too_long")
    closure_hits = [term for term in ["安心", "省心", "放心", "踏实", "心里有底", "选对", "没选错"] if term in body[-45:]]
    if closure_hits:
        flags.append("formulaic_closure")
    if _ingredient_effect_mismatch(text):
        flags.append("ingredient_effect_mismatch")
    if _wrong_relation_carry(plan, text):
        flags.append("relation_selling_mismatch")
    if _fixed_usage_overstated(text):
        flags.append("fixed_usage_overstated")
    if _too_many_article_proofs(text):
        flags.append("too_many_proof_points")
    if re.search(r"旺玥.{0,4}牛奶|旺玥牛奶", text):
        flags.append("wrong_product_form_wangyue_milk")

    flags = sorted(set(flags))
    machine_pass = not flags
    hard_human_flags = {
        "forbidden_terms",
        "current_time_or_season_anchor",
        "product_form_error",
        "under3_context",
        "ingredient_effect_mismatch",
        "wrong_product_form_wangyue_milk",
        "empty_body",
        "missing_wangyue",
    }
    human_usable = not any(flag in hard_human_flags for flag in flags)
    reason = "可进入业务人工候选池" if human_usable else "硬伤需修：" + "；".join(flag for flag in flags if flag in hard_human_flags)
    return {
        "pass": machine_pass,
        "flags": flags,
        "human_business_usable": human_usable,
        "human_business_reason": reason,
        "forbidden_hits": forbidden_hits,
        "closure_hits": closure_hits,
    }


def _summary(items: list[dict[str, Any]], *, elapsed_seconds: float) -> dict[str, Any]:
    generated = [item for item in items if item.get("generated")]
    machine_pass = [item["item_no"] for item in generated if item.get("machine_final_pass")]
    machine_review = [item["item_no"] for item in generated if not item.get("machine_final_pass")]
    plan_valid = [item["item_no"] for item in items if item.get("plan_valid")]
    plan_rejected = [item["item_no"] for item in items if not item.get("plan_valid")]
    human_usable = [item["item_no"] for item in generated if item.get("human_business_usable")]
    human_fix = [item["item_no"] for item in generated if not item.get("human_business_usable")]
    return {
        "total_count": len(items),
        "generated_count": len(generated),
        "failed_count": len(items) - len(generated),
        "machine_final_pass_count": len(machine_pass),
        "machine_final_pass_items": machine_pass,
        "machine_needs_review_count": len(machine_review),
        "machine_needs_review_items": machine_review,
        "direct_pass_without_post_rewrite_count": len(machine_pass),
        "direct_pass_without_post_rewrite_items": machine_pass,
        "pass_after_post_rewrite_count": 0,
        "pass_after_post_rewrite_items": [],
        "plan_valid_count": len(plan_valid),
        "plan_valid_items": plan_valid,
        "plan_rejected_count": len(plan_rejected),
        "plan_rejected_items": plan_rejected,
        "human_business_usable_count": len(human_usable),
        "human_business_usable_items": human_usable,
        "human_needs_fix_count": len(human_fix),
        "human_needs_fix_items": human_fix,
        "max_pairwise_jaccard_2gram": _max_pairwise_jaccard([item.get("body") or "" for item in generated]),
        "closure_hit_count": sum(1 for item in generated if item.get("closure_hits")),
        "forbidden_hit_count": sum(len(item.get("forbidden_hits") or []) for item in generated),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "seconds_per_attempt": round(elapsed_seconds / max(1, len(items)), 2),
    }


def _write_plan_csv(path: Path, items: list[dict[str, Any]]) -> None:
    fields = [
        "item_no",
        "source_row_no",
        "target_stage",
        "target_proof",
        "plan_valid",
        "plan_issues",
        "product_relation_stage",
        "proof_mechanism",
        "painpoint",
        "post_intent",
        "life_trigger",
        "product_entry",
        "selling_point_use",
        "positive_evidence",
        "story_spine",
        "stop_point",
        "title",
        "body",
        "machine_final_pass",
        "machine_flags",
        "human_business_usable",
        "human_business_reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in items:
            plan = item.get("plan") or {}
            target = item.get("target_kernel") or {}
            writer.writerow({
                "item_no": item.get("item_no"),
                "source_row_no": item.get("source_row_no"),
                "target_stage": target.get("product_relation_stage"),
                "target_proof": target.get("proof_mechanism"),
                "plan_valid": item.get("plan_valid"),
                "plan_issues": ",".join(item.get("plan_issues") or []),
                "product_relation_stage": plan.get("product_relation_stage"),
                "proof_mechanism": plan.get("proof_mechanism"),
                "painpoint": plan.get("painpoint"),
                "post_intent": plan.get("post_intent"),
                "life_trigger": plan.get("life_trigger"),
                "product_entry": plan.get("product_entry"),
                "selling_point_use": plan.get("selling_point_use"),
                "positive_evidence": plan.get("positive_evidence"),
                "story_spine": plan.get("story_spine"),
                "stop_point": plan.get("stop_point"),
                "title": item.get("title"),
                "body": item.get("body"),
                "machine_final_pass": item.get("machine_final_pass"),
                "machine_flags": ",".join(item.get("machine_flags") or []),
                "human_business_usable": item.get("human_business_usable"),
                "human_business_reason": item.get("human_business_reason"),
            })


def _write_preview(path: Path, response_path: Path, prompt_path: Path, plan_csv_path: Path, response: dict[str, Any]) -> None:
    summary = response["report"]["summary"]
    lines = [
        "# v440 two-step product-relation probe preview",
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
        f"- machine final pass: {summary['machine_final_pass_count']} / {summary['generated_count']} -> {summary['machine_final_pass_items']}",
        f"- machine needs review: {summary['machine_needs_review_count']} -> {summary['machine_needs_review_items']}",
        f"- direct pass without post-rewrite: {summary['direct_pass_without_post_rewrite_count']} -> {summary['direct_pass_without_post_rewrite_items']}",
        f"- pass after post-rewrite: {summary['pass_after_post_rewrite_count']} -> {summary['pass_after_post_rewrite_items']}",
        f"- human/business usable: {summary['human_business_usable_count']} -> {summary['human_business_usable_items']}",
        f"- human needs fix: {summary['human_needs_fix_count']} -> {summary['human_needs_fix_items']}",
        f"- plan valid: {summary['plan_valid_count']} / {summary['total_count']} -> {summary['plan_valid_items']}",
        f"- plan rejected: {summary['plan_rejected_count']} -> {summary['plan_rejected_items']}",
        f"- max pairwise similarity: {summary['max_pairwise_jaccard_2gram']}",
        f"- closure hit count: {summary['closure_hit_count']}",
        f"- forbidden hit count: {summary['forbidden_hit_count']}",
        f"- elapsed seconds: {summary['elapsed_seconds']}",
        f"- seconds per attempt: {summary['seconds_per_attempt']}",
        "",
        "## First-Principles Assessment",
        "",
        "这一版验证 v439 的关系核能否用更薄链路执行：先定产品关系阶段和证明机制，再写正文。",
        "重点不是最终可量产，而是看两件事：旧三段式惯性是否下降，强种草是否还能保留。",
        "",
        "## Items",
        "",
    ]
    for item in response["items"]:
        plan = item.get("plan") or {}
        target = item.get("target_kernel") or {}
        lines.extend([
            f"### {item['item_no']}. {item.get('title') or ''}",
            "",
            f"- source_row_no: `{item.get('source_row_no')}`",
            f"- target: `{target.get('product_relation_stage')}` / `{target.get('proof_mechanism')}`",
            f"- plan: `{plan.get('product_relation_stage')}` / `{plan.get('proof_mechanism')}`",
            f"- plan valid: `{item.get('plan_valid')}`; issues: `{', '.join(item.get('plan_issues') or [])}`",
            f"- machine final pass: `{item.get('machine_final_pass')}`; flags: `{', '.join(item.get('machine_flags') or [])}`",
            f"- human/business usable: `{item.get('human_business_usable')}`; reason: {item.get('human_business_reason') or ''}",
            f"- post intent: {plan.get('post_intent') or ''}",
            f"- life trigger: {plan.get('life_trigger') or ''}",
            f"- product entry: {plan.get('product_entry') or ''}",
            f"- selling point: {plan.get('selling_point_use') or ''}",
            f"- positive evidence: {plan.get('positive_evidence') or ''}",
            f"- stop point: {plan.get('stop_point') or ''}",
            "",
            item.get("body") or "",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _format_prompt_sample(index: int, row: dict[str, Any], kernel: dict[str, str], plan_prompt: str, plan: dict[str, Any], writer_prompt: str) -> str:
    return "\n".join([
        "# v440 two-step product-relation rendered prompt",
        "",
        f"- item_no: `{index}`",
        f"- source_row_no: `{row.get('source_row_no') or row.get('item_no') or index}`",
        f"- target kernel: `{kernel.get('product_relation_stage')}` / `{kernel.get('proof_mechanism')}`",
        "",
        "## Relation Planner System",
        "",
        "```text",
        PLAN_SYSTEM,
        "```",
        "",
        "## Relation Planner User",
        "",
        "```json",
        plan_prompt,
        "```",
        "",
        "## Relation Planner Output",
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


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and term in text]


def _current_time_anchor(text: str) -> bool:
    return bool(re.search(r"(换季|流感|春游|秋游|现在.{0,6}(春天|夏天|秋天|冬天)|这个季节|最近.{0,10}(流行|病毒|感冒|咳|中招))", text))


def _product_form_error(text: str) -> bool:
    return bool(re.search(r"(奶瓶|盒装|吸管|便携|小包|条装|书包.{0,6}(侧袋|里面)|独立冲泡|自己.{0,8}(冲奶|泡奶|舀粉)|旺玥.{0,4}牛奶)", text))


def _under3_context(text: str) -> bool:
    return bool(re.search(r"(一岁|两岁|1岁|2岁|刚断奶|辅食|三段奶粉|二段奶粉|一段奶粉|3段|2段|1段)", text))


def _formulaic_closure(text: str) -> bool:
    for match in re.finditer(r"(安心|省心|放心|踏实|心里有底|心安)", text):
        prefix = text[max(0, match.start() - 6) : match.start()]
        if any(neg in prefix for neg in ("不写", "不用", "不要", "不能", "避免")):
            continue
        return True
    return False


def _too_many_proofs(text: str) -> bool:
    return _count_terms(text, ["少请假", "精神头", "专注", "饭量", "身高", "体重", "结实", "长肉", "喝完", "复购"]) >= 4


def _too_many_article_proofs(text: str) -> bool:
    return _count_terms(text, ["少请假", "精神头", "专注", "饭量", "身高", "体重", "结实", "长肉", "喝完", "复购", "钙铁锌", "DHA", "燕窝酸", "乳铁蛋白", "HMO"]) >= 6


def _ingredient_effect_mismatch(text: str) -> bool:
    return bool(re.search(r"(乳铁蛋白|HMO)[^。！？\n]{0,22}(长肉|结实|抱起来沉|衣服撑|跑跳有劲|身高|体重)", text))


def _fixed_usage_overstated(text: str) -> bool:
    return bool(
        re.search(
            r"(每天.{0,10}(一杯|喝|冲|主动要|自己主动)|每次.{0,10}(喝完|喝光|端起来)|"
            r"这几个月.{0,18}每次|一直喝着没断|固定.{0,8}(喝|安排))",
            text,
        )
    )


def _wrong_relation_carry(plan: dict[str, Any], text: str) -> bool:
    stage = str(plan.get("product_relation_stage") or "")
    if "熟悉日常" in stage and re.search(r"(保护力|钙铁锌|DHA|燕窝酸|成长|少请假|精神头)", text):
        return True
    if "初试" in stage and re.search(r"(连着几天|一直|长期|复购|少请假|身高|体重|专注)", text):
        return True
    return False


def _count_terms(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term in text)


def _plan_main_text(plan: dict[str, Any]) -> str:
    keys = [
        "product_relation_stage",
        "proof_mechanism",
        "painpoint",
        "post_intent",
        "life_trigger",
        "product_entry",
        "selling_point_use",
        "positive_evidence",
        "story_spine",
        "stop_point",
        "title_angle",
    ]
    return json.dumps({key: plan.get(key) for key in keys}, ensure_ascii=False)


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


if __name__ == "__main__":
    main()
