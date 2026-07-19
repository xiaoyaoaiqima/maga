"""Tests for the focused Wangyue fluency judge contract."""

import pytest

from app.services import focused_llm_judge_runtime as runtime_module
from app.services.executor_invocation_service import DirectLLMCallResult
from app.services.wangyue_fluency_judge_service import (
    FLUENCY_SYSTEM_PROMPT,
    WangyueFluencyJudgeService,
    parse_wangyue_fluency_judgment,
)


def test_parse_fluency_judgment_keeps_minimal_contract() -> None:
    result = parse_wangyue_fluency_judgment(
        '{"label":"block","issue_code":"unnatural_collocation","evidence":"饭菜经常不稳定"}'
    )

    assert result.model_dump() == {
        "label": "block",
        "issue_code": "unnatural_collocation",
        "evidence": "饭菜经常不稳定",
    }


def test_parse_fluency_judgment_normalizes_invalid_output_to_watch() -> None:
    result = parse_wangyue_fluency_judgment("not json")

    assert result.label == "watch"
    assert result.issue_code == "semantic_discontinuity"


def test_fluency_prompt_protects_real_ugc_colloquial_language() -> None:
    assert "蔫蔫的、精神头足" in FLUENCY_SYSTEM_PROMPT
    assert "狗都嫌的年纪" in FLUENCY_SYSTEM_PROMPT
    assert "必须 pass" in FLUENCY_SYSTEM_PROMPT
    assert "保护屏障撑起来" in FLUENCY_SYSTEM_PROMPT
    assert "不能自动 block" in FLUENCY_SYSTEM_PROMPT
    assert "不要求补齐旧状态、参照系、时间点或完整因果链" in FLUENCY_SYSTEM_PROMPT
    assert "没有解释如何改善食欲" in FLUENCY_SYSTEM_PROMPT
    assert "逻辑不完整、因果偏松、参照不足都不是流畅性 block" in FLUENCY_SYSTEM_PROMPT
    assert "ta/Ta/TA" in FLUENCY_SYSTEM_PROMPT
    assert "中英文混写代词" in FLUENCY_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_fluency_judge_keeps_runtime_metadata(monkeypatch) -> None:
    async def fake_call_direct_llm(**_kwargs):
        return DirectLLMCallResult(
            content='{"label":"pass","issue_code":"none","evidence":"口语自然"}',
            model_code="test-model",
            provider_code="test-provider",
            provider_model="provider-test-model",
            usage={"input_tokens": 14, "output_tokens": 5, "total_tokens": 19},
            latency_ms=82,
        )

    monkeypatch.setattr(runtime_module, "call_direct_llm", fake_call_direct_llm)

    result = await WangyueFluencyJudgeService().review(
        title="玩回来也不蔫",
        body="以前玩回来蔫蔫的，这阵子精神头足。",
        model_config={"provider_code": "test-provider", "model_code": "test-model"},
    )

    assert result.label == "pass"
    assert result.runtime_metadata["usage"]["total_tokens"] == 19
    assert result.runtime_metadata["latency_ms"] == 82
