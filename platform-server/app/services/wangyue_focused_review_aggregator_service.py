"""Deterministic aggregation for Wangyue focused review judgments."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


FOCUSED_REVIEW_DIMENSIONS = (
    "temporal_logic",
    "claim_public_disease",
    "content_fit",
    "fluency",
)
FOCUSED_REWRITE_MODE_BY_ISSUE = {
    ("temporal_logic", "same_period_state_contradiction"): "compliance_cleanup",
    ("temporal_logic", "immediate_rescue_causality"): "compliance_cleanup",
    ("temporal_logic", "insufficient_effect_duration"): "compliance_cleanup",
    ("temporal_logic", "publication_time_anchor"): "compliance_cleanup",
    ("temporal_logic", "short_period_hard_reversal"): "compliance_cleanup",
    ("temporal_logic", "missing_transition_duration"): "compliance_cleanup",
    ("temporal_logic", "decision_execution_stage_conflict"): "compliance_cleanup",
    ("temporal_logic", "recent_problem_long_usage_conflict"): "compliance_cleanup",
    ("temporal_logic", "continuous_use_baseline_conflict"): "compliance_cleanup",
    ("claim_public_disease", "immediate_rescue_claim"): "compliance_cleanup",
    ("claim_public_disease", "medical_authority_claim"): "compliance_cleanup",
    ("claim_public_disease", "medical_treatment_claim"): "compliance_cleanup",
    ("claim_public_disease", "disease_prevention_guarantee"): "compliance_cleanup",
    ("claim_public_disease", "current_public_disease_environment"): "compliance_cleanup",
    ("content_fit", "abstract_brief_translation"): "fluency_humanize",
    ("content_fit", "unnatural_product_appearance"): "fluency_humanize",
    ("fluency", "unnatural_collocation"): "fluency_humanize",
    ("fluency", "semantic_discontinuity"): "fluency_humanize",
    ("fluency", "title_body_contradiction"): "fluency_humanize",
    ("fluency", "instruction_leak"): "fluency_humanize",
    ("fluency", "incomplete_sentence"): "fluency_humanize",
}


@dataclass(frozen=True)
class WangyueFocusedReviewIssue:
    dimension: str
    label: str
    issue_code: str
    evidence: str
    rewrite_mode: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "label": self.label,
            "issue_code": self.issue_code,
            "evidence": self.evidence,
            "rewrite_mode": self.rewrite_mode,
        }


@dataclass(frozen=True)
class WangyueFocusedReviewAggregate:
    decision: str
    issues: list[WangyueFocusedReviewIssue] = field(default_factory=list)
    unavailable_dimensions: list[str] = field(default_factory=list)
    rewrite_modes: list[str] = field(default_factory=list)
    requires_rewrite: bool = False
    can_auto_pool: bool = False
    blocked_by_code_hard: bool = False

    def model_dump(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "issues": [issue.model_dump() for issue in self.issues],
            "unavailable_dimensions": list(self.unavailable_dimensions),
            "rewrite_modes": list(self.rewrite_modes),
            "requires_rewrite": self.requires_rewrite,
            "can_auto_pool": self.can_auto_pool,
            "blocked_by_code_hard": self.blocked_by_code_hard,
        }


def aggregate_wangyue_focused_reviews(
    judgments: Mapping[str, Any],
    *,
    hard_pass: bool | None,
) -> WangyueFocusedReviewAggregate:
    issues: list[WangyueFocusedReviewIssue] = []
    unavailable_dimensions: list[str] = []
    rewrite_modes: list[str] = []

    for dimension in FOCUSED_REVIEW_DIMENSIONS:
        judgment = judgments.get(dimension)
        if not isinstance(judgment, Mapping):
            unavailable_dimensions.append(dimension)
            continue
        label = str(judgment.get("label") or "").strip().lower()
        if label not in {"pass", "watch", "block"}:
            unavailable_dimensions.append(dimension)
            continue
        if label == "pass":
            continue
        issue_code = str(judgment.get("issue_code") or "none")
        rewrite_mode = (
            FOCUSED_REWRITE_MODE_BY_ISSUE.get((dimension, issue_code))
            if label == "block"
            else None
        )
        issue = WangyueFocusedReviewIssue(
            dimension=dimension,
            label=label,
            issue_code=issue_code,
            evidence=str(judgment.get("evidence") or "")[:300],
            rewrite_mode=rewrite_mode,
        )
        issues.append(issue)
        if rewrite_mode and rewrite_mode not in rewrite_modes:
            rewrite_modes.append(rewrite_mode)

    has_block = hard_pass is False or any(issue.label == "block" for issue in issues)
    if has_block:
        decision = "block"
    elif unavailable_dimensions or any(issue.label == "watch" for issue in issues):
        decision = "watch"
    else:
        decision = "pass"

    return WangyueFocusedReviewAggregate(
        decision=decision,
        issues=issues,
        unavailable_dimensions=unavailable_dimensions,
        rewrite_modes=rewrite_modes,
        requires_rewrite=bool(rewrite_modes) and hard_pass is not False,
        can_auto_pool=hard_pass is not False and not has_block and not unavailable_dimensions,
        blocked_by_code_hard=hard_pass is False,
    )


def compare_focused_review_with_legacy(
    aggregate: WangyueFocusedReviewAggregate,
    legacy_review: Mapping[str, Any] | None,
) -> dict[str, Any]:
    focused_action = _focused_review_action(aggregate)
    if not isinstance(legacy_review, Mapping):
        return {
            "legacy_available": False,
            "legacy_requires_rewrite": None,
            "focused_requires_rewrite": aggregate.requires_rewrite,
            "rewrite_decision_match": None,
            "legacy_action": None,
            "focused_action": focused_action,
            "action_match": None,
        }
    legacy_requires_rewrite = bool(
        legacy_review.get("mark_rewrite_required", legacy_review.get("rewrite_required", False))
    )
    if aggregate.blocked_by_code_hard:
        action_match = None
    elif aggregate.unavailable_dimensions:
        action_match = False
    elif aggregate.requires_rewrite:
        action_match = legacy_requires_rewrite
    elif aggregate.decision == "block":
        action_match = False
    else:
        action_match = not legacy_requires_rewrite
    legacy_action = "rewrite" if legacy_requires_rewrite else "pool"
    return {
        "legacy_available": True,
        "legacy_requires_rewrite": legacy_requires_rewrite,
        "legacy_issue_codes": list(legacy_review.get("issues") or []),
        "focused_requires_rewrite": aggregate.requires_rewrite,
        "rewrite_decision_match": legacy_requires_rewrite == aggregate.requires_rewrite,
        "legacy_action": legacy_action,
        "focused_action": focused_action,
        "action_match": action_match,
    }


def _focused_review_action(aggregate: WangyueFocusedReviewAggregate) -> str:
    if aggregate.blocked_by_code_hard:
        return "hard_block"
    if aggregate.unavailable_dimensions:
        return "hold"
    if aggregate.requires_rewrite:
        return "rewrite"
    if aggregate.decision == "block":
        return "manual_review"
    return "pool"
