"""Tests for executor mock using MAGA generation snapshots."""

import pytest

from app.services.executor_invocation_service import MockExecutorInvocationClient


@pytest.mark.asyncio
async def test_mock_executor_generate_draft_consumes_generation_snapshot_assets_and_diversity():
    client = MockExecutorInvocationClient()
    envelope = {
        "stage_call_id": "stage_1",
        "capability": "xhs.generate_draft",
        "input": {
            "structured_brief": {
                "product_topic": "宝宝便便不规律",
                "target_audience": "新手妈妈",
                "style": "经验老道型",
            },
            "generation_snapshot": {
                "assets": {
                    "painpoint": {"painpoint": "便便不规律", "description": "便便状态不稳定", "selling_point": "好消化易吸收"},
                    "selling_point": {"selling_point": "好消化易吸收", "advantage": "形成结构松散的软凝乳"},
                    "reference_examples": [
                        {"title": "纯分享，转源悦3个月的真实感受", "body": "先观察宝宝便便和喝奶状态，不要一上来就焦虑。"}
                    ],
                    "compliance_rules": [{"dimension": "禁止治疗便秘", "risk_level": "high"}],
                },
                "diversity_slot": {
                    "opening_type": "过来人提醒",
                    "structure_type": "痛点-观察-建议",
                    "emotion": "稳",
                    "cta_type": "轻建议",
                },
                "constraints": {"must_reference_example_without_copying": True},
            },
        },
    }

    result = await client.invoke(invoke_url="mock://maga-worker/invoke", envelope=envelope)

    draft = result.output["draft"]
    assert "便便不规律" in draft["title"]
    assert "源悦" in draft["body"]
    assert "好消化易吸收" in draft["body"]
    assert "过来人" in draft["body"]
    assert "治疗便秘" not in draft["body"]
    assert "改善便秘" not in draft["body"]
    assert "解决肠胃问题" not in draft["body"]
    assert "不要一上来就焦虑" not in draft["body"]


@pytest.mark.asyncio
async def test_mock_executor_pipeline_keeps_generation_snapshot_through_stages():
    client = MockExecutorInvocationClient()
    generation_snapshot = {
        "assets": {
            "painpoint": {"painpoint": "便便不规律", "description": "便便状态不稳定", "selling_point": "好消化易吸收"},
            "selling_point": {"selling_point": "好消化易吸收"},
            "reference_examples": [{"title": "真实经验", "body": "先观察便便状态。"}],
            "compliance_rules": [{"dimension": "禁止医疗化表述", "risk_level": "high"}],
        },
        "diversity_slot": {"opening_type": "真实经历", "structure_type": "经历-转折-选择"},
    }
    first = await client.invoke(
        invoke_url="mock://maga-worker/invoke",
        envelope={
            "stage_call_id": "stage_interpret",
            "capability": "xhs.interpret_brief",
            "input": {
                "product_topic": "宝宝便便不规律",
                "target_audience": "新手妈妈",
                "style": "经验老道型",
                "generation_snapshot": generation_snapshot,
            },
        },
    )

    assert first.output["generation_snapshot"] == generation_snapshot
