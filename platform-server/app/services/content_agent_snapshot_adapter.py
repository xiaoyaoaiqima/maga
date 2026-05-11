"""Adapter from MAGA content-agent task snapshots to xhs-writer brief.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

DEFAULT_XHS_BRIEF_TYPE = "xhs_product_seeding_professional_advisor"

_PASSTHROUGH_KEYS = (
    "brief_id",
    "brief_type",
    "brand",
    "products",
    "campaign",
    "painpoint_ratio",
    "persona_target",
    "content_structure",
    "score_threshold",
    "max_rewrites",
    "soft_floor",
    "soft_weights",
)


def build_xhs_brief(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build an xhs-writer compatible brief dict from a MAGA task snapshot.

    Preferred input shape is snapshot["input"]["xhs_brief"], which is copied with
    only xhs-writer-facing keys plus a MAGA provenance block. For early local
    integration, flat MAGA snapshot fields are also accepted and normalized.
    """
    input_snapshot = _as_dict(snapshot.get("input"))
    asset_refs = _as_dict(snapshot.get("asset_refs"))
    source = _as_dict(input_snapshot.get("xhs_brief")) if isinstance(input_snapshot.get("xhs_brief"), Mapping) else input_snapshot

    brief: dict[str, Any] = {}
    for key in _PASSTHROUGH_KEYS:
        if key in source and source[key] is not None:
            brief[key] = source[key]

    brief.setdefault("brief_id", _default_brief_id(snapshot))
    brief.setdefault("brief_type", source.get("brief_type") or DEFAULT_XHS_BRIEF_TYPE)

    brand = brief.get("brand") or source.get("brand_code") or source.get("brand_name")
    if not brand:
        raise ValueError("xhs brief requires brand")
    brief["brand"] = brand

    products = _normalize_products(brief.get("products") or source.get("product_code") or source.get("product_codes") or source.get("product"))
    if not products:
        raise ValueError("xhs brief requires products")
    brief["products"] = products

    if "campaign" not in brief:
        campaign = _build_campaign(source)
        if campaign:
            brief["campaign"] = campaign

    if "persona_target" not in brief:
        persona = _build_persona_target(source)
        if persona:
            brief["persona_target"] = persona

    if "content_structure" not in brief:
        content_structure = _build_content_structure(source)
        if content_structure:
            brief["content_structure"] = content_structure

    brief["maga"] = {
        "task_id": snapshot.get("task_id"),
        "run_id": snapshot.get("run_id"),
        "task_type": snapshot.get("task_type"),
        "asset_refs": asset_refs,
    }
    return brief


def dump_xhs_brief_yaml(brief: Mapping[str, Any]) -> str:
    """Serialize xhs brief as stable UTF-8 YAML for xhs_runtime.run_full_flow."""
    return yaml.safe_dump(dict(brief), allow_unicode=True, sort_keys=False, default_flow_style=False)


def write_xhs_brief_yaml(snapshot: Mapping[str, Any], output_path: str | Path) -> Path:
    """Build and write xhs-writer brief.yaml, creating parent directories."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_xhs_brief_yaml(build_xhs_brief(snapshot)), encoding="utf-8")
    return path


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _default_brief_id(snapshot: Mapping[str, Any]) -> str:
    task_id = snapshot.get("task_id") or "unknown"
    run_id = snapshot.get("run_id")
    if run_id is not None:
        return f"maga-task-{task_id}-run-{run_id}"
    return f"maga-task-{task_id}"


def _normalize_products(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        code = value.get("code") or value.get("product_code") or value.get("id") or value.get("name")
        return [str(code)] if code else []
    if isinstance(value, list):
        products: list[str] = []
        for item in value:
            if isinstance(item, str):
                products.append(item)
            elif isinstance(item, Mapping):
                code = item.get("code") or item.get("product_code") or item.get("id") or item.get("name")
                if code:
                    products.append(str(code))
        return products
    return []


def _build_campaign(source: Mapping[str, Any]) -> dict[str, Any]:
    campaign: dict[str, Any] = {}
    name = source.get("campaign_name") or source.get("topic") or source.get("product_topic")
    if name:
        campaign["name"] = name
    if "start" in source:
        campaign["start"] = source["start"]
    if "end" in source:
        campaign["end"] = source["end"]
    if "must_keywords" in source:
        campaign["must_keywords"] = source.get("must_keywords") or []
    if "must_messages" in source:
        campaign["must_messages"] = source.get("must_messages") or []
    elif campaign:
        campaign["must_messages"] = []
    return campaign


def _build_persona_target(source: Mapping[str, Any]) -> dict[str, Any]:
    persona: dict[str, Any] = {}
    identity = source.get("target_persona") or source.get("persona") or source.get("identity")
    if identity:
        persona["identity"] = identity
    for key in ("voice", "brand_familiarity"):
        if key in source and source[key] is not None:
            persona[key] = source[key]
    return persona


def _build_content_structure(source: Mapping[str, Any]) -> dict[str, Any]:
    structure: dict[str, Any] = {}
    constraints = _as_dict(source.get("content_constraints"))
    for key in ("word_count", "emoji", "title_style", "layout"):
        value = source.get(key)
        if value is None:
            value = constraints.get(key)
        if value is not None:
            structure[key] = value
    return structure
