"""Convert MAGA batch item plans to xhs-writer generation snapshots."""
from __future__ import annotations

from typing import Any


def build_xhs_generation_snapshot_from_brief(
    *,
    product_topic: str,
    target_audience: str | None = None,
    style: str | None = None,
) -> dict[str, Any]:
    """Build the minimal single-item snapshot for direct generation.

    Single generation should use the same executor contract as batch generation:
    MAGA sends an immutable `generation_snapshot`, while the worker decides how
    to render it. This minimal snapshot has no asset refs yet but keeps the
    runtime path consistent.
    """
    plan = {
        "item_no": 1,
        "product_topic": product_topic,
        "target_audience": target_audience,
        "style": style,
        "diversity_slot": {},
    }
    snapshot = build_xhs_generation_snapshot_from_plan(plan)
    snapshot["constraints"]["must_use_painpoint"] = False
    snapshot["constraints"]["must_reference_example_without_copying"] = False
    snapshot["batch_context"]["source"] = "single_generation"
    return snapshot


def build_xhs_generation_snapshot_from_plan(
    plan: dict[str, Any],
    *,
    batch_id: int | None = None,
    batch_code: str | None = None,
) -> dict[str, Any]:
    """Build the per-item executor input snapshot consumed by xhs-writer.

    The snapshot keeps MAGA as source of truth: all business assets are copied
    from the batch plan, while xhs-writer only receives the immutable execution
    input it needs for one content item.
    """
    reference_refs = plan.get("reference_example_refs") or []
    compliance_refs = plan.get("compliance_rule_refs") or []
    item_no = plan.get("item_no")
    return {
        "brief": {
            "product_topic": plan.get("product_topic"),
            "target_audience": plan.get("target_audience"),
            "style": plan.get("style"),
        },
        "assets": {
            "asset_key": plan.get("asset_key"),
            "painpoint": _snapshot(plan.get("painpoint_ref")),
            "selling_point": _snapshot(plan.get("selling_point_ref")),
            "reference_examples": [_snapshot(ref) for ref in reference_refs],
            "compliance_rules": [_snapshot(ref) for ref in compliance_refs],
        },
        "asset_refs": {
            "painpoint_ref": _without_snapshot(plan.get("painpoint_ref")),
            "selling_point_ref": _without_snapshot(plan.get("selling_point_ref")),
            "reference_example_refs": [_without_snapshot(ref) for ref in reference_refs],
            "compliance_rule_refs": [_without_snapshot(ref) for ref in compliance_refs],
        },
        "diversity_slot": plan.get("diversity_slot") or {},
        "batch_context": {
            "batch_id": batch_id,
            "batch_code": batch_code,
            "item_no": item_no,
        },
        "constraints": {
            "must_use_painpoint": True,
            "must_reference_example_without_copying": True,
            "avoid_same_opening_group": (plan.get("diversity_slot") or {}).get("forbidden_overlap_group"),
            "output_fields": ["title", "body"],
        },
    }


def _snapshot(ref: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ref:
        return None
    snapshot = ref.get("snapshot")
    return snapshot if isinstance(snapshot, dict) else None


def _without_snapshot(ref: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ref:
        return None
    return {key: value for key, value in ref.items() if key != "snapshot"}
