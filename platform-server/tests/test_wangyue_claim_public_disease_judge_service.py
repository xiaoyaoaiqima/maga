"""Tests for the focused Wangyue claim/public-disease judge contract."""

import pytest

from app.services import focused_llm_judge_runtime as runtime_module
from app.services.executor_invocation_service import DirectLLMCallResult
from app.services.wangyue_claim_public_disease_judge_service import (
    CLAIM_PUBLIC_DISEASE_MODEL_CODE,
    CLAIM_PUBLIC_DISEASE_SYSTEM_PROMPT,
    WangyueClaimPublicDiseaseJudgeService,
    parse_wangyue_claim_public_disease_judgment,
)


def test_claim_public_disease_judge_uses_dedicated_model_code() -> None:
    assert CLAIM_PUBLIC_DISEASE_MODEL_CODE == "deepseek-v4-flash"


def test_parse_claim_public_disease_judgment_keeps_minimal_contract() -> None:
    result = parse_wangyue_claim_public_disease_judgment(
        '{"label":"block","issue_code":"immediate_rescue_claim","evidence":"打喷嚏后马上换旺玥"}'
    )

    assert result.model_dump() == {
        "label": "block",
        "issue_code": "immediate_rescue_claim",
        "evidence": "打喷嚏后马上换旺玥",
    }


def test_parse_claim_public_disease_judgment_normalizes_invalid_output_to_watch() -> None:
    result = parse_wangyue_claim_public_disease_judgment("not json")

    assert result.label == "watch"
    assert result.issue_code == "past_public_disease_reference"


def test_claim_public_disease_prompt_preserves_allowed_observations() -> None:
    assert "不要因为出现感冒、请假、全勤就硬拦" in CLAIM_PUBLIC_DISEASE_SYSTEM_PROMPT
    assert "不审核一般时间逻辑" in CLAIM_PUBLIC_DISEASE_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_claim_public_disease_judge_uses_direct_llm_metadata(monkeypatch) -> None:
    calls = []

    async def fake_call_direct_llm(**kwargs):
        calls.append(kwargs)
        return DirectLLMCallResult(
            content='{"label":"pass","issue_code":"none","evidence":"过去经历"}',
            model_code="test-model",
            provider_code="test-provider",
            provider_model="provider-test-model",
            usage={"input_tokens": 16, "output_tokens": 7, "total_tokens": 23},
            latency_ms=98,
        )

    monkeypatch.setattr(runtime_module, "call_direct_llm", fake_call_direct_llm)

    result = await WangyueClaimPublicDiseaseJudgeService().review(
        title="去年感冒那阵",
        body="去年孩子有阵子感冒，现在只是翻照片想起来。",
        model_config={"provider_code": "test-provider", "model_code": "test-model"},
    )

    assert result.label == "pass"
    assert len(calls) == 1
    assert result.runtime_metadata["usage"]["total_tokens"] == 23
    assert result.runtime_metadata["latency_ms"] == 98
