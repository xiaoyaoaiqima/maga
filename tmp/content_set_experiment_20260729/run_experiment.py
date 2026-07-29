#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path("/Users/luxifa/maga")
OUTPUT_DIR = ROOT / "tmp/content_set_experiment_20260729"
BASE_PROMPT_PATH = ROOT / "prompts/a2舆情改善评论-批量生成-提示词.md"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        key, raw = value.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = raw.strip().strip('"').strip("'")


def endpoint(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return f"{value}/chat/completions"
    return f"{value}/v1/chat/completions"


def call_model(prompt: str, *, temperature: float = 0.78, max_tokens: int = 2200) -> tuple[dict[str, Any], float]:
    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("missing DEEPSEEK_API_KEY")
    base_url = (os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com/v1").strip()
    model = (os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是擅长规划中文社区内容组合并严格输出 JSON 的内容策略编辑。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }
    request = urllib.request.Request(
        endpoint(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"model HTTP {exc.code}: {body}") from exc
    latency = time.perf_counter() - started
    raw = str(data["choices"][0]["message"].get("content") or "")
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    parsed, _end = json.JSONDecoder().raw_decode(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("model output is not a JSON object")
    return parsed, round(latency, 3)


def strategy_planner_prompt(base_prompt: str) -> str:
    return f"""为下面这批 A2 舆情改善评论先规划 10 张内容策略卡，不要写评论正文。

这是内部内容实验草稿，不作为未披露的真实消费者评价直接发布。

策略卡必须共同满足：
- 恰好 10 张，strategy_id 为 S01 至 S10
- length_band 恰好分布为 short 1 张、medium 6 张、long 3 张
- 每张只围绕一个主要反应
- scene、subject、action、reaction、opening_style、ending_style 尽量不重复
- brand_mention=true 恰好 1 张
- emoji=true 最多 1 张
- punctuation=true 最多 1 张
- 策略卡之间要形成一组自然分布，不要只是同义词替换

每张策略卡字段：
- strategy_id
- length_band: short / medium / long
- angle: 本条核心反应
- scene: 生活场景
- subject: 说话主语或观察入口
- action: 与有货、到货、库存稳定相关的动作
- reaction: 个人反应
- opening_style: 开头方式
- ending_style: 收尾方式
- brand_mention: boolean
- emoji: boolean
- punctuation: boolean

只输出 JSON：{{"strategies":[...]}}

业务提示词：
{base_prompt}
"""


def direct_batch_prompt(base_prompt: str) -> str:
    return f"""{base_prompt}

本次是内部内容组合实验。请在同一次调用中先自行规划差异，再生成完整 10 条评论。
- 数量恰好 10 条
- 长度分布：短评 1 条、中评 6 条、长评 3 条
- 不显示内部规划过程
- 只输出 JSON：{{"items":["评论1","评论2","评论3","评论4","评论5","评论6","评论7","评论8","评论9","评论10"]}}
"""


def single_comment_prompt(base_prompt: str, strategy: dict[str, Any]) -> str:
    return f"""{base_prompt}

本次只生成内容组合中的一条评论。整批差异已经由外部策略卡规划，不需要再规划其他评论。
严格按这张策略卡写作：
{json.dumps(strategy, ensure_ascii=False, indent=2)}

长度口径：short 不超过 12 字；medium 15 至 28 字；long 35 至 45 字。
brand_mention=false 时不要出现 a2 或其他产品名。
emoji=false 时不要使用 emoji。punctuation=false 时不要使用句号或叹号。
只输出 JSON：{{"comment":"..."}}
"""


def strategy_batch_prompt(base_prompt: str, strategies: list[dict[str, Any]]) -> str:
    count = len(strategies)
    first_id = str(strategies[0]["strategy_id"])
    last_id = str(strategies[-1]["strategy_id"])
    return f"""{base_prompt}

本次是内部内容组合实验。下面已经给出 {count} 张互不相同的策略卡，请在同一次调用中逐卡生成，一张策略卡对应一条评论。

策略卡：
{json.dumps(strategies, ensure_ascii=False, indent=2)}

要求：
- 不重新合并或改写策略卡，不让一条评论承担多张卡
- 每条只实现对应 strategy_id 的 scene、action 和 reaction
- 长度口径：short 不超过 12 字；medium 15 至 28 字；long 35 至 45 字
- brand_mention=false 时不要出现 a2 或其他产品名
- emoji=false 时不要使用 emoji；punctuation=false 时不要使用句号或叹号
- 只输出 JSON：{{"items":[{{"strategy_id":"S01","comment":"..."}}]}}
- items 必须恰好 {count} 个，并按 {first_id} 至 {last_id} 排列
"""


def normalize_comment(value: Any) -> str:
    return str(value or "").strip().strip("“”\"'")


def parse_direct(result: dict[str, Any]) -> list[str]:
    items = result.get("items")
    if not isinstance(items, list):
        raise ValueError("direct batch missing items")
    comments = [normalize_comment(item) for item in items]
    if len(comments) != 10 or not all(comments):
        raise ValueError(f"direct batch returned {len(comments)} usable items")
    return comments


def parse_strategy_batch(result: dict[str, Any], strategies: list[dict[str, Any]]) -> list[str]:
    items = result.get("items")
    if not isinstance(items, list):
        raise ValueError("strategy batch missing items")
    by_id = {
        str(item.get("strategy_id") or "").strip(): normalize_comment(item.get("comment"))
        for item in items
        if isinstance(item, dict)
    }
    comments = [by_id.get(str(strategy["strategy_id"]), "") for strategy in strategies]
    if len(comments) != len(strategies) or not all(comments):
        raise ValueError(f"strategy batch returned {sum(bool(item) for item in comments)} usable items")
    return comments


def length_band(length: int) -> str:
    if length <= 12:
        return "short"
    if 15 <= length <= 28:
        return "medium"
    if 35 <= length <= 45:
        return "long"
    return "gap_or_out"


def ngrams(text: str, size: int = 2) -> set[str]:
    compact = re.sub(r"\s+", "", text)
    return {compact[index : index + size] for index in range(max(0, len(compact) - size + 1))}


def jaccard(left: str, right: str) -> float:
    left_grams = ngrams(left)
    right_grams = ngrams(right)
    union = left_grams | right_grams
    return len(left_grams & right_grams) / len(union) if union else 0.0


def metrics(comments: list[str]) -> dict[str, Any]:
    lengths = [len(comment) for comment in comments]
    pairwise = [
        jaccard(comments[left], comments[right])
        for left in range(len(comments))
        for right in range(left + 1, len(comments))
    ]
    openings = [re.sub(r"^[，。！？,!?；;\s]+", "", comment)[:4] for comment in comments]
    endings = [re.sub(r"[，。！？,!?；;\s]+$", "", comment)[-4:] for comment in comments]
    return {
        "count": len(comments),
        "unique_count": len(set(comments)),
        "lengths": lengths,
        "length_band_counts": dict(Counter(length_band(length) for length in lengths)),
        "max_pairwise_jaccard_2gram": round(max(pairwise) if pairwise else 0.0, 4),
        "avg_pairwise_jaccard_2gram": round(sum(pairwise) / len(pairwise) if pairwise else 0.0, 4),
        "duplicate_opening_4_count": sum(count - 1 for count in Counter(openings).values() if count > 1),
        "duplicate_ending_4_count": sum(count - 1 for count in Counter(endings).values() if count > 1),
        "brand_mention_count": sum("a2" in comment.lower() for comment in comments),
        "emoji_count": sum(bool(re.search(r"[^\w\s\u4e00-\u9fff，。！？,.!?；;、]", comment)) for comment in comments),
        "period_or_exclamation_count": sum(bool(re.search(r"[。！!]", comment)) for comment in comments),
    }


def render_preview(
    strategies: list[dict[str, Any]],
    arms: dict[str, dict[str, Any]],
    sampled_prompt: str,
) -> str:
    lines = [
        "# 内容组合生成实验预览",
        "",
        "> 只报告确定性结构指标；内容好不好由人工 taste 判断，不使用机器审核结论。",
        "",
        "## 指标对比",
        "",
        "| 组别 | 调用方式 | 耗时 | 长度分布 | 最大二元相似度 | 重复开头 | 重复结尾 |",
        "|---|---|---:|---|---:|---:|---:|",
    ]
    labels = {
        "direct_batch": "直接批量成文",
        "strategy_separate": "策略卡后逐条成文",
        "strategy_microbatch": "策略卡后每次两条",
        "strategy_batch": "策略卡后批量成文",
    }
    modes = {
        "direct_batch": "1 次",
        "strategy_separate": "10 次并发",
        "strategy_microbatch": "5 次并发",
        "strategy_batch": "1 次",
    }
    for key in ("direct_batch", "strategy_separate", "strategy_microbatch", "strategy_batch"):
        arm = arms[key]
        value = arm["metrics"]
        lines.append(
            f"| {labels[key]} | {modes[key]} | {arm['latency_s']:.3f}s | "
            f"{value['length_band_counts']} | {value['max_pairwise_jaccard_2gram']:.4f} | "
            f"{value['duplicate_opening_4_count']} | {value['duplicate_ending_4_count']} |"
        )
    lines.extend(["", "## 完整结果", ""])
    for index, strategy in enumerate(strategies):
        lines.extend(
            [
                f"### {strategy['strategy_id']} · {strategy['length_band']} · {strategy['angle']}",
                "",
                f"- 策略：{strategy['scene']} / {strategy['action']} / {strategy['reaction']}",
                f"- 直接批量：{arms['direct_batch']['comments'][index]}",
                f"- 逐条生成：{arms['strategy_separate']['comments'][index]}",
                f"- 每次两条：{arms['strategy_microbatch']['comments'][index]}",
                f"- 策略批量：{arms['strategy_batch']['comments'][index]}",
                "",
            ]
        )
    lines.extend(
        [
            "## 随机抽样完整生成 Prompt",
            "",
            "抽样：S04，策略卡后逐条生成。",
            "",
            "```text",
            sampled_prompt,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    load_dotenv(ROOT / ".env")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base_prompt = BASE_PROMPT_PATH.read_text(encoding="utf-8")

    planner_prompt = strategy_planner_prompt(base_prompt)
    planner_result, planner_latency = call_model(planner_prompt, max_tokens=2600)
    strategies = planner_result.get("strategies")
    if not isinstance(strategies, list) or len(strategies) != 10:
        raise ValueError("strategy planner did not return exactly 10 strategies")
    strategy_ids = [str(item.get("strategy_id") or "") for item in strategies if isinstance(item, dict)]
    if strategy_ids != [f"S{index:02d}" for index in range(1, 11)]:
        raise ValueError(f"unexpected strategy ids: {strategy_ids}")

    direct_prompt = direct_batch_prompt(base_prompt)
    direct_result, direct_latency = call_model(direct_prompt)
    direct_comments = parse_direct(direct_result)

    single_prompts = [single_comment_prompt(base_prompt, strategy) for strategy in strategies]
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        single_results = list(executor.map(call_model, single_prompts))
    separate_latency = round(time.perf_counter() - started, 3)
    separate_comments = [normalize_comment(result.get("comment")) for result, _latency in single_results]
    if len(separate_comments) != 10 or not all(separate_comments):
        raise ValueError("separate generation returned empty comment")

    micro_groups = [strategies[index : index + 2] for index in range(0, len(strategies), 2)]
    micro_prompts = [strategy_batch_prompt(base_prompt, group) for group in micro_groups]
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        micro_results = list(executor.map(call_model, micro_prompts))
    micro_latency = round(time.perf_counter() - started, 3)
    micro_comments: list[str] = []
    for group, (result, _latency) in zip(micro_groups, micro_results, strict=True):
        micro_comments.extend(parse_strategy_batch(result, group))

    batch_prompt = strategy_batch_prompt(base_prompt, strategies)
    batch_result, batch_latency = call_model(batch_prompt, max_tokens=2600)
    batch_comments = parse_strategy_batch(batch_result, strategies)

    arms = {
        "direct_batch": {
            "comments": direct_comments,
            "latency_s": direct_latency,
            "metrics": metrics(direct_comments),
            "raw_output": direct_result,
        },
        "strategy_separate": {
            "comments": separate_comments,
            "latency_s": separate_latency,
            "individual_latency_s": [latency for _result, latency in single_results],
            "metrics": metrics(separate_comments),
            "raw_output": [result for result, _latency in single_results],
        },
        "strategy_microbatch": {
            "comments": micro_comments,
            "latency_s": micro_latency,
            "individual_latency_s": [latency for _result, latency in micro_results],
            "metrics": metrics(micro_comments),
            "raw_output": [result for result, _latency in micro_results],
        },
        "strategy_batch": {
            "comments": batch_comments,
            "latency_s": batch_latency,
            "metrics": metrics(batch_comments),
            "raw_output": batch_result,
        },
    }
    artifact = {
        "model": os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash",
        "planner_latency_s": planner_latency,
        "strategies": strategies,
        "arms": arms,
    }
    (OUTPUT_DIR / "report.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "strategy_planner_prompt.txt").write_text(planner_prompt, encoding="utf-8")
    (OUTPUT_DIR / "direct_batch_prompt.txt").write_text(direct_prompt, encoding="utf-8")
    (OUTPUT_DIR / "strategy_batch_prompt.txt").write_text(batch_prompt, encoding="utf-8")
    (OUTPUT_DIR / "sampled_single_prompt_S04.txt").write_text(single_prompts[3], encoding="utf-8")
    (OUTPUT_DIR / "preview.md").write_text(
        render_preview(strategies, arms, single_prompts[3]),
        encoding="utf-8",
    )
    print(json.dumps({"planner_latency_s": planner_latency, "arms": {key: value["metrics"] for key, value in arms.items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
