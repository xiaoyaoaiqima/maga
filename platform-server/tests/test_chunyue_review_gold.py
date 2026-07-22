from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.content_batch_execution_service import (
    ContentBatchExecutionService,
    _should_review_product_experience_llm_quality,
)
from app.services import product_experience_llm_review_service as review_module


GOLD_PATH = Path(__file__).parents[1] / "evals" / "chunyue_review_gold_v1_business_usability.json"


def test_chunyue_business_usability_gold_keeps_approved_boundaries() -> None:
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_code"] == "chunyue_review_gold_v1"
    assert payload["review_rubric_code"] == review_module.CHUNYUE_REVIEW_RUBRIC_CODE
    assert payload["review_status"] == "approved"
    labels = {
        item["meta"]["case_code"]: item["meta"]["expected_label"]
        for item in payload["items"]
    }
    assert labels == {
        "CYU-001": "hold_out",
        "CYU-002": "direct_pool",
        "CYU-003": "direct_pool",
        "CYU-004": "direct_pool",
        "CYU-005": "direct_pool",
        "CYU-006": "light_fix_usable",
        "CYU-007": "direct_pool",
        "CYU-008": "direct_pool",
        "CYU-009": "direct_pool",
    }


def test_chunyue_review_prompt_contains_user_confirmed_calibration() -> None:
    prompt = review_module._CHUNYUE_SYSTEM_PROMPT

    assert review_module.CHUNYUE_REVIEW_RUBRIC_CODE in prompt
    assert "奶源知根知底" in prompt
    assert "现在喝着挺安稳" in prompt
    assert "宝宝喝得挺顺口" in prompt
    assert "焦虑终结者" in prompt
    assert "让敏敏宝宝安心" in prompt
    assert "不强制文章完成“最终选择/购买莼悦”的闭环" in prompt
    assert "就靠这个依据确认的" in prompt
    assert "别的品牌介绍里从没这样说过" in prompt


def test_chunyue_review_user_prompt_carries_source_expression_and_rubric_code() -> None:
    payload = json.loads(
        review_module._user_prompt(
            title="被家长一句话种草了莼悦",
            body="回家确认属实，果断选了莼悦。现在喝着挺安稳。",
            plan={
                "asset_key": review_module.CHUNYUE_ARTICLE_ASSET_KEY,
                "selling_painpoint_expression": "欧盟和中国双重有机认证的有机产品",
                "selling_painpoint_expression_source_row_no": 30,
                "content_direction": "写妈妈了解到莼悦的过程。",
                "variation_slots": [
                    {"slot_code": "info_source", "value": "其他家长随口提到"}
                ],
            },
            phrase_review=None,
        )
    )

    assert payload["task"] == "review_chunyue_ugc_business_usability"
    assert payload["review_rubric_code"] == review_module.CHUNYUE_REVIEW_RUBRIC_CODE
    assert payload["plan"]["selling_painpoint_expression"] == "欧盟和中国双重有机认证的有机产品"
    assert payload["plan"]["selling_painpoint_expression_source_row_no"] == 30


def test_chunyue_asset_is_in_article_business_usability_replay_scope() -> None:
    assert _should_review_product_experience_llm_quality(
        {
            "rule_type": "business_rule",
            "asset_key": review_module.CHUNYUE_ARTICLE_ASSET_KEY,
        }
    )


@pytest.mark.asyncio
async def test_chunyue_review_persists_rubric_code(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_direct_llm_text(**kwargs):
        captured["system_prompt"] = kwargs["system_prompt"]
        captured["user_prompt"] = kwargs["user_prompt"]
        captured["max_tokens"] = kwargs["max_tokens"]
        return json.dumps(
            {
                "pass": True,
                "rewrite_required": False,
                "severity": "pass",
                "business_usability_tier": "direct_pool",
                "business_usability_reason": "抽象使用感受允许",
                "issues": [],
                "product_appearance_naturalness": 4,
                "decision_chain_fit": 4,
                "product_value_strength": 5,
                "human_realness": 4,
                "overall_reason": "可直接入池",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(review_module, "call_direct_llm_text", fake_call_direct_llm_text)
    review = await review_module.ProductExperienceLLMReviewService().review(
        title="被家长一句话种草了莼悦",
        body="回家确认属实，果断选了莼悦。现在喝着挺安稳。",
        plan={
            "asset_key": review_module.CHUNYUE_ARTICLE_ASSET_KEY,
            "selling_painpoint_expression": "欧盟和中国双重有机认证的有机产品",
            "model_config": {"provider_code": "aihubmix", "model_code": "deepseek-v4-flash"},
        },
    )

    assert captured["system_prompt"] == review_module._CHUNYUE_SYSTEM_PROMPT
    assert captured["max_tokens"] == 2400
    assert json.loads(str(captured["user_prompt"]))["review_rubric_code"] == review_module.CHUNYUE_REVIEW_RUBRIC_CODE
    assert review.review_rubric_code == review_module.CHUNYUE_REVIEW_RUBRIC_CODE
    assert review.review_attempts == 1
    assert review.model_dump()["review_rubric_code"] == review_module.CHUNYUE_REVIEW_RUBRIC_CODE


def test_chunyue_review_rubric_code_is_persisted_in_quality_summary() -> None:
    service = object.__new__(ContentBatchExecutionService)
    item = SimpleNamespace(quality_json={})
    review = review_module.ProductExperienceLLMReview(
        pass_=True,
        rewrite_required=False,
        severity="pass",
        business_usability_tier="direct_pool",
        review_rubric_code=review_module.CHUNYUE_REVIEW_RUBRIC_CODE,
    )

    service._mark_product_experience_llm_review(
        item,
        review,
        mark_rewrite_required=False,
    )

    assert (
        item.quality_json["product_experience_llm_quality_review"]["review_rubric_code"]
        == review_module.CHUNYUE_REVIEW_RUBRIC_CODE
    )


@pytest.mark.asyncio
async def test_chunyue_review_retries_once_after_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            "not-json",
            json.dumps(
                {
                    "pass": True,
                    "rewrite_required": False,
                    "severity": "pass",
                    "business_usability_tier": "direct_pool",
                    "business_usability_reason": "允许抽象使用感受",
                    "issues": [],
                    "overall_reason": "可直接入池",
                },
                ensure_ascii=False,
            ),
        ]
    )

    async def fake_call_direct_llm_text(**_kwargs):
        return next(responses)

    monkeypatch.setattr(review_module, "call_direct_llm_text", fake_call_direct_llm_text)
    review = await review_module.ProductExperienceLLMReviewService().review(
        title="被家长一句话种草了莼悦",
        body="现在喝着挺安稳。",
        plan={
            "asset_key": review_module.CHUNYUE_ARTICLE_ASSET_KEY,
            "selling_painpoint_expression": "欧盟和中国双重有机认证的有机产品",
            "model_config": {"provider_code": "aihubmix", "model_code": "deepseek-v4-flash"},
        },
    )

    assert review.review_attempts == 2
    assert review.business_usability_tier == "direct_pool"
