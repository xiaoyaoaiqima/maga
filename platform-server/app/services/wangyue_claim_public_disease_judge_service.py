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
    "concrete_disease_scenario",
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
5. 不论过去或现在，只要展开感冒、咳嗽、传染、发烧、医院或请假等具体疾病、就医和请假场景，block，concrete_disease_scenario。明确写同伴生病，也按此项 block。
6. 少中招、容易中招、保护力在线、状态稳、小状况少些属于抽象保护力或状态表达，可以 pass；不能因为这些抽象表达出现“中招、保护力、状态、小状况”就误判为具体疾病场景。全勤或普通出勤记录本轮不单独 block，除非同时出现第 5 条的具体场景。

issue_code 只能从以下值选择：none、own_illness_reduction_observation、past_public_disease_reference、immediate_rescue_claim、medical_authority_claim、medical_treatment_claim、disease_prevention_guarantee、current_public_disease_environment、concrete_disease_scenario。label=pass 时 issue_code 必须是 none。

只输出 JSON object：{"label":"pass|watch|block","issue_code":"上述枚举之一","evidence":"原文证据"}。"""
