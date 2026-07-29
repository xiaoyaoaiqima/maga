#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        key, raw = value.split("=", 1)
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = raw.strip().strip('"').strip("'")


def endpoint(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return f"{value}/chat/completions"
    return f"{value}/v1/chat/completions"


def chinese_length(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def length_band(length: int) -> str:
    if 6 <= length <= 12:
        return "short"
    if 13 <= length <= 24:
        return "medium"
    if 25 <= length <= 40:
        return "long"
    return "out_of_range"


def analyze(items: list[str], latency_s: float, usage: dict[str, Any], finish_reason: Any) -> dict[str, Any]:
    lengths = [len(item) for item in items]
    han_lengths = [chinese_length(item) for item in items]
    return {
        "count": len(items),
        "latency_s": round(latency_s, 3),
        "lengths": lengths,
        "han_lengths": han_lengths,
        "bands": [length_band(length) for length in lengths],
        "band_counts": {
            band: sum(length_band(length) == band for length in lengths)
            for band in ("short", "medium", "long", "out_of_range")
        },
        "unique_count": len(set(items)),
        "finish_reason": finish_reason,
        "usage": usage,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--append-prompt", type=Path, action="append")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=1200)
    args = parser.parse_args()

    load_dotenv(Path("/Users/luxifa/maga/.env"))
    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    base_url = (os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com/v1").strip()
    model = (os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip()
    if not api_key:
        raise RuntimeError("missing DEEPSEEK_API_KEY")

    prompt = args.prompt.read_text(encoding="utf-8")
    for append_prompt in args.append_prompt or []:
        prompt = f"{prompt}\n\n{append_prompt.read_text(encoding='utf-8')}"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    system_message = "你是严格遵守批次约束的中文社区评论写手。"
    (args.output_dir / "rendered_prompt.md").write_text(prompt, encoding="utf-8")
    (args.output_dir / "request.json").write_text(
        json.dumps(
            {
                "endpoint": endpoint(base_url),
                "model": model,
                "system_message": system_message,
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summaries: list[dict[str, Any]] = []

    for run_no in range(1, args.runs + 1):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
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
        latency_s = time.perf_counter() - started
        choice = data["choices"][0]
        message = choice["message"]
        raw = str(message.get("content") or "")
        parsed = json.loads(raw)
        items = parsed.get("items") if isinstance(parsed, dict) else None
        if isinstance(items, list) and items and all(isinstance(item, dict) for item in items):
            expected_strategy_ids = [f"S{index:02d}" for index in range(1, 11)]
            strategy_ids = [str(item.get("strategy_id") or "").strip() for item in items]
            if strategy_ids != expected_strategy_ids:
                raise ValueError(f"run {run_no}: strategy ids mismatch: {strategy_ids}")
            items = [str(item.get("comment") or "").strip() for item in items]
        if isinstance(parsed, dict) and not isinstance(items, list):
            short_items = parsed.get("short_items")
            medium_items = parsed.get("medium_items")
            long_items = parsed.get("long_items")
            if (
                isinstance(short_items, list)
                and isinstance(medium_items, list)
                and isinstance(long_items, list)
                and len(short_items) == 1
                and len(medium_items) == 5
                and len(long_items) == 4
            ):
                items = [
                    short_items[0],
                    medium_items[0],
                    long_items[0],
                    medium_items[1],
                    long_items[1],
                    medium_items[2],
                    long_items[2],
                    medium_items[3],
                    long_items[3],
                    medium_items[4],
                ]
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise ValueError(f"run {run_no}: output is not an items string array")
        if len(items) != 10 or any(not item for item in items):
            raise ValueError(f"run {run_no}: expected 10 non-empty comments, got {len(items)}")
        summary = analyze(items, latency_s, data.get("usage") or {}, choice.get("finish_reason"))
        summary["run_no"] = run_no
        summaries.append(summary)
        (args.output_dir / f"run_{run_no}.json").write_text(
            json.dumps({"raw_output": parsed, "items": items, "summary": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    (args.output_dir / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
