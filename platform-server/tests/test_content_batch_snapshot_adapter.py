"""Tests for converting batch plans into executor generation snapshots."""

from app.services.content_batch_snapshot_adapter import (
    build_xhs_generation_snapshot_from_brief,
    build_xhs_generation_snapshot_from_plan,
)


def test_build_xhs_generation_snapshot_from_batch_plan_includes_assets_and_diversity():
    plan = {
        "item_no": 7,
        "asset_key": "yuanyue",
        "product_topic": "宝宝便便不规律",
        "target_audience": "新手妈妈",
        "style": "经验老道型",
        "painpoint_ref": {
            "asset_type": "painpoint_model",
            "asset_key": "yuanyue",
            "item_index": 0,
            "item_id": "pain_001",
            "snapshot": {"painpoint": "便便不规律", "description": "便便偏干", "selling_point": "好消化易吸收"},
        },
        "selling_point_ref": {
            "asset_type": "product_selling_points",
            "asset_key": "yuanyue",
            "item_index": 1,
            "item_id": "sell_002",
            "snapshot": {"selling_point": "好消化易吸收", "advantage": "软凝乳"},
        },
        "reference_example_refs": [
            {
                "asset_type": "reference_examples",
                "asset_key": "yuanyue",
                "item_index": 3,
                "item_id": "yuanyue_ref_004",
                "snapshot": {"title": "真实经验", "body": "先看便便状态", "painpoint": "便便偏干"},
            }
        ],
        "compliance_rule_refs": [
            {
                "asset_type": "compliance_rules",
                "asset_key": "yuanyue",
                "item_index": 2,
                "item_id": "rule_003",
                "snapshot": {"dimension": "禁止治疗便秘", "risk_level": "high"},
            }
        ],
        "diversity_slot": {
            "opening_type": "过来人提醒",
            "structure_type": "痛点-观察-建议",
            "emotion": "稳",
            "cta_type": "轻建议",
            "forbidden_overlap_group": "G07",
        },
    }

    snapshot = build_xhs_generation_snapshot_from_plan(plan, batch_id=1, batch_code="batch_demo")

    assert snapshot["brief"] == {
        "product_topic": "宝宝便便不规律",
        "target_audience": "新手妈妈",
        "style": "经验老道型",
    }
    assert snapshot["assets"]["painpoint"]["painpoint"] == "便便不规律"
    assert snapshot["assets"]["selling_point"]["selling_point"] == "好消化易吸收"
    assert snapshot["assets"]["reference_examples"][0]["title"] == "真实经验"
    assert snapshot["assets"]["compliance_rules"][0]["dimension"] == "禁止治疗便秘"
    assert snapshot["diversity_slot"]["opening_type"] == "过来人提醒"
    assert snapshot["batch_context"] == {"batch_id": 1, "batch_code": "batch_demo", "item_no": 7}
    assert snapshot["constraints"]["output_fields"] == ["title", "body"]
    assert snapshot["constraints"]["must_reference_example_without_copying"] is True


def test_build_xhs_generation_snapshot_from_brief_creates_minimal_single_generation_snapshot():
    snapshot = build_xhs_generation_snapshot_from_brief(
        product_topic="美素佳儿源悦",
        target_audience="新手妈妈",
        style="情绪共情",
    )

    assert snapshot["brief"] == {
        "product_topic": "美素佳儿源悦",
        "target_audience": "新手妈妈",
        "style": "情绪共情",
    }
    assert snapshot["assets"]["asset_key"] is None
    assert snapshot["assets"]["painpoint"] is None
    assert snapshot["assets"]["selling_point"] is None
    assert snapshot["assets"]["reference_examples"] == []
    assert snapshot["assets"]["compliance_rules"] == []
    assert snapshot["batch_context"]["source"] == "single_generation"
    assert snapshot["constraints"]["must_use_painpoint"] is False
    assert snapshot["constraints"]["must_reference_example_without_copying"] is False
    assert snapshot["constraints"]["output_fields"] == ["title", "body"]
