"""Tests for the focused Wangyue temporal-logic judge contract."""

import pytest

from app.services import focused_llm_judge_runtime as runtime_module
from app.services.executor_invocation_service import DirectLLMCallResult

from app.services.wangyue_temporal_logic_judge_service import (
    TEMPORAL_LOGIC_MODEL_CODE,
    TEMPORAL_LOGIC_MAX_TOKENS,
    TEMPORAL_LOGIC_SYSTEM_PROMPT,
    WangyueTemporalLogicJudgeService,
    _has_valid_judgment_contract,
    _merge_runtime_metadata,
    parse_wangyue_temporal_logic_judgment,
)


def test_temporal_logic_judge_uses_dedicated_model_code() -> None:
    assert TEMPORAL_LOGIC_MODEL_CODE == "deepseek-v4-flash"


def test_temporal_prompt_does_not_treat_meal_gap_as_immediate_rescue() -> None:
    assert "普通一顿饭没吃好" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "不属于立即补救" in TEMPORAL_LOGIC_SYSTEM_PROMPT


def test_temporal_prompt_covers_added_stage_and_duration_boundaries() -> None:
    assert "short_period_hard_reversal" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "missing_transition_duration" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "decision_execution_stage_conflict" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "recent_problem_long_usage_conflict" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "continuous_use_baseline_conflict" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "后来”单独出现只表示叙述顺序" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "“前阵子”固定表示距今15-45天" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "四个月约120天" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "不得因为“好像”判成轻微波动" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "优先用 insufficient_effect_duration" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "明确表示产品在不超过一天或极短期内生效" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "必须 block / insufficient_effect_duration，不得判 watch" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "两处“这段时间”属于同一窗口，必须 block" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "明确改成“前段时间他容易中招”" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "旧阶段与当前阶段已经分开，应 pass" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "补救行为或意图" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "不要求原文已经宣称产品生效" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "“流感”另属于确定性硬禁词" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "发布时间锚点是独立硬规则" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "不判断审核当天是否真的处于对应季节或天气" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "即使正文没有疾病、群体请假、产品效果、前后反转或其它时间矛盾" in TEMPORAL_LOGIC_SYSTEM_PROMPT
    assert "最近降温挺明显" in TEMPORAL_LOGIC_SYSTEM_PROMPT


def test_parse_temporal_logic_judgment_keeps_minimal_contract() -> None:
    result = parse_wangyue_temporal_logic_judgment(
        '{"label":"block","issue_code":"same_period_state_contradiction","evidence":"两个这段时间"}'
    )

    assert result.model_dump() == {
        "label": "block",
        "issue_code": "same_period_state_contradiction",
        "evidence": "两个这段时间",
    }
    assert result.raw_response == (
        '{"label":"block","issue_code":"same_period_state_contradiction","evidence":"两个这段时间"}'
    )


def test_parse_temporal_logic_judgment_accepts_added_issue_code() -> None:
    result = parse_wangyue_temporal_logic_judgment(
        '{"label":"block","issue_code":"decision_execution_stage_conflict","evidence":"还在纠结但已喝一周"}'
    )

    assert result.label == "block"
    assert result.issue_code == "decision_execution_stage_conflict"


def test_parse_temporal_logic_judgment_normalizes_invalid_output_to_watch() -> None:
    result = parse_wangyue_temporal_logic_judgment("not json")

    assert result.label == "watch"
    assert result.issue_code == "mixed_state_same_period"


def test_parse_temporal_logic_judgment_forces_pass_issue_to_none() -> None:
    result = parse_wangyue_temporal_logic_judgment(
        '```json\n{"label":"pass","issue_code":"publication_time_anchor","evidence":"去年冬天"}\n```'
    )

    assert result.label == "pass"
    assert result.issue_code == "none"
    assert result.evidence == "去年冬天"


def test_temporal_logic_contract_rejects_non_json_output() -> None:
    assert _has_valid_judgment_contract("not json") is False
    assert _has_valid_judgment_contract(
        '{"label":"block","issue_code":"same_period_state_contradiction","evidence":"两个这段时间"}'
    ) is True


def test_focused_contract_allows_pass_without_evidence_but_requires_watch_evidence() -> None:
    assert _has_valid_judgment_contract('{"label":"pass","issue_code":"none"}') is True
    assert _has_valid_judgment_contract('{"label":"pass"}') is True
    assert (
        _has_valid_judgment_contract(
            '{"label":"watch","issue_code":"mixed_state_same_period"}'
        )
        is False
    )


def test_temporal_logic_retry_metadata_sums_token_usage() -> None:
    merged = _merge_runtime_metadata(
        {"usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}, "latency_ms": 100},
        {
            "model_code": "deepseek-v4-flash",
            "usage": {"input_tokens": 11, "output_tokens": 3, "total_tokens": 14},
            "latency_ms": 150,
        },
    )

    assert merged["retry_count"] == 1
    assert merged["usage"] == {"input_tokens": 21, "output_tokens": 5, "total_tokens": 26}
    assert merged["latency_ms"] == 250


@pytest.mark.asyncio
async def test_temporal_logic_judge_uses_direct_llm_path(monkeypatch) -> None:
    calls = []

    async def fake_call_direct_llm(**kwargs):
        calls.append(kwargs)
        return DirectLLMCallResult(
            content='{"label":"pass","issue_code":"none","evidence":"时间阶段清楚"}',
            model_code="test-model",
            provider_code="test-provider",
            provider_model="provider-test-model",
            usage={"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            latency_ms=123,
        )

    monkeypatch.setattr(runtime_module, "call_direct_llm", fake_call_direct_llm)

    result = await WangyueTemporalLogicJudgeService().review(
        title="过去那阵",
        body="去年请过假，今年状态正常。",
        model_config={"provider_code": "test-provider", "model_code": "test-model"},
    )

    assert result.label == "pass"
    assert len(calls) == 1
    assert calls[0]["model_config"]["provider"] == "test-provider"
    assert calls[0]["model_config"]["model"] == "test-model"
    assert calls[0]["max_tokens"] == TEMPORAL_LOGIC_MAX_TOKENS == 800
    assert result.runtime_metadata == {
        "model_code": "test-model",
        "provider_code": "test-provider",
        "provider_model": "provider-test-model",
        "usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
        "latency_ms": 123,
        "retry_count": 0,
    }


@pytest.mark.asyncio
async def test_temporal_logic_judge_raises_when_retry_contract_is_still_invalid(monkeypatch) -> None:
    async def fake_call_direct_llm(**_kwargs):
        return DirectLLMCallResult(
            content='{"label":"watch"}',
            model_code="test-model",
            provider_code="test-provider",
            provider_model="provider-test-model",
            usage={"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
            latency_ms=80,
        )

    monkeypatch.setattr(runtime_module, "call_direct_llm", fake_call_direct_llm)

    with pytest.raises(ValueError, match="valid JSON contract after retry"):
        await WangyueTemporalLogicJudgeService().review(
            title="普通记录",
            body="孩子最近状态还行。",
            model_config={"provider_code": "test-provider", "model_code": "test-model"},
        )
