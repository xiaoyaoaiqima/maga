import pytest

from scripts.upgrade_a2_four_comment_categories import (
    GENERATION_INSTRUCTION,
    upgrade_content,
)


def _item(rule_id: str, business_rule: str, source_row_no: int) -> dict:
    return {
        "rule_id": rule_id,
        "business_rule": business_rule,
        "source_row_no": source_row_no,
        "comment_prompt_bundle": {
            "generation_instruction": "旧生文指令",
            "content_direction": "旧内容方向",
            "activity_material": [],
            "writing_requirements": [],
            "notes": [],
        },
        "examples": [],
    }


def test_upgrade_content_updates_target_instructions_and_adds_two_direct_rules():
    content = {
        "items": [
            _item("stock", "有货-直给简单报喜", 1),
            _item("batch", "批批检-直给认可", 2),
            _item("member", "会员权益-集罐换礼", 3),
            _item("transfer", "转奶-转奶前先看报告", 4),
        ]
    }

    updated = upgrade_content(content)
    by_id = {item["rule_id"]: item for item in updated["items"]}

    assert content["items"][0]["comment_prompt_bundle"]["generation_instruction"] == "旧生文指令"
    assert by_id["stock"]["comment_prompt_bundle"]["generation_instruction"] == GENERATION_INSTRUCTION
    assert by_id["batch"]["comment_prompt_bundle"]["generation_instruction"] == GENERATION_INSTRUCTION
    assert by_id["member"]["comment_prompt_bundle"]["generation_instruction"] == GENERATION_INSTRUCTION
    assert by_id["transfer"]["comment_prompt_bundle"]["generation_instruction"] == "旧生文指令"
    assert by_id["a2_direct_48"]["source_row_no"] == 5
    assert by_id["a2_direct_49"]["source_row_no"] == 6
    assert by_id["a2_direct_49"]["comment_prompt_bundle"]["generation_instruction"] == GENERATION_INSTRUCTION
    assert "三方质检报告" in by_id["a2_direct_49"]["activity_material"][0]


def test_upgrade_content_rejects_duplicate_new_rule_ids():
    content = {"items": [_item("a2_direct_48", "批批检-罐底扫码直给", 1)]}

    with pytest.raises(ValueError, match="already contains new rules"):
        upgrade_content(content)
