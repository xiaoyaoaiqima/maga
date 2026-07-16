"""Shared direct-call runtime for small focused LLM judges."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from app.services.executor_invocation_service import DirectLLMCallResult, call_direct_llm


FOCUSED_JUDGE_LABELS = {"pass", "watch", "block"}


@dataclass(slots=True)
class FocusedJudgeCallResult:
    raw_response: str
    runtime_metadata: dict[str, Any]


async def call_focused_judge(
    *,
    model_config: dict[str, Any] | None,
    system_prompt: str,
    user_prompt: str,
    issue_codes: set[str],
    max_tokens: int = 300,
) -> FocusedJudgeCallResult:
    config = focused_judge_model_config(model_config, max_tokens=max_tokens)
    response = await call_direct_llm(
        model_config=config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0,
        max_tokens=max_tokens,
    )
    response_payload = direct_llm_result_payload(response)
    raw_response = response.content
    if not has_valid_focused_judgment_contract(raw_response, issue_codes=issue_codes):
        retry = await call_direct_llm(
            model_config=config,
            system_prompt=system_prompt,
            user_prompt=f"{user_prompt}\n\n上次输出格式错误。现在只输出一个合法 JSON object，不要解释。",
            temperature=0,
            max_tokens=max_tokens,
        )
        raw_response = retry.content
        response_payload = merge_focused_runtime_metadata(
            response_payload,
            direct_llm_result_payload(retry),
        )
        if not has_valid_focused_judgment_contract(raw_response, issue_codes=issue_codes):
            raise ValueError("focused judge did not return a valid JSON contract after retry")
    return FocusedJudgeCallResult(
        raw_response=raw_response,
        runtime_metadata={
            "model_code": response_payload.get("model_code"),
            "provider_code": response_payload.get("provider_code"),
            "provider_model": response_payload.get("provider_model"),
            "usage": response_payload.get("usage") or {},
            "latency_ms": int(response_payload.get("latency_ms") or 0),
            "retry_count": int(response_payload.get("retry_count") or 0),
        },
    )


def normalize_focused_judgment(
    raw_response: str,
    *,
    issue_codes: set[str],
    fallback_issue_code: str,
) -> tuple[str, str, str]:
    payload = extract_focused_json_object(raw_response)
    label = str(payload.get("label") or "watch").strip().lower()
    if label not in FOCUSED_JUDGE_LABELS:
        label = "watch"
    issue_code = str(payload.get("issue_code") or "none").strip()
    if issue_code not in issue_codes:
        issue_code = "none" if label == "pass" else fallback_issue_code
    if label == "pass":
        issue_code = "none"
    elif issue_code == "none":
        issue_code = fallback_issue_code
    evidence = str(payload.get("evidence") or "").strip()[:300]
    return label, issue_code, evidence


def focused_judge_model_config(
    model_config: dict[str, Any] | None,
    *,
    max_tokens: int,
) -> dict[str, Any]:
    config = dict(model_config or {})
    return {
        **config,
        "provider": config.get("provider") or config.get("provider_code"),
        "model": config.get("model") or config.get("model_code") or config.get("ge_model"),
        "temperature": 0,
        "max_tokens": max_tokens,
    }


def extract_focused_json_object(raw_response: str) -> dict[str, Any]:
    text = str(raw_response or "").strip()
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def has_valid_focused_judgment_contract(raw_response: str, *, issue_codes: set[str]) -> bool:
    payload = extract_focused_json_object(raw_response)
    label = str(payload.get("label") or "").strip().lower()
    issue_code = str(payload.get("issue_code") or "").strip()
    evidence = payload.get("evidence")
    return (
        label in FOCUSED_JUDGE_LABELS
        and (issue_code in issue_codes or (label == "pass" and not issue_code))
        and (label == "pass" or (isinstance(evidence, str) and bool(evidence.strip())))
    )


def direct_llm_result_payload(result: DirectLLMCallResult) -> dict[str, Any]:
    return {
        "content": result.content,
        "model_code": result.model_code,
        "provider_code": result.provider_code,
        "provider_model": result.provider_model,
        "usage": result.usage,
        "latency_ms": result.latency_ms,
        "retry_count": 0,
    }


def merge_focused_runtime_metadata(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_usage = first.get("usage") if isinstance(first.get("usage"), dict) else {}
    second_usage = second.get("usage") if isinstance(second.get("usage"), dict) else {}
    usage = {
        key: int(first_usage.get(key) or 0) + int(second_usage.get(key) or 0)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    return {
        **second,
        "usage": usage,
        "latency_ms": int(first.get("latency_ms") or 0) + int(second.get("latency_ms") or 0),
        "retry_count": 1,
    }
