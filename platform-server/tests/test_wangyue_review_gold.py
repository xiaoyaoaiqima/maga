"""Regression checks for Wangyue review gold datasets and test-case metadata."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.expert_eval import (
    TestCaseCreate as CaseCreate,
    TestCaseImportItem as CaseImportItem,
    TestCaseItem as CaseItem,
)
from app.services.forbidden_term_review_service import (
    WANGYUE_STATIC_FORBIDDEN_TERMS,
    find_forbidden_hits,
)
from app.services.product_experience_phrase_guard_service import review_product_experience_phrase
from app.services.test_case_service import TestCaseService as CaseService


GOLD_PATH = Path(__file__).parents[1] / "evals" / "wangyue_review_gold_v1_temporal.json"
PRODUCT_USAGE_GOLD_PATH = Path(__file__).parents[1] / "evals" / "wangyue_review_gold_v1_product_usage.json"
REWRITE_QUALITY_GOLD_PATH = Path(__file__).parents[1] / "evals" / "wangyue_review_gold_v1_rewrite_quality.json"


class _Result:
    def all(self) -> list[tuple[str]]:
        return []


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def execute(self, _statement: object) -> _Result:
        return _Result()

    async def commit(self) -> None:
        return None

    async def refresh(self, item: object) -> None:
        if getattr(item, "id", None) is None:
            item.id = len(self.added)


def test_wangyue_temporal_gold_slice_has_stable_labels_and_boundaries() -> None:
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    items = payload["items"]

    assert payload["dataset_code"] == "wangyue_review_gold_v1"
    assert payload["slice"] == "temporal_logic_v1"
    assert payload["review_status"] == "approved"
    assert len(items) == 15
    assert {item["meta"]["expected_label"] for item in items} == {"pass", "watch", "block"}

    case_codes = [item["meta"]["case_code"] for item in items]
    assert len(case_codes) == len(set(case_codes))
    assert all(item["meta"]["evidence"] for item in items)
    assert all(item["tags"]["dimension"] == "temporal_logic" for item in items)
    assert all(
        set(item["meta"].get("acceptable_labels") or [item["meta"]["expected_label"]])
        <= {"pass", "watch", "block"}
        for item in items
    )

    by_code = {item["meta"]["case_code"]: item for item in items}
    assert by_code["WYT-001"]["meta"]["expected_label"] == "block"
    assert by_code["WYT-001"]["meta"]["issue_code"] == "same_period_state_contradiction"
    assert by_code["WYT-003"]["meta"]["expected_label"] == "pass"
    assert by_code["WYT-005"]["meta"]["acceptable_labels"] == ["pass", "watch"]
    assert by_code["WYT-009"]["meta"]["expected_label"] == "watch"


def test_wangyue_product_usage_gold_slice_has_stable_labels_and_boundaries() -> None:
    payload = json.loads(PRODUCT_USAGE_GOLD_PATH.read_text(encoding="utf-8"))
    items = payload["items"]

    assert payload["dataset_code"] == "wangyue_review_gold_v1"
    assert payload["slice"] == "product_usage_facts_v1"
    assert payload["review_status"] == "approved"
    assert len(items) == 15
    assert {item["meta"]["expected_label"] for item in items} == {"pass", "block"}
    assert all(item["tags"]["dimension"] == "product_usage_facts" for item in items)

    case_codes = [item["meta"]["case_code"] for item in items]
    assert len(case_codes) == len(set(case_codes))
    by_code = {item["meta"]["case_code"]: item for item in items}
    assert by_code["WYU-009"]["meta"]["expected_label"] == "block"
    assert by_code["WYU-010"]["meta"]["expected_label"] == "pass"
    assert by_code["WYU-011"]["meta"]["expected_label"] == "pass"
    assert by_code["WYU-013"]["meta"]["issue_code"] == "wangyue_four_stage_association"


def test_wangyue_rewrite_quality_gold_slice_has_item5_regression_pair() -> None:
    payload = json.loads(REWRITE_QUALITY_GOLD_PATH.read_text(encoding="utf-8"))
    items = payload["items"]

    assert payload["dataset_code"] == "wangyue_review_gold_v1"
    assert payload["slice"] == "rewrite_quality_v1"
    assert payload["review_status"] == "approved"
    assert [item["case_code"] for item in items] == ["WYR-001", "WYR-002"]
    assert items[0]["expected_label"] == "reject"
    assert "时候交替" in items[0]["after"]
    assert items[1]["expected_label"] == "accept"


def test_approved_product_usage_gold_matches_current_hard_review() -> None:
    payload = json.loads(PRODUCT_USAGE_GOLD_PATH.read_text(encoding="utf-8"))
    plan = {
        "asset_key": "wangyue_v3_core_storyline_article_rules",
        "corpus": "0705旺玥活动",
    }
    mismatches = []

    for item in payload["items"]:
        review = review_product_experience_phrase(
            title=item["title"],
            body=item["content"],
            plan=plan,
        )
        forbidden_hits = find_forbidden_hits(
            f"{item['title']}\n{item['content']}",
            WANGYUE_STATIC_FORBIDDEN_TERMS,
        )
        predicted = "block" if review.rewrite_required or forbidden_hits else "pass"
        expected = item["meta"]["expected_label"]
        if predicted != expected:
            mismatches.append(
                {
                    "case_code": item["meta"]["case_code"],
                    "expected": expected,
                    "predicted": predicted,
                    "reasons": review.reasons,
                    "forbidden_hits": forbidden_hits,
                }
            )

    assert mismatches == []


def test_test_case_schema_exposes_gold_meta_and_tags() -> None:
    item = CaseItem.model_validate(
        SimpleNamespace(
            id=1,
            test_set_code="wangyue_review_gold_v1",
            title="时间逻辑样本",
            content="正文",
            image_url=None,
            meta={"expected_label": "block"},
            tags={"dimension": "temporal_logic"},
            enabled=1,
            create_time=None,
            update_time=None,
        )
    )

    assert item.meta == {"expected_label": "block"}
    assert item.tags == {"dimension": "temporal_logic"}


@pytest.mark.asyncio
async def test_test_case_service_persists_gold_meta_and_tags() -> None:
    session = _FakeSession()
    service = CaseService(session)  # type: ignore[arg-type]

    created = await service.create(
        CaseCreate(
            test_set_code="wangyue_review_gold_v1",
            title="同一时间窗口矛盾",
            content="这段时间总不舒服，这段时间状态一直挺稳。",
            meta={"expected_label": "block", "issue_code": "same_period_state_contradiction"},
            tags={"dimension": "temporal_logic"},
        )
    )

    assert created.meta == {
        "expected_label": "block",
        "issue_code": "same_period_state_contradiction",
    }
    assert created.tags == {"dimension": "temporal_logic"}

    imported, skipped = await service.batch_import(
        "wangyue_review_gold_v1",
        [
            CaseImportItem(
                title="清楚的前后阶段",
                content="前阵子容易不舒服，这段时间状态稳。",
                meta={"expected_label": "pass", "issue_code": "none"},
                tags={"dimension": "temporal_logic"},
            )
        ],
    )

    assert (imported, skipped) == (1, 0)
    imported_case = session.added[-1]
    assert imported_case.meta == {"expected_label": "pass", "issue_code": "none"}
    assert imported_case.tags == {"dimension": "temporal_logic"}
