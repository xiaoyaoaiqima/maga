"""Small helpers for building rewrite prompt context."""
from __future__ import annotations

from typing import Any


A2_REIYU_ARTICLE_ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"


def rewrite_business_rule_context(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    allowed_keys = (
        "rule_type",
        "asset_key",
        "product_topic",
        "target_audience",
        "persona_target",
        "style",
        "business_rule",
        "article_rule",
        "topic",
        "corpus",
        "examples",
        "supplements",
        "painpoint_ref",
        "selling_point_ref",
        "reference_example_refs",
        "writing_pattern_ref",
        "compliance_rule_refs",
        "output_fields",
        "source_row_no",
        "quality_guard_profile_key",
    )
    context = {key: plan[key] for key in allowed_keys if key in plan and plan[key] is not None}
    if (
        str(plan.get("prompt_mode") or "").strip() == "layered_article"
        and str(plan.get("asset_key") or "").strip() == A2_REIYU_ARTICLE_ASSET_KEY
    ):
        context.pop("corpus", None)
        selected_materials = []
        for slot in plan.get("variation_slots") or []:
            if not isinstance(slot, dict):
                continue
            slot_code = str(slot.get("slot_code") or "").strip()
            if slot_code in {"content_direction", "positive_expression"}:
                continue
            value = str(slot.get("value") or "").strip()
            if not value:
                continue
            selected_materials.append(
                {
                    "slot_code": slot_code,
                    "slot_name": str(slot.get("slot_name") or "").strip(),
                    "value": value,
                    **({"item_id": slot["item_id"]} if slot.get("item_id") else {}),
                }
            )
        if selected_materials:
            context["selected_materials"] = selected_materials
        hard_boundaries = [
            str(value).strip()
            for value in plan.get("hard_boundaries") or []
            if str(value).strip()
        ]
        if hard_boundaries:
            context["hard_boundaries"] = hard_boundaries
    if str(plan.get("prompt_mode") or "").strip() == "rule_corpus_as_prompt":
        rendered_prompt = str(
            ((plan.get("unified_generation") or {}).get("rendered_prompt") or "")
        ).strip()
        if rendered_prompt:
            rendered_corpus = rendered_prompt.split("\n\n【生成要求】", 1)[0].strip()
            if rendered_corpus:
                context["corpus"] = rendered_corpus
    return context
