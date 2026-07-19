"""Tests for deterministic Wangyue focused-review aggregation."""

from app.services.wangyue_focused_review_aggregator_service import (
    aggregate_wangyue_focused_reviews,
    compare_focused_review_with_legacy,
)


def _pass() -> dict[str, str]:
    return {"label": "pass", "issue_code": "none", "evidence": ""}


def test_aggregate_routes_compliance_before_fluency_without_rewriting_watch() -> None:
    result = aggregate_wangyue_focused_reviews(
        {
            "temporal_logic": {
                "label": "block",
                "issue_code": "publication_time_anchor",
                "evidence": "最近正是流感季",
            },
            "claim_public_disease": _pass(),
            "content_fit": {
                "label": "watch",
                "issue_code": "ad_like_closure",
                "evidence": "泛情绪收口",
            },
            "fluency": {
                "label": "block",
                "issue_code": "unnatural_collocation",
                "evidence": "饭菜经常不稳定",
            },
        },
        hard_pass=True,
    )

    assert result.decision == "block"
    assert result.rewrite_modes == ["compliance_cleanup", "fluency_humanize"]
    assert result.requires_rewrite is True
    assert result.can_auto_pool is False
    assert [issue.label for issue in result.issues] == ["block", "watch", "block"]


def test_aggregate_routes_added_temporal_issue_to_compliance_cleanup() -> None:
    result = aggregate_wangyue_focused_reviews(
        {
            "temporal_logic": {
                "label": "block",
                "issue_code": "pre_usage_effect_evidence",
                "evidence": "去年秋天早于喝旺玥小半年的使用周期",
            },
            "claim_public_disease": _pass(),
            "content_fit": _pass(),
            "fluency": _pass(),
        },
        hard_pass=True,
    )

    assert result.decision == "block"
    assert result.rewrite_modes == ["compliance_cleanup"]
    assert result.requires_rewrite is True


def test_aggregate_unavailable_dimension_is_watch_and_prevents_auto_pool() -> None:
    result = aggregate_wangyue_focused_reviews(
        {
            "temporal_logic": _pass(),
            "claim_public_disease": _pass(),
            "content_fit": _pass(),
        },
        hard_pass=True,
    )

    assert result.decision == "watch"
    assert result.unavailable_dimensions == ["fluency"]
    assert result.requires_rewrite is False
    assert result.can_auto_pool is False

    comparison = compare_focused_review_with_legacy(
        result,
        {"mark_rewrite_required": False, "issues": []},
    )
    assert comparison["focused_action"] == "hold"
    assert comparison["legacy_action"] == "pool"
    assert comparison["action_match"] is False


def test_aggregate_watch_can_pool_when_every_judge_is_available() -> None:
    result = aggregate_wangyue_focused_reviews(
        {
            "temporal_logic": _pass(),
            "claim_public_disease": {
                "label": "watch",
                "issue_code": "past_public_disease_reference",
                "evidence": "以前班里有人请假",
            },
            "content_fit": _pass(),
            "fluency": _pass(),
        },
        hard_pass=True,
    )

    assert result.decision == "watch"
    assert result.requires_rewrite is False
    assert result.can_auto_pool is True


def test_post_type_mismatch_blocks_without_inventing_content_in_rewrite() -> None:
    result = aggregate_wangyue_focused_reviews(
        {
            "temporal_logic": _pass(),
            "claim_public_disease": _pass(),
            "content_fit": {
                "label": "block",
                "issue_code": "post_type_mismatch",
                "evidence": "家庭清单里只有旺玥",
            },
            "fluency": _pass(),
        },
        hard_pass=True,
    )

    assert result.decision == "block"
    assert result.rewrite_modes == []
    assert result.requires_rewrite is False
    assert result.can_auto_pool is False

    comparison = compare_focused_review_with_legacy(
        result,
        {"mark_rewrite_required": False, "issues": []},
    )
    assert comparison["legacy_action"] == "pool"
    assert comparison["focused_action"] == "manual_review"
    assert comparison["action_match"] is False


def test_compare_uses_legacy_mark_rewrite_action_not_raw_model_opinion() -> None:
    aggregate = aggregate_wangyue_focused_reviews(
        {dimension: _pass() for dimension in (
            "temporal_logic",
            "claim_public_disease",
            "content_fit",
            "fluency",
        )},
        hard_pass=True,
    )

    comparison = compare_focused_review_with_legacy(
        aggregate,
        {
            "rewrite_required": True,
            "mark_rewrite_required": False,
            "issues": ["claim_risk"],
        },
    )

    assert comparison["legacy_requires_rewrite"] is False
    assert comparison["rewrite_decision_match"] is True
    assert comparison["action_match"] is True


def test_code_hard_block_is_outside_legacy_reviewer_action_comparison() -> None:
    aggregate = aggregate_wangyue_focused_reviews(
        {
            "temporal_logic": _pass(),
            "claim_public_disease": _pass(),
            "content_fit": _pass(),
            "fluency": _pass(),
        },
        hard_pass=False,
    )

    comparison = compare_focused_review_with_legacy(
        aggregate,
        {"mark_rewrite_required": False, "issues": []},
    )

    assert aggregate.blocked_by_code_hard is True
    assert comparison["focused_action"] == "hard_block"
    assert comparison["action_match"] is None
