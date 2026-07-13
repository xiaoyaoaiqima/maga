import json
from types import SimpleNamespace

import pytest

from scripts.update_comment_business_rule_item import _content_with_updated_corpus, _extract_examples_from_corpus


def test_update_comment_business_rule_item_by_source_row_no_preserves_other_items():
    content = {
        "items": [
            {
                "rule_id": "business_rule_001",
                "business_rule": "有货+批批检，补货前先扫物流码",
                "source_row_no": 1,
                "corpus": "旧语料1",
            },
            {
                "rule_id": "business_rule_015",
                "business_rule": "批批检+转奶，转奶前看蜡样那项",
                "source_row_no": 15,
                "corpus": "旧语料15",
            },
        ]
    }
    args = SimpleNamespace(rule_id=None, source_row_no=15, business_rule=None)

    updated, summary = _content_with_updated_corpus(content, args, new_corpus="新语料15")

    assert content["items"][1]["corpus"] == "旧语料15"
    assert updated["items"][0]["corpus"] == "旧语料1"
    assert updated["items"][1]["corpus"] == "新语料15"
    assert summary["index"] == 1
    assert summary["rule_id"] == "business_rule_015"
    assert summary["changed"] is True


def test_update_comment_business_rule_item_show_current_does_not_change_corpus():
    content = {
        "items": [
            {
                "rule_id": "business_rule_015",
                "business_rule": "批批检+转奶，转奶前看蜡样那项",
                "source_row_no": 15,
                "corpus": "当前语料",
            }
        ]
    }
    args = SimpleNamespace(rule_id="business_rule_015", source_row_no=None, business_rule=None)

    updated, summary = _content_with_updated_corpus(content, args, new_corpus=None)

    assert updated["items"][0]["corpus"] == "当前语料"
    assert summary["old_corpus"] == "当前语料"
    assert summary["new_corpus"] == "当前语料"
    assert summary["changed"] is False


def test_update_comment_business_rule_item_rejects_ambiguous_business_rule():
    content = {
        "items": [
            {"rule_id": "a", "business_rule": "同一个业务规则", "source_row_no": 1, "corpus": "a"},
            {"rule_id": "b", "business_rule": "同一个业务规则", "source_row_no": 2, "corpus": "b"},
        ]
    }
    args = SimpleNamespace(rule_id=None, source_row_no=None, business_rule="同一个业务规则")

    with pytest.raises(ValueError, match="selector matched multiple items"):
        _content_with_updated_corpus(content, args, new_corpus="新语料")


def test_update_comment_business_rule_item_requires_items_list():
    args = SimpleNamespace(rule_id="business_rule_015", source_row_no=None, business_rule=None)

    with pytest.raises(ValueError, match="content_json.items must be a list"):
        _content_with_updated_corpus({"items": {}}, args, new_corpus="新语料")


def test_update_comment_business_rule_item_can_sync_examples_from_corpus():
    content = {
        "items": [
            {
                "rule_id": "business_rule_001",
                "business_rule": "剧情讨论",
                "source_row_no": 1,
                "corpus": "旧语料",
                "examples": ["旧示例"],
            }
        ]
    }
    corpus = "剧情讨论：\n\n轻规则。\n\n示例：\n- 新示例1\n- 新示例2\n\n注意：示例只作为语义素材。"
    args = SimpleNamespace(
        rule_id="business_rule_001",
        source_row_no=None,
        business_rule=None,
        sync_examples_from_corpus=True,
    )

    updated, summary = _content_with_updated_corpus(content, args, new_corpus=corpus)

    assert updated["items"][0]["examples"] == ["新示例1", "新示例2"]
    assert summary["old_example_count"] == 1
    assert summary["new_example_count"] == 2


def test_extract_examples_from_corpus_stops_before_note():
    corpus = "标题：\n\n示例：\n- A\n- B\n\n注意：不要抽我\n- C"

    assert _extract_examples_from_corpus(corpus) == ["A", "B"]


def test_update_comment_business_rule_item_can_set_variation_slots():
    content = {
        "items": [
            {
                "rule_id": "business_rule_002",
                "business_rule": "渠道和场景轮换",
                "source_row_no": 2,
                "corpus": "旧语料",
            }
        ]
    }
    slots = [
        {"slot_code": "info_source", "slot_name": "信息来源", "options": ["朋友", "导购"]}
    ]
    args = SimpleNamespace(
        rule_id="business_rule_002",
        source_row_no=None,
        business_rule=None,
        variation_slots_json=json.dumps(slots, ensure_ascii=False),
    )

    updated, summary = _content_with_updated_corpus(content, args, new_corpus="新语料")

    assert updated["items"][0]["variation_slots"] == slots
    assert summary["new_variation_slots"] == slots
    assert summary["changed"] is True
