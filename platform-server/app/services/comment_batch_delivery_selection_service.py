"""Select a diverse delivery subset from an oversampled comment batch."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any


class CommentBatchDeliverySelectionService:
    """Keep business eligibility separate from batch-level delivery selection."""

    def select_batch(self, items: list[Any]) -> dict[str, Any] | None:
        generated_items = [
            item
            for item in sorted(items, key=lambda value: int(getattr(value, "item_no", 0) or 0))
            if getattr(item, "status", None) == "generated" and str(getattr(item, "body", "") or "").strip()
        ]
        if not generated_items:
            return None
        config = _delivery_selection_config(generated_items)
        if not config or config.get("enabled") is False:
            return None

        target_count = _bounded_int(config.get("target_count"), default=0, minimum=0, maximum=300)
        if target_count <= 0:
            return None
        max_similarity = _ratio_value(config.get("max_similarity"), default=0.45)
        require_hard_pass = config.get("require_hard_pass") is not False
        prefix_config = _frequency_config(config.get("opening_prefix_frequency"), default_max_count=5)
        first_char_config = _frequency_config(config.get("opening_first_char_frequency"), default_max_count=None)
        clause_config = _frequency_config(config.get("opening_clause_frequency"), default_max_count=2)

        candidates: list[dict[str, Any]] = []
        exact_duplicate_items: list[Any] = []
        ineligible_items: list[Any] = []
        seen: set[str] = set()
        for item in generated_items:
            quality = getattr(item, "quality_json", None) or {}
            if require_hard_pass and quality.get("hard_pass") is not True:
                ineligible_items.append(item)
                continue
            body = str(getattr(item, "body", "") or "").strip()
            normalized = _normalized(body)
            if not normalized:
                ineligible_items.append(item)
                continue
            if normalized in seen:
                exact_duplicate_items.append(item)
                continue
            seen.add(normalized)
            candidates.append(
                {
                    "item": item,
                    "body": body,
                    "normalized": normalized,
                    "ngrams": _ngrams(body),
                    "score": _quality_score(item),
                    "stable_key": _stable_key(item),
                }
            )

        selected = _select_diverse(
            candidates,
            target_count=target_count,
            max_similarity=max_similarity,
            prefix_config=prefix_config,
            first_char_config=first_char_config,
            clause_config=clause_config,
        )
        selected_ids = {id(candidate["item"]) for candidate in selected}
        selected_item_nos = [int(getattr(candidate["item"], "item_no", 0) or 0) for candidate in selected]
        selected_count = len(selected)
        shortfall_count = max(0, target_count - selected_count)
        suggested_bulk_refill_count = _suggested_bulk_refill_count(shortfall_count, config)
        max_pairwise_similarity = _max_pairwise_similarity(selected)
        summary = {
            "source": "comment_batch_delivery_selection",
            "target_count": target_count,
            "generated_count": len(generated_items),
            "eligible_count": len(candidates),
            "selected_count": selected_count,
            "shortfall_count": shortfall_count,
            "suggested_bulk_refill_count": suggested_bulk_refill_count,
            "exact_duplicate_count": len(exact_duplicate_items),
            "business_ineligible_count": len(ineligible_items),
            "max_pairwise_similarity": round(max_pairwise_similarity, 4),
            "selected_item_nos": selected_item_nos,
            "config": {
                "max_similarity": max_similarity,
                "require_hard_pass": require_hard_pass,
                "opening_prefix_frequency": prefix_config,
                "opening_first_char_frequency": first_char_config,
                "opening_clause_frequency": clause_config,
            },
        }

        duplicate_ids = {id(item) for item in exact_duplicate_items}
        ineligible_ids = {id(item) for item in ineligible_items}
        selected_rank = {id(candidate["item"]): index for index, candidate in enumerate(selected, start=1)}
        for item in generated_items:
            item_id = id(item)
            quality = dict(getattr(item, "quality_json", None) or {})
            selected_flag = item_id in selected_ids
            reason = None
            if item_id in ineligible_ids:
                reason = "business_hard_pass_required"
            elif item_id in duplicate_ids:
                reason = "exact_duplicate"
            elif not selected_flag:
                reason = _non_selection_reason(
                    item,
                    selected,
                    max_similarity=max_similarity,
                    prefix_config=prefix_config,
                    first_char_config=first_char_config,
                    clause_config=clause_config,
                )
            quality["delivery_selection"] = {
                **summary,
                "selected": selected_flag,
                "delivery_rank": selected_rank.get(item_id),
                "non_selection_reason": reason,
            }
            item.quality_json = quality
        return summary


def _select_diverse(
    candidates: list[dict[str, Any]],
    *,
    target_count: int,
    max_similarity: float,
    prefix_config: dict[str, int] | None,
    first_char_config: dict[str, int] | None,
    clause_config: dict[str, int] | None,
) -> list[dict[str, Any]]:
    remaining = sorted(candidates, key=lambda item: (-item["score"], item["stable_key"]))
    selected: list[dict[str, Any]] = []
    prefix_counts: Counter[str] = Counter()
    first_char_counts: Counter[str] = Counter()
    clause_counts: Counter[str] = Counter()
    while remaining and len(selected) < target_count:
        ranked: list[tuple[float, int, str, dict[str, Any]]] = []
        for candidate in remaining:
            body = candidate["body"]
            if _frequency_cap_hit(body, prefix_counts, prefix_config, value_kind="prefix"):
                continue
            if _frequency_cap_hit(body, first_char_counts, first_char_config, value_kind="first_char"):
                continue
            if _frequency_cap_hit(body, clause_counts, clause_config, value_kind="clause"):
                continue
            candidate_similarity = max(
                (_jaccard(candidate["ngrams"], item["ngrams"]) for item in selected),
                default=0.0,
            )
            if candidate_similarity >= max_similarity:
                continue
            ranked.append((candidate_similarity, -candidate["score"], candidate["stable_key"], candidate))
        if not ranked:
            break
        _, _, _, chosen = min(ranked)
        remaining.remove(chosen)
        selected.append(chosen)
        _increment_frequency(chosen["body"], prefix_counts, prefix_config, value_kind="prefix")
        _increment_frequency(chosen["body"], first_char_counts, first_char_config, value_kind="first_char")
        _increment_frequency(chosen["body"], clause_counts, clause_config, value_kind="clause")
    return selected


def _quality_score(item: Any) -> int:
    quality = getattr(item, "quality_json", None) or {}
    review = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
    body = str(getattr(item, "body", "") or "")
    score = 100
    if quality.get("hard_pass") is True:
        score += 20
    if review.get("rewrite_required") is not True:
        score += 5
    if 5 <= len(body) <= 45:
        score += 3
    if len(body) > 80:
        score -= 10
    return score


def _non_selection_reason(
    item: Any,
    selected: list[dict[str, Any]],
    *,
    max_similarity: float,
    prefix_config: dict[str, int] | None,
    first_char_config: dict[str, int] | None,
    clause_config: dict[str, int] | None,
) -> str:
    body = str(getattr(item, "body", "") or "")
    prefix_counts = Counter(
        _opening_value(candidate["body"], prefix_config, value_kind="prefix")
        for candidate in selected
        if prefix_config
    )
    first_char_counts = Counter(
        _opening_value(candidate["body"], first_char_config, value_kind="first_char")
        for candidate in selected
        if first_char_config
    )
    clause_counts = Counter(
        _opening_value(candidate["body"], clause_config, value_kind="clause")
        for candidate in selected
        if clause_config
    )
    if _frequency_cap_hit(body, prefix_counts, prefix_config, value_kind="prefix"):
        return "opening_prefix_cap_exceeded"
    if _frequency_cap_hit(body, first_char_counts, first_char_config, value_kind="first_char"):
        return "opening_first_char_cap_exceeded"
    if _frequency_cap_hit(body, clause_counts, clause_config, value_kind="clause"):
        return "opening_clause_cap_exceeded"
    similarity = max(
        (_jaccard(_ngrams(body), candidate["ngrams"]) for candidate in selected),
        default=0.0,
    )
    if similarity >= max_similarity:
        return "similarity_threshold_exceeded"
    return "delivery_target_reached"


def _frequency_config(value: Any, *, default_max_count: int | None) -> dict[str, int] | None:
    if not isinstance(value, dict) or value.get("enabled") is False:
        return None
    max_count = _bounded_int(value.get("max_count"), default=default_max_count or 0, minimum=0, maximum=300)
    if max_count <= 0:
        return None
    return {
        "prefix_chars": _bounded_int(value.get("prefix_chars"), default=3, minimum=1, maximum=10),
        "max_count": max_count,
    }


def _frequency_cap_hit(
    body: str,
    counts: Counter[str],
    config: dict[str, int] | None,
    *,
    value_kind: str,
) -> bool:
    if not config:
        return False
    value = _opening_value(body, config, value_kind=value_kind)
    return bool(value) and counts[value] >= config["max_count"]


def _increment_frequency(
    body: str,
    counts: Counter[str],
    config: dict[str, int] | None,
    *,
    value_kind: str,
) -> None:
    if not config:
        return
    value = _opening_value(body, config, value_kind=value_kind)
    if value:
        counts[value] += 1


def _opening_value(body: str, config: dict[str, int] | None, *, value_kind: str) -> str:
    if not config:
        return ""
    normalized = re.sub(r"^[\s，。！？!?,～~；;：:]+", "", body)
    if value_kind == "clause":
        return re.split(r"[，。！？!?,～~；;：:]", normalized, maxsplit=1)[0].strip()
    if value_kind == "first_char":
        return normalized[:1]
    return normalized[: config["prefix_chars"]]


def _max_pairwise_similarity(selected: list[dict[str, Any]]) -> float:
    maximum = 0.0
    for index, left in enumerate(selected):
        for right in selected[index + 1 :]:
            maximum = max(maximum, _jaccard(left["ngrams"], right["ngrams"]))
    return maximum


def _suggested_bulk_refill_count(shortfall_count: int, config: dict[str, Any]) -> int:
    if shortfall_count <= 0:
        return 0
    minimum = _bounded_int(config.get("min_bulk_refill_count"), default=30, minimum=1, maximum=300)
    maximum = _bounded_int(config.get("max_bulk_refill_count"), default=100, minimum=1, maximum=300)
    multiplier = _positive_float(config.get("bulk_refill_multiplier"), default=3.0)
    return min(maximum, max(minimum, math.ceil(shortfall_count * multiplier)))


def _delivery_selection_config(items: list[Any]) -> dict[str, Any]:
    for item in items:
        plan = getattr(item, "plan_json", None)
        if isinstance(plan, dict) and isinstance(plan.get("delivery_selection"), dict):
            return plan["delivery_selection"]
    return {}


def _normalized(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text.lower())


def _ngrams(text: str, size: int = 2) -> set[str]:
    normalized = _normalized(text)
    if len(normalized) <= size:
        return {normalized} if normalized else set()
    return {normalized[index : index + size] for index in range(len(normalized) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _stable_key(item: Any) -> str:
    raw = f"{getattr(item, 'item_no', 0)}:{getattr(item, 'body', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _ratio_value(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(parsed, 1.0))


def _positive_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed > 0 else default
