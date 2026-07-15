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
