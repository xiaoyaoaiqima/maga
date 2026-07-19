"""Batch-level variation review for generated comments."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExpressionFrequencyRule:
    group_key: str
    terms: tuple[str, ...]
    max_ratio: float
    label: str
    risk_level: str = "medium"
    scan_fields: tuple[str, ...] = ("body",)
    match_mode: str = "contains"


class CommentBatchVariationReviewService:
    """Review batch-level sameness that cannot be judged from one comment alone."""

    def review_batch(self, items: list[Any]) -> dict[str, Any] | None:
        generated_items = [
            item
            for item in sorted(items, key=lambda value: int(getattr(value, "item_no", 0) or 0))
            if getattr(item, "status", None) == "generated" and str(getattr(item, "body", "") or "").strip()
        ]
        if not generated_items:
            return None
        config = _batch_variation_config(generated_items)
        if not config or config.get("enabled") is False:
            return None
        affects_hard_pass = config.get("affects_hard_pass") is not False
        rules = _expression_frequency_rules(config)
        expression_metrics = [_metric_for_rule(generated_items, rule) for rule in rules]
        opening_metrics = _opening_frequency_metrics(generated_items, config)
        if not expression_metrics and not opening_metrics:
            return None

        for item in generated_items:
            expression_issues = _issues_for_item(item, expression_metrics)
            opening_issues = _opening_issues_for_item(item, opening_metrics)
            _attach_variation_payload(
                item,
                expression_metrics=expression_metrics,
                opening_metrics=opening_metrics,
                issues=[*expression_issues, *opening_issues],
                affects_hard_pass=affects_hard_pass,
            )
        return {
            "source": "comment_batch_variation_review",
            "pass": all(metric["pass"] for metric in [*expression_metrics, *opening_metrics]),
            "affects_hard_pass": affects_hard_pass,
            "expression_frequency": {"metrics": expression_metrics},
            "opening_frequency": {"metrics": opening_metrics},
        }


def _metric_for_rule(items: list[Any], rule: ExpressionFrequencyRule) -> dict[str, Any]:
    hit_items = [
        item
        for item in items
        if _item_matches_rule(item, rule)
    ]
    total_count = len(items)
    max_allowed_count = _max_allowed_count(total_count, rule.max_ratio)
    overflow_items = hit_items[max_allowed_count:]
    ratio = len(hit_items) / total_count if total_count else 0
    return {
        "group_key": rule.group_key,
        "label": rule.label,
        "terms": list(rule.terms),
        "match_mode": rule.match_mode,
        "hit_item_nos": [getattr(item, "item_no", None) for item in hit_items],
        "overflow_item_nos": [getattr(item, "item_no", None) for item in overflow_items],
        "hit_count": len(hit_items),
        "total_count": total_count,
        "ratio": round(ratio, 4),
        "max_ratio": rule.max_ratio,
        "max_allowed_count": max_allowed_count,
        "risk_level": rule.risk_level,
        "pass": len(hit_items) <= max_allowed_count,
    }


def _issues_for_item(item: Any, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    item_no = getattr(item, "item_no", None)
    issues: list[dict[str, Any]] = []
    for metric in metrics:
        if item_no not in (metric.get("overflow_item_nos") or []):
            continue
        issues.append(
            {
                "issue_family": "expression_frequency",
                "code": "batch_expression_frequency_cap_exceeded",
                "message": f"{metric.get('label') or metric.get('group_key')} 表达在本批次出现过于集中",
                "evidence": metric.get("terms") or [],
                "risk_level": metric.get("risk_level") or "medium",
                "metric": metric,
            }
        )
    return issues


def _opening_frequency_metrics(items: list[Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    prefix_config = config.get("opening_prefix_frequency")
    if isinstance(prefix_config, dict) and prefix_config.get("enabled") is not False:
        prefix_chars = _bounded_int(prefix_config.get("prefix_chars"), default=3, minimum=1, maximum=10)
        metric = _opening_group_metric(
            items,
            config=prefix_config,
            group_key="opening_prefix_frequency",
            label=str(prefix_config.get("label") or f"开头前{prefix_chars}字").strip(),
            value_getter=lambda item: _opening_prefix(getattr(item, "body", ""), prefix_chars),
            details={"prefix_chars": prefix_chars},
        )
        if metric:
            metrics.append(metric)

    clause_config = config.get("opening_clause_frequency")
    if isinstance(clause_config, dict) and clause_config.get("enabled") is not False:
        metric = _opening_group_metric(
            items,
            config=clause_config,
            group_key="opening_clause_frequency",
            label=str(clause_config.get("label") or "相同开头分句").strip(),
            value_getter=lambda item: _opening_clause(getattr(item, "body", "")),
            details={},
        )
        if metric:
            metrics.append(metric)
    return metrics


def _opening_group_metric(
    items: list[Any],
    *,
    config: dict[str, Any],
    group_key: str,
    label: str,
    value_getter: Any,
    details: dict[str, Any],
) -> dict[str, Any] | None:
    groups: dict[str, list[Any]] = {}
    for item in items:
        value = str(value_getter(item) or "").strip()
        if value:
            groups.setdefault(value, []).append(item)
    if not groups:
        return None
    max_count = _optional_positive_int(config.get("max_count"))
    max_ratio = _ratio_value(config.get("max_ratio"))
    if max_count is None and max_ratio is None:
        return None
    allowed_count = max_count if max_count is not None else _max_allowed_count(len(items), max_ratio or 0)
    group_metrics: list[dict[str, Any]] = []
    overflow_item_nos: list[int] = []
    for value, hit_items in groups.items():
        overflow_items = hit_items[allowed_count:]
        overflow_nos = [int(getattr(item, "item_no", 0) or 0) for item in overflow_items]
        overflow_item_nos.extend(overflow_nos)
        if len(hit_items) > 1:
            group_metrics.append(
                {
                    "value": value,
                    "hit_count": len(hit_items),
                    "hit_item_nos": [int(getattr(item, "item_no", 0) or 0) for item in hit_items],
                    "overflow_item_nos": overflow_nos,
                    "pass": not overflow_items,
                }
            )
    return {
        "group_key": group_key,
        "label": label,
        "max_count": allowed_count,
        "max_ratio": max_ratio,
        "risk_level": str(config.get("risk_level") or "medium").strip(),
        "overflow_item_nos": overflow_item_nos,
        "groups": group_metrics,
        "pass": not overflow_item_nos,
        **details,
    }


def _opening_issues_for_item(item: Any, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    item_no = int(getattr(item, "item_no", 0) or 0)
    issues: list[dict[str, Any]] = []
    for metric in metrics:
        if item_no not in (metric.get("overflow_item_nos") or []):
            continue
        evidence = [
            group.get("value")
            for group in metric.get("groups") or []
            if item_no in (group.get("overflow_item_nos") or [])
        ]
        issues.append(
            {
                "issue_family": "opening_frequency",
                "code": "batch_opening_frequency_cap_exceeded",
                "message": f"{metric.get('label') or '评论开头'}在本批次出现过于集中",
                "evidence": evidence,
                "risk_level": metric.get("risk_level") or "medium",
                "metric": metric,
            }
        )
    return issues


def _opening_prefix(text: Any, prefix_chars: int) -> str:
    normalized = re.sub(r"^[\s，。！？!?,～~；;：:]+", "", str(text or ""))
    return normalized[:prefix_chars]


def _opening_clause(text: Any) -> str:
    normalized = re.sub(r"^[\s，。！？!?,～~；;：:]+", "", str(text or ""))
    return re.split(r"[，。！？!?,～~；;：:]", normalized, maxsplit=1)[0].strip()


def _attach_variation_payload(
    item: Any,
    *,
    expression_metrics: list[dict[str, Any]],
    opening_metrics: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    affects_hard_pass: bool,
) -> None:
    quality = dict(getattr(item, "quality_json", None) or {})
    existing = quality.get("batch_variation_review") if isinstance(quality.get("batch_variation_review"), dict) else {}
    similarity = _similarity_summary(quality)
    payload = {
        **existing,
        "source": "comment_batch_variation_review",
        "pass": not issues and similarity["pass"],
        "affects_hard_pass": affects_hard_pass,
        "similarity": similarity,
        "expression_frequency": {
            "pass": all(metric["pass"] for metric in expression_metrics),
            "metrics": expression_metrics,
            "issues": [issue for issue in issues if issue.get("issue_family") == "expression_frequency"],
        },
        "opening_frequency": {
            "pass": all(metric["pass"] for metric in opening_metrics),
            "metrics": opening_metrics,
            "issues": [issue for issue in issues if issue.get("issue_family") == "opening_frequency"],
        },
    }
    quality["batch_variation_review"] = payload
    if issues:
        if affects_hard_pass:
            _sync_issues_to_review_report(quality, issues)
        else:
            _sync_issues_to_advisory_report(quality, issues)
    item.quality_json = quality


def _sync_issues_to_review_report(quality: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    review_report = dict(quality.get("review_report") or {})
    hard_results = [
        dict(result)
        for result in review_report.get("hard_results") or []
        if isinstance(result, dict) and not str(result.get("ae_code") or "").startswith("batch_variation.")
    ]
    for issue in issues:
        hard_results.append(
            {
                "ae_code": f"batch_variation.{issue.get('code') or 'issue'}",
                "pass": False,
                "risk_level": issue.get("risk_level") or "medium",
                "feedback": issue.get("message") or "批次表达同质化审核未通过",
                "evidence": issue.get("evidence") or [],
            }
        )
    review_report["hard_results"] = hard_results
    review_report["rewrite_required"] = True
    review_report["rewrite_reason"] = "批次表达同质化审核未通过"
    quality["review_report"] = review_report
    quality["hard_pass"] = False


def _sync_issues_to_advisory_report(quality: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    review_report = dict(quality.get("review_report") or {})
    advisory_results = [
        dict(result)
        for result in review_report.get("advisory_results") or []
        if isinstance(result, dict) and not str(result.get("ae_code") or "").startswith("batch_variation.")
    ]
    for issue in issues:
        advisory_results.append(
            {
                "ae_code": f"batch_variation.{issue.get('code') or 'issue'}",
                "pass": False,
                "risk_level": issue.get("risk_level") or "medium",
                "feedback": issue.get("message") or "批次表达同质化提示",
                "evidence": issue.get("evidence") or [],
                "affects_hard_pass": False,
            }
        )
    review_report["advisory_results"] = advisory_results
    quality["review_report"] = review_report


def _similarity_summary(quality: dict[str, Any]) -> dict[str, Any]:
    rewrites = quality.get("similarity_rewrites") if isinstance(quality.get("similarity_rewrites"), list) else []
    review_report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
    failed_rewrites = [
        rewrite
        for rewrite in rewrites
        if isinstance(rewrite, dict) and rewrite.get("similarity_rewrite_passed") is False
    ]
    report_failed = review_report.get("similarity_rewrite_passed") is False
    return {
        "source": "comment_similarity_review",
        "pass": not failed_rewrites and not report_failed,
        "rewrite_count": len(rewrites),
        "rewrites": rewrites,
    }


def _expression_frequency_rules(config: dict[str, Any]) -> list[ExpressionFrequencyRule]:
    raw = config.get("expression_frequency")
    if isinstance(raw, dict):
        raw_rules = raw.get("rules") or raw.get("groups") or []
    else:
        raw_rules = raw or []
    rules: list[ExpressionFrequencyRule] = []
    for index, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            continue
        terms = tuple(str(term).strip() for term in item.get("terms") or [] if str(term).strip())
        if not terms:
            continue
        max_ratio = _ratio_value(item.get("max_ratio"))
        if max_ratio is None:
            continue
        group_key = str(item.get("group_key") or item.get("key") or f"expression_group_{index + 1}").strip()
        scan_fields = tuple(str(field).strip() for field in item.get("scan_fields") or ("body",) if str(field).strip())
        match_mode = str(item.get("match_mode") or "contains").strip().lower()
        if match_mode not in {"contains", "prefix"}:
            match_mode = "contains"
        rules.append(
            ExpressionFrequencyRule(
                group_key=group_key,
                label=str(item.get("label") or group_key).strip(),
                terms=terms,
                max_ratio=max_ratio,
                risk_level=str(item.get("risk_level") or "medium").strip(),
                scan_fields=scan_fields or ("body",),
                match_mode=match_mode,
            )
        )
    return rules


def _batch_variation_config(items: list[Any]) -> dict[str, Any]:
    for item in items:
        plan = getattr(item, "plan_json", None)
        if not isinstance(plan, dict):
            continue
        config = plan.get("batch_variation_review")
        if isinstance(config, dict):
            return config
    return {}


def _item_text(item: Any, fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for field in fields:
        normalized = field.lower()
        if normalized in {"body", "正文"}:
            values.append(str(getattr(item, "body", "") or ""))
        elif normalized in {"title", "标题"}:
            values.append(str(getattr(item, "title", "") or ""))
    return "\n".join(values)


def _item_matches_rule(item: Any, rule: ExpressionFrequencyRule) -> bool:
    text = _item_text(item, rule.scan_fields)
    if rule.match_mode == "prefix":
        normalized = text.lstrip()
        return any(normalized.startswith(term) for term in rule.terms)
    return any(term in text for term in rule.terms)


def _max_allowed_count(total_count: int, max_ratio: float) -> int:
    if max_ratio <= 0:
        return 0
    return max(1, math.floor(total_count * max_ratio))


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _ratio_value(value: Any) -> float | None:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return None
    if ratio < 0 or ratio > 1:
        return None
    return ratio
