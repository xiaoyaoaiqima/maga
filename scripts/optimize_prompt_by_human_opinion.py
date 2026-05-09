#!/usr/bin/env python3
"""
Global prompt optimizer from human feedback.

Reads a prompt TXT and a human-opinion/problem TXT, calls an OpenAI-compatible
chat completions API, and writes global prompt cleanup advice to stdout or JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://aihubmix.com/v1"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 8000
DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_OUTPUT_DIR = "prompt_optimize_results"


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    finish_reason: str
    usage: dict[str, Any]
    raw_response: dict[str, Any]


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


SYSTEM_PROMPT = """你是一个资深提示词架构师，擅长整理冗长、重复、矛盾的内容生成提示词。
你需要根据“原始提示词”和“人类优化意见”，从全局视角诊断提示词结构问题，并给出可执行的整理方案。

这个任务不是根据某一篇生成内容做局部修补，而是根据人类意见优化整份提示词。常见背景包括：
- 提示词太长，规则重复，模型注意力被分散。
- 不同章节存在同义重复、强弱不一致或互相矛盾。
- 上层规则和局部规则边界不清，导致执行优先级混乱。
- 禁止项、允许项、示例、卖点、结构要求混在一起，导致模型误读。
- 人类希望保留核心控制力，同时降低冗余和冲突。

优化原则：
- 以人类意见为最高依据；不要引入人类意见没有要求的新创作方向、新品牌规则或新内容策略。
- 优先做全局整理：去重、合并同义规则、消除矛盾、明确优先级、把规则放回更合适的章节。
- 不要为了简洁删除关键红线、品牌限制、合规限制、输入变量约束和必须完成的任务目标。
- 如果两条规则语义相同但强度不同，保留更清晰、更可执行的一条，并在 reason 中说明取舍。
- 如果两条规则冲突，优先保留更贴近任务目标、合规红线或人类意见的一条；不要简单并列保留。
- patches 应服务于全局结构整理，可以包含 delete、replace、insert_after、insert_before，但每个 patch 都必须能被人工直接定位。
- 同一处问题只输出一个 patch；不要用多个 patch 重复表达同一个整理意图。
- 如果需要大段重组，优先输出少量“replace 整段”的 patch，而不是很多碎片化 patch。
- 如果人类意见不足以支持直接修改，只在 risk_notes 或 modify_suggestion 中提示，不要写入 patches。

请只输出 JSON，不要输出 Markdown，不要解释 JSON 外的内容。
所有字段值都必须是合法 JSON 字符串；如果包含换行，请使用 \\n 转义，不要输出未转义的真实换行。
JSON 字段必须包含：
- prompt_issue: 从全局视角说明原提示词的主要问题。
- modify_suggestion: 具体整理策略，说明应该删什么、合并什么、保留什么。
- added_content: 建议新增到原提示词里的内容，只写新增片段；如果没有新增则返回空字符串。
- removed_content: 建议删除或弱化的原文片段摘要；如果没有删除则返回空字符串。
- patches: 数组，给出可直接人工替换的修改块。每个元素必须包含 operation、old_text、new_text、reason。
  - operation 只能是 replace、delete、insert_after、insert_before 之一。
  - old_text 必须是原提示词中可以直接搜索定位的连续原文片段；如果是新增，请填写插入位置附近的原文锚点。
  - new_text 是替换后或新增后的内容；如果是删除则返回空字符串。
  - reason 用一句话说明这条 patch 如何解决重复、矛盾、冗长或优先级问题。
- revised_prompt: 默认返回空字符串，不要输出完整修改后提示词，避免超长截断。
- risk_notes: 说明本次整理可能影响的约束或需要人工复核的点；如果没有则返回空字符串。
- confidence: 0 到 1 之间的小数，表示你对诊断的置信度。
"""


USER_PROMPT_TEMPLATE = """# 背景信息
## 原始提示词:
{prompt}

## 人类优化意见 / 问题描述:
{problem}

# 你的任务
请直接根据人类意见，从全局视角优化这份提示词。
重点检查重复、矛盾、冗长、规则散落、优先级不清、示例污染和局部规则覆盖全局规则等问题。"""


def parse_args() -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Read prompt/problem TXT files and globally optimize a prompt from human feedback.",
    )
    parser.add_argument("--prompt-file", required=True, help="TXT file containing the prompt to optimize.")
    parser.add_argument("--problem-file", required=True, help="TXT file containing human feedback/opinion.")
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


def build_user_prompt(prompt: str, problem: str, include_revised_prompt: bool) -> str:
    user_prompt = USER_PROMPT_TEMPLATE.format(prompt=prompt, problem=problem)
    if include_revised_prompt:
        return (
            user_prompt
            + "\n\n# 输出要求补充\n"
            + "可以输出完整 revised_prompt，但必须保证 JSON 完整闭合。"
            + "即使输出完整 revised_prompt，也必须输出 patches 数组，便于人工定位关键改动。"
        )
    return (
        user_prompt
        + "\n\n# 输出要求补充\n"
        + "不要输出完整 revised_prompt，请将 revised_prompt 返回为空字符串。"
        + "请重点输出 patches 数组，优先给出少量高价值的全局整理 patch。"
        + "如果不能找到可直接搜索的原文片段，不要编造 old_text，请选择最接近的原文锚点并使用 insert_after 或 insert_before。"
        + "输出 patches 前先做一次去重检查：同一根因、同一整理意图只保留一个 patch。"
    )


def normalize_chat_completions_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return f"{value}/chat/completions"
    return value


def build_chat_payload(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    token_param = "max_completion_tokens" if model.lower().startswith("gpt-5") else "max_tokens"
    payload[token_param] = max_tokens
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def read_http_error(error: urllib.error.HTTPError) -> str:
    body = error.read().decode("utf-8", errors="replace").strip()
    if body:
        return f"HTTP {error.code}: {body}"
    return f"HTTP {error.code}: {error.reason}"


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
) -> ChatCompletionResult:
    payload = build_chat_payload(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )

    req = urllib.request.Request(
        normalize_chat_completions_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ValueError(read_http_error(e)) from e
    result = json.loads(raw)
    choices = result.get("choices") or [{}]
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    return ChatCompletionResult(
        content=(message.get("content") or "").strip(),
        finish_reason=str(choice.get("finish_reason") or ""),
        usage=usage,
        raw_response=result,
    )


def build_empty_content_error(completion: ChatCompletionResult) -> str:
    usage_text = json.dumps(completion.usage, ensure_ascii=False)
    return (
        "模型返回了空 content，无法解析 JSON。"
        f"finish_reason={completion.finish_reason or 'unknown'}，usage={usage_text}。"
        "如果 finish_reason=length 且 reasoning_tokens 接近 max_tokens，"
        "请提高 --max-tokens，或缩短输入提示词。"
    )


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
    parsed.setdefault("risk_notes", "")
    parsed.setdefault("confidence", "")
    patches = parsed.get("patches")
    if not isinstance(patches, list):
        parsed["patches"] = []
    return parsed


def format_multiline_value(value: Any, indent: str = "  ") -> list[str]:
    text = str(value)
    if "\n" not in text:
        return [text]
    lines = ["|"]
    for line in text.splitlines():
        lines.append(f"{indent}{line}")
    return lines


def format_result_for_console(result: dict[str, Any]) -> str:
    """Render parsed JSON as copy-friendly text without JSON quote escaping."""
    lines: list[str] = []
    scalar_fields = (
        "prompt_issue",
        "modify_suggestion",
        "added_content",
        "removed_content",
        "revised_prompt",
        "risk_notes",
        "confidence",
    )
    for field in scalar_fields:
        values = format_multiline_value(result.get(field, ""), indent="  ")
        if len(values) == 1:
            lines.append(f"{field}: {values[0]}")
        else:
            lines.append(f"{field}: {values[0]}")
            lines.extend(values[1:])

    for field in ("parse_error", "raw_output"):
        if field in result:
            values = format_multiline_value(result.get(field, ""), indent="  ")
            if len(values) == 1:
                lines.append(f"{field}: {values[0]}")
            else:
                lines.append(f"{field}: {values[0]}")
                lines.extend(values[1:])

    patches = result.get("patches")
    lines.append("patches:")
    if not isinstance(patches, list) or not patches:
        lines.append("  []")
        return "\n".join(lines)

    for index, patch in enumerate(patches, start=1):
        if not isinstance(patch, dict):
            lines.append(f"  - #{index}: {patch}")
            continue
        lines.append(f"  - #{index}")
        for field in ("operation", "old_text", "new_text", "reason"):
            values = format_multiline_value(patch.get(field, ""), indent="      ")
            if len(values) == 1:
                lines.append(f"    {field}: {values[0]}")
            else:
                lines.append(f"    {field}: {values[0]}")
                lines.extend(values[1:])
    return "\n".join(lines)


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
    debug_path = debug_dir / f"human_prompt_optimize_debug_{run_id}.json"
    payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "problem": problem,
        "input_files": {
            "prompt_file": str(Path(args.prompt_file)),
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


def append_debug_response_summary(debug_path: Path, completion: ChatCompletionResult) -> None:
    payload = json.loads(debug_path.read_text(encoding="utf-8"))
    # 只记录响应摘要，避免把完整模型输出写进 debug 日志造成文件过大。
    payload["response_summary"] = {
        "finish_reason": completion.finish_reason,
        "content_length": len(completion.content),
        "usage": completion.usage,
        "raw_response_id": completion.raw_response.get("id"),
        "raw_response_model": completion.raw_response.get("model"),
    }
    debug_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    try:
        if not args.api_key:
            raise ValueError("未配置 API Key，请设置 OPENAI_API_KEY / AIHUBMIX_API_KEY，或传入 --api-key")

        prompt = read_required_text(Path(args.prompt_file), "prompt")
        problem = read_required_text(Path(args.problem_file), "problem")
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_prompt = build_user_prompt(prompt, problem, args.include_revised_prompt)
        debug_path = write_debug_log(
            debug_dir=Path(args.debug_dir),
            run_id=run_id,
            args=args,
            problem=problem,
            user_prompt=user_prompt,
        )
        completion = call_openai_compatible(
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
        append_debug_response_summary(debug_path, completion)
        raw_output = completion.content
        if not raw_output:
            raise ValueError(f"{build_empty_content_error(completion)} debug log written: {debug_path}")
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
                "risk_notes": "",
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
            print(format_result_for_console(parsed))
            print(f"debug log written: {debug_path}", file=sys.stderr)
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
