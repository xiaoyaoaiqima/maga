"""Focused LLM judge for Wangyue temporal logic evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from app.services.executor_invocation_service import call_direct_llm_text


TEMPORAL_LABELS = {"pass", "watch", "block"}
TEMPORAL_ISSUE_CODES = {
    "none",
    "same_period_state_contradiction",
    "immediate_rescue_causality",
    "insufficient_effect_duration",
    "publication_time_anchor",
    "mixed_state_same_period",
    "past_public_disease_reference",
}


@dataclass(slots=True)
class WangyueTemporalLogicJudgment:
    label: str
    issue_code: str
    evidence: str
    raw_response: str = ""
    runtime_metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "issue_code": self.issue_code,
            "evidence": self.evidence,
        }


class WangyueTemporalLogicJudgeService:
    """Judge only timeline coherence; this service is not wired into production review."""

    async def review(
        self,
        *,
        title: str | None,
        body: str | None,
        model_config: dict[str, Any] | None = None,
    ) -> WangyueTemporalLogicJudgment:
        config = _judge_model_config(model_config)
        user_prompt = f"标题：{title or ''}\n正文：{body or ''}"
        response = await call_direct_llm_text(
            model_config=config,
            system_prompt=TEMPORAL_LOGIC_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0,
            max_tokens=300,
        )
        response_payload = {"content": str(response or "")}
        raw_response = str(response or "")
        if not _has_valid_judgment_contract(raw_response):
            retry = await call_direct_llm_text(
                model_config=config,
                system_prompt=TEMPORAL_LOGIC_SYSTEM_PROMPT,
                user_prompt=f"{user_prompt}\n\n上次输出格式错误。现在只输出一个合法 JSON object，不要解释。",
                temperature=0,
                max_tokens=300,
            )
            retry_payload = {"content": str(retry or "")}
            raw_response = str(retry_payload.get("content") or "")
            response_payload = _merge_runtime_metadata(response_payload, retry_payload)
        judgment = parse_wangyue_temporal_logic_judgment(raw_response)
        judgment.runtime_metadata = {
            "model_code": response_payload.get("model_code"),
            "provider_code": response_payload.get("provider_code"),
            "usage": response_payload.get("usage") or {},
            "retry_count": int(response_payload.get("retry_count") or 0),
        }
        return judgment


def parse_wangyue_temporal_logic_judgment(raw_response: str) -> WangyueTemporalLogicJudgment:
    payload = _extract_json_object(raw_response)
    label = str(payload.get("label") or "watch").strip().lower()
    if label not in TEMPORAL_LABELS:
        label = "watch"
    issue_code = str(payload.get("issue_code") or "none").strip()
    if issue_code not in TEMPORAL_ISSUE_CODES:
        issue_code = "none" if label == "pass" else "mixed_state_same_period"
    if label == "pass":
        issue_code = "none"
    elif issue_code == "none":
        issue_code = "mixed_state_same_period"
    evidence = str(payload.get("evidence") or "").strip()[:300]
    return WangyueTemporalLogicJudgment(
        label=label,
        issue_code=issue_code,
        evidence=evidence,
        raw_response=raw_response[:2000],
    )


def _judge_model_config(model_config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(model_config or {})
    return {
        **config,
        "provider": config.get("provider") or config.get("provider_code"),
        "model": config.get("model") or config.get("model_code") or config.get("ge_model"),
        "temperature": 0,
        "max_tokens": 300,
    }


def _extract_json_object(raw_response: str) -> dict[str, Any]:
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


def _has_valid_judgment_contract(raw_response: str) -> bool:
    payload = _extract_json_object(raw_response)
    return (
        str(payload.get("label") or "").strip().lower() in TEMPORAL_LABELS
        and str(payload.get("issue_code") or "").strip() in TEMPORAL_ISSUE_CODES
        and isinstance(payload.get("evidence"), str)
    )


def _merge_runtime_metadata(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_usage = first.get("usage") if isinstance(first.get("usage"), dict) else {}
    second_usage = second.get("usage") if isinstance(second.get("usage"), dict) else {}
    usage = {
        key: int(first_usage.get(key) or 0) + int(second_usage.get(key) or 0)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    return {
        **second,
        "usage": usage,
        "retry_count": 1,
    }


TEMPORAL_LOGIC_SYSTEM_PROMPT = """你只审核旺玥文章的时间逻辑，不审核产品事实、违禁词、人味、种草强弱，也不改写。

判断标准：
1. 同一时间窗口同时写持续不好和持续稳定，且没有“以前/前阵子/后来/换后”等阶段转换：block，same_period_state_contradiction。“总是/一直/三天两头/频繁不舒服”属于持续负面，不能和“状态一直稳/整体稳”并存，不要降成 watch。
2. 单次打喷嚏、刚换产品、刚开罐，立刻承接补救、长期保护力或累计效果：block，按 immediate_rescue_causality 或 insufficient_effect_duration。
3. “现在/最近”绑定流感季、换季、入冬等依赖发布时间成立的环境：block，publication_time_anchor。明确过去式可以保留。
4. “偶尔/有点”这类局部小状况与整体状态稳定可以共存，但标 watch，mixed_state_same_period。
5. 过去的周围孩子生病只作背景、不依赖当前环境成立：pass 或 watch；没有公共疾病对照且时间阶段清楚、效果有观察跨度：pass。

issue_code 只能从以下值选择：none、same_period_state_contradiction、immediate_rescue_causality、insufficient_effect_duration、publication_time_anchor、mixed_state_same_period、past_public_disease_reference。label=pass 时 issue_code 必须是 none。

只输出 JSON object：{"label":"pass|watch|block","issue_code":"上述枚举之一","evidence":"原文证据"}。"""
