import json
from types import SimpleNamespace

import pytest

from scripts.update_comment_business_rule_item import (
    _content_with_deleted_item,
    _content_with_updated_corpus,
    _extract_examples_from_corpus,
    _load_new_corpus,
    _validate_delete_args,
)


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


def test_update_comment_business_rule_item_can_set_layered_comment_fields():
    content = {
        "items": [
            {
                "rule_id": "a2_direct_01",
                "business_rule": "有货-直给到货情绪",
                "source_row_no": 1,
                "corpus": "保留旧语料",
                "examples": ["旧示例"],
            }
        ]
    }
    args = SimpleNamespace(
        rule_id="a2_direct_01",
        source_row_no=None,
        business_rule=None,
        content_direction_text="写看到供货恢复消息后的即时反应。",
        activity_material_json=json.dumps(["a2已到货或来货", "用户可以买到新货"], ensure_ascii=False),
        examples_json=json.dumps(["a2终于到货了", "我也买到了新货了"], ensure_ascii=False),
    )

    updated, summary = _content_with_updated_corpus(content, args, new_corpus="")

    item = updated["items"][0]
    assert item["corpus"] == "保留旧语料"
    assert item["content_direction"] == "写看到供货恢复消息后的即时反应。"
    assert item["activity_material"] == ["a2已到货或来货", "用户可以买到新货"]
    assert item["examples"] == ["a2终于到货了", "我也买到了新货了"]
    assert summary["changed"] is True


def test_load_new_corpus_allows_variation_slot_only_update():
    args = SimpleNamespace(
        corpus_file=None,
        corpus_text=None,
        new_business_rule=None,
        variation_slots_json="[]",
    )

    assert _load_new_corpus(args) == ""


def test_update_comment_business_rule_item_can_set_ugc_post_type_only():
    content = {
        "items": [
            {
                "rule_id": "business_rule_002",
                "business_rule": "选奶复盘",
                "source_row_no": 2,
                "corpus": "保留语料",
                "ugc_post_type": "轻复盘型",
            }
        ]
    }
    args = SimpleNamespace(
        rule_id="business_rule_002",
        source_row_no=None,
        business_rule=None,
        new_business_rule=None,
        variation_slots_json=None,
        ugc_post_type="对比选择型",
    )

    updated, summary = _content_with_updated_corpus(content, args, new_corpus="")

    assert updated["items"][0]["corpus"] == "保留语料"
    assert updated["items"][0]["ugc_post_type"] == "对比选择型"
    assert summary["old_ugc_post_type"] == "轻复盘型"
    assert summary["new_ugc_post_type"] == "对比选择型"
    assert summary["changed"] is True


def test_delete_business_rule_item_preserves_other_items():
    content = {
        "items": [
            {
                "rule_id": "business_rule_002",
                "business_rule": "选奶复盘",
                "source_row_no": 2,
                "corpus": "保留语料",
            },
            {
                "rule_id": "business_rule_013",
                "business_rule": "对比选择",
                "source_row_no": 13,
                "corpus": "删除语料",
            },
        ]
    }
    args = SimpleNamespace(rule_id="business_rule_013", source_row_no=None, business_rule=None)

    updated, summary = _content_with_deleted_item(content, args)

    assert len(content["items"]) == 2
    assert updated["items"] == [content["items"][0]]
    assert summary["rule_id"] == "business_rule_013"
    assert summary["remaining_item_count"] == 1
    assert summary["deleted"] is True


def test_delete_business_rule_item_rejects_update_arguments():
    args = SimpleNamespace(
        corpus_file=None,
        corpus_text="新语料",
        new_business_rule=None,
        variation_slots_json=None,
        ugc_post_type=None,
        sync_examples_from_corpus=False,
    )

    with pytest.raises(ValueError, match="cannot be combined"):
        _validate_delete_args(args)
