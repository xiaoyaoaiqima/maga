"""MAGA -> Executor protocol v0.1 invocation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
import re
import time
from typing import Any

import httpx

from app.utils.model_config import ensure_chat_completions_endpoint, normalize_default_model

PROTOCOL_VERSION = "0.1"
DIRECT_LLM_INVOKE_SCHEMES = ("llm://", "direct://")
DIRECT_LLM_DEFAULT_BASE_URL = "https://aihubmix.com/v1"


@dataclass(frozen=True)
class InvokeResult:
    """Normalized result of calling an executor /invoke endpoint."""

    mode: str
    stage_call_id: str
    status: str = "succeeded"
    output: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_invoke_envelope(
    *,
    run_id: int,
    task_id: int,
    stage_call_id: str,
    capability: str,
    schema_version: str,
    run_token: str,
    input_payload: dict[str, Any],
    callback_base_url: str,
    deadline_at: datetime | None,
) -> dict[str, Any]:
    """Build the protocol v0.1 invocation envelope sent from MAGA to Executor."""
    callback_base = callback_base_url.rstrip("/")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "task_id": task_id,
        "stage_call_id": stage_call_id,
        "capability": capability,
        "schema_version": schema_version,
        "deadline_at": _iso_or_none(deadline_at),
        "executor_hints": {"timeout_seconds": 60},
        "input": input_payload or {},
        "callback": {
            "events_url": f"{callback_base}/runs/{run_id}/events",
            "artifacts_url": f"{callback_base}/runs/{run_id}/artifacts",
            "human_review_url": f"{callback_base}/runs/{run_id}/human-review",
        },
    }


class MockExecutorInvocationClient:
    """Local deterministic mock for early API smoke before Hermes /invoke exists."""

    async def invoke(self, *, invoke_url: str, envelope: dict[str, Any], executor_token: str | None = None) -> InvokeResult:
        input_payload = envelope.get("input") or {}
        capability = envelope.get("capability")
        output: dict[str, Any]
        if capability == "asset.import":
            asset_key = input_payload.get("asset_key") or "yuanyue"
            source_hash = input_payload.get("source_hash") or "mock-source-hash"
            output = {
                "asset_key": asset_key,
                "source_hash": source_hash,
                "warnings": ["mock asset.import output; start real maga-worker for workbook parsing"],
                "assets": [
                    {
                        "asset_type": "brand_profile",
                        "asset_key": asset_key,
                        "display_name": "源悦品牌资料",
                        "content_json": {
                            "brand_key": asset_key,
                            "brand_name": "源悦",
                            "content_focus": "好消化易吸收，对应便便好，不上火",
                            "content_style": "高质量真实用户ugc",
                        },
                    },
                    {
                        "asset_type": "product_selling_points",
                        "asset_key": asset_key,
                        "display_name": "源悦产品卖点",
                        "content_json": {
                            "items": [
                                {
                                    "level": "核心卖点",
                                    "selling_point": "好消化易吸收",
                                    "ingredient": "软分子蛋白",
                                    "advantage": "形成结构松散的软凝乳",
                                    "expressions": ["喝起来温和，宝宝接受度更友好"],
                                }
                            ]
                        },
                    },
                    {
                        "asset_type": "painpoint_model",
                        "asset_key": asset_key,
                        "display_name": "源悦主题/痛点模型",
                        "content_json": {
                            "topics": [
                                {
                                    "topic": "便便不规律",
                                    "painpoint": "便便不规律",
                                    "descriptions": ["羊屎蛋/干硬", "便便又干又硬"],
                                    "selling_points": [
                                        {
                                            "selling_point": "好消化易吸收",
                                            "descriptions": ["软分子蛋白形成结构松散的软凝乳"],
                                            "expressions": ["便便基本一天一次，拉起来也不费劲"],
                                        }
                                    ],
                                }
                            ],
                            "items": [
                                {
                                    "painpoint": "便便不规律",
                                    "description": "羊屎蛋/干硬；便便又干又硬",
                                    "selling_point": "好消化易吸收",
                                    "selling_points": ["好消化易吸收"],
                                }
                            ],
                        },
                    },
                    {
                        "asset_type": "reference_examples",
                        "asset_key": asset_key,
                        "display_name": "源悦参考例文",
                        "content_json": {
                            "items": [
                                {
                                    "example_id": "yuanyue_ref_mock_001",
                                    "title": "真实经验！转奶终于不踩坑",
                                    "body": "新手妈妈别急着焦虑，先看宝宝喝奶和便便状态。",
                                    "reference_type": "用后分享",
                                    "style_tags": ["用后分享"],
                                }
                            ]
                        },
                    },
                    {
                        "asset_type": "ugc_expression_corpus",
                        "asset_key": asset_key,
                        "display_name": "源悦 UGC 卖点表述语料",
                        "content_json": {
                            "items": [
                                {
                                    "painpoint_or_selling_point": "便便不规律",
                                    "expression": "便便基本一天一次，拉起来也不费劲",
                                    "owner": "mock",
                                }
                            ]
                        },
                    },
                    {
                        "asset_type": "compliance_rules",
                        "asset_key": asset_key,
                        "display_name": "源悦审核规则",
                        "content_json": {
                            "items": [
                                {
                                    "dimension": "不得宣称治疗便秘",
                                    "feedback": "避免医疗化、绝对化表述",
                                }
                            ]
                        },
                    },
                ],
            }
        elif capability == "content.generate":
            output = _mock_unified_content_generation(input_payload)
        elif capability == "content.rewrite":
            output = _mock_content_rewrite(input_payload)
        else:
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                status="failed",
                error_code="input_invalid",
                error_message=f"unsupported capability: {capability}",
                stats={"mock": True},
            )
        return InvokeResult(
            mode="sync",
            stage_call_id=envelope["stage_call_id"],
            output=output,
            stats={"mock": True},
        )


def _mock_unified_content_generation(input_payload: dict[str, Any]) -> dict[str, Any]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        business_rule = input_payload.get("business_rule") or {}
        comment = _mock_comment_from_rule(business_rule)
        if not comment:
            comment = _mock_comment_from_rule(input_payload)
        return {
            "comment": comment,
            "runtime_result": {
                "mode": "content_fake",
                "fake": True,
                "reason": "mock_executor",
                "expert_config_code": ((input_payload.get("expert") or {}).get("expert_config_code")),
            },
        }

    business_rule = input_payload.get("business_rule") or {}
    selected = input_payload.get("selected_keywords") or []
    topic = business_rule.get("product_topic") or business_rule.get("business_rule") or "业务规则"
    target = business_rule.get("target_audience") or "妈妈"
    persona = _selected_keyword_name(selected, "persona") or "真实妈妈"
    method = _selected_keyword_name(selected, "writing_method") or "自然表达"
    multi_output_count = _mock_article_multi_output_count(input_payload)
    if multi_output_count > 1:
        items = [
            {
                "title": f"{topic}，{persona}的真实分享{i}",
                "body": (
                    f"围绕{topic}，写给{target}，第{i}篇用{persona}的口吻承接业务规则，"
                    f"再用{method}把具体感受讲清楚。整体表达保持自然克制。"
                ),
            }
            for i in range(1, multi_output_count + 1)
        ]
        return {
            "items": items,
            "runtime_result": {
                "mode": "content_fake",
                "fake": True,
                "reason": "mock_executor",
                "expert_config_code": ((input_payload.get("expert") or {}).get("expert_config_code")),
            },
        }
    return {
        "title": f"{topic}，{persona}的真实分享",
        "body": f"围绕{topic}，写给{target}，用{persona}的口吻承接业务规则，再用{method}把具体感受讲清楚。整体表达保持自然克制，不夸大、不照搬示例。",
        "runtime_result": {
            "mode": "content_fake",
            "fake": True,
            "reason": "mock_executor",
            "expert_config_code": ((input_payload.get("expert") or {}).get("expert_config_code")),
        },
    }


def _mock_article_multi_output_count(input_payload: dict[str, Any]) -> int:
    business_rule = input_payload.get("business_rule") or {}
    for key in ("multi_output_count", "article_output_count", "items_per_prompt"):
        try:
            value = int(business_rule.get(key) or input_payload.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 1:
            return max(1, min(value, 2))
    rendered_prompt = str(input_payload.get("rendered_prompt") or "")
    match = re.search(r"一次生成\s*(\\d+)\\s*篇", rendered_prompt)
    if match:
        return max(1, min(int(match.group(1)), 2))
    return 1


def _mock_content_rewrite(input_payload: dict[str, Any]) -> dict[str, Any]:
    previous = input_payload.get("previous_content") or input_payload.get("previous_draft") or {}
    if not isinstance(previous, dict):
        previous = {}
    hits = [
        str(value).strip()
        for value in [
            *(input_payload.get("forbidden_hits") or []),
            *(input_payload.get("style_hits") or []),
        ]
        if str(value).strip()
    ]
    replacements = _mock_replacements(input_payload)
    operator_feedback = str(
        input_payload.get("operator_feedback")
        or (input_payload.get("review_report") or {}).get("operator_feedback")
        or ""
    ).strip()
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        comment = _mock_remove_or_replace_terms(str(previous.get("comment") or previous.get("body") or ""), hits, replacements)
        if operator_feedback and comment:
            comment = f"{comment} 我会按这个方向再具体一点。"
        return {
            "comment": comment or "这个点我也在关注，想看看大家真实反馈。",
            "runtime_result": {
                "mode": "content_rewrite_fake",
                "fake": True,
                "reason": "mock_executor",
            },
        }
    similarity = (input_payload.get("review_report") or {}).get("similarity")
    if isinstance(similarity, dict):
        reason = str((input_payload.get("review_report") or {}).get("rewrite_reason") or similarity.get("reason") or "")
        return {
            "title": "降重后的标题",
            "body": f"换一个开头和结构来写。触发原因：{reason}",
            "final": {"title": "降重后的标题", "body": f"换一个开头和结构来写。触发原因：{reason}"},
            "runtime_result": {
                "mode": "content_rewrite_fake",
                "fake": True,
                "reason": "mock_executor",
            },
        }
    title = _mock_remove_or_replace_terms(str(previous.get("title") or ""), hits, replacements) or "改写后标题"
    body = _mock_remove_or_replace_terms(str(previous.get("body") or ""), hits, replacements) or "改写后正文"
    if operator_feedback:
        body = f"{body}\n\n按运营反馈调整：{operator_feedback}"
    return {
        "title": title,
        "body": body,
        "final": {"title": title, "body": body},
        "runtime_result": {
            "mode": "content_rewrite_fake",
            "fake": True,
            "reason": "mock_executor",
        },
    }


def _mock_replacements(input_payload: dict[str, Any]) -> dict[str, str]:
    forbidden_raw = input_payload.get("forbidden_replacements") if isinstance(input_payload.get("forbidden_replacements"), dict) else {}
    style_raw = input_payload.get("style_replacements") if isinstance(input_payload.get("style_replacements"), dict) else {}
    raw = {**forbidden_raw, **style_raw}
    if not isinstance(raw, dict):
        return {}
    return {
        str(term).strip(): str(replacement).strip()
        for term, replacement in raw.items()
        if str(term).strip() and str(replacement).strip()
    }


def _mock_remove_or_replace_terms(value: str, hits: list[str], replacements: dict[str, str]) -> str:
    text = value
    for term in hits:
        text = text.replace(term, replacements.get(term, ""))
    while "  " in text:
        text = text.replace("  ", " ")
    for duplicate in ["、、", "，，", "。。", "；；"]:
        while duplicate in text:
            text = text.replace(duplicate, duplicate[0])
    return text.strip(" ，。；、")


def _selected_keyword_name(selected_keywords: list[dict[str, Any]], category_code: str) -> str | None:
    for item in selected_keywords:
        if item.get("category_code") == category_code:
            value = item.get("keyword_name")
            return str(value) if value else None
    return None


def _mock_comment_from_rule(input_payload: dict[str, Any]) -> str:
    examples = [
        str(value).strip()
        for value in [
            *(input_payload.get("examples") or []),
            *(input_payload.get("supplements") or []),
        ]
        if str(value).strip()
    ]
    if examples:
        try:
            item_no = int(input_payload.get("item_no") or 1)
        except (TypeError, ValueError):
            item_no = 1
        return examples[(item_no - 1) % len(examples)]

    business_rule = str(input_payload.get("business_rule") or "这个角度").strip()
    return f"这个{business_rule}我还挺有共鸣的，想看看其他妈妈怎么说。"


def _is_direct_llm_invoke_url(invoke_url: str | None) -> bool:
    return str(invoke_url or "").lower().startswith(DIRECT_LLM_INVOKE_SCHEMES)


def _stats(started: float, *, adapter: str, executor: str) -> dict[str, Any]:
    return {
        "executor": executor,
        "module": "content-generator",
        "adapter": adapter,
        "total_latency_ms": int((time.perf_counter() - started) * 1000),
    }


class DirectLLMInvocationClient:
    """In-process executor for content generation without Hermes / worker HTTP."""

    async def invoke(self, *, invoke_url: str, envelope: dict[str, Any], executor_token: str | None = None) -> InvokeResult:
        started = time.perf_counter()
        capability = envelope.get("capability")
        try:
            if capability == "content.generate":
                output = await _direct_content_generate(envelope.get("input") or {})
            elif capability == "content.rewrite":
                output = await _direct_content_rewrite(envelope.get("input") or {})
            else:
                return InvokeResult(
                    mode="sync",
                    stage_call_id=envelope["stage_call_id"],
                    status="failed",
                    error_code="input_invalid",
                    error_message=f"direct LLM executor only supports content.generate/content.rewrite, got: {capability}",
                    stats=_stats(started, adapter="platform_server.direct_llm", executor="direct-llm"),
                )
        except Exception as exc:  # noqa: BLE001 - convert provider/runtime errors into protocol status
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                status="failed",
                error_code="direct_llm_error",
                error_message=_direct_llm_error_message(exc, capability),
                stats=_stats(started, adapter="platform_server.direct_llm", executor="direct-llm"),
            )

        return InvokeResult(
            mode="sync",
            stage_call_id=envelope["stage_call_id"],
            output=output,
            stats=_stats(started, adapter="platform_server.direct_llm", executor="direct-llm"),
        )


async def _direct_content_generate(input_payload: dict[str, Any]) -> dict[str, Any]:
    model_config = input_payload.get("model_config") or {}
    model = _direct_model_code(model_config, fallback_key="MAGA_DIRECT_CONTENT_MODEL")
    temperature = _float_or_default(model_config.get("temperature"), 0.8)
    max_tokens = _int_or_none(model_config.get("max_tokens"))
    system = str(
        model_config.get("system_prompt")
        or "你是中文小红书内容生成器，严格按用户提示输出，不解释过程。"
    )
    prompt = str(input_payload.get("rendered_prompt") or "").strip() or _fallback_rendered_prompt(input_payload)
    output, meta = await _direct_generate_with_empty_retry(
        input_payload,
        model_config=model_config,
        model=model,
        system=system,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        normalizer=_normalize_unified_content_output,
        empty_output_factory=_empty_content_from_unified_input,
    )
    output["runtime_result"] = {
        "mode": "direct_llm_content_runtime",
        "fake": False,
        "expert_config_code": (input_payload.get("expert") or {}).get("expert_config_code"),
        "provider_code": model_config.get("provider_code"),
        "model_code": model,
        **meta,
    }
    return output


async def _direct_content_rewrite(input_payload: dict[str, Any]) -> dict[str, Any]:
    previous = _rewrite_previous_content(input_payload)
    content_type = str(input_payload.get("content_type") or ("comment" if previous.get("comment") else "article"))
    output_fields = input_payload.get("output_fields") or (["comment"] if content_type == "comment" else ["title", "body"])
    forbidden_hits = _rewrite_forbidden_hits(input_payload)
    forbidden_replacements = _rewrite_forbidden_replacements(input_payload)
    model_config = input_payload.get("model_config") or input_payload.get("rewrite_model_config") or {}
    model = _direct_model_code(model_config, fallback_key="MAGA_DIRECT_REWRITE_MODEL")
    temperature = _float_or_default(model_config.get("temperature"), 0.35)
    max_tokens = _int_or_none(model_config.get("max_tokens"))
    system = str(
        model_config.get("system_prompt")
        or "你是中文内容审核后的自然改写助手，只按要求改写，不解释过程。"
    )
    prompt = str(input_payload.get("rendered_prompt") or "").strip()
    if not prompt:
        prompt = _rewrite_prompt(
            input_payload,
            previous=previous,
            forbidden_hits=forbidden_hits,
            forbidden_replacements=forbidden_replacements,
            content_type=content_type,
        )

    output, meta = await _direct_rewrite_with_empty_retry(
        input_payload,
        model_config=model_config,
        model=model,
        system=system,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        content_type=content_type,
        output_fields=output_fields,
    )
    output["runtime_result"] = {
        "mode": "direct_llm_content_rewrite_runtime",
        "fake": False,
        "provider_code": model_config.get("provider_code"),
        "model_code": model,
        "forbidden_hits": forbidden_hits,
        "expert_config_code": (input_payload.get("expert") or {}).get("expert_config_code"),
        **meta,
    }
    return output


async def _direct_rewrite_with_empty_retry(
    input_payload: dict[str, Any],
    *,
    model_config: dict[str, Any],
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    max_tokens: int | None,
    content_type: str,
    output_fields: list[Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts = [
        prompt,
        (
            f"{prompt}\n\n"
            "再次提醒：必须输出非空改写结果。评论只输出一条评论正文；文章只输出符合要求的标题和正文。"
        ),
    ]
    last_raw = ""
    last_error: ValueError | None = None
    for attempt_no, attempt_prompt in enumerate(attempts, start=1):
        raw = await _call_openai_compatible_model(
            model=model,
            system=system,
            user=attempt_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model_config=model_config,
        )
        last_raw = str(raw or "")
        if not last_raw.strip():
            last_error = ValueError("content.rewrite produced empty output")
            continue
        try:
            output = _normalize_rewrite_output(raw, input_payload, content_type=content_type, output_fields=output_fields)
        except ValueError as exc:
            last_error = exc
            if "empty" in str(exc):
                continue
            raise
        return output, {
            "fallback": False,
            "model_attempts": attempt_no,
            "raw_output_length": len(last_raw),
        }
    raise ValueError(str(last_error or "content.rewrite produced empty output"))


async def _direct_generate_with_empty_retry(
    input_payload: dict[str, Any],
    *,
    model_config: dict[str, Any],
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    max_tokens: int | None,
    normalizer,
    empty_output_factory,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts = [
        prompt,
        (
            f"{prompt}\n\n"
            f"再次提醒：必须输出非空结果。{_empty_retry_output_reminder(input_payload)}"
        ),
    ]
    last_raw = ""
    last_error: ValueError | None = None
    for attempt_no, attempt_prompt in enumerate(attempts, start=1):
        raw = await _call_openai_compatible_model(
            model=model,
            system=system,
            user=attempt_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model_config=model_config,
        )
        last_raw = str(raw or "")
        try:
            output = normalizer(last_raw, input_payload)
        except ValueError as exc:
            last_error = exc
            if "empty" in str(exc):
                continue
            raise
        return output, {
            "fallback": False,
            "model_attempts": attempt_no,
            "raw_output_length": len(last_raw),
            "empty_output": False,
        }

    # Preserve the old worker contract: empty generation is explicit output,
    # so upstream quality gates can mark/retry the item instead of duplicating examples.
    return empty_output_factory(input_payload), {
        "fallback": False,
        "model_attempts": len(attempts),
        "raw_output_length": len(last_raw),
        "empty_output": True,
        "empty_reason": str(last_error or "empty_model_output"),
    }


async def _call_openai_compatible_model(
    *,
    model: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int | None,
    model_config: dict[str, Any],
) -> str:
    endpoint = _direct_model_endpoint(model_config)
    api_key = _direct_model_api_key(model_config)
    timeout_s = _float_or_default(
        model_config.get("timeout") or os.getenv("MAGA_DIRECT_MODEL_TIMEOUT"),
        90.0,
    )
    retry_count = _direct_model_retry_count(model_config.get("max_retries"))

    if not endpoint:
        raise RuntimeError("直连大模型缺少 base_url/endpoint，请先配置 llm_provider_config.base_url 或环境变量")
    if not api_key:
        raise RuntimeError("直连大模型缺少 API Key，请先配置 llm_provider_config.api_key 或环境变量")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system or ""},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    last_error = ""
    for _ in range(retry_count):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            return _extract_openai_choice_content(data)
        except httpx.TimeoutException:
            last_error = f"直连大模型调用超时(timeout={timeout_s}s)"
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "")[:300]
            last_error = f"直连大模型 HTTP {exc.response.status_code}: {body}"
        except httpx.RequestError as exc:
            last_error = f"直连大模型网络错误: {exc}"
        except ValueError as exc:
            last_error = f"直连大模型响应解析失败: {exc}"
    raise RuntimeError(f"{last_error}，已重试 {retry_count} 次")


def _extract_openai_choice_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices")
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    if content is None:
        content = first.get("text")
    return str(content or "")


def _direct_model_code(model_config: dict[str, Any], *, fallback_key: str) -> str:
    return normalize_default_model(
        model_config.get("model_code")
        or model_config.get("provider_model")
        or model_config.get("ge_model")
        or os.getenv(fallback_key)
        or os.getenv("MAGA_DIRECT_CONTENT_MODEL")
        or os.getenv("DEEPSEEK_MODEL")
    )


def _direct_model_endpoint(model_config: dict[str, Any]) -> str | None:
    base_url = (
        model_config.get("base_url")
        or model_config.get("endpoint")
        or os.getenv("MAGA_DIRECT_MODEL_BASE_URL")
        or os.getenv("DEEPSEEK_API_BASE")
        or os.getenv("AIHUBMIX_BASE_URL")
        or os.getenv("AIHUBMIX_API_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("ARK_BASE_URL")
        or DIRECT_LLM_DEFAULT_BASE_URL
    )
    return ensure_chat_completions_endpoint(str(base_url)) if base_url else None


def _direct_model_api_key(model_config: dict[str, Any]) -> str | None:
    value = (
        model_config.get("api_key")
        or os.getenv("MAGA_DIRECT_MODEL_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("AIHUBMIX_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("ARK_API_KEY")
    )
    return str(value).strip() if value else None


def _direct_model_retry_count(value: Any) -> int:
    try:
        retry_count = int(value) if value is not None else 3
    except (TypeError, ValueError):
        retry_count = 3
    return max(1, min(retry_count, 3))


def _direct_llm_error_message(exc: Exception, capability: Any) -> str:
    text = str(exc).strip() or type(exc).__name__
    return f"后端直连大模型执行失败：{text}。当前失败阶段：{capability}"


def _normalize_comment_text(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:text|markdown)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value).strip()
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if lines:
        value = lines[0]
    value = re.sub(r"^(?:[-*•]\s*|\d+[、.．]\s*)", "", value).strip()
    value = re.sub(r"^(评论正文|评论|输出)[:：]\s*", "", value).strip()
    return value.strip("“”\"' ")


def _comment_output_format_mode(input_payload: dict[str, Any]) -> str:
    output_format = input_payload.get("output_format")
    mode = ""
    if isinstance(output_format, dict):
        mode = str(output_format.get("mode") or output_format.get("output_format_mode") or "").strip()
    mode = mode or str(input_payload.get("output_format_mode") or "").strip()
    return mode if mode in {"json_string_array", "json_object_array"} else "plain_comment"


def _empty_retry_output_reminder(input_payload: dict[str, Any]) -> str:
    if input_payload.get("content_type") == "comment" or (input_payload.get("output_fields") or []) == ["comment"]:
        mode = _comment_output_format_mode(input_payload)
        if mode == "json_string_array":
            return "评论只输出 JSON 字符串数组；文章输出标题和正文。"
        if mode == "json_object_array":
            return '评论只输出 JSON 对象数组，每个对象包含 "comment" 字段；文章输出标题和正文。'
        return "评论只输出一条评论正文；文章输出标题和正文。"
    return "评论只输出一条评论正文；文章输出标题和正文。"


def _normalize_comment_array_output(raw: str, *, mode: str) -> list[str]:
    parsed = _parse_json_value(raw)
    if not isinstance(parsed, list):
        return []
    comments: list[str] = []
    for item in parsed:
        if mode == "json_string_array":
            comment = _normalize_comment_text(str(item or ""))
        elif isinstance(item, dict):
            comment = _normalize_comment_text(
                str(
                    item.get("comment")
                    or item.get("评论")
                    or item.get("content")
                    or item.get("内容")
                    or item.get("text")
                    or item.get("回复")
                    or ""
                )
            )
        else:
            comment = ""
        if comment:
            comments.append(comment)
    return comments


def _empty_content_from_unified_input(input_payload: dict[str, Any]) -> dict[str, str]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        mode = _comment_output_format_mode(input_payload)
        if mode in {"json_string_array", "json_object_array"}:
            return {"comment": "", "comments": [], "items": []}
        return {"comment": ""}
    return {"title": "", "body": ""}


def _normalize_unified_content_output(raw: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        mode = _comment_output_format_mode(input_payload)
        if mode in {"json_string_array", "json_object_array"}:
            comments = _normalize_comment_array_output(raw, mode=mode)
            if not comments:
                raise ValueError("content.generate produced empty comment array")
            return {
                "comment": comments[0],
                "comments": comments,
                "items": [{"comment": comment} for comment in comments],
                "output_format_mode": mode,
            }
        comment = _normalize_comment_text(raw)
        if not comment:
            raise ValueError("content.generate produced empty comment")
        return {"comment": comment}

    parsed = _parse_json_object(raw)
    multi_items = _article_items_from_parsed_json(parsed)
    if multi_items:
        first = multi_items[0]
        return {"title": first["title"], "body": first["body"], "items": multi_items}

    title = _clean_generated_article_text(parsed.get("title") or parsed.get("标题"))
    body = _clean_generated_article_text(parsed.get("body") or parsed.get("正文"))
    if not title or not body:
        title, body = _loose_title_body_from_text(raw) or _title_body_from_text(raw)
    title, body = _flatten_nested_article_json(title, body)
    title = _clean_generated_article_text(title)
    body = _clean_generated_article_text(body)
    if not body:
        raise ValueError("content.generate produced empty body")
    return {"title": title or "今天这点变化", "body": body}


def _rewrite_previous_content(input_payload: dict[str, Any]) -> dict[str, str]:
    previous = input_payload.get("previous_content") or input_payload.get("previous_draft") or {}
    content_type = str(input_payload.get("content_type") or "")
    if isinstance(previous, str):
        if content_type == "comment" or (input_payload.get("output_fields") or []) == ["comment"]:
            return {"comment": previous}
        title, body = _title_body_from_text(previous)
        return {"title": title, "body": body}
    if not isinstance(previous, dict):
        previous = {}
    if content_type == "comment" or (input_payload.get("output_fields") or []) == ["comment"]:
        return {"comment": str(previous.get("comment") or previous.get("body") or input_payload.get("comment") or "").strip()}
    return {
        "title": str(previous.get("title") or input_payload.get("title") or "").strip(),
        "body": str(previous.get("body") or previous.get("comment") or input_payload.get("body") or "").strip(),
    }


def _rewrite_forbidden_hits(input_payload: dict[str, Any]) -> list[str]:
    values = input_payload.get("forbidden_hits")
    if values is None:
        values = ((input_payload.get("review_report") or {}).get("forbidden_terms_review") or {}).get("hits")
    if values is None:
        values = (((input_payload.get("review_report") or {}).get("hard_results") or [{}])[0] or {}).get("evidence")
    return [str(value).strip() for value in values or [] if str(value).strip()]


def _rewrite_forbidden_replacements(input_payload: dict[str, Any]) -> dict[str, str]:
    raw = input_payload.get("forbidden_replacements") or input_payload.get("replacement_map") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(term).strip(): str(replacement).strip()
        for term, replacement in raw.items()
        if str(term).strip() and str(replacement).strip()
    }


def _rewrite_prompt(
    input_payload: dict[str, Any],
    *,
    previous: dict[str, str],
    forbidden_hits: list[str],
    forbidden_replacements: dict[str, str],
    content_type: str,
) -> str:
    output_instruction = (
        "输出要求：只输出改写后的评论正文，不要标题、编号、解释。"
        if content_type == "comment"
        else '输出要求：只输出 JSON，格式为 {"title": "...", "body": "..."}，不要解释。'
    )
    parts = [
        f"内容类型：{content_type}",
        "原内容：\n" + json.dumps(previous, ensure_ascii=False, indent=2),
        f"必须删除或自然替换的违禁词：{'、'.join(forbidden_hits) if forbidden_hits else '无'}",
        "指定替换映射：\n"
        + (
            "\n".join(f"- {term} -> {replacement}" for term, replacement in forbidden_replacements.items())
            if forbidden_replacements
            else "无"
        ),
        "改写原则：优先删除、压缩或替换命中词和相关句子，尽量保留原意、语气、结构和业务规则；不要为了多样化扩写新情节；不得新增功效承诺、医疗诊断或绝对化表达。",
        output_instruction,
    ]
    instructions = input_payload.get("rewrite_instructions") or []
    if instructions:
        parts.append("补充指令：\n" + "\n".join(f"- {item}" for item in instructions if str(item).strip()))
    business_rule = input_payload.get("business_rule")
    if business_rule:
        parts.append("业务规则：\n" + json.dumps(business_rule, ensure_ascii=False, indent=2))
    selected_keywords = input_payload.get("selected_keywords")
    if selected_keywords:
        parts.append("已选表达扩散语料：\n" + json.dumps(selected_keywords, ensure_ascii=False, indent=2))
    return "\n\n".join(parts)


def _normalize_rewrite_output(
    raw: str,
    input_payload: dict[str, Any],
    *,
    content_type: str,
    output_fields: list[Any],
) -> dict[str, Any]:
    if content_type == "comment" or output_fields == ["comment"]:
        parsed = _parse_json_object(raw)
        comment = str(parsed.get("comment") or parsed.get("评论") or "").strip() if parsed else ""
        comment = _normalize_comment_text(comment or raw)
        if not comment:
            raise ValueError("content.rewrite produced empty comment")
        return {"comment": comment}

    parsed = _parse_json_object(raw)
    title = str(parsed.get("title") or parsed.get("标题") or "").strip()
    body = str(parsed.get("body") or parsed.get("正文") or "").strip()
    if not title or not body:
        title, body = _loose_title_body_from_text(raw) or _title_body_from_text(raw)
    title, body = _flatten_nested_article_json(title, body)
    if not body:
        previous = _rewrite_previous_content(input_payload)
        body = previous.get("body") or ""
    if not body:
        raise ValueError("content.rewrite produced empty body")
    title = title or (_rewrite_previous_content(input_payload).get("title") or "改写后标题")
    return {"title": title, "body": body, "final": {"title": title, "body": body}}


def _flatten_nested_article_json(title: str, body: str) -> tuple[str, str]:
    """Recover when a model puts the full article JSON inside the body field."""
    body_text = str(body or "").strip()
    if not body_text:
        return str(title or "").strip(), body_text
    nested = _parse_json_object(body_text)
    if not nested:
        return str(title or "").strip(), body_text
    nested_body = str(nested.get("body") or nested.get("正文") or "").strip()
    if not nested_body:
        return str(title or "").strip(), body_text
    nested_title = str(nested.get("title") or nested.get("标题") or "").strip()
    return nested_title or str(title or "").strip(), nested_body


def _article_items_from_parsed_json(parsed: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = parsed.get("items") or parsed.get("文章列表") or parsed.get("内容列表")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        title = _clean_generated_article_text(raw_item.get("title") or raw_item.get("标题"))
        body = _clean_generated_article_text(raw_item.get("body") or raw_item.get("正文"))
        if body:
            items.append({"title": title or "今天这点变化", "body": body})
    return items


def _clean_generated_article_text(value: Any) -> str:
    text = str(value or "").strip()
    text = _strip_topic_tags(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def _strip_topic_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"#[^\s#，。！？、；;]{1,40}\[话题\]#?", "", text)
    cleaned = re.sub(r"#[^\s#，。！？、；;]{1,40}#", "", cleaned)
    cleaned = re.sub(r"(?:\s*#[^\s#，。！？、；;]{1,40})+\s*$", "", cleaned)
    cleaned = re.sub(r"\[[^\[\]]{1,12}话题[^\[\]]{0,12}\]", "", cleaned)
    return cleaned.strip()


def _parse_json_object(raw: str) -> dict[str, Any]:
    parsed = _parse_json_value(raw)
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_value(raw: str) -> Any:
    value = str(raw or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value).strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", value, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _loose_title_body_from_text(raw: str) -> tuple[str, str] | None:
    value = str(raw or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value).strip()
    title_match = re.search(
        r'["“]?(?:title|标题)["”]?\s*[:：]\s*["“](?P<title>.+?)["”]\s*,?',
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body_match = re.search(
        r'["“]?(?:body|正文)["”]?\s*[:：]\s*["“](?P<body>.+)["”]\s*[,}]?\s*$',
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not title_match or not body_match:
        return None
    title = title_match.group("title").strip()
    body = body_match.group("body").strip()
    body = body.replace("\\n", "\n").replace('\\"', '"')
    # 大模型偶尔漏掉 JSON 右括号，但字段本身完整；这里只恢复字段内容，不吞掉其他纯文本。
    return (title, body) if title and body else None


def _title_body_from_text(raw: str) -> tuple[str, str]:
    lines = [line.strip() for line in str(raw or "").splitlines() if line.strip()]
    title = ""
    body_lines: list[str] = []
    for line in lines:
        normalized = re.sub(r"^(?:[-*•]\s*|\d+[、.．]\s*)", "", line).strip()
        title_match = re.match(r"^(?:标题|title)[:：]\s*(.+)$", normalized, flags=re.IGNORECASE)
        body_match = re.match(r"^(?:正文|body)[:：]\s*(.+)$", normalized, flags=re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            continue
        if body_match:
            body_lines.append(body_match.group(1).strip())
            continue
        body_lines.append(normalized)
    if not title and body_lines:
        first = body_lines[0]
        if len(first) <= 36 and len(body_lines) > 1:
            title = first
            body_lines = body_lines[1:]
    return title, "\n".join(body_lines).strip()


def _fallback_rendered_prompt(input_payload: dict[str, Any]) -> str:
    parts = [
        f"内容类型：{input_payload.get('content_type') or ''}",
        f"输出字段：{input_payload.get('output_fields') or []}",
        "业务规则：\n" + json.dumps(input_payload.get("business_rule") or {}, ensure_ascii=False, indent=2),
        "表达扩散语料：\n" + json.dumps(input_payload.get("selected_keywords") or [], ensure_ascii=False, indent=2),
    ]
    return "\n\n".join(parts)


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None




def _default_timeout_seconds() -> float:
    raw = os.getenv("MAGA_EXECUTOR_INVOKE_TIMEOUT_SECONDS", "180")
    try:
        return float(raw)
    except ValueError:
        return 180.0


class ExecutorInvocationClient:
    """HTTP client for MAGA push invocation of an executor capability."""

    def __init__(self, http_client: Any | None = None, timeout_seconds: float | None = None):
        self.http_client = http_client or httpx.AsyncClient()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else _default_timeout_seconds()

    async def invoke(self, *, invoke_url: str, envelope: dict[str, Any], executor_token: str | None = None) -> InvokeResult:
        if _is_direct_llm_invoke_url(invoke_url):
            return await DirectLLMInvocationClient().invoke(
                invoke_url=invoke_url,
                envelope=envelope,
                executor_token=executor_token,
            )

        headers = {"X-Maga-Protocol-Version": PROTOCOL_VERSION}
        if executor_token:
            headers["Authorization"] = f"Bearer {executor_token}"
        response = await self.http_client.post(
            invoke_url,
            json=envelope,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        payload = response.json()

        if response.status_code == 200:
            status = payload.get("status") or "succeeded"
            return InvokeResult(
                mode="sync",
                stage_call_id=payload.get("stage_call_id") or envelope["stage_call_id"],
                status=status,
                output=payload.get("output") if status == "succeeded" else None,
                stats=payload.get("stats"),
                error_code=payload.get("error_code"),
                error_message=payload.get("error_message"),
            )

        if response.status_code == 202:
            raise RuntimeError("MVP protocol requires sync /invoke response; async ack is not supported")

        raise RuntimeError(f"Executor invoke failed: status={response.status_code} body={response.text}")
