"""Focused LLM judge for Wangyue claims and public-disease context."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.focused_llm_judge_runtime import call_focused_judge, normalize_focused_judgment


CLAIM_PUBLIC_DISEASE_ISSUE_CODES = {
    "none",
    "own_illness_reduction_observation",
    "past_public_disease_reference",
    "immediate_rescue_claim",
    "medical_authority_claim",
    "medical_treatment_claim",
    "disease_prevention_guarantee",
    "current_public_disease_environment",
}
CLAIM_PUBLIC_DISEASE_MODEL_CODE = "deepseek-v4-flash"


@dataclass(slots=True)
class WangyueClaimPublicDiseaseJudgment:
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


class WangyueClaimPublicDiseaseJudgeService:
    """Judge only disease claims and public-disease context."""

    async def review(
        self,
        *,
        title: str | None,
        body: str | None,
        model_config: dict[str, Any] | None = None,
    ) -> WangyueClaimPublicDiseaseJudgment:
        user_prompt = f"标题：{title or ''}\n正文：{body or ''}"
        call = await call_focused_judge(
            model_config=model_config,
            system_prompt=CLAIM_PUBLIC_DISEASE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            issue_codes=CLAIM_PUBLIC_DISEASE_ISSUE_CODES,
            max_tokens=300,
        )
        judgment = parse_wangyue_claim_public_disease_judgment(call.raw_response)
        judgment.runtime_metadata = call.runtime_metadata
        return judgment


def parse_wangyue_claim_public_disease_judgment(
    raw_response: str,
) -> WangyueClaimPublicDiseaseJudgment:
    label, issue_code, evidence = normalize_focused_judgment(
        raw_response,
        issue_codes=CLAIM_PUBLIC_DISEASE_ISSUE_CODES,
        fallback_issue_code="past_public_disease_reference",
    )
    return WangyueClaimPublicDiseaseJudgment(
        label=label,
        issue_code=issue_code,
        evidence=evidence,
        raw_response=raw_response[:2000],
    )
CLAIM_PUBLIC_DISEASE_SYSTEM_PROMPT = """你只审核旺玥文章中的疾病功效宣称、医疗背书、即时补救和公共疾病环境，不审核一般时间逻辑、产品事实、人味、种草强弱，也不改写。

判断标准：
1. 孩子出现当下症状后，马上换旺玥、多冲一杯或写成赶紧补救、缓解症状：block，immediate_rescue_claim。
2. 医生等医疗权威为旺玥背书防病功效：block，medical_authority_claim。把旺玥写成治疗疾病、解决感冒问题：block，medical_treatment_claim。
3. 保证喝了不会生病、防感冒或完全不用担心：block，disease_prevention_guarantee。
4. “现在/最近正是流感季”、班里当前大量孩子生病等公共疾病环境，用来衬托旺玥效果：block，current_public_disease_environment。
5. 过去发生的感冒、请假，以及长期使用后的全勤、少请假、小状况少些等普通自家观察：pass。不要因为出现感冒、请假、全勤就硬拦。
6. “感冒比以前少了”可以 pass 或 watch；标 watch 时用 own_illness_reduction_observation。明确过去式的同伴生病、班级请假可以 pass 或 watch；标 watch 时用 past_public_disease_reference。

issue_code 只能从以下值选择：none、own_illness_reduction_observation、past_public_disease_reference、immediate_rescue_claim、medical_authority_claim、medical_treatment_claim、disease_prevention_guarantee、current_public_disease_environment。label=pass 时 issue_code 必须是 none。

只输出 JSON object：{"label":"pass|watch|block","issue_code":"上述枚举之一","evidence":"原文证据"}。"""
