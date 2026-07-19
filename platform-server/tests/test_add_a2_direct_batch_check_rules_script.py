import pytest

from scripts.add_a2_direct_batch_check_rules import NEW_RULES, add_direct_rules


def test_add_direct_rules_appends_three_zero_shot_rules_without_touching_existing_items():
    content = {
        "items": [
            {
                "rule_id": "existing",
                "source_row_no": 32,
                "business_rule": "保留规则",
                "examples": ["保留示例"],
            }
        ]
    }

    updated = add_direct_rules(content)
    by_id = {item["rule_id"]: item for item in updated["items"]}

    assert content["items"] == [
        {
            "rule_id": "existing",
            "source_row_no": 32,
            "business_rule": "保留规则",
            "examples": ["保留示例"],
        }
    ]
    assert [item["rule_id"] for item in updated["items"][-3:]] == [
        "a2_direct_45",
        "a2_direct_46",
        "a2_direct_47",
    ]
    assert [item["source_row_no"] for item in updated["items"][-3:]] == [33, 34, 35]
    assert by_id["a2_direct_45"]["prompt_mode"] == "comment_prompt_bundle"
    assert by_id["a2_direct_45"]["comment_prompt_bundle"]["activity_material"] == [
        "a2公开每批检测信息。"
    ]
    assert by_id["a2_direct_46"]["examples"] == NEW_RULES[1]["examples"]
    assert "观望" in by_id["a2_direct_47"]["comment_prompt_bundle"]["notes"][1]
    assert all(item["supplements"] == [] for item in updated["items"][-3:])


def test_add_direct_rules_rejects_duplicate_rule_ids():
    content = {
        "items": [
            {
                "rule_id": "a2_direct_45",
                "source_row_no": 33,
            }
        ]
    }

    with pytest.raises(ValueError, match="already contains new rules"):
        add_direct_rules(content)
