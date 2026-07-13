#!/usr/bin/env python3
"""Run a DeepSeek LLM business-usability review over an existing A2 A/B output."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from export_content_ab_review import render_experiment_preview
from generate_a2_direct_from_rule_bank import load_rules
from run_qwen3_a2_news_comment_probe import call_system_deepseek


DEFAULT_OUTPUT_DIR = Path(
    "outputs/a2_sentiment_comments_20260709_new_demo_clean/"
    "run_qwen3_4b_vs_system_deepseek_a2_news_003_20_20260710"
)
DEFAULT_RULE_BANK = Path(
    "outputs/a2_sentiment_comments_20260709_new_demo_clean/"
    "a2_sentiment_news_comment_rule_bank_8cats_20260709.csv"
)
REVIEW_SYSTEM_PROMPT = (
    "你是A2舆情改善评论的业务可用性审核员。输入内容已经通过机器审核，"
    "不要复核违禁词或其他机器硬规则；只按给定业务规则和示例判断，不补充品牌事实。"
)


def load_trace(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def extract_json_array(raw: str) -> list[dict[str, Any]]:
    value = raw.strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value).strip()
    try:
        payload = json.loads(value, strict=False)
    except json.JSONDecodeError:
        match = re.search(r"\[\s*\{.*\}\s*\]", value, flags=re.S)
        if not match:
            raise
        payload = json.loads(match.group(0), strict=False)
    if not isinstance(payload, list):
        raise ValueError("LLM review response is not a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def align_review_item_numbers(
    reviews: list[dict[str, Any]], expected: list[int]
) -> list[dict[str, Any]]:
    actual = [int(item.get("item_no") or 0) for item in reviews]
    if actual == expected:
        return reviews
    if actual == list(range(1, len(reviews) + 1)):
        for item, item_no in zip(reviews, expected, strict=True):
            item["item_no"] = item_no
        return reviews
    raise ValueError(f"review item order mismatch: {actual}")


def review_prompt(rule: dict[str, str], rows: list[dict[str, str]]) -> str:
    comments = "\n".join(f"{row['item_no']}. {row['内容']}" for row in rows)
    if rule["category"] == "舆情缓和-个人经历与个体差异":
        return f"""请审核下面{len(rows)}条已通过机器审核的小红书A2舆情改善评论。

【本批分类】
{rule['category']}

【这批要表达的意思】
{rule['focus']}

【可参考的真实评论形态】
{rule['examples']}

【业务分档】
- direct_pool：原文可以直接交付。主要意思落在当前子方向，像真实妈妈顺手接一句，不诊断、不承诺、不替品牌辩护；长度和信息密度接近参考示例。允许自然带半句相邻方向。
- light_fix_usable：主体方向可用，但有一处局部问题，例如口气稍硬、替代原因写得略像结论、过于完整像客服，做小改即可。
- hold_out：不建议使用。明显否定或压制对方，确定归因，给医疗建议，攻击竞品/评论者，强行阻止转奶，承诺产品效果，或主体像品牌辩护。

【只审核以下业务维度】
- 是否主要贴合当前子方向；问句、“可能/说不准”的陈述句、个人时间顺序都可以，不要机械要求固定句式。
- 相邻子方向自然带半句可以保留；只有因此形成冗长完整解释链时才降档。
- 是否避免诊断、明确确定因果、医疗建议和产品效果承诺。个人经历中的先后变化、正向生活感受、其他奶粉对比本身不是确定因果，不应仅因此降档。
- 是否像真实评论，而不是品牌辩护、客服话术或完整科普。
- 是否足够简短，一条只说一个重点；把个人经历、替代变量、个体差异混在一句，通常应判为light_fix_usable。
- 是否出现“像妈妈、提醒一句、当前子方向”等生成指令泄漏；出现时不得判direct_pool。
- 是否贴合本批子方向，但允许同一条自然带到相邻子方向。

【审核边界】
- 这些评论已经通过机器审核。不要复核违禁词、硬禁词、长度、重复或关键词命中，不要输出机器审核结论。
- 不得仅凭“便便、胃口、辅食、天气、没遇到”等单个词语判错，必须结合整句语义判断。
- 只审核原文，不脑补竞品背景，不要求每条提到 a2。

【待审核评论】
{comments}

只输出JSON数组，必须正好{len(rows)}项并按item_no排序：
[
  {{
    "item_no": 1,
    "business_usability_tier": "direct_pool|light_fix_usable|hold_out",
    "severity": "pass|minor|rewrite",
    "issue_codes": ["off_rule|dismissive_tone|definitive_causality|medical_advice|competitor_attack|forced_no_switch|product_guarantee|brand_defense_tone|generic_brief_tone|ai_like"],
    "reason": "一句具体理由",
    "evidence": "原文中的短证据",
    "rewrite_direction": "无需修改或一句修改方向"
  }}
]"""
    return f"""请审核下面{len(rows)}条已通过机器审核的小红书A2舆情改善评论。

【本批分类】
{rule['category']}

【这批要表达的意思】
{rule['focus']}

【可参考的真实评论形态】
{rule['examples']}

【业务分档】
- direct_pool：原文可以直接交付。符合本批分类，像真实评论区表达，不依赖未提供的品牌事实，没有明显客服教程、运营总结腔或负面舆情回忆。
- light_fix_usable：方向和主体可用，但有一个局部问题，做小改即可。例如略泛、稍专业、轻微像教程、一个未经支持的推测或口气偏硬。
- hold_out：不建议使用。核心意思明显跑题、凭空新增具体产品事实/检测结论、像客服操作说明、广告/运营话术，或需要重写主体。

【只审核以下业务维度】
- 分类贴合：评论表达是否属于本批分类和 focus，允许围绕同一主题做自然追问或信息延伸。
- 事实支持：可以保留未知感和个人感受，但不能把规则、示例未提供的具体事实写成已确认结论。
- 评论质感：是否像真实评论区表达，避免客服教程、后台总结、广告文案和明显 AI 腔。
- 修改成本：原文能否直用、只需局部轻改，还是必须重写主体。

【审核边界】
- 这些评论已经通过机器审核。不要复核违禁词、硬禁词、长度、重复或分类关键词命中，不要输出机器审核结论。
- 不得仅凭单个词语判错，必须结合整句语义以及本批规则、focus 和示例判断。
- 必须以本批规则和示例为最高标准，不要用通用广告审美替代 demo。
- 只审核原文，不替模型脑补上下文。

【待审核评论】
{comments}

只输出JSON数组，必须正好{len(rows)}项并按item_no排序：
[
  {{
    "item_no": 1,
    "business_usability_tier": "direct_pool|light_fix_usable|hold_out",
    "severity": "pass|minor|rewrite",
    "issue_codes": ["off_rule|unsupported_fact|tutorial_tone|generic_brief_tone|ai_like|format_mismatch"],
    "reason": "一句具体理由",
    "evidence": "原文中的短证据",
    "rewrite_direction": "无需修改或一句修改方向"
  }}
]"""


def run_review(
    *,
    rule: dict[str, str],
    rows: list[dict[str, str]],
    model: str,
    maga_url: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not rows:
        return [], {"success": True, "provider_code": "not_run", "provider_model": "not_run"}
    prompt = review_prompt(rule, rows)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = call_system_deepseek(
                prompt
                + (
                    "\n\n上一次输出不是合法JSON。字符串内容中的双引号必须转义；"
                    "不要输出JSON之外的任何文字。"
                    if attempt
                    else ""
                ),
                model=model,
                base_url=maga_url,
                temperature=0.1,
                max_tokens=6000,
                system_prompt=REVIEW_SYSTEM_PROMPT,
            )
            reviews = extract_json_array(str(response.get("content") or ""))
            if len(reviews) != len(rows):
                raise ValueError(f"expected {len(rows)} reviews, got {len(reviews)}")
            expected = [int(row["item_no"]) for row in rows]
            return align_review_item_numbers(reviews, expected), response
        except (TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2)
                continue
            raise
    raise RuntimeError("LLM review failed") from last_error


def machine_blocked_reviews(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for row in rows:
        reason = row["失败原因"] or "machine audit blocked"
        reviews.append(
            {
                "item_no": int(row["item_no"]),
                "business_usability_tier": "not_run",
                "severity": "machine_blocked",
                "issue_codes": ["machine_blocked", reason],
                "reason": f"机器审核未通过，未进入LLM review：{reason}",
                "evidence": row["内容"],
                "rewrite_direction": "先修复机器审核原因，再进入LLM review",
            }
        )
    return reviews


def write_review_csv(path: Path, rows: list[dict[str, str]], reviews: list[dict[str, Any]]) -> None:
    review_by_no = {int(item["item_no"]): item for item in reviews}
    output: list[dict[str, str]] = []
    for row in rows:
        review = review_by_no[int(row["item_no"])]
        output.append(
            {
                **row,
                "LLM业务档位": str(review.get("business_usability_tier") or ""),
                "LLM严重度": str(review.get("severity") or ""),
                "LLM问题码": json.dumps(review.get("issue_codes") or [], ensure_ascii=False),
                "LLM理由": str(review.get("reason") or ""),
                "LLM证据": str(review.get("evidence") or ""),
                "LLM修改方向": str(review.get("rewrite_direction") or ""),
            }
        )
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)


def tier_counts(reviews: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(item.get("business_usability_tier") or "hold_out") for item in reviews)


def effective_tier_counts(
    rows: list[dict[str, str]],
    reviews: list[dict[str, Any]],
) -> Counter[str]:
    review_by_no = {int(item["item_no"]): item for item in reviews}
    counts: Counter[str] = Counter()
    for row in rows:
        if row["是否通过"] != "是":
            counts["machine_blocked"] += 1
            continue
        review = review_by_no[int(row["item_no"])]
        counts[str(review.get("business_usability_tier") or "not_run")] += 1
    return counts


def normalized_items(
    rows: list[dict[str, str]],
    reviews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    review_by_no = {int(item["item_no"]): item for item in reviews}
    items: list[dict[str, Any]] = []
    for row in rows:
        item_no = int(row["item_no"])
        review = review_by_no[item_no]
        items.append(
            {
                "item_no": item_no,
                "pair_id": f"item-{item_no:02d}",
                "category": row["分类"],
                "content": row["内容"],
                "status": "generated",
                "machine_review": {
                    "pass": row["是否通过"] == "是",
                    "reason": row["失败原因"],
                },
                "llm_review": {
                    "tier": review.get("business_usability_tier"),
                    "severity": review.get("severity"),
                    "issue_codes": review.get("issue_codes") or [],
                    "reason": review.get("reason"),
                    "evidence": review.get("evidence"),
                    "rewrite_direction": review.get("rewrite_direction"),
                },
            }
        )
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rule-bank", type=Path, default=DEFAULT_RULE_BANK)
    parser.add_argument("--rule-id", default="a2_news_003")
    parser.add_argument("--review-model", default="deepseek-v4-flash")
    parser.add_argument("--maga-url", default="http://127.0.0.1:5100")
    parser.add_argument("--reuse-existing-review", action="store_true")
    args = parser.parse_args()

    rule = next(rule for rule in load_rules(args.rule_bank) if rule["rule_id"] == args.rule_id)
    qwen_rows = load_trace(args.output_dir / "qwen3_4b_ollama_trace.csv")
    deepseek_rows = load_trace(args.output_dir / "deepseek_v4_flash_system_trace.csv")
    qwen_review_path = args.output_dir / "qwen3_4b_ollama_llm_review.json"
    deepseek_review_path = args.output_dir / "deepseek_v4_flash_system_llm_review.json"
    qwen_review_csv = args.output_dir / "qwen3_4b_ollama_llm_review.csv"
    deepseek_review_csv = args.output_dir / "deepseek_v4_flash_system_llm_review.csv"
    if args.reuse_existing_review:
        qwen_review_payload = json.loads(qwen_review_path.read_text(encoding="utf-8"))
        deepseek_review_payload = json.loads(deepseek_review_path.read_text(encoding="utf-8"))
        qwen_reviews = qwen_review_payload["items"]
        deepseek_reviews = deepseek_review_payload["items"]
        qwen_review_call = qwen_review_payload["reviewer"]
        deepseek_review_call = deepseek_review_payload["reviewer"]
    else:
        qwen_passed_rows = [row for row in qwen_rows if row["是否通过"] == "是"]
        qwen_blocked_rows = [row for row in qwen_rows if row["是否通过"] != "是"]
        deepseek_passed_rows = [row for row in deepseek_rows if row["是否通过"] == "是"]
        deepseek_blocked_rows = [row for row in deepseek_rows if row["是否通过"] != "是"]
        qwen_reviews, qwen_review_call = run_review(
            rule=rule, rows=qwen_passed_rows, model=args.review_model, maga_url=args.maga_url
        )
        deepseek_reviews, deepseek_review_call = run_review(
            rule=rule, rows=deepseek_passed_rows, model=args.review_model, maga_url=args.maga_url
        )
        qwen_reviews = sorted(
            [*qwen_reviews, *machine_blocked_reviews(qwen_blocked_rows)],
            key=lambda item: int(item["item_no"]),
        )
        deepseek_reviews = sorted(
            [*deepseek_reviews, *machine_blocked_reviews(deepseek_blocked_rows)],
            key=lambda item: int(item["item_no"]),
        )
        qwen_review_path.write_text(
            json.dumps(
                {"reviewer": {k: v for k, v in qwen_review_call.items() if k not in {"content", "raw_response"}}, "items": qwen_reviews},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        deepseek_review_path.write_text(
            json.dumps(
                {"reviewer": {k: v for k, v in deepseek_review_call.items() if k not in {"content", "raw_response"}}, "items": deepseek_reviews},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    write_review_csv(qwen_review_csv, qwen_rows, qwen_reviews)
    write_review_csv(deepseek_review_csv, deepseek_rows, deepseek_reviews)

    qwen_counts = effective_tier_counts(qwen_rows, qwen_reviews)
    deepseek_counts = effective_tier_counts(deepseek_rows, deepseek_reviews)
    qwen_raw = json.loads((args.output_dir / "qwen3_4b_ollama_raw.json").read_text(encoding="utf-8"))
    deepseek_raw = json.loads((args.output_dir / "deepseek_v4_flash_system_raw.json").read_text(encoding="utf-8"))
    batch_id = str(qwen_raw["config"]["batch_id"])

    experiment_path = args.output_dir / "a2_qwen3_4b_vs_deepseek_ab_review.json"
    preview_path = args.output_dir / "a2_qwen3_4b_vs_deepseek_v4_flash_preview.md"
    qwen_direct = qwen_counts["direct_pool"]
    deepseek_direct = deepseek_counts["direct_pool"]
    if qwen_direct > deepseek_direct:
        conclusion = "按机器先过、再进入LLM review的门禁口径，Qwen 本轮有效 direct 高于 DeepSeek，但仍有机器拦截项需要回看。"
    elif qwen_direct < deepseek_direct:
        conclusion = "本轮 LLM review 仍更支持 DeepSeek；Qwen 暂不直接替换。"
    else:
        conclusion = "按机器先过、再进入LLM review的门禁口径，两组本轮有效 direct 持平，暂不能仅凭本批决定替换模型。"
    experiment = {
        "experiment_id": batch_id,
        "title": f"A2 Model A/B Review｜{rule['category']}",
        "content_type": "comment",
        "comparison_mode": "aggregate",
        "conclusion": conclusion,
        "changed_dimensions": [
            {
                "name": "生成模型 / Provider",
                "values": {
                    "control": "deepseek / deepseek-v4-flash",
                    "candidate": "ollama / qwen3:4b-instruct-2507-q4_K_M",
                },
            }
        ],
        "controlled_dimensions": [
            {"name": "业务规则", "value": f"{rule['rule_id']}｜{rule['category']}"},
            {"name": "生成 Prompt", "value": "两组完全相同，见 sampled_prompt"},
            {"name": "temperature", "value": qwen_raw["config"]["temperature"]},
            {"name": "max_tokens", "value": qwen_raw["config"]["max_tokens"]},
            {
                "name": "LLM reviewer",
                "value": f"{qwen_review_call.get('provider_code')} / {qwen_review_call.get('provider_model')}",
            },
        ],
        "group_conclusions": [
            "本实验为同一条规则的一次20条聚合生成，两组 item_no 只是展示顺序，不视为逐条随机种子配对。",
            "机器审核是LLM review前置门禁；机器未过的item不进入有效LLM可用统计。",
            "LLM review 与机器审核必须分开展示；运营最终判断尚未执行。",
        ],
        "arms": [
            {
                "arm_id": "control",
                "label": "A｜DeepSeek 对照组",
                "role": "control",
                "metrics": {
                    "attempted": len(deepseek_rows),
                    "latency_ms": deepseek_raw["call"]["latency_ms"],
                    "input_tokens": deepseek_raw["call"]["usage"]["input_tokens"],
                    "output_tokens": deepseek_raw["call"]["usage"]["output_tokens"],
                },
                "items": normalized_items(deepseek_rows, deepseek_reviews),
            },
            {
                "arm_id": "candidate",
                "label": "B｜Qwen3-4B 候选组",
                "role": "candidate",
                "metrics": {
                    "attempted": len(qwen_rows),
                    "latency_ms": qwen_raw["call"]["latency_ms"],
                    "input_tokens": qwen_raw["call"]["usage"]["input_tokens"],
                    "output_tokens": qwen_raw["call"]["usage"]["output_tokens"],
                },
                "items": normalized_items(qwen_rows, qwen_reviews),
            },
        ],
        "artifacts": {
            "experiment_json": str(experiment_path),
            "control_raw": str(args.output_dir / "deepseek_v4_flash_system_raw.json"),
            "candidate_raw": str(args.output_dir / "qwen3_4b_ollama_raw.json"),
            "control_llm_review": str(deepseek_review_path),
            "candidate_llm_review": str(qwen_review_path),
            "sampled_prompt": str(args.output_dir / "a2_ab_complete_rendered_prompt.md"),
        },
    }
    experiment_path.write_text(json.dumps(experiment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    preview_path.write_text(render_experiment_preview(experiment), encoding="utf-8")
    print(preview_path)
    print(qwen_review_path)
    print(deepseek_review_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
