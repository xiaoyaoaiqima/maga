from scripts.migrate_a2_comment_prompt_bundles import RULE_CONTENT, migrate_content


def _business_rule_for_test(rule_id: str) -> str:
    if rule_id == "a2_direct_01":
        return "有货-旧规则"
    if rule_id in {"a2_direct_04", "a2_direct_05", "a2_direct_06", "a2_direct_21", "a2_direct_23", "a2_direct_35"}:
        return f"批批检-{rule_id}"
    if rule_id in {"a2_direct_10", "a2_direct_11", "a2_direct_13", "a2_direct_14", "a2_direct_24", "a2_direct_37"}:
        return f"转奶-{rule_id}"
    if rule_id in {"a2_direct_28", "a2_direct_29", "a2_direct_30", "a2_direct_31", "a2_direct_32", "a2_direct_33", "a2_direct_34"}:
        return f"会员权益-{rule_id}"
    return f"有货-{rule_id}"


def test_migrate_content_builds_bundles_and_splits_direct_arrival_rule():
    content = {
        "items": [
            {
                "rule_id": rule_id,
                "business_rule": _business_rule_for_test(rule_id),
                "corpus": "旧语料",
                "examples": ["旧示例"],
                "supplements": [],
                "source_row_no": index,
                "variation_slots": [{"slot_code": "old", "slot_name": "旧槽", "options": ["旧值"]}],
            }
            for index, rule_id in enumerate(RULE_CONTENT, start=1)
        ],
        "comment_tone_options": {"stock": [{"prompt": "旧语气"}]},
        "comment_persona_options": {"stock": [{"prompt": "旧人设"}]},
    }

    migrated = migrate_content(content)

    assert len(migrated["items"]) == len(RULE_CONTENT) + 2
    assert migrated["comment_prompt_bundle_schema_version"] == 1
    assert "comment_tone_options" not in migrated
    assert "comment_persona_options" not in migrated
    by_id = {item["rule_id"]: item for item in migrated["items"]}
    assert by_id["a2_direct_01"]["business_rule"] == "有货-直给简单报喜"
    assert by_id["a2_direct_43"]["business_rule"] == "有货-直给已经买到"
    assert by_id["a2_direct_44"]["business_rule"] == "有货-直给准备购买"
    assert by_id["a2_direct_01"]["comment_prompt_bundle"]["writing_requirements"] == ["字数在20字以内"]
    assert by_id["a2_direct_05"]["comment_prompt_bundle"]["notes"] == [
        "不补活动素材外的检测项目、数值或安全结论。"
    ]
    assert all(item["prompt_mode"] == "comment_prompt_bundle" for item in migrated["items"])
    assert all("variation_slots" not in item for item in migrated["items"])

    migrated_again = migrate_content(migrated)
    assert len(migrated_again["items"]) == len(RULE_CONTENT) + 2
    assert len({item["rule_id"] for item in migrated_again["items"]}) == len(RULE_CONTENT) + 2
