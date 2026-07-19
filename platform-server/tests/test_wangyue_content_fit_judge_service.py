"""Tests for the focused Wangyue content-fit judge contract."""

import pytest

from app.services import focused_llm_judge_runtime as runtime_module
from app.services.executor_invocation_service import DirectLLMCallResult
from app.services.wangyue_content_fit_judge_service import (
    CONTENT_FIT_ISSUE_CODES,
    CONTENT_FIT_MODEL_CODE,
    CONTENT_FIT_MAX_TOKENS,
    CONTENT_FIT_SYSTEM_PROMPT,
    WangyueContentFitJudgeService,
    parse_wangyue_content_fit_judgment,
)


def test_content_fit_judge_uses_dedicated_model_code() -> None:
    assert CONTENT_FIT_MODEL_CODE == "deepseek-v4-flash"


def test_parse_content_fit_judgment_keeps_minimal_contract() -> None:
    result = parse_wangyue_content_fit_judgment(
        '{"label":"block","issue_code":"unnatural_product_appearance","evidence":"安排进日常奶粉里"}'
    )

    assert result.model_dump() == {
        "label": "block",
        "issue_code": "unnatural_product_appearance",
        "evidence": "安排进日常奶粉里",
    }


def test_parse_content_fit_judgment_normalizes_invalid_output_to_watch() -> None:
    result = parse_wangyue_content_fit_judgment("not json")

    assert result.label == "watch"
    assert result.issue_code == "unnatural_product_appearance"


def test_content_fit_prompt_preserves_watch_only_boundaries() -> None:
    assert "正文已有具体生活反馈，直接 pass" in CONTENT_FIT_SYSTEM_PROMPT
    assert "仍然不能仅凭这些词 block" in CONTENT_FIT_SYSTEM_PROMPT
    assert "不能仅因节点多、链路完整而标 watch 或 block" in CONTENT_FIT_SYSTEM_PROMPT
    assert "节点密度和同类链路占比属于批量治理" in CONTENT_FIT_SYSTEM_PROMPT
    assert "overcomplete_decision_chain" not in CONTENT_FIT_ISSUE_CODES
    assert "不是合规 hard fail" in CONTENT_FIT_SYSTEM_PROMPT
    assert "没有写满两周、补货或明确复购" in CONTENT_FIT_SYSTEM_PROMPT
    assert "也必须 pass" in CONTENT_FIT_SYSTEM_PROMPT
    assert "完全没有实际使用" in CONTENT_FIT_SYSTEM_PROMPT
    assert "家里有这罐旺玥，日常安排会更好接上" in CONTENT_FIT_SYSTEM_PROMPT
    assert "正常冲一杯旺玥" in CONTENT_FIT_SYSTEM_PROMPT
    assert "新罐开封/刚开新罐”本身可以是普通生活动作" in CONTENT_FIT_SYSTEM_PROMPT
    assert "没有借开罐复盘产品理由，应 pass" in CONTENT_FIT_SYSTEM_PROMPT
    assert "不能因为目标帖子类型是复购/长期使用或后面有正常反馈而放行" in CONTENT_FIT_SYSTEM_PROMPT
    assert "不能仅因为出现“重新看奶粉、后来选了旺玥”就 block" in CONTENT_FIT_SYSTEM_PROMPT
    assert "目标帖子类型只用于生成多样化和批量分布优化" in CONTENT_FIT_SYSTEM_PROMPT
    assert "家庭清单只写旺玥" in CONTENT_FIT_SYSTEM_PROMPT
    assert "应 pass 或 watch" in CONTENT_FIT_SYSTEM_PROMPT
    assert "“营养满满”是普通宝妈口语里的正向评价" in CONTENT_FIT_SYSTEM_PROMPT
    assert "不能仅凭这个词判" in CONTENT_FIT_SYSTEM_PROMPT
    assert "消化吸收体验可以直接表达" in CONTENT_FIT_SYSTEM_PROMPT
    assert "形成明确消化效果链" in CONTENT_FIT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_content_fit_judge_passes_post_type_and_keeps_runtime_metadata(monkeypatch) -> None:
    calls = []

    async def fake_call_direct_llm(**kwargs):
        calls.append(kwargs)
        return DirectLLMCallResult(
            content='{"label":"pass","issue_code":"none","evidence":"补货动作自然"}',
            model_code="test-model",
            provider_code="test-provider",
            provider_model="provider-test-model",
            usage={"input_tokens": 15, "output_tokens": 6, "total_tokens": 21},
            latency_ms=87,
        )

    monkeypatch.setattr(runtime_module, "call_direct_llm", fake_call_direct_llm)

    result = await WangyueContentFitJudgeService().review(
        title="这罐快空了",
        body="这罐旺玥快空了，我又补了一罐。",
        post_type="复购长期使用",
        model_config={"provider_code": "test-provider", "model_code": "test-model"},
    )

    assert result.label == "pass"
    assert "目标帖子类型：复购长期使用" in calls[0]["user_prompt"]
    assert calls[0]["max_tokens"] == CONTENT_FIT_MAX_TOKENS == 800
    assert result.runtime_metadata["usage"]["total_tokens"] == 21
    assert result.runtime_metadata["latency_ms"] == 87
