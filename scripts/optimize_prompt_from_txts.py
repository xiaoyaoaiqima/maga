#!/usr/bin/env python3
"""
Single prompt optimizer MVP.

Reads prompt/content/problem from three TXT files, calls an OpenAI-compatible
chat completions API, and writes prompt optimization advice to stdout or a file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 3000
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_OUTPUT_DIR = "prompt_optimize_results"


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


SYSTEM_PROMPT = """你是一个资深小红书内容生产与提示词优化专家。
你需要根据原始生文提示词、生成结果和运营审查问题，反推出提示词设计上的缺陷，并给出可执行的修改方案。
优先修改规则指令，尽量不修改痛点描述/卖点描述这类纯描述类提示词。

优化原则：
- 只提出能被“生成结果 + 运营审查问题”直接支持的最小必要修改，避免把单个问题扩展成更宽、更硬的禁令。
- 禁止过度泛化：如果问题是某个固定句式或表达方式违规，只禁止该句式/表达方式，不要额外禁止关键词在其他合理语境中出现。
- 不要新增位置类、开场类、结构类限制，除非运营审查问题明确指出位置、开场或结构本身有问题。
- 新增规则应尽量贴近原提示词已有规则的颗粒度，一次只解决当前证据能解释的问题。
- 如果某条建议属于“可能有帮助但证据不足”，不要写入 added_content 或 patches，可在 modify_suggestion 中弱提示。

请只输出 JSON，不要输出 Markdown，不要解释 JSON 外的内容。
所有字段值都必须是合法 JSON 字符串；如果包含换行，请使用 \\n 转义，不要输出未转义的真实换行。
JSON 字段必须包含：
- prompt_issue: 原提示词的问题在哪里
- modify_suggestion: 应该怎么修改，要求具体可执行
- added_content: 建议新增到原提示词里的内容，只写新增片段；如果没有新增则返回空字符串
- removed_content: 建议从原提示词中删除或弱化的内容，只写删除片段；如果没有删除则返回空字符串
- patches: 数组，给出可直接人工替换的修改块。每个元素必须包含 operation、old_text、new_text、reason。
  - operation 只能是 replace、delete、insert_after、insert_before 之一。
  - old_text 必须是原提示词中可以直接搜索定位的连续原文片段；如果是新增，请填写插入位置附近的原文锚点。
  - new_text 是替换后或新增后的内容；如果是删除则返回空字符串。
  - reason 用一句话说明为什么这样改。
- revised_prompt: 默认返回空字符串，不要输出完整修改后提示词，避免超长截断
- confidence: 0 到 1 之间的小数，表示你对诊断的置信度
"""


USER_PROMPT_TEMPLATE = """# 背景信息
## 生文用到的提示词:
{prompt}

## 生成的内容：
{content}

## 运营审查发现的问题：
{problem}

# 你的任务
输出生文提示词的问题在哪里，怎么修改。"""


def parse_args() -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Read prompt/content/problem TXT files and optimize the generation prompt.",
    )
    parser.add_argument("--prompt-file", required=True, help="TXT file containing the generation prompt.")
    parser.add_argument("--content-file", required=True, help="TXT file containing generated content.")
    parser.add_argument("--problem-file", required=True, help="TXT file containing operation review problems.")
    parser.add_argument("--output", help="Optional output JSON filename/path. If omitted, prints to stdout.")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for result JSON files. Defaults to {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--debug-dir",
        default="debug_log",
        help="Directory for model input debug logs. Defaults to debug_log.",
    )
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
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--include-revised-prompt",
        action="store_true",
        help="Ask the model to output a full revised prompt. Disabled by default to avoid truncation.",
    )
    return parser.parse_args()


def read_required_text(path: Path, label: str) -> str:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError(f"{label} 文件为空: {path}")
    return text


def build_user_prompt(prompt: str, content: str, problem: str, include_revised_prompt: bool) -> str:
    user_prompt = USER_PROMPT_TEMPLATE.format(
        prompt=prompt,
        content=content,
        problem=problem,
    )
    if include_revised_prompt:
        return (
            user_prompt
        + "\n\n# 输出要求补充\n"
        + "可以输出完整 revised_prompt，但必须保证 JSON 完整闭合。"
        + "同时必须输出 patches 数组，便于人工定位替换。"
    )
    return (
        user_prompt
        + "\n\n# 输出要求补充\n"
        + "不要输出完整 revised_prompt，请将 revised_prompt 返回为空字符串。"
        + "请重点输出 patches 数组，便于人工按 old_text 搜索定位并替换。"
        + "如果不能找到可直接搜索的原文片段，不要编造 old_text，请选择最接近的原文锚点并使用 insert_after 或 insert_before。"
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

    req = urllib.request.Request(
        normalize_chat_completions_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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


def normalize_result(parsed: dict[str, Any]) -> dict[str, Any]:
    parsed.setdefault("prompt_issue", "")
    parsed.setdefault("modify_suggestion", "")
    parsed.setdefault("added_content", "")
    parsed.setdefault("removed_content", "")
    parsed.setdefault("revised_prompt", "")
    parsed.setdefault("confidence", "")
    patches = parsed.get("patches")
    if not isinstance(patches, list):
        parsed["patches"] = []
    return parsed


def with_timestamp_suffix(path: Path, run_id: str) -> Path:
    return path.with_name(f"{path.stem}_{run_id}{path.suffix}")


def resolve_output_path(output: str, output_dir: str, run_id: str) -> Path:
    raw_path = Path(output)
    if raw_path.parent == Path(".") or raw_path.parts[:1] == ("local_data",):
        raw_path = Path(output_dir) / raw_path.name
    return with_timestamp_suffix(raw_path, run_id)


def write_debug_log(
    *,
    debug_dir: Path,
    run_id: str,
    args: argparse.Namespace,
    problem: str,
    user_prompt: str,
) -> Path:
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / f"prompt_optimize_debug_{run_id}.json"
    payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "problem": problem,
        "input_files": {
            "prompt_file": str(Path(args.prompt_file)),
            "content_file": str(Path(args.content_file)),
            "problem_file": str(Path(args.problem_file)),
        },
        "model_params": {
            "base_url": normalize_chat_completions_url(args.base_url),
            "model": args.model,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "timeout": args.timeout,
            "json_mode": not args.no_json_mode,
        },
        "request_messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    debug_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return debug_path


def main() -> int:
    args = parse_args()
    try:
        if not args.api_key:
            raise ValueError("未配置 API Key，请设置 OPENAI_API_KEY / AIHUBMIX_API_KEY，或传入 --api-key")

        prompt = read_required_text(Path(args.prompt_file), "prompt")
        content = read_required_text(Path(args.content_file), "content")
        problem = read_required_text(Path(args.problem_file), "problem")
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_prompt = build_user_prompt(prompt, content, problem, args.include_revised_prompt)
        debug_path = write_debug_log(
            debug_dir=Path(args.debug_dir),
            run_id=run_id,
            args=args,
            problem=problem,
            user_prompt=user_prompt,
        )
        raw_output = call_openai_compatible(
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
        try:
            parsed = normalize_result(extract_json_object(raw_output))
        except (json.JSONDecodeError, ValueError) as e:
            parsed = {
                "prompt_issue": "",
                "modify_suggestion": "",
                "added_content": "",
                "removed_content": "",
                "patches": [],
                "revised_prompt": "",
                "confidence": "",
                "raw_output": raw_output,
                "parse_error": f"{type(e).__name__}: {e}",
            }
        output = json.dumps(parsed, ensure_ascii=False, indent=2)

        if args.output:
            output_path = resolve_output_path(args.output, args.output_dir, run_id)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output + "\n", encoding="utf-8")
            print(f"output written: {output_path}")
            print(f"debug log written: {debug_path}")
        else:
            print(output)
            print(f"debug log written: {debug_path}", file=sys.stderr)
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
