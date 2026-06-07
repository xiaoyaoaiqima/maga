#!/usr/bin/env python3
"""
Missed issue critic prompt optimizer.

Reads content/prompt/problem from three TXT files:
- content: original article body that passed or was not flagged correctly
- prompt: critic prompt to optimize
- problem: human-described issue that should have been caught
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from datetime import datetime
from pathlib import Path

from optimize_critic_prompt_from_txts import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    call_openai_compatible,
    extract_json_object,
    load_dotenv,
    normalize_chat_completions_url,
    normalize_result,
    read_required_text,
    resolve_output_path,
)


DEFAULT_OUTPUT_DIR = "critic_missed_issue_optimize_results"
DEFAULT_DEBUG_DIR = "critic_missed_issue_debug_log"


SYSTEM_PROMPT = """你是一个资深内容审核规则与提示词优化专家。
你需要根据正文、原始审核提示词和人类指出的漏审问题，反推出审核提示词为什么没有把问题审核出来，并给出可直接执行的修改方案。

输入约定：
- content 是正文原文，不包含模型审核结果。
- prompt 是原始审核提示词。
- problem 是人类指出“应该审核出来但没有审核出来”的问题。

优化原则：
- 这是漏审修复，不是误判修复；重点补充必要判定条件、证据要求、problem_context_list 定位要求和可验证触发条件。
- 只提出能被“正文 + 漏审问题”直接支持的最小必要修改，不要把单个 badcase 扩展成更宽的禁令。
- 如果原审核提示词已有相近规则，优先 replace 那条规则，让它更清晰、更可执行；不要重复新增同义规则。
- 如果原审核提示词缺少对应规则，优先在最相近章节补充一条具体规则，并写清楚：触发条件、必须命中的原文证据、违规原因表达方式。
- 对单篇 badcase 的局部漏审，优先把“正文原文 + 人类指出的问题”写成审核提示词中的违规示例/漏审示例，不要改写成抽象泛化规则。
- patch 必须服务于提高召回，不能为了召回而放宽证据要求到语义联想或模糊相似。
- 默认只输出 1 个最小 patch；只有漏审问题明确包含多个彼此独立根因，才输出多个 patches。

请只输出 JSON，不要输出 Markdown，不要解释 JSON 外的内容。
所有字段值都必须是合法 JSON 字符串；如果包含换行，请使用 \\n 转义，不要输出未转义的真实换行。
JSON 字段必须包含：
- prompt_issue: 原审核提示词为什么漏审
- modify_suggestion: 应该怎么修改，要求具体可执行
- added_content: 建议新增到原审核提示词里的内容，只写新增片段；如果没有新增则返回空字符串
- removed_content: 建议从原审核提示词中删除或弱化的内容，只写删除片段；如果没有删除则返回空字符串
- patches: 数组，给出可直接人工替换的修改块。每个元素必须包含 operation、old_text、new_text、reason。
  - operation 只能是 replace、delete、insert_after、insert_before 之一。
  - old_text 必须是原审核提示词中可以直接搜索定位的连续原文片段；如果是新增，请填写插入位置附近的原文锚点。
  - new_text 是替换后或新增后的内容；如果是删除则返回空字符串。
  - reason 用一句话说明为什么这样改能修复漏审，并说明它为什么不是重复规则或冲突规则。
- revised_prompt: 默认返回空字符串，不要输出完整修改后审核提示词，避免超长截断
- confidence: 0 到 1 之间的小数，表示你对诊断的置信度
"""


USER_PROMPT_TEMPLATE = """# 背景信息
## 正文原文:
{content}

## 原始审核提示词:
{prompt}

## 人类指出的漏审问题:
{problem}

# 你的任务
输出审核提示词为什么没有审核出这个问题，以及应该怎么修改审核提示词。"""


def parse_args() -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Read content/prompt/problem TXT files and optimize a critic prompt for missed issues.",
    )
    parser.add_argument("--content-file", required=True, help="TXT file containing the original article body.")
    parser.add_argument("--prompt-file", required=True, help="TXT file containing the critic prompt.")
    parser.add_argument("--problem-file", required=True, help="TXT file containing the missed issue description.")
    parser.add_argument("--output", help="Optional output JSON filename/path. If omitted, prints to stdout.")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for result JSON files. Defaults to {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--debug-dir",
        default=DEFAULT_DEBUG_DIR,
        help=f"Directory for model input debug logs. Defaults to {DEFAULT_DEBUG_DIR}.",
    )
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL), help="Model name.")
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


def build_user_prompt(content: str, prompt: str, problem: str, include_revised_prompt: bool) -> str:
    user_prompt = USER_PROMPT_TEMPLATE.format(content=content, prompt=prompt, problem=problem)
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
        + "输出 patches 前按顺序自检：是否已有同义规则可改、是否能修复漏审、是否会造成过度召回。"
    )


def write_debug_log(
    *,
    debug_dir: Path,
    run_id: str,
    args: argparse.Namespace,
    problem: str,
    user_prompt: str,
) -> Path:
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / f"critic_missed_issue_optimize_debug_{run_id}.json"
    payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "problem": problem,
        "input_files": {
            "content_file": str(Path(args.content_file)),
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
    debug_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return debug_path


def main() -> int:
    args = parse_args()
    try:
        if not args.api_key:
            raise ValueError("未配置 API Key，请设置 OPENAI_API_KEY / AIHUBMIX_API_KEY，或传入 --api-key")

        content = read_required_text(Path(args.content_file), "content")
        prompt = read_required_text(Path(args.prompt_file), "prompt")
        problem = read_required_text(Path(args.problem_file), "problem")
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_prompt = build_user_prompt(content, prompt, problem, args.include_revised_prompt)
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
