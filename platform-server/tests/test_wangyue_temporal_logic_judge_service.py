"""Tests for the focused Wangyue temporal-logic judge contract."""

import pytest

from app.services import wangyue_temporal_logic_judge_service as judge_module

from app.services.wangyue_temporal_logic_judge_service import (
    WangyueTemporalLogicJudgeService,
    _has_valid_judgment_contract,
    _merge_runtime_metadata,
    parse_wangyue_temporal_logic_judgment,
)


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


def test_temporal_logic_retry_metadata_sums_token_usage() -> None:
    merged = _merge_runtime_metadata(
        {"usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}},
        {"model_code": "deepseek-v4-flash", "usage": {"input_tokens": 11, "output_tokens": 3, "total_tokens": 14}},
    )

    assert merged["retry_count"] == 1
    assert merged["usage"] == {"input_tokens": 21, "output_tokens": 5, "total_tokens": 26}


@pytest.mark.asyncio
async def test_temporal_logic_judge_uses_direct_llm_path(monkeypatch) -> None:
    calls = []

    async def fake_call_direct_llm_text(**kwargs):
        calls.append(kwargs)
        return '{"label":"pass","issue_code":"none","evidence":"时间阶段清楚"}'

    monkeypatch.setattr(judge_module, "call_direct_llm_text", fake_call_direct_llm_text)

    result = await WangyueTemporalLogicJudgeService().review(
        title="过去那阵",
        body="去年请过假，今年状态正常。",
        model_config={"provider_code": "test-provider", "model_code": "test-model"},
    )

    assert result.label == "pass"
    assert len(calls) == 1
    assert calls[0]["model_config"]["provider"] == "test-provider"
    assert calls[0]["model_config"]["model"] == "test-model"
