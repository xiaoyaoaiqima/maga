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


DEFAULT_BASE_URL = "https://aihubmix.com/v1"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 3000
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_OUTPUT_DIR = "prompt_optimize_results"
DEFAULT_NEW_PROMPT_OUTPUT = "local_data/new_prompt.txt"
DEFAULT_NEW_CONTENT_OUTPUT = "local_data/new_content.txt"
DEFAULT_GENERATION_MODEL = "deepseek-chat"
DEFAULT_GENERATION_BASE_URL = "https://api.deepseek.com"
DEFAULT_GENERATION_TEMPERATURE = 0.7
DEFAULT_GENERATION_MAX_TOKENS = 3000


GENERATION_SYSTEM_PROMPT = """你是一个专业的小红书内容创作者。
请严格按照用户提供的生文提示词执行，只输出生成正文，不要解释过程。"""


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
- 先判断问题边界：如果问题只涉及某个固定句式、表达方式、场景或论证缺口，只修补这个边界，不要额外禁止相关关键词在其他合理语境中出现。
- 对单篇 badcase 的局部问题，优先把“生成原文 + 具体问题”写成提示词中的反例/违规示例，不要改写成“可能让读者困惑、不符合常识”等抽象禁令。
- 如果原提示词已有相近的违规示例或反例位置，优先在该位置补充一条具体 badcase，格式必须包含原文和问题，例如：`- 违规示例：`原文片段`\n- 问题：具体说明这句为什么不成立/不可理解/会误导`。
- 修改前必须检索原提示词中的同义、近义、上位和下位规则；已有规则能承载本次要求时，优先 replace 那条已有规则，让它更清晰或更可执行，不要新增同义规则。
- 新增规则是最后手段；只有原提示词没有可承载要求的规则，且新增内容不与现有规则冲突时，才允许 insert_after 或 insert_before。
- 输出 patch 前必须做冲突扫描：检查 new_text 是否会和原提示词中的任务目标、合规红线、允许表达、结构要求或示例发生矛盾；如果会矛盾，优先修改或删除冲突原文，不要简单并列新增相反规则。
- 默认只输出 1 个最小 patch；只有运营审查问题明确包含多个彼此独立根因，才输出多个 patches。
- 不要把同一要求同时写进总规则和子规则，也不要同时 replace 两段来表达同一个修改意图。
- 如果需要增强一条已有要求，优先修改最贴近生成失败位置的局部规则；只有当局部规则缺失时，才修改更上层的总规则。
- 若运营审查问题指向“同质化、模板化、固定句式复用”，优先把原规则里的模板短语库、固定推荐句式改成“可变化维度 + 禁用固定套话”的生成约束；不要继续追加更多同类示例句或可选短语。
- 对结尾权益、福利、礼包类规则，patch 必须同时保留业务边界和表达多样性：明确权益触发动作、权益位置、福利感表达和句式结构中至少变化 2 处；禁止把“安排上 / 解锁 / 诚意很足 / 实用又惊喜”等促销套话写成推荐表达。
- 如果某条建议属于“可能有帮助但证据不足”，不要写入 added_content 或 patches，只在 modify_suggestion 中弱提示。

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
  - reason 用一句话说明为什么这样改，并说明它为什么不是重复规则或冲突规则。
  - patches 之间不得语义重复；如果两个 patch 的 new_text 在解决同一件事，只保留更贴近问题位置、改动更小的一个。
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
    parser.add_argument(
        "--new-prompt-output",
        default=DEFAULT_NEW_PROMPT_OUTPUT,
        help=f"Path for the patch-applied prompt TXT. Defaults to {DEFAULT_NEW_PROMPT_OUTPUT}.",
    )
    parser.add_argument(
        "--new-content-output",
        default=DEFAULT_NEW_CONTENT_OUTPUT,
        help=f"Path for one generated content sample using the new prompt. Defaults to {DEFAULT_NEW_CONTENT_OUTPUT}.",
    )
    parser.add_argument(
        "--skip-generate-new-content",
        action="store_true",
        help="Only write the optimized prompt, do not call a model to generate new content.",
    )
    parser.add_argument(
        "--generation-model",
        default=os.getenv("DEEPSEEK_MODEL", DEFAULT_GENERATION_MODEL),
        help=f"Model used to generate new content. Defaults to {DEFAULT_GENERATION_MODEL}.",
    )
    parser.add_argument(
        "--generation-base-url",
        default=(
            os.getenv("DEEPSEEK_API_BASE")
            or os.getenv("DEEPSEEK_BASE_URL")
            or DEFAULT_GENERATION_BASE_URL
        ),
        help=f"OpenAI-compatible base URL for new content generation. Defaults to {DEFAULT_GENERATION_BASE_URL}.",
    )
    parser.add_argument(
        "--generation-api-key",
        default=os.getenv("DEEPSEEK_API_KEY"),
        help="API key for new content generation. Defaults to DEEPSEEK_API_KEY; falls back to --api-key.",
    )
    parser.add_argument("--generation-temperature", type=float, default=DEFAULT_GENERATION_TEMPERATURE)
    parser.add_argument("--generation-max-tokens", type=int, default=DEFAULT_GENERATION_MAX_TOKENS)
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
        + "输出 patches 前按顺序自检：是否已有同义规则可改、是否与现有规则冲突、是否还能用更少规则完成。"
        + "如果自检后发现证据不足或会制造冲突，请不要输出 patch，只在 modify_suggestion 中说明。"
    )


def normalize_chat_completions_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return f"{value}/chat/completions"
    return f"{value}/v1/chat/completions"


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
) -> str:
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


def apply_patch_operation(prompt: str, patch: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    operation = str(patch.get("operation", "")).strip()
    old_text = str(patch.get("old_text", ""))
    new_text = str(patch.get("new_text", ""))
    summary = {
        "operation": operation,
        "old_text": old_text,
        "applied": False,
        "error": "",
    }
    if operation not in {"replace", "delete", "insert_after", "insert_before"}:
        summary["error"] = f"不支持的 operation: {operation}"
        return prompt, summary
    if not old_text:
        summary["error"] = "old_text 为空，无法定位"
        return prompt, summary
    if old_text not in prompt:
        summary["error"] = "old_text 未在原提示词中找到"
        return prompt, summary

    # 只改第一个精确命中的锚点，避免同一段文本重复出现时误伤后续规则。
    if operation == "replace":
        updated = prompt.replace(old_text, new_text, 1)
    elif operation == "delete":
        updated = prompt.replace(old_text, "", 1)
    elif operation == "insert_after":
        updated = prompt.replace(old_text, f"{old_text}\n{new_text}", 1)
    else:
        updated = prompt.replace(old_text, f"{new_text}\n{old_text}", 1)
    summary["applied"] = True
    return updated, summary


def build_revised_prompt(prompt: str, parsed: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    revised_prompt = str(parsed.get("revised_prompt") or "").strip()
    if revised_prompt:
        return revised_prompt, [
            {
                "operation": "revised_prompt",
                "old_text": "",
                "applied": True,
                "error": "",
            }
        ]

    updated = prompt
    summaries: list[dict[str, Any]] = []
    patches = parsed.get("patches")
    if not isinstance(patches, list):
        return updated, summaries
    for patch in patches:
        if not isinstance(patch, dict):
            summaries.append(
                {
                    "operation": "",
                    "old_text": "",
                    "applied": False,
                    "error": "patch 不是 JSON object",
                }
            )
            continue
        updated, summary = apply_patch_operation(updated, patch)
        summaries.append(summary)
    return updated.strip(), summaries


def write_text_output(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


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
        "confidence",
    )
    for field in scalar_fields:
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
        new_prompt, patch_apply_results = build_revised_prompt(prompt, parsed)
        new_prompt_path = write_text_output(Path(args.new_prompt_output), new_prompt)
        parsed["new_prompt_path"] = str(new_prompt_path)
        parsed["patch_apply_results"] = patch_apply_results

        if not args.skip_generate_new_content:
            generation_api_key = args.generation_api_key or args.api_key
            if not generation_api_key:
                raise ValueError("未配置 DeepSeek API Key，请设置 DEEPSEEK_API_KEY，或传入 --generation-api-key")
            new_content = call_openai_compatible(
                api_key=generation_api_key,
                base_url=args.generation_base_url,
                model=args.generation_model,
                system_prompt=GENERATION_SYSTEM_PROMPT,
                user_prompt=new_prompt,
                temperature=args.generation_temperature,
                max_tokens=args.generation_max_tokens,
                timeout=args.timeout,
                json_mode=False,
            )
            new_content_path = write_text_output(Path(args.new_content_output), new_content)
            parsed["new_content_path"] = str(new_content_path)
            parsed["generation_model_params"] = {
                "base_url": normalize_chat_completions_url(args.generation_base_url),
                "model": args.generation_model,
                "temperature": args.generation_temperature,
                "max_tokens": args.generation_max_tokens,
                "timeout": args.timeout,
            }
        output = json.dumps(parsed, ensure_ascii=False, indent=2)

        if args.output:
            output_path = resolve_output_path(args.output, args.output_dir, run_id)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output + "\n", encoding="utf-8")
            print(f"output written: {output_path}")
            print(f"debug log written: {debug_path}")
            print(f"new prompt written: {new_prompt_path}")
            if parsed.get("new_content_path"):
                print(f"new content written: {parsed['new_content_path']}")
        else:
            print(format_result_for_console(parsed))
            print(f"new_prompt_path: {new_prompt_path}")
            if parsed.get("new_content_path"):
                print(f"new_content_path: {parsed['new_content_path']}")
            print(f"debug log written: {debug_path}", file=sys.stderr)
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
