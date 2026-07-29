from __future__ import annotations

import json
from pathlib import Path


GOLD_PATH = (
    Path(__file__).parents[1]
    / "evals"
    / "a2_momclass_review_gold_v1_teacher_attribution.json"
)


def _items() -> dict[str, dict]:
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    return {item["meta"]["case_code"]: item for item in payload["items"]}


def test_a2_momclass_teacher_attribution_gold_contract() -> None:
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_code"] == "a2_momclass_review_gold_v1"
    assert payload["slice"] == "teacher_attribution_and_logic_v1"
    assert payload["review_status"] == "approved"
    assert payload["labels"] == ["pass", "light_fix", "reject"]
    assert len(payload["items"]) == 16


def test_teacher_and_other_mother_reported_reactions_pass() -> None:
    items = _items()

    for case_code in {
        "A2MC-TA-001",
        "A2MC-TA-002",
        "A2MC-TA-003",
        "A2MC-TA-004",
        "A2MC-TA-005",
        "A2MC-TA-006",
    }:
        assert items[case_code]["meta"]["expected_label"] == "pass"

    assert "老师说" in items["A2MC-TA-001"]["content"]
    assert "旁边宝妈说她家宝宝" in items["A2MC-TA-006"]["content"]


def test_gold_does_not_ban_colloquial_words_without_context() -> None:
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    items = _items()
    rubric = "\n".join(payload["rubric"])

    assert items["A2MC-TA-007"]["meta"]["expected_label"] == "pass"
    assert items["A2MC-TA-008"]["meta"]["expected_label"] == "pass"
    assert "不因单个‘才’字机械打回" in rubric
    assert "‘黄金便、睡得香、长肉、愿意喝、肚肚舒服’不是通用禁词" in rubric


def test_teacher_claim_can_pass_while_text_fragment_needs_fix() -> None:
    items = _items()
    fragmented = items["A2MC-TA-009"]

    assert fragmented["meta"]["expected_label"] == "light_fix"
    assert fragmented["meta"]["issue_code"] == "malformed_text_fragment"
    assert "老师还讲到" in fragmented["content"]
    assert "每天黄金便" in fragmented["content"]


def test_only_impossible_personal_experience_is_rejected() -> None:
    items = _items()

    assert items["A2MC-TA-015"]["meta"]["expected_label"] == "reject"
    assert items["A2MC-TA-016"]["meta"]["expected_label"] == "reject"
    assert "我还没生" in items["A2MC-TA-015"]["content"]
    assert "已经验证" in items["A2MC-TA-016"]["content"]
