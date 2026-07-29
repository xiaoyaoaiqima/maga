import pytest

from app.services import product_experience_llm_review_service as review_module
from app.services.product_experience_llm_review_service import ProductExperienceLLMReviewService


@pytest.mark.asyncio
async def test_product_experience_review_uses_direct_llm_path(monkeypatch) -> None:
    calls = []

    async def fake_call_direct_llm_text(**kwargs):
        calls.append(kwargs)
        return '{"pass":true,"rewrite_required":false,"severity":"pass","issues":[]}'

    monkeypatch.setattr(review_module, "call_direct_llm_text", fake_call_direct_llm_text)

    result = await ProductExperienceLLMReviewService().review(
        title="日常记录",
        body="家里一直喝旺玥，孩子日常状态不错。",
        plan={"model_config": {"provider_code": "test-provider", "model_code": "test-model"}},
    )

    assert result.pass_ is True
    assert len(calls) == 1
    assert calls[0]["model_config"]["provider"] == "test-provider"
    assert calls[0]["model_config"]["model"] == "test-model"
    assert calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_a2_review_retries_invalid_json_with_repair_prompt(monkeypatch) -> None:
    calls = []
    responses = iter(
        [
            "这篇可以直接使用",
            "仍然不是JSON",
            '{"pass":true,"rewrite_required":false,"severity":"pass","issues":[]}',
        ]
    )

    async def fake_call_direct_llm_text(**kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(review_module, "call_direct_llm_text", fake_call_direct_llm_text)

    result = await ProductExperienceLLMReviewService().review(
        title="a2至初活动",
        body="家里一直喝a2至初。",
        plan={
            "asset_key": "a2_reiyu_ugc_post_rules_v1",
            "model_config": {"provider_code": "test-provider", "model_code": "test-model"},
        },
    )

    assert result.pass_ is True
    assert result.review_attempts == 3
    assert len(calls) == 3
    assert calls[0]["temperature"] == 0.1
    assert calls[1]["temperature"] == 0.0
    assert all(call["response_format"] == {"type": "json_object"} for call in calls)
    assert "上一次输出无法解析" in calls[1]["user_prompt"]
    assert "只返回一个完整 JSON object" in calls[2]["user_prompt"]
