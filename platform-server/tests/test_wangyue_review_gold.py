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
from app.services.wangyue_temporal_logic_judge_service import TEMPORAL_ISSUE_CODES


GOLD_PATH = Path(__file__).parents[1] / "evals" / "wangyue_review_gold_v1_temporal.json"
PRODUCT_USAGE_GOLD_PATH = Path(__file__).parents[1] / "evals" / "wangyue_review_gold_v1_product_usage.json"
REWRITE_QUALITY_GOLD_PATH = Path(__file__).parents[1] / "evals" / "wangyue_review_gold_v1_rewrite_quality.json"
REWRITE_QUALITY_HOLDOUT_PATH = (
    Path(__file__).parents[1]
    / "evals"
    / "wangyue_review_gold_v1_rewrite_quality_holdout_candidate.json"
)
FLUENCY_GOLD_PATH = Path(__file__).parents[1] / "evals" / "wangyue_review_gold_v1_fluency.json"
CONTENT_FIT_GOLD_PATH = Path(__file__).parents[1] / "evals" / "wangyue_review_gold_v1_content_fit.json"


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
    assert len(items) == 28
    assert {item["meta"]["expected_label"] for item in items} == {"pass", "watch", "block"}

    case_codes = [item["meta"]["case_code"] for item in items]
    assert len(case_codes) == len(set(case_codes))
    assert all(item["meta"]["evidence"] for item in items)
    assert all(item["tags"]["dimension"] == "temporal_logic" for item in items)
    assert {item["meta"]["issue_code"] for item in items} <= TEMPORAL_ISSUE_CODES
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
    assert by_code["WYT-016"]["meta"]["expected_label"] == "pass"
    assert by_code["WYT-017"]["meta"]["issue_code"] == "short_period_hard_reversal"
    assert "必须block，不得降为watch" in by_code["WYT-007"]["meta"]["reason"]
    assert by_code["WYT-018"]["meta"]["expected_label"] == "pass"
    assert by_code["WYT-019"]["meta"]["issue_code"] == "missing_transition_duration"
    assert by_code["WYT-021"]["meta"]["issue_code"] == "decision_execution_stage_conflict"
    assert by_code["WYT-023"]["meta"]["issue_code"] == "recent_problem_long_usage_conflict"
    assert "15-45天" in by_code["WYT-023"]["meta"]["reason"]
    assert "约为120天" in by_code["WYT-023"]["meta"]["reason"]
    assert by_code["WYT-025"]["meta"]["issue_code"] == "continuous_use_baseline_conflict"
    assert by_code["WYT-026"]["meta"]["expected_label"] == "pass"
    assert by_code["WYT-027"]["meta"]["expected_label"] == "pass"
    assert "前段时间" in by_code["WYT-027"]["content"]
    assert by_code["WYT-028"]["meta"]["issue_code"] == "publication_time_anchor"
    assert "流感" not in by_code["WYT-028"]["content"]
    assert "最近降温" in by_code["WYT-028"]["content"]
    assert "补救行为或意图本身就必须block" in by_code["WYT-006"]["meta"]["reason"]
    assert "确定性禁词审核直接ban" in by_code["WYT-011"]["meta"]["reason"]


def test_wangyue_product_usage_gold_slice_has_stable_labels_and_boundaries() -> None:
    payload = json.loads(PRODUCT_USAGE_GOLD_PATH.read_text(encoding="utf-8"))
    items = payload["items"]

    assert payload["dataset_code"] == "wangyue_review_gold_v1"
    assert payload["slice"] == "product_usage_facts_v1"
    assert payload["review_status"] == "approved"
    assert len(items) == 17
    assert {item["meta"]["expected_label"] for item in items} == {"pass", "block"}
    assert all(item["tags"]["dimension"] == "product_usage_facts" for item in items)

    case_codes = [item["meta"]["case_code"] for item in items]
    assert len(case_codes) == len(set(case_codes))
    by_code = {item["meta"]["case_code"]: item for item in items}
    assert by_code["WYU-009"]["meta"]["expected_label"] == "block"
    assert by_code["WYU-010"]["meta"]["expected_label"] == "pass"
    assert by_code["WYU-011"]["meta"]["expected_label"] == "pass"
    assert by_code["WYU-013"]["meta"]["issue_code"] == "wangyue_four_stage_association"
    assert by_code["WYU-016"]["meta"]["expected_label"] == "pass"
    assert by_code["WYU-017"]["meta"]["expected_label"] == "pass"


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


def test_wangyue_rewrite_quality_holdout_candidate_uses_real_before_after_pairs() -> None:
    payload = json.loads(REWRITE_QUALITY_HOLDOUT_PATH.read_text(encoding="utf-8"))
    items = payload["items"]

    assert payload["review_status"] == "candidate"
    assert payload["slice"] == "rewrite_quality_holdout_v1_candidate"
    assert len(items) == 15
    assert {item["suggested_label"] for item in items} == {"accept", "retry", "reject"}
    assert all(item["before"]["body"] and item["after"]["body"] for item in items)
    assert all(item["source"] for item in items)


def test_wangyue_fluency_gold_keeps_human_approved_incomplete_logic_samples() -> None:
    payload = json.loads(FLUENCY_GOLD_PATH.read_text(encoding="utf-8"))
    by_code = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert payload["review_status"] == "approved"
    assert len(payload["items"]) == 17
    assert by_code["WYL-016"]["meta"]["expected_label"] == "pass"
    assert "以前总要我托一把的" in by_code["WYL-016"]["content"]
    assert by_code["WYL-017"]["meta"]["expected_label"] == "pass"


def test_wangyue_content_fit_gold_sets_two_week_long_term_minimum() -> None:
    payload = json.loads(CONTENT_FIT_GOLD_PATH.read_text(encoding="utf-8"))
    by_code = {item["meta"]["case_code"]: item for item in payload["items"]}

    assert payload["review_status"] == "approved"
    assert len(payload["items"]) == 19
    assert by_code["WYF-002"]["meta"]["expected_label"] == "pass"
    assert by_code["WYF-002"]["meta"]["issue_code"] == "none"
    assert by_code["WYF-004"]["meta"]["expected_label"] == "block"
    assert by_code["WYF-004"]["meta"]["issue_code"] == "abstract_brief_translation"
    assert by_code["WYF-007"]["meta"]["expected_label"] == "pass"
    assert by_code["WYF-007"]["meta"]["issue_code"] == "none"
    assert by_code["WYF-013"]["meta"]["expected_label"] == "pass"
    assert by_code["WYF-013"]["meta"]["issue_code"] == "none"
    assert by_code["WYF-016"]["meta"]["expected_label"] == "pass"
    assert by_code["WYF-016"]["context"]["post_type"] == "复购/长期使用"
    assert by_code["WYF-017"]["meta"]["expected_label"] == "pass"
    assert "饭量不稳" in by_code["WYF-012"]["content"]
    assert "饭菜不稳定" not in by_code["WYF-012"]["content"]
    assert by_code["WYF-018"]["meta"]["expected_label"] == "pass"
    assert "一直会看的方向" not in by_code["WYF-010"]["content"]
    assert by_code["WYF-019"]["meta"]["expected_label"] == "pass"
    assert "不能因为出现“重新看奶粉、后来选了”" in by_code["WYF-009"]["meta"]["reason"]
    assert by_code["WYF-014"]["meta"]["expected_label"] == "watch"
    assert by_code["WYF-014"]["meta"]["acceptable_labels"] == ["pass", "watch"]


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
