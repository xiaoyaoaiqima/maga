import pytest

from scripts.merge_a2_stock_direct_rules import (
    BATCH_VARIATION_REVIEW,
    CONTENT_DIRECTION,
    EXPRESSION_PATH_PROMPT_SLOTS,
    GENERATION_INSTRUCTION,
    merge_content,
)


def _item(rule_id: str, business_rule: str, source_row_no: int, examples: list[str]) -> dict:
    return {
        "rule_id": rule_id,
        "business_rule": business_rule,
        "source_row_no": source_row_no,
        "corpus": "旧内容方向",
        "examples": examples,
        "supplements": ["旧补充"],
        "comment_prompt_bundle": {
            "generation_instruction": "旧生文指令",
            "content_direction": "旧内容方向",
            "activity_material": [],
            "writing_requirements": [],
            "notes": [],
        },
    }


def test_merge_content_keeps_two_stock_direct_rules_and_updates_scenarios():
    content = {
        "items": [
            _item("a2_direct_01", "有货-直给简单报喜", 1, ["a2到货了"]),
            _item("a2_direct_43", "有货-直给已经买到", 2, ["我也买到了新货"]),
            _item("a2_direct_44", "有货-直给准备购买", 3, ["准备去看看"]),
            _item("other", "其他规则", 4, ["保留"]),
        ],
        "comment_scenarios": [
            {
                "scenario_code": "crm_ec_regular",
                "directions": [{"direction_code": "arrival", "rule_ids": ["a2_direct_01", "other"]}],
            }
        ],
    }

    updated = merge_content(content)
    by_id = {item["rule_id"]: item for item in updated["items"]}

    assert set(by_id) == {"a2_direct_01", "a2_direct_43", "other"}
    assert by_id["a2_direct_01"]["business_rule"] == "有货-直给-提产品"
    assert by_id["a2_direct_43"]["business_rule"] == "有货-直给-不提产品"
    assert by_id["a2_direct_01"]["content_direction"] == CONTENT_DIRECTION
    assert by_id["a2_direct_43"]["comment_prompt_bundle"]["generation_instruction"] == GENERATION_INSTRUCTION
    assert by_id["a2_direct_01"]["activity_material"] == [
        "a2或a2至初已经到货、来货，或重新能买到。"
    ]
    assert "不要提产品名" in by_id["a2_direct_43"]["activity_material"][0]
    assert by_id["a2_direct_01"]["examples"] == ["a2到货了"]
    assert by_id["a2_direct_43"]["examples"] == ["我也买到了新货"]
    for rule_id in ("a2_direct_01", "a2_direct_43"):
        assert by_id[rule_id]["prompt_slots"] == EXPRESSION_PATH_PROMPT_SLOTS
        assert by_id[rule_id]["prompt_slot_selection_mode"] == "round_robin"
        assert by_id[rule_id]["bundle_prompt_slots_source"] == "rule_asset"
        assert by_id[rule_id]["batch_variation_review"] == BATCH_VARIATION_REVIEW
        assert "delivery_selection" not in by_id[rule_id]
    assert [item["source_row_no"] for item in updated["items"]] == [1, 2, 3]
    assert updated["comment_scenarios"][0]["directions"][0]["rule_ids"] == [
        "a2_direct_01",
        "a2_direct_43",
        "other",
    ]


def test_merge_content_is_idempotent_when_removed_rule_is_already_absent():
    content = {
        "items": [
            _item("a2_direct_01", "有货-直给简单报喜", 1, []),
            _item("a2_direct_43", "有货-直给已经买到", 2, []),
            _item("other", "其他规则", 3, ["保留"]),
        ]
    }

    updated = merge_content(content)

    assert [item["rule_id"] for item in updated["items"]] == [
        "a2_direct_01",
        "a2_direct_43",
        "other",
    ]
    assert updated["items"][2] == content["items"][2]


def test_merge_content_requires_both_active_stock_rules():
    content = {"items": [_item("a2_direct_01", "有货-直给简单报喜", 1, [])]}

    with pytest.raises(ValueError, match="a2_direct_43"):
        merge_content(content)
