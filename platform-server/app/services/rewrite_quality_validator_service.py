"""Focused before/after validation for post-generation rewrites."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from app.services.executor_invocation_service import call_direct_llm_text


REWRITE_QUALITY_LABELS = {"accept", "retry", "reject"}
REWRITE_QUALITY_MODEL_CODE = "qwen-plus"
REWRITE_QUALITY_ISSUE_CODES = {
    "none",
    "fluency_regression",
    "semantic_discontinuity",
    "required_fact_loss",
}


@dataclass(slots=True)
class RewriteQualityJudgment:
    label: str
    issue_code: str
    evidence: str

    def model_dump(self) -> dict[str, str]:
        return {
            "label": self.label,
            "issue_code": self.issue_code,
            "evidence": self.evidence,
        }


class RewriteQualityValidatorService:
    """Compare a rewrite candidate with its source using a short fixed rubric."""

    async def review(
        self,
        *,
        before: dict[str, str],
        after: dict[str, str],
        rewrite_source: str,
        target_issue: str,
        plan: dict[str, Any] | None,
    ) -> RewriteQualityJudgment:
        config = _review_model_config(plan or {})
        prompt = _user_prompt(
            before=before,
            after=after,
            rewrite_source=rewrite_source,
            target_issue=target_issue,
        )
        response = await call_direct_llm_text(
            model_config=config,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0,
            max_tokens=350,
            response_format={"type": "json_object"},
        )
        judgment = parse_rewrite_quality_judgment(str(response or ""))
        if judgment is not None:
            return judgment

        retry_response = await call_direct_llm_text(
            model_config=config,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=f"{prompt}\n\n上次输出格式错误。只输出合法 JSON object，不要解释。",
            temperature=0,
            max_tokens=350,
            response_format={"type": "json_object"},
        )
        judgment = parse_rewrite_quality_judgment(str(retry_response or ""))
        if judgment is None:
            raise ValueError("rewrite quality validator did not return a JSON object")
        return judgment


def parse_rewrite_quality_judgment(raw_response: str) -> RewriteQualityJudgment | None:
    payload = _extract_json_object(raw_response)
    if not payload:
        return None
    label = str(payload.get("label") or "").strip().lower()
    issue_code = str(payload.get("issue_code") or "").strip()
    evidence = str(payload.get("evidence") or "").strip()[:300]
    if label not in REWRITE_QUALITY_LABELS or issue_code not in REWRITE_QUALITY_ISSUE_CODES:
        return None
    if label == "accept":
        issue_code = "none"
    elif issue_code == "none":
        return None
    return RewriteQualityJudgment(label=label, issue_code=issue_code, evidence=evidence)


def _review_model_config(plan: dict[str, Any]) -> dict[str, Any]:
    unified_generation = plan.get("unified_generation") or {}
    expert = unified_generation.get("expert") or {}
    model_config = dict(
        plan.get("model_config")
        or unified_generation.get("model_config")
        or expert.get("model_config")
        or {}
    )
    return {
        **model_config,
        "provider": model_config.get("provider") or model_config.get("provider_code"),
        "model": model_config.get("model") or model_config.get("model_code") or model_config.get("ge_model"),
        "temperature": 0,
        "max_tokens": 350,
    }


def _user_prompt(
    *,
    before: dict[str, str],
    after: dict[str, str],
    rewrite_source: str,
    target_issue: str,
) -> str:
    return json.dumps(
        {
            "task": "validate_rewrite_candidate",
            "rewrite_source": rewrite_source,
            "target_issue": target_issue,
            "before": before,
            "after": after,
        },
        ensure_ascii=False,
    )


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


_SYSTEM_PROMPT = """你只验收一次中文内容改写，不审核品牌合规、产品卖点或种草强弱，也不继续改写。

比较 before 和 after，只检查三件事：
1. after 是否出现新的病句、搭配错误或难以理解的表达；
2. 句子和上下文是否仍然连续，指代和时间关系是否清楚；
3. after 是否无故删除或改变 before 中的人物、产品、时间、数量和关键事实。

目标问题被删除是正常改写，不算事实损失。只要 after 通顺、意思连续且关键事实保留，就 accept。
局部调整即可修好时用 retry；明显改坏、语义漂移或关键事实丢失时用 reject。

issue_code 只能是 none、fluency_regression、semantic_discontinuity、required_fact_loss。
只输出 JSON object：{"label":"accept|retry|reject","issue_code":"上述枚举之一","evidence":"简短证据"}。"""
