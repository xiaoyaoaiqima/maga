#!/usr/bin/env python3
"""Run local comment generation smoke through maga-worker /invoke."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEYWORD_CSV = ROOT / "关键词语料/系统提示词关键词_评论联调.csv"
DEFAULT_COMMENT_ANGLE_CSV = ROOT / "关键词语料/评论切角_子关键词导出.csv"
DEFAULT_WORKER_URL = "http://127.0.0.1:8765/invoke"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke local comment keyword assets with maga-worker.")
    parser.add_argument("--keyword-csv", type=Path, default=DEFAULT_KEYWORD_CSV)
    parser.add_argument("--comment-angle-csv", type=Path, default=DEFAULT_COMMENT_ANGLE_CSV)
    parser.add_argument("--worker-url", default=os.environ.get("MAGA_WORKER_INVOKE_URL_LOCAL", DEFAULT_WORKER_URL))
    parser.add_argument("--targets", nargs="+", default=["便便问题", "消化吸收", "生长发育"])
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--print-prompt", action="store_true", help="Print the rendered prompt instead of invoking worker.")
    args = parser.parse_args()

    selected_keywords = load_selected_keywords(args.keyword_csv)
    rules = load_comment_angle_rows(args.comment_angle_csv)
    results = []
    for index, target in enumerate(args.targets, start=1):
        rule = next((row for row in rules if target in row.get("评论切角", "")), None)
        if not rule:
            results.append({"target": target, "error": "missing_comment_angle"})
            continue
        input_snapshot = build_input_snapshot(rule, selected_keywords, index)
        if args.print_prompt:
            results.append(
                {
                    "target": target,
                    "rendered_prompt": input_snapshot["rendered_prompt"],
                }
            )
            continue
        response = invoke_worker(args.worker_url, input_snapshot, index, timeout=args.timeout)
        results.append({"target": target, **response})

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def load_selected_keywords(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    keywords_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["类别Code"], row["子关键词Code"])
        keyword = keywords_by_key.setdefault(
            key,
            {
                "category_code": row["类别Code"],
                "category_name": row["类别名称"],
                "keyword_code": row["子关键词Code"],
                "keyword_name": row["子关键词名称"],
                "corpus": [],
            },
        )
        corpus = row["语料"].strip()
        if corpus and corpus not in keyword["corpus"]:
            keyword["corpus"].append(corpus)
    return list(keywords_by_key.values())


def load_comment_angle_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig") as f:
        content = "".join(line for line in f if not line.startswith("#"))
    return list(csv.DictReader(io.StringIO(content)))


def build_input_snapshot(rule: dict[str, str], selected_keywords: list[dict[str, Any]], index: int) -> dict[str, Any]:
    business_rule = {
        "rule_type": "comment_angle",
        "product_topic": "美素佳儿源悦活动评论",
        "comment_angle": rule["评论切角"],
        "corpus": rule["语料"],
        "examples": examples_from_corpus(rule["语料"]),
        "asset_key": "yuanyue_comment_activity",
        "rule_id": f"local_smoke_{index}",
    }
    return {
        "schema_version": "1",
        "capability": "content.generate",
        "content_type": "comment",
        "output_fields": ["comment"],
        "business_rule": business_rule,
        "selected_keywords": selected_keywords,
        "expert": {
            "expert_config_code": "comment_generator_v1",
            "expert_config_name": "评论生成 Expert",
            "expert_type": "GENERATION",
            "source": "local_smoke",
        },
        "model_config": {
            "temperature": 0.85,
            "max_tokens": 256,
            "system_prompt": "你是中文小红书母婴评论生成器。必须输出非空的一条评论正文，不解释过程。",
        },
        "rendered_prompt": render_prompt(business_rule, selected_keywords),
    }


def examples_from_corpus(corpus: str) -> list[str]:
    if "示例" not in corpus:
        return []
    parts = re.split(r"示例[:：]", corpus, maxsplit=1)
    if len(parts) < 2:
        return []
    body = re.split(r"\n\s*注意[:：]", parts[1], maxsplit=1)[0]
    examples = []
    for line in body.splitlines():
        item = re.sub(r"^[\-\*•]\s*", "", line.strip())
        item = re.sub(r"^\d+[、.．]\s*", "", item).strip()
        if item:
            examples.append(item)
    return examples


def render_prompt(business_rule: dict[str, Any], selected_keywords: list[dict[str, Any]]) -> str:
    return (
        "你是小红书母婴评论生成 expert。\n"
        "请根据业务规则和系统内置关键词语料，生成一条自然评论。\n\n"
        "【业务规则】\n"
        f"{business_rule_text(business_rule)}\n\n"
        "【本次自动选中的系统关键词语料】\n"
        f"{keyword_corpus_text(selected_keywords)}\n\n"
        "【生成要求】\n"
        "只输出一条自然评论正文；像真实评论区，不要标题、编号、解释；"
        "可以借鉴示例的语义方向，但不要照搬原句；不承诺解决所有问题，不做医疗化诊断。"
    )


def business_rule_text(rule: dict[str, Any]) -> str:
    lines = [
        "- 规则类型：comment_angle",
        "- 主题：美素佳儿源悦活动评论",
        f"- 评论切角：{rule['comment_angle']}",
        f"- 业务语料：\n{rule['corpus']}",
    ]
    examples = [str(item).strip() for item in rule.get("examples") or [] if str(item).strip()]
    if examples:
        lines.append("- 参考示例：\n" + "\n".join(f"  - {item}" for item in examples[:8]))
    return "\n".join(lines)


def keyword_corpus_text(selected_keywords: list[dict[str, Any]]) -> str:
    parts = []
    for item in selected_keywords:
        corpus_text = "\n".join(f"  - {line}" for line in item.get("corpus") or [])
        parts.append(f"- {item['category_name']} / {item['keyword_name']}：\n{corpus_text}")
    return "\n".join(parts)


def invoke_worker(worker_url: str, input_snapshot: dict[str, Any], index: int, *, timeout: float) -> dict[str, Any]:
    envelope = {
        "protocol_version": "0.1",
        "run_id": f"local-smoke-{index}",
        "task_id": f"local-smoke-{index}",
        "stage_call_id": f"local-smoke-{index}-generate",
        "capability": "content.generate",
        "executor_hints": {"source": "codex-local-smoke"},
        "input": input_snapshot,
    }
    request = urllib.request.Request(
        worker_url,
        data=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Maga-Protocol-Version": "0.1",
            "Authorization": f"Bearer {os.environ.get('MAGA_WORKER_EXECUTOR_TOKEN', 'test-token')}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "error": "HTTPError",
            "status": exc.code,
            "body": exc.read().decode("utf-8", errors="replace"),
        }
    except Exception as exc:  # noqa: BLE001 - smoke should report provider/runtime errors.
        return {
            "error": type(exc).__name__,
            "body": str(exc),
        }


if __name__ == "__main__":
    raise SystemExit(main())
