"""Tests for structured xhs-writer review reports."""

import pytest

from app.services.executor_invocation_service import MockExecutorInvocationClient


@pytest.mark.asyncio
async def test_mock_executor_review_returns_structured_review_report():
    client = MockExecutorInvocationClient()
    result = await client.invoke(
        invoke_url="mock://maga-worker/invoke",
        envelope={
            "stage_call_id": "stage-review",
            "capability": "xhs.run_ae_review",
            "input": {
                "draft": {"title": "便便不规律别急", "body": "源悦好消化易吸收，日常观察不替代专业建议。"},
                "structured_brief": {"product_topic": "宝宝便便不规律"},
                "generation_snapshot": {
                    "assets": {"compliance_rules": [{"dimension": "禁止治疗便秘", "risk_level": "high"}]}
                },
            },
        },
    )

    report = result.output["review_report"]
    assert result.output["hard_results"] == report["hard_results"]
    assert result.output["soft_scores"] == report["soft_scores"]
    assert report["rewrite_required"] is False
    assert report["risk_level"] == "high"
    assert [item["ae_code"] for item in report["hard_results"]] == ["brand_product_guard", "compliance_redline"]
    assert {item["ae_code"] for item in report["soft_scores"]} == {"xhs_structure", "naturalness_ai_smell"}
