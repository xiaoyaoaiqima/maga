import pytest

from scripts.persist_a2_batch_check_expression_paths import (
    BATCH_VARIATION_REVIEW,
    CODE_NAMING_NOTE,
    COLOR_NOTE,
    EXPRESSION_PATHS,
    PROMPT_BUNDLE_UPDATES,
    SINGLE_POINT_NOTE,
    TARGET_RULE_IDS,
    merge_content,
)


def _item(rule_id: str, source_row_no: int) -> dict:
    return {
        "rule_id": rule_id,
        "source_row_no": source_row_no,
        "business_rule": rule_id,
        "prompt_mode": "comment_prompt_bundle",
        "comment_prompt_bundle": {"generation_instruction": "保留"},
        "examples": ["保留示例"],
    }


def test_merge_content_persists_paths_and_variation_review_without_touching_other_rules():
    content = {
        "items": [
            *[_item(rule_id, index) for index, rule_id in enumerate(TARGET_RULE_IDS, start=1)],
            _item("other", 6),
        ]
    }

    updated = merge_content(content)
    by_id = {item["rule_id"]: item for item in updated["items"]}

    assert updated["items"][-1] == content["items"][-1]
    for rule_id in TARGET_RULE_IDS:
        assert by_id[rule_id]["prompt_slots"] == {
            "本条表达路径": EXPRESSION_PATHS[rule_id]
        }
        assert by_id[rule_id]["prompt_slot_selection_mode"] == "round_robin"
        assert by_id[rule_id]["bundle_prompt_slots_source"] == "rule_asset"
        assert by_id[rule_id]["batch_variation_review"] == BATCH_VARIATION_REVIEW
        assert by_id[rule_id]["comment_prompt_bundle"] == {
            "generation_instruction": "保留",
            **PROMPT_BUNDLE_UPDATES[rule_id],
        }
        assert by_id[rule_id]["content_direction"] == PROMPT_BUNDLE_UPDATES[rule_id]["content_direction"]
        assert by_id[rule_id]["activity_material"] == PROMPT_BUNDLE_UPDATES[rule_id]["activity_material"]
        assert by_id[rule_id]["corpus"] == PROMPT_BUNDLE_UPDATES[rule_id]["content_direction"]
        assert by_id[rule_id]["examples"] == ["保留示例"]
        assert "delivery_selection" not in by_id[rule_id]


def test_merge_content_is_idempotent_and_replaces_old_paths():
    content = {
        "items": [
            {
                **_item(rule_id, index),
                "prompt_slots": {"本条表达路径": ["旧路径"]},
                "batch_variation_review": {"enabled": False},
            }
            for index, rule_id in enumerate(TARGET_RULE_IDS, start=1)
        ]
    }

    first = merge_content(content)
    second = merge_content(first)

    assert second == first


def test_merge_content_requires_all_target_rules():
    content = {
        "items": [
            _item(rule_id, index)
            for index, rule_id in enumerate(TARGET_RULE_IDS[:-1], start=1)
        ]
    }

    with pytest.raises(ValueError, match="a2_direct_49"):
        merge_content(content)


def test_expression_paths_keep_rule_facts_separate():
    assert all("扫码" not in path and "罐底" not in path for path in EXPRESSION_PATHS["a2_direct_45"])
    assert all("三方质检报告" not in path for path in EXPRESSION_PATHS["a2_direct_46"])
    assert all("报告内容不同" not in path for paths in EXPRESSION_PATHS.values() for path in paths)
    assert all("物流码" not in path and "二维码" not in path for paths in EXPRESSION_PATHS.values() for path in paths)
    assert all(len(paths) == 10 for paths in EXPRESSION_PATHS.values())
    assert all(
        any(marker in path for path in EXPRESSION_PATHS[rule_id] for marker in ("买过", "长期给宝宝喝", "习惯"))
        for rule_id in TARGET_RULE_IDS
    )


def test_merge_content_adds_new_business_notes_without_rewriting_examples():
    content = {
        "items": [
            _item("a2_direct_01", 1),
            _item("a2_direct_43", 2),
            *[_item(rule_id, index) for index, rule_id in enumerate(TARGET_RULE_IDS, start=3)],
        ]
    }

    updated = merge_content(content)
    by_id = {item["rule_id"]: item for item in updated["items"]}

    for rule_id in ("a2_direct_01", "a2_direct_43"):
        assert by_id[rule_id]["comment_prompt_bundle"]["notes"] == [COLOR_NOTE]
    for rule_id in TARGET_RULE_IDS:
        notes = by_id[rule_id]["comment_prompt_bundle"]["notes"]
        assert COLOR_NOTE in notes
        assert SINGLE_POINT_NOTE in notes
        assert by_id[rule_id]["examples"] == ["保留示例"]
    for rule_id in ("a2_direct_45", "a2_direct_46", "a2_direct_47"):
        assert CODE_NAMING_NOTE not in by_id[rule_id]["comment_prompt_bundle"]["notes"]
    for rule_id in ("a2_direct_48", "a2_direct_49"):
        assert CODE_NAMING_NOTE in by_id[rule_id]["comment_prompt_bundle"]["notes"]


def test_variation_review_tracks_observed_opener_and_closure_clusters():
    metrics = {
        item["group_key"]: item
        for item in BATCH_VARIATION_REVIEW["expression_frequency"]
    }

    assert metrics["opener_gang"]["match_mode"] == "prefix"
    assert metrics["closure_tashi"]["terms"] == ["踏实"]
    assert metrics["clarity_cluster"]["terms"] == ["清楚", "清晰", "直观"]
