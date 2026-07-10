#!/usr/bin/env python3
"""Compare local Ollama Qwen3 4B with MAGA's routed DeepSeek on one A2 rule."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from generate_a2_direct_from_rule_bank import (
    audit,
    generalize_competitor_brand_terms,
    jaccard_2gram,
    load_rules,
    max_pairwise_similarity,
    near_duplicate_reason,
    parse_comments,
    prompt_for,
)


DEFAULT_BASE_DIR = Path("outputs/a2_sentiment_comments_20260709_new_demo_clean")
DEFAULT_RULE_BANK = DEFAULT_BASE_DIR / "a2_sentiment_news_comment_rule_bank_8cats_20260709.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_BASE_DIR / "run_qwen3_4b_vs_system_deepseek_a2_news_003_20_20260710"
DEFAULT_QWEN_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
SYSTEM_PROMPT = "你是严格按要求输出 JSON 的中文UGC扩散写手。"


def get_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout: float,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:1000]}") from exc


def call_ollama(
    prompt: str,
    *,
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    response = post_json(
        base_url.rstrip("/") + "/api/chat",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        },
        timeout=240,
    )
    return {
        "success": True,
        "content": str(response.get("message", {}).get("content", "")).strip(),
        "model_code": model,
        "provider_code": "ollama",
        "provider_model": str(response.get("model") or model),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": {
            "input_tokens": int(response.get("prompt_eval_count") or 0),
            "output_tokens": int(response.get("eval_count") or 0),
            "total_tokens": int(response.get("prompt_eval_count") or 0)
            + int(response.get("eval_count") or 0),
        },
        "raw_response": response,
    }


def call_system_deepseek(
    prompt: str,
    *,
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str = SYSTEM_PROMPT,
) -> dict[str, Any]:
    routes_payload = get_json(base_url.rstrip("/") + "/api/v1/llm-providers/routes", 30)
    routes = (routes_payload.get("data") or {}).get("items") or []
    candidates = [
        route
        for route in routes
        if route.get("model_code") == model and route.get("enabled")
    ]
    if not candidates:
        raise RuntimeError(f"no enabled system route for {model}")
    route = sorted(candidates, key=lambda item: int(item.get("priority") or 0), reverse=True)[0]
    provider_code = str(route.get("provider_code") or "")
    config_payload = get_json(
        base_url.rstrip("/") + f"/api/v1/llm-providers/{provider_code}/internal-config",
        30,
    )
    provider = config_payload.get("data") or config_payload
    api_key = str(provider.get("api_key") or "").strip()
    provider_base_url = str(provider.get("base_url") or "").rstrip("/")
    if not api_key or not provider_base_url:
        raise RuntimeError(f"incomplete internal config for provider {provider_code}")
    endpoint = (
        provider_base_url + "/chat/completions"
        if provider_base_url.endswith("/v1")
        else provider_base_url + "/v1/chat/completions"
    )
    started = time.perf_counter()
    response = post_json(
        endpoint,
        {
            "model": str(route.get("provider_model") or model),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=240,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"system provider response has no choices: {response}")
    usage = response.get("usage") or {}
    return {
        "success": True,
        "content": str((choices[0].get("message") or {}).get("content") or "").strip(),
        "model_code": model,
        "provider_code": provider_code,
        "provider_model": str(route.get("provider_model") or model),
        "provider_base_url": provider_base_url,
        "route_priority": int(route.get("priority") or 0),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        },
        "raw_response": response,
    }


def audit_response(
    content: str,
    *,
    rule: dict[str, str],
    count: int,
    similarity_threshold: float,
) -> list[dict[str, str]]:
    trace: list[dict[str, str]] = []
    seen: set[str] = set()
    accepted: list[str] = []
    for item_no, text in enumerate(parse_comments(content)[:count], start=1):
        normalized = generalize_competitor_brand_terms(text)
        reason = audit(rule["category"], normalized, seen, "sentiment_news")
        if not reason:
            reason = near_duplicate_reason(normalized, accepted, similarity_threshold)
        passed = not reason
        trace.append(
            {
                "item_no": str(item_no),
                "规则ID": rule["rule_id"],
                "分类": rule["category"],
                "内容": normalized,
                "是否通过": "是" if passed else "否",
                "失败原因": reason,
            }
        )
        if passed:
            seen.add(normalized)
            accepted.append(normalized)
    return trace


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["item_no", "规则ID", "分类", "内容", "是否通过", "失败原因"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def metrics(trace: list[dict[str, str]]) -> dict[str, Any]:
    passed = [row for row in trace if row["是否通过"] == "是"]
    failed = [row for row in trace if row["是否通过"] != "是"]
    max_similarity, max_pair, warning_count = max_pairwise_similarity(passed)
    return {
        "generated": len(trace),
        "passed": len(passed),
        "failed": len(failed),
        "fail_reasons": dict(Counter(row["失败原因"] for row in failed)),
        "max_pairwise_jaccard_2gram": round(max_similarity, 3),
        "similarity_pairs_ge_0_5": warning_count,
        "max_pair": max_pair,
    }


def cross_model_similarity(
    left: list[dict[str, str]], right: list[dict[str, str]]
) -> tuple[float, tuple[str, str] | None]:
    best = (0.0, None)
    for left_row in left:
        for right_row in right:
            score = jaccard_2gram(left_row["内容"], right_row["内容"])
            if score > best[0]:
                best = (score, (left_row["内容"], right_row["内容"]))
    return best


def write_prompt(path: Path, batch_id: str, rule: dict[str, str], prompt: str) -> None:
    path.write_text(
        "\n".join(
            [
                "# A2 A/B Complete Rendered Prompt",
                "",
                f"- batch_id: `{batch_id}`",
                f"- rule_id: `{rule['rule_id']}`",
                f"- category: `{rule['category']}`",
                f"- system_prompt: `{SYSTEM_PROMPT}`",
                "",
                "```text",
                prompt,
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def append_items(lines: list[str], title: str, trace: list[dict[str, str]]) -> None:
    lines.extend([f"## {title}", ""])
    for row in trace:
        marker = "✅" if row["是否通过"] == "是" else "💣"
        status = "可用" if row["是否通过"] == "是" else row["失败原因"]
        lines.extend(
            [
                f"### {marker} item {row['item_no']}｜{status}",
                "",
                row["内容"],
                "",
            ]
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rule-bank", type=Path, default=DEFAULT_RULE_BANK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rule-id", default="a2_news_003")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--qwen-model", default=DEFAULT_QWEN_MODEL)
    parser.add_argument("--deepseek-model", default=DEFAULT_DEEPSEEK_MODEL)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--maga-url", default="http://127.0.0.1:5100")
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=3600)
    parser.add_argument("--similarity-threshold", type=float, default=0.86)
    args = parser.parse_args()

    rules = load_rules(args.rule_bank)
    selected = [rule for rule in rules if rule["rule_id"] == args.rule_id]
    if len(selected) != 1:
        raise SystemExit(f"expected exactly one rule for {args.rule_id}, got {len(selected)}")
    rule = selected[0]
    prompt = prompt_for(rule["focus"], rule["examples"], args.count, "sentiment_news")
    batch_id = f"a2-ab-{args.rule_id}-{args.count}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = args.output_dir / "a2_ab_complete_rendered_prompt.md"
    qwen_raw_path = args.output_dir / "qwen3_4b_ollama_raw.json"
    deepseek_raw_path = args.output_dir / "deepseek_v4_flash_system_raw.json"
    qwen_trace_path = args.output_dir / "qwen3_4b_ollama_trace.csv"
    deepseek_trace_path = args.output_dir / "deepseek_v4_flash_system_trace.csv"
    preview_path = args.output_dir / "a2_qwen3_4b_vs_deepseek_v4_flash_preview.md"

    qwen = call_ollama(
        prompt,
        model=args.qwen_model,
        base_url=args.ollama_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    deepseek = call_system_deepseek(
        prompt,
        model=args.deepseek_model,
        base_url=args.maga_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    qwen_trace = audit_response(
        qwen["content"],
        rule=rule,
        count=args.count,
        similarity_threshold=args.similarity_threshold,
    )
    deepseek_trace = audit_response(
        deepseek["content"],
        rule=rule,
        count=args.count,
        similarity_threshold=args.similarity_threshold,
    )
    qwen_metrics = metrics(qwen_trace)
    deepseek_metrics = metrics(deepseek_trace)
    cross_score, cross_pair = cross_model_similarity(qwen_trace, deepseek_trace)

    config = {
        "batch_id": batch_id,
        "rule_id": rule["rule_id"],
        "category": rule["category"],
        "system_prompt": SYSTEM_PROMPT,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "count": args.count,
    }
    qwen_raw_path.write_text(
        json.dumps({"config": config, "call": qwen}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    deepseek_raw_path.write_text(
        json.dumps({"config": config, "call": deepseek}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(qwen_trace_path, qwen_trace)
    write_csv(deepseek_trace_path, deepseek_trace)
    write_prompt(prompt_path, batch_id, rule, prompt)

    lines = [
        f"# A2 Qwen3 4B Ollama vs System DeepSeek｜{rule['category']}",
        "",
        "标识说明：💣 需修｜⚠️ 重点看｜👀 观察｜✅ 可用｜⛔ 生成失败｜🧪 draft测试",
        "",
        "## Conclusion",
        "",
        "🧪 draft 对照：两组使用同一份 A2 prompt、system prompt、温度和 token 上限；业务可用性需人工复核。",
        "",
        "## Key Metrics",
        "",
        f"- batch_id: `{batch_id}`",
        f"- Qwen: `{qwen['provider_code']}` / `{qwen['provider_model']}` / {qwen_metrics['passed']}/{qwen_metrics['generated']} machine pass / {qwen['latency_ms']} ms",
        f"- DeepSeek: `{deepseek.get('provider_code')}` / `{deepseek.get('provider_model')}` / {deepseek_metrics['passed']}/{deepseek_metrics['generated']} machine pass / {deepseek.get('latency_ms')} ms",
        f"- Qwen fail reasons: `{json.dumps(qwen_metrics['fail_reasons'], ensure_ascii=False)}`",
        f"- DeepSeek fail reasons: `{json.dumps(deepseek_metrics['fail_reasons'], ensure_ascii=False)}`",
        f"- Qwen max internal similarity: {qwen_metrics['max_pairwise_jaccard_2gram']}",
        f"- DeepSeek max internal similarity: {deepseek_metrics['max_pairwise_jaccard_2gram']}",
        f"- max cross-model similarity: {cross_score:.3f}",
        "",
        "## Candidate Change",
        "",
        "只替换调用端：本机 Ollama Qwen3 4B vs MAGA 系统路由 DeepSeek；输入 prompt 与审核函数完全相同。",
        "",
        "## 重点看",
        "",
        f"- Qwen 最高内部相似对: `{qwen_metrics['max_pair']}`",
        f"- DeepSeek 最高内部相似对: `{deepseek_metrics['max_pair']}`",
        f"- 两模型最相似对: `{cross_pair}`",
        "",
    ]
    append_items(lines, "Qwen3 4B｜Ollama", qwen_trace)
    append_items(lines, "deepseek-v4-flash｜MAGA 系统路由", deepseek_trace)
    lines.extend(
        [
            "## 调试信息",
            "",
            f"- qwen_raw: `{qwen_raw_path}`",
            f"- deepseek_raw: `{deepseek_raw_path}`",
            f"- qwen_trace: `{qwen_trace_path}`",
            f"- deepseek_trace: `{deepseek_trace_path}`",
            f"- rendered_prompt: `{prompt_path}`",
            "",
        ]
    )
    preview_path.write_text("\n".join(lines), encoding="utf-8")

    print(preview_path)
    print(prompt_path)
    print(qwen_raw_path)
    print(deepseek_raw_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
