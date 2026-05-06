#!/usr/bin/env python3
"""
Batch prompt optimizer MVP.

Reads a CSV with prompt/content/problem columns, calls an OpenAI-compatible
chat completions API, and writes prompt diagnosis results to a CSV.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any



DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 3000
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_RETRIES = 2


def load_dotenv(path: Path = Path(".env")) -> None:
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


REQUIRED_COLUMNS = ("prompt", "title", "content", "problem")
OUTPUT_COLUMNS = (
    "id",
    "prompt_issue",
    "modify_suggestion",
    "added_content",
    "removed_content",
    "revised_prompt",
    "confidence",
    "raw_output",
    "error",
)


SYSTEM_PROMPT = """你是一个资深小红书内容生产与提示词优化专家。
你需要根据原始生文提示词、生成结果和运营审查问题，反推出提示词设计上的缺陷，并给出可执行的修改方案。

优化原则：
- 只提出能被“生成结果 + 运营审查问题”直接支持的最小必要修改，避免把单个问题扩展成更宽、更硬的禁令。
- 禁止过度泛化：如果问题是某个固定句式或表达方式违规，只禁止该句式/表达方式，不要额外禁止关键词在其他合理语境中出现。
- 不要新增位置类、开场类、结构类限制，除非运营审查问题明确指出位置、开场或结构本身有问题。
- 新增规则应尽量贴近原提示词已有规则的颗粒度，一次只解决当前证据能解释的问题。
- 如果某条建议属于“可能有帮助但证据不足”，不要写入 added_content，可在 modify_suggestion 中弱提示。

请只输出 JSON，不要输出 Markdown，不要解释 JSON 外的内容。
所有字段值都必须是合法 JSON 字符串；如果包含换行，请使用 \\n 转义，不要输出未转义的真实换行。
JSON 字段必须包含：
- prompt_issue: 原提示词的问题在哪里
- modify_suggestion: 应该怎么修改，要求具体可执行
- added_content: 建议新增到原提示词里的内容，只写新增片段；如果没有新增则返回空字符串
- removed_content: 建议从原提示词中删除或弱化的内容，只写删除片段；如果没有删除则返回空字符串
- revised_prompt: 默认返回空字符串，不要输出完整修改后提示词，避免超长截断
- confidence: 0 到 1 之间的小数，表示你对诊断的置信度
"""


USER_PROMPT_TEMPLATE = """# 背景信息
## 生文用到的提示词:
{prompt}

## 生成的标题：
{title}

## 生成的内容：
{content}

## 运营审查发现的问题：
{problem}

# 你的任务
输出生文提示词的问题在哪里，怎么修改。

# 输出要求补充
不要输出完整 revised_prompt，请将 revised_prompt 返回为空字符串。
请重点输出 added_content 和 removed_content，便于人工合并修改。"""


def parse_args() -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Read a CSV and batch optimize generation prompts.",
    )
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--id-column", default="id", help="ID column name. Defaults to id.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows.")
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent LLM calls. Defaults to 3.")
    parser.add_argument("--resume", action="store_true", help="Skip rows whose id already exists in output.")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retries per row. Defaults to 2.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout seconds.")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", DEFAULT_MODEL), help="Model name.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL") or os.getenv("AIHUBMIX_API_URL") or DEFAULT_BASE_URL,
        help="OpenAI-compatible chat completions URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENAI_API_KEY") or os.getenv("AIHUBMIX_API_KEY"),
        help="API key. Defaults to OPENAI_API_KEY or AIHUBMIX_API_KEY.",
    )
    parser.add_argument(
        "--no-json-mode",
        action="store_true",
        help="Disable response_format=json_object for providers that do not support JSON mode.",
    )
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    return parser.parse_args()


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("输入 CSV 缺少表头")
        rows = [dict(row) for row in reader]
        return rows, list(reader.fieldnames)


def validate_columns(fieldnames: list[str], id_column: str) -> None:
    missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
    if missing:
        raise ValueError(f"输入 CSV 缺少必填列: {', '.join(missing)}")


def read_processed_ids(path: Path, id_column: str) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or id_column not in reader.fieldnames:
            return set()
        return {str(row.get(id_column, "")).strip() for row in reader if row.get(id_column)}


def ensure_output(path: Path, input_columns: list[str]) -> tuple[list[str], bool]:
    output_columns = list(dict.fromkeys(input_columns + list(OUTPUT_COLUMNS)))
    exists_with_content = path.exists() and path.stat().st_size > 0
    if not exists_with_content:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=output_columns)
            writer.writeheader()
    return output_columns, exists_with_content


def build_user_prompt(row: dict[str, str]) -> str:
    return USER_PROMPT_TEMPLATE.format(
        prompt=(row.get("prompt") or "").strip(),
        title=(row.get("title") or "").strip(),
        content=(row.get("content") or "").strip(),
        problem=(row.get("problem") or "").strip(),
    )


def normalize_chat_completions_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return f"{value}/chat/completions"
    return value


def call_openai_compatible(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
    json_mode: bool,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        normalize_chat_completions_url(base_url),
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    result = json.loads(raw)
    return (((result.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("模型输出不是 JSON object")
    return value


async def optimize_one(row: dict[str, str], args: argparse.Namespace) -> dict[str, str]:
    user_prompt = build_user_prompt(row)
    raw_output = ""
    last_error = ""

    for attempt in range(args.retries + 1):
        try:
            raw_output = await asyncio.to_thread(
                call_openai_compatible,
                api_key=args.api_key,
                base_url=args.base_url,
                model=args.model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                json_mode=not args.no_json_mode,
            )
            parsed = extract_json_object(raw_output)
            return {
                **row,
                "prompt_issue": str(parsed.get("prompt_issue", "")).strip(),
                "modify_suggestion": str(parsed.get("modify_suggestion", "")).strip(),
                "added_content": str(parsed.get("added_content", "")).strip(),
                "removed_content": str(parsed.get("removed_content", "")).strip(),
                "revised_prompt": str(parsed.get("revised_prompt", "")).strip(),
                "confidence": str(parsed.get("confidence", "")).strip(),
                "raw_output": raw_output,
                "error": "",
            }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt < args.retries:
                await asyncio.sleep((2**attempt) + random.random())
                continue

    return {
        **row,
        "prompt_issue": "",
        "modify_suggestion": "",
        "added_content": "",
        "removed_content": "",
        "revised_prompt": "",
        "confidence": "",
        "raw_output": raw_output,
        "error": last_error or "unknown_error",
    }


async def run_batch(args: argparse.Namespace) -> None:
    if not args.api_key:
        raise ValueError("未配置 API Key，请设置 OPENAI_API_KEY / AIHUBMIX_API_KEY，或传入 --api-key")

    input_path = Path(args.input)
    output_path = Path(args.output)
    rows, input_columns = read_csv(input_path)
    validate_columns(input_columns, args.id_column)
    for index, row in enumerate(rows, start=1):
        row.setdefault(args.id_column, str(index))
    if args.id_column not in input_columns:
        input_columns = [args.id_column] + input_columns

    if args.limit is not None:
        rows = rows[: args.limit]

    processed_ids = read_processed_ids(output_path, args.id_column) if args.resume else set()
    pending_rows = [
        row for row in rows
        if str(row.get(args.id_column, "")).strip() not in processed_ids
    ]
    output_columns, _ = ensure_output(output_path, input_columns)
    semaphore = asyncio.Semaphore(max(args.concurrency, 1))
    file_lock = asyncio.Lock()
    total = len(pending_rows)
    started_at = time.time()

    async def worker(index: int, row: dict[str, str]) -> None:
        async with semaphore:
            row_id = row.get(args.id_column, index)
            print(f"[{index}/{total}] optimizing id={row_id}", flush=True)
            result = await optimize_one(row, args)
            async with file_lock:
                with output_path.open("a", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=output_columns, extrasaction="ignore")
                    writer.writerow(result)
            if result.get("error"):
                print(f"[{index}/{total}] failed id={row_id}: {result['error']}", flush=True)
            else:
                print(f"[{index}/{total}] done id={row_id}", flush=True)

    await asyncio.gather(*(worker(i, row) for i, row in enumerate(pending_rows, start=1)))
    elapsed = time.time() - started_at
    print(f"completed: total={total}, output={output_path}, elapsed={elapsed:.1f}s", flush=True)


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run_batch(args))
        return 0
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
