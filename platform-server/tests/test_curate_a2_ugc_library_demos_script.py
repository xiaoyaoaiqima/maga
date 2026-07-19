from scripts.curate_a2_ugc_library_demos import RULE_UPDATES, curate_content


def _item(rule_id: str, examples: list[str]) -> dict:
    return {
        "rule_id": rule_id,
        "business_rule": rule_id,
        "corpus": "旧内容方向",
        "content_direction": "旧内容方向",
        "examples": examples,
        "supplements": ["旧补充"],
        "comment_prompt_bundle": {
            "generation_instruction": "生成一条评论。",
            "content_direction": "旧内容方向",
            "activity_material": [],
            "writing_requirements": [],
            "notes": [],
        },
    }


def test_curate_content_updates_selected_rules_without_touching_other_rules():
    content = {
        "items": [
            *[_item(rule_id, ["旧示例"]) for rule_id in RULE_UPDATES],
            _item("untouched", ["保留示例"]),
        ]
    }

    updated = curate_content(content)
    by_id = {item["rule_id"]: item for item in updated["items"]}

    assert content["items"][0]["examples"] == ["旧示例"]
    assert by_id["untouched"]["examples"] == ["保留示例"]
    assert by_id["a2_direct_43"]["examples"] == RULE_UPDATES["a2_direct_43"]["examples"]
    assert by_id["a2_direct_28"]["supplements"] == []
    assert "自行车" in "\n".join(by_id["a2_direct_28"]["examples"])
    assert "扭扭车" in "\n".join(by_id["a2_direct_28"]["examples"])
    assert "婴儿推车" in "\n".join(by_id["a2_direct_28"]["examples"])
    assert by_id["a2_direct_28"]["activity_material"] == RULE_UPDATES["a2_direct_28"]["activity_material"]
    assert (
        by_id["a2_direct_31"]["comment_prompt_bundle"]["activity_material"]
        == RULE_UPDATES["a2_direct_31"]["activity_material"]
    )
    assert "宝宝夏凉被" in "\n".join(by_id["a2_direct_31"]["examples"])
    assert "a2&小马宝莉黄金手串" in "\n".join(by_id["a2_direct_31"]["examples"])
    assert "a2营养全家礼" in "\n".join(by_id["a2_direct_31"]["examples"])
    assert "积分" in "\n".join(by_id["a2_direct_31"]["examples"])
    assert by_id["a2_direct_28"]["corpus"] == RULE_UPDATES["a2_direct_28"]["content_direction"]
    assert (
        by_id["a2_direct_28"]["comment_prompt_bundle"]["content_direction"]
        == RULE_UPDATES["a2_direct_28"]["content_direction"]
    )
    assert "🍊" not in "\n".join(by_id["a2_direct_33"]["examples"])
