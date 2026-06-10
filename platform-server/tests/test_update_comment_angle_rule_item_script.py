from types import SimpleNamespace

import pytest

from scripts.update_comment_angle_rule_item import _content_with_updated_corpus, _extract_examples_from_corpus


def test_update_comment_angle_rule_item_by_source_row_no_preserves_other_items():
    content = {
        "items": [
            {
                "rule_id": "comment_angle_001",
                "comment_angle": "有货+批批检，补货前先扫物流码",
                "source_row_no": 1,
                "corpus": "旧语料1",
            },
            {
                "rule_id": "comment_angle_015",
                "comment_angle": "批批检+转奶，转奶前看蜡样那项",
                "source_row_no": 15,
                "corpus": "旧语料15",
            },
        ]
    }
    args = SimpleNamespace(rule_id=None, source_row_no=15, comment_angle=None)

    updated, summary = _content_with_updated_corpus(content, args, new_corpus="新语料15")

    assert content["items"][1]["corpus"] == "旧语料15"
    assert updated["items"][0]["corpus"] == "旧语料1"
    assert updated["items"][1]["corpus"] == "新语料15"
    assert summary["index"] == 1
    assert summary["rule_id"] == "comment_angle_015"
    assert summary["changed"] is True


def test_update_comment_angle_rule_item_show_current_does_not_change_corpus():
    content = {
        "items": [
            {
                "rule_id": "comment_angle_015",
                "comment_angle": "批批检+转奶，转奶前看蜡样那项",
                "source_row_no": 15,
                "corpus": "当前语料",
            }
        ]
    }
    args = SimpleNamespace(rule_id="comment_angle_015", source_row_no=None, comment_angle=None)

    updated, summary = _content_with_updated_corpus(content, args, new_corpus=None)

    assert updated["items"][0]["corpus"] == "当前语料"
    assert summary["old_corpus"] == "当前语料"
    assert summary["new_corpus"] == "当前语料"
    assert summary["changed"] is False


def test_update_comment_angle_rule_item_rejects_ambiguous_comment_angle():
    content = {
        "items": [
            {"rule_id": "a", "comment_angle": "同一个切角", "source_row_no": 1, "corpus": "a"},
            {"rule_id": "b", "comment_angle": "同一个切角", "source_row_no": 2, "corpus": "b"},
        ]
    }
    args = SimpleNamespace(rule_id=None, source_row_no=None, comment_angle="同一个切角")

    with pytest.raises(ValueError, match="selector matched multiple items"):
        _content_with_updated_corpus(content, args, new_corpus="新语料")


def test_update_comment_angle_rule_item_requires_items_list():
    args = SimpleNamespace(rule_id="comment_angle_015", source_row_no=None, comment_angle=None)

    with pytest.raises(ValueError, match="content_json.items must be a list"):
        _content_with_updated_corpus({"items": {}}, args, new_corpus="新语料")


def test_update_comment_angle_rule_item_can_sync_examples_from_corpus():
    content = {
        "items": [
            {
                "rule_id": "comment_angle_001",
                "comment_angle": "剧情讨论",
                "source_row_no": 1,
                "corpus": "旧语料",
                "examples": ["旧示例"],
            }
        ]
    }
    corpus = "剧情讨论：\n\n轻规则。\n\n示例：\n- 新示例1\n- 新示例2\n\n注意：示例只作为语义素材。"
    args = SimpleNamespace(
        rule_id="comment_angle_001",
        source_row_no=None,
        comment_angle=None,
        sync_examples_from_corpus=True,
    )

    updated, summary = _content_with_updated_corpus(content, args, new_corpus=corpus)

    assert updated["items"][0]["examples"] == ["新示例1", "新示例2"]
    assert summary["old_example_count"] == 1
    assert summary["new_example_count"] == 2


def test_extract_examples_from_corpus_stops_before_note():
    corpus = "标题：\n\n示例：\n- A\n- B\n\n注意：不要抽我\n- C"

    assert _extract_examples_from_corpus(corpus) == ["A", "B"]
