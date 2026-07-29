"""Batch planning service for MAGA content generation."""
from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from secrets import SystemRandom
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.models.maga_assets import AssetRegistry
from app.services.business_rule_asset_types import ARTICLE_BUSINESS_RULE_ASSET_TYPES
from app.services.product_experience_rule_service import DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME
from app.services.real_user_example_pool_service import (
    DEFAULT_COMMENT_SAMPLE_COUNT,
    DEFAULT_NOTE_SAMPLE_COUNT,
    REAL_USER_EXAMPLE_POOL_ASSET_TYPE,
    infer_real_user_tags,
    select_real_user_examples,
)
from app.services.system_prompt_keyword_service import DEFAULT_SYSTEM_KEYWORD_ASSET_KEY

DEFAULT_CONTENT_WORD_COUNT = "150-250"
DEFAULT_CONTENT_EMOJI = "少量"
ARTICLE_RULE_EXAMPLE_SAMPLE_COUNT = 3
ARTICLE_RULE_MAX_EXAMPLE_SAMPLE_COUNT = 8
MOUTH_PHRASE_BUDGET_DEFAULT_BASE = 20
AUDIT_ONLY_DEFAULT_ASSET_KEYS = {"a2_momclass_month_center"}
CURRENT_WANGYUE_ARTICLE_ASSET_KEY = "wangyue_v3_core_storyline_article_rules"
NO_INSPIRATION_CLUE = "不使用灵感线索"
SOURCE_ROW_RULE_OVERRIDE_FIELDS = {
    "story_spine",
    "scene_motive_bucket",
    "selling_description",
    "selling_kernel",
    "corpus",
}


class ContentBatchPlanner:
    """Create item-level generation plans from MAGA asset snapshots."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_batch_plan(
        self,
        *,
        asset_key: str,
        rule_id: str | None = None,
        source_row_no: int | None = None,
        product_topic: str | None,
        target_audience: str | None,
        persona_target: str | None = None,
        style: str | None,
        count: int,
        articles_per_prompt: int = 1,
        postprocess_mode: str | None = None,
        keyword_asset_key: str | None = None,
        prompt_mode: str | None = None,
        draft_corpus: str | None = None,
        draft_selling_painpoint_group: str | None = None,
        draft_rule_id: str | None = None,
        draft_source_row_no: int | None = None,
        model_config: dict[str, Any] | None = None,
        model_config_rotation: list[dict[str, Any]] | None = None,
        created_by: str | None = None,
    ) -> ContentBatchJob:
        if count <= 0:
            raise ValueError("count must be positive")
        normalized_postprocess_mode = _resolve_postprocess_mode(asset_key, postprocess_mode)

        rule_asset = await self._latest_article_business_rule_asset(asset_key)
        if rule_asset is not None:
            return await self._create_article_business_rule_plan(
                rule_asset,
                requested_count=count,
                rule_id=rule_id,
                source_row_no=source_row_no,
                keyword_asset_key=keyword_asset_key,
                prompt_mode=prompt_mode,
                articles_per_prompt=articles_per_prompt,
                postprocess_mode=normalized_postprocess_mode,
                draft_corpus=draft_corpus,
                draft_selling_painpoint_group=draft_selling_painpoint_group,
                draft_rule_id=draft_rule_id or rule_id,
                draft_source_row_no=(
                    draft_source_row_no
                    if draft_source_row_no is not None
                    else source_row_no
                ),
                model_config=model_config,
                model_config_rotation=model_config_rotation,
                created_by=created_by,
            )
        if articles_per_prompt > 1:
            raise ValueError("articles_per_prompt is only supported for article_business_rule_set assets")
        if not product_topic:
            raise ValueError(f"missing article_business_rule_set for {asset_key}")

        painpoints_asset = await self._latest_asset("painpoint_model", asset_key)
        selling_asset = await self._latest_asset("product_selling_points", asset_key)
        examples_asset = await self._latest_asset("reference_examples", asset_key)
        writing_patterns_asset = await self._latest_asset("reference_writing_patterns", asset_key)
        compliance_asset = await self._latest_asset("compliance_rules", asset_key)

        painpoints = self._painpoint_items(painpoints_asset)
        selling_points = self._items(selling_asset)
        examples = self._items(examples_asset)
        writing_patterns = self._items(writing_patterns_asset)
        compliance_rules = self._items(compliance_asset)
        if not painpoints:
            raise ValueError(f"missing painpoint_model items for {asset_key}")
        if not selling_points:
            raise ValueError(f"missing product_selling_points items for {asset_key}")
        if not examples:
            raise ValueError(f"missing reference_examples items for {asset_key}")

        job = ContentBatchJob(
            batch_code=f"batch_{uuid.uuid4().hex[:12]}",
            asset_key=asset_key,
            product_topic=product_topic,
            target_audience=target_audience,
            style=style,
            count=count,
            status="planned",
            strategy_json={
                "use_painpoints": True,
                "use_reference_examples": True,
                "diversity": "high",
                "executor": DEFAULT_EXECUTOR_CODE,
                "persona_target": persona_target,
                "postprocess_mode": normalized_postprocess_mode,
            },
            diversity_plan_json={},
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()

        used_asset_combo_keys: set[str] = set()
        for index in range(count):
            plan = self._build_item_plan(
                item_no=index + 1,
                asset_key=asset_key,
                product_topic=product_topic,
                target_audience=target_audience,
                persona_target=persona_target,
                style=style,
                keyword_asset_key=_normalize_keyword_asset_key(keyword_asset_key),
                painpoints=painpoints,
                selling_points=selling_points,
                examples=examples,
                writing_patterns=writing_patterns,
                compliance_rules=compliance_rules,
                model_config=_rotated_model_config(index + 1, model_config, model_config_rotation),
                used_asset_combo_keys=used_asset_combo_keys,
            )
            used_asset_combo_keys.add(plan["asset_combo_key"])
            self.db.add(ContentBatchItem(batch_id=job.id, item_no=index + 1, status="planned", plan_json=plan))
        await self.db.flush()
        return job

    async def _latest_article_business_rule_asset(self, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type.in_(ARTICLE_BUSINESS_RULE_ASSET_TYPES),
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _create_article_business_rule_plan(
        self,
        asset: AssetRegistry,
        *,
        requested_count: int,
        rule_id: str | None,
        source_row_no: int | None,
        keyword_asset_key: str | None,
        prompt_mode: str | None,
        articles_per_prompt: int,
        postprocess_mode: str | None,
        draft_corpus: str | None,
        draft_selling_painpoint_group: str | None,
        draft_rule_id: str | None,
        draft_source_row_no: int | None,
        model_config: dict[str, Any] | None,
        model_config_rotation: list[dict[str, Any]] | None,
        created_by: str | None,
    ) -> ContentBatchJob:
        rules = self._article_business_rule_items(asset)
        draft_override = _normalize_article_draft_rule_override(
            draft_corpus=draft_corpus,
            draft_selling_painpoint_group=draft_selling_painpoint_group,
            draft_rule_id=draft_rule_id,
            draft_source_row_no=draft_source_row_no,
        )
        if draft_override:
            rules = _article_rules_with_draft_override(rules, draft_override)
        focus_rules = _filter_rules(rules, rule_id=rule_id, source_row_no=source_row_no)
        if rule_id or source_row_no is not None:
            rules = focus_rules
        if not rules:
            raise ValueError(f"article_business_rule_set is empty for {asset.asset_key}")
        focus_single_rule = bool(rule_id) or source_row_no is not None
        asset_allows_repeat = _article_business_asset_allows_repeat(asset)
        limit = self._article_business_generation_limit(
            asset,
            rules,
            requested_count=requested_count,
            allow_repeat=focus_single_rule or asset_allows_repeat,
        )
        product_topic = (
            (asset.content_json or {}).get("activity_name")
            or asset.display_name
            or DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME
        )
        resolved_prompt_mode = _resolve_prompt_mode(prompt_mode, asset)
        resolved_keyword_asset_key = (
            None
            if resolved_prompt_mode == "rule_corpus_as_prompt"
            else _resolve_keyword_asset_key(keyword_asset_key, asset)
        )
        quality_guard_profile_key = _resolve_quality_guard_profile_key(asset)
        real_user_pool_asset = await self._latest_real_user_pool_asset(asset)
        real_user_pool_items = _real_user_pool_items(real_user_pool_asset)
        real_user_pool_config = _resolve_real_user_pool_config(asset)
        title_shape_pool_asset = await self._latest_real_user_pool_asset_by_key(
            str(real_user_pool_config.get("title_shape_fallback_pool_asset_key") or "").strip()
        )
        title_shape_pool_items = _real_user_pool_items(title_shape_pool_asset)
        source_type = asset.asset_type
        job = ContentBatchJob(
            batch_code=f"batch_{uuid.uuid4().hex[:12]}",
            asset_key=asset.asset_key,
            product_topic=product_topic,
            target_audience=None,
            style=None,
            count=limit,
            status="planned",
            strategy_json={
                "source": source_type,
                "rule_asset_id": asset.id,
                "rule_asset_version": asset.version_no,
                "executor": DEFAULT_EXECUTOR_CODE,
                "generation_mode": "unified_content_generate",
                "postprocess_mode": postprocess_mode,
                "keyword_asset_key": resolved_keyword_asset_key,
                "prompt_mode": resolved_prompt_mode,
                "quality_guard_profile_key": quality_guard_profile_key,
                "articles_per_prompt": max(1, min(int(articles_per_prompt or 1), 2)),
                "real_user_pool_asset_key": real_user_pool_asset.asset_key if real_user_pool_asset else None,
                "real_user_pool_asset_id": real_user_pool_asset.id if real_user_pool_asset else None,
                "real_user_pool_asset_version": real_user_pool_asset.version_no if real_user_pool_asset else None,
                "title_shape_pool_asset_key": title_shape_pool_asset.asset_key if title_shape_pool_asset else None,
                "title_shape_pool_asset_id": title_shape_pool_asset.id if title_shape_pool_asset else None,
                "title_shape_pool_asset_version": title_shape_pool_asset.version_no if title_shape_pool_asset else None,
                "rule_id_filter": rule_id,
                "source_row_no_filter": source_row_no,
                "allow_repeat_generation": focus_single_rule or asset_allows_repeat,
            },
            diversity_plan_json={},
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()

        normalized_articles_per_prompt = max(1, min(int(articles_per_prompt or 1), 2))
        selected_rules = _select_article_business_rules_for_generation(
            rules,
            limit=limit,
            allow_repeat=focus_single_rule or asset_allows_repeat,
            articles_per_prompt=normalized_articles_per_prompt,
            randomize_order=asset.asset_key == CURRENT_WANGYUE_ARTICLE_ASSET_KEY,
        )
        used_real_user_hashes: set[str] = set()
        used_real_user_route_families: dict[str, int] = {}
        used_title_reference_examples: set[str] = set()
        mouth_phrase_budget_items = _build_mouth_phrase_budget_items(
            _resolve_mouth_phrase_budget_config(asset),
            item_count=limit,
        )
        group_counters: dict[str, int] = {}
        open_groups: dict[str, dict[str, int]] = {}
        rule_occurrence_counts: dict[str, int] = {}
        for index, rule in enumerate(selected_rules):
            rule_occurrence_key = str(
                rule.get("rule_id")
                or rule.get("source_row_no")
                or rule.get("business_rule")
                or index
            )
            rule_occurrence_no = rule_occurrence_counts.get(rule_occurrence_key, 0) + 1
            rule_occurrence_counts[rule_occurrence_key] = rule_occurrence_no
            plan = self._product_experience_plan_from_rule(
                rule,
                asset=asset,
                item_no=index + 1,
                variation_item_no=rule_occurrence_no,
                variation_batch_seed=job.id,
                keyword_asset_key=resolved_keyword_asset_key,
                prompt_mode=resolved_prompt_mode,
                quality_guard_profile_key=quality_guard_profile_key,
                model_config=_rotated_model_config(index + 1, model_config, model_config_rotation),
                real_user_pool_asset=real_user_pool_asset,
                real_user_pool_items=real_user_pool_items,
                real_user_pool_config=real_user_pool_config,
                title_shape_pool_asset=title_shape_pool_asset,
                title_shape_pool_items=title_shape_pool_items,
                used_real_user_hashes=used_real_user_hashes,
                used_real_user_route_families=used_real_user_route_families,
                used_title_reference_examples=used_title_reference_examples,
                mouth_phrase_budget=mouth_phrase_budget_items[index]
                if index < len(mouth_phrase_budget_items)
                else None,
            )
            if normalized_articles_per_prompt > 1:
                group_key = _article_multi_output_rule_key(rule)
                current_group = open_groups.get(group_key)
                if current_group is None or current_group["member_count"] >= normalized_articles_per_prompt:
                    group_no = group_counters.get(group_key, 0) + 1
                    group_counters[group_key] = group_no
                    current_group = {"group_no": group_no, "member_count": 0}
                    open_groups[group_key] = current_group
                current_group["member_count"] += 1
                plan["multi_output_group"] = {
                    "enabled": True,
                    "group_id": f"{group_key}:group{current_group['group_no']}",
                    "group_key": group_key,
                    "output_index": current_group["member_count"] - 1,
                    "requested_count": normalized_articles_per_prompt,
                }
            self.db.add(
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=index + 1,
                    status="planned",
                    plan_json=plan,
                )
            )
        await self.db.flush()
        return job

    async def _latest_asset(self, asset_type: str, asset_key: str) -> AssetRegistry | None:
        asset_stage = "candidate" if asset_type == "reference_writing_patterns" else "production"
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == asset_type,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == asset_stage,
            )
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_real_user_pool_asset(self, rule_asset: AssetRegistry) -> AssetRegistry | None:
        asset_key = _resolve_real_user_pool_asset_key(rule_asset)
        return await self._latest_real_user_pool_asset_by_key(asset_key)

    async def _latest_real_user_pool_asset_by_key(self, asset_key: str | None) -> AssetRegistry | None:
        if not asset_key:
            return None
        result = await self.db.execute(
            select(AssetRegistry.id)
            .where(
                AssetRegistry.asset_type == REAL_USER_EXAMPLE_POOL_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        asset_id = result.scalar_one_or_none()
        if asset_id is None:
            return None
        return await self.db.get(AssetRegistry, asset_id)

    def _build_item_plan(
        self,
        *,
        item_no: int,
        asset_key: str,
        product_topic: str,
        target_audience: str | None,
        persona_target: str | None = None,
        style: str | None,
        keyword_asset_key: str | None,
        painpoints: list[dict[str, Any]],
        selling_points: list[dict[str, Any]],
        examples: list[dict[str, Any]],
        writing_patterns: list[dict[str, Any]],
        compliance_rules: list[dict[str, Any]],
        model_config: dict[str, Any] | None = None,
        used_asset_combo_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        zero = item_no - 1
        pain_idx, selling_idx, example_idx, asset_reuse_reason = self._asset_indices(
            zero,
            painpoint_count=len(painpoints),
            selling_point_count=len(selling_points),
            example_count=len(examples),
            used_asset_combo_keys=used_asset_combo_keys or set(),
        )
        compliance_idx = zero % max(len(compliance_rules), 1)
        asset_combo_key = self._asset_combo_key(pain_idx, selling_idx, example_idx)
        writing_pattern_idx = self._writing_pattern_index(
            zero,
            writing_patterns=writing_patterns,
            product_topic=product_topic,
            target_audience=target_audience,
            style=style,
        )

        return {
            "item_no": item_no,
            "asset_key": asset_key,
            "product_topic": product_topic,
            "target_audience": target_audience,
            "persona_target": persona_target,
            "style": style,
            "keyword_asset_key": keyword_asset_key,
            "asset_combo_key": asset_combo_key,
            "asset_reuse_reason": asset_reuse_reason,
            "painpoint_ref": self._ref("painpoint_model", asset_key, pain_idx, painpoints[pain_idx]),
            "selling_point_ref": self._ref("product_selling_points", asset_key, selling_idx, selling_points[selling_idx]),
            "reference_example_refs": [self._ref("reference_examples", asset_key, example_idx, examples[example_idx])],
            "writing_pattern_ref": self._ref(
                "reference_writing_patterns",
                asset_key,
                writing_pattern_idx,
                writing_patterns[writing_pattern_idx],
            )
            if writing_pattern_idx is not None
            else None,
            "compliance_rule_refs": [
                self._ref("compliance_rules", asset_key, compliance_idx, compliance_rules[compliance_idx])
            ]
            if compliance_rules
            else [],
            "brief_constraints": {
                "word_count": DEFAULT_CONTENT_WORD_COUNT,
                "emoji": DEFAULT_CONTENT_EMOJI,
                "must_use_painpoint": True,
                "must_reference_example_without_copying": True,
                "output_fields": ["title", "body"],
            },
            "model_config": model_config or {},
        }

    def _article_business_rule_items(self, asset: AssetRegistry) -> list[dict[str, Any]]:
        items = (asset.content_json or {}).get("items")
        return [
            item
            for item in items or []
            if isinstance(item, dict)
            and item.get("business_rule")
        ]

    def _article_business_generation_limit(
        self,
        asset: AssetRegistry,
        rules: list[dict[str, Any]],
        *,
        requested_count: int,
        allow_repeat: bool = False,
    ) -> int:
        metadata_limit = (asset.metadata_json or {}).get("default_generation_count")
        content_limit = (asset.content_json or {}).get("default_generation_count")
        value = requested_count or metadata_limit or content_limit
        try:
            limit = int(value)
        except (TypeError, ValueError):
            limit = requested_count
        limit = max(1, limit)
        return limit if allow_repeat else min(limit, len(rules))

    def _product_experience_generation_limit(
        self,
        asset: AssetRegistry,
        rules: list[dict[str, Any]],
        *,
        requested_count: int,
    ) -> int:
        return self._article_business_generation_limit(asset, rules, requested_count=requested_count)

    def _product_experience_plan_from_rule(
        self,
        rule: dict[str, Any],
        *,
        asset: AssetRegistry,
        item_no: int,
        variation_item_no: int | None = None,
        variation_batch_seed: int | None = None,
        keyword_asset_key: str | None,
        prompt_mode: str | None = None,
        quality_guard_profile_key: str | None,
        model_config: dict[str, Any] | None,
        real_user_pool_asset: AssetRegistry | None = None,
        real_user_pool_items: list[dict[str, Any]] | None = None,
        real_user_pool_config: dict[str, Any] | None = None,
        title_shape_pool_asset: AssetRegistry | None = None,
        title_shape_pool_items: list[dict[str, Any]] | None = None,
        used_real_user_hashes: set[str] | None = None,
        used_real_user_route_families: dict[str, int] | set[str] | None = None,
        used_title_reference_examples: set[str] | None = None,
        mouth_phrase_budget: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        asset_content = asset.content_json or {}
        asset_metadata = asset.metadata_json or {}
        rule, rule_override_meta = _apply_source_row_rule_override(asset, rule, item_no=item_no)
        resolved_rule_prompt_mode = (
            _normalize_prompt_mode(rule.get("prompt_mode") or rule.get("generation_prompt_mode"))
            or prompt_mode
        )
        rule_type = (
            rule.get("rule_type")
            or asset_content.get("rule_type")
            or "business_rule"
        )
        selected_examples, example_meta = self._selected_rule_examples(
            rule,
            sample_count=self._article_business_example_sample_count(asset, rule),
        )
        business_rule = rule.get("business_rule")
        resolved_model_config = self._article_business_model_config(asset, model_config)
        resolved_real_user_pool_config = _real_user_pool_config_for_rule(real_user_pool_config or {}, rule)
        content_path_control = _resolve_content_path_control(asset, rule)
        resolved_real_user_pool_config = _real_user_pool_config_with_content_path_control(
            resolved_real_user_pool_config,
            content_path_control,
        )
        primary_real_user_pool_config = dict(resolved_real_user_pool_config)
        title_shape_count = _int_or_none(primary_real_user_pool_config.get("title_shape_count"))
        if title_shape_pool_asset is not None and title_shape_pool_items and title_shape_count:
            primary_real_user_pool_config["title_shape_count"] = 0
        real_user_examples, real_user_meta = self._selected_real_user_examples(
            rule,
            real_user_pool_asset=real_user_pool_asset,
            real_user_pool_items=real_user_pool_items or [],
            real_user_pool_config=primary_real_user_pool_config,
            used_real_user_hashes=used_real_user_hashes,
            used_real_user_route_families=used_real_user_route_families,
        )
        title_shape_examples, title_shape_meta = self._selected_title_shape_fallback_examples(
            rule,
            title_shape_pool_asset=title_shape_pool_asset,
            title_shape_pool_items=title_shape_pool_items or [],
            real_user_pool_config=resolved_real_user_pool_config,
            used_real_user_hashes=used_real_user_hashes,
        )
        if title_shape_examples:
            real_user_examples = [*real_user_examples, *title_shape_examples]
            real_user_meta = _merge_real_user_fallback_meta(
                real_user_meta,
                title_shape_meta,
                fallback_key="title_shape",
            )
        real_user_title_refs, real_user_title_meta = _selected_real_user_title_reference_examples(
            real_user_pool_items or [],
            rule,
            resolved_real_user_pool_config,
            selected_examples=real_user_examples,
        )
        static_title_refs = (
            []
            if resolved_real_user_pool_config.get("disable_static_title_reference") is True
            else _selected_title_reference_examples(
                asset,
                rule,
                used_title_reference_examples=used_title_reference_examples,
                stack_avoid=_string_list(resolved_real_user_pool_config.get("prompt_family_stack_avoid")),
                selected_real_user_meta=real_user_meta,
            )
        )
        if used_title_reference_examples is not None:
            used_title_reference_examples.update(static_title_refs)
        title_reference_examples = _unique_strings([*real_user_title_refs, *static_title_refs])[:8]
        title_reference_all_examples = _unique_strings([
            *_title_reference_pool(asset, rule),
            *real_user_title_refs,
        ])
        if real_user_meta is not None and real_user_title_meta:
            real_user_meta = {
                **real_user_meta,
                "title_reference": real_user_title_meta,
            }
        field_owner_clean = _is_field_owner_clean_rule(asset, rule)
        ugc_post_type = (
            None
            if asset.asset_key == CURRENT_WANGYUE_ARTICLE_ASSET_KEY
            and resolved_rule_prompt_mode == "rule_corpus_as_prompt"
            else (
                _resolve_string_field("ugc_post_type", asset, rule)
                if field_owner_clean
                else _resolve_ugc_post_type(asset, rule, item_no=item_no)
            )
        )
        selling_painpoint_group = _resolve_string_field("selling_painpoint_group", asset, rule)
        post_type = _resolve_post_type(asset, rule)
        selling_painpoint_expression = _resolve_selling_painpoint_expression(
            asset,
            selling_painpoint_group,
            post_type=post_type,
            item_no=item_no,
        )
        painpoint = None if selling_painpoint_group else _resolve_painpoint(asset, rule, item_no=item_no)
        selling_point = None if selling_painpoint_group else _resolve_selling_point(asset, rule, item_no=item_no)
        positive_evidence = _resolve_positive_evidence(asset, rule)
        selling_description = _resolve_selling_description(asset, rule)
        selling_point_surface = _resolve_selling_point_surface(asset, rule)
        ingredient_surface = _resolve_ingredient_surface(asset, rule)
        benefit_surface = _resolve_benefit_surface(asset, rule)
        product_appearance_mode = _resolve_product_appearance_mode(asset, rule)
        product_name = _resolve_product_name(asset, rule)
        selling_kernel = (
            None
            if field_owner_clean
            else _resolve_selling_kernel(
                asset,
                rule,
                painpoint=painpoint,
                selling_point=selling_point,
                positive_evidence=positive_evidence,
                selling_description=selling_description,
                selling_point_surface=selling_point_surface,
                ingredient_surface=ingredient_surface,
                benefit_surface=benefit_surface,
            )
        )
        expression_mechanism = _resolve_expression_mechanism(asset, rule)
        life_trigger = (
            _resolve_string_field("life_trigger", asset, rule)
            if field_owner_clean
            else _resolve_life_trigger(asset, rule, item_no=item_no)
        )
        product_role = (
            _resolve_string_field("product_role", asset, rule)
            if field_owner_clean
            else _resolve_product_role(asset, rule, item_no=item_no)
        )
        product_relation = (
            _resolve_string_field("product_relation", asset, rule)
            if field_owner_clean
            else _resolve_product_relation(
                asset,
                rule,
                product_appearance_mode=product_appearance_mode,
                product_role=product_role,
            )
        )
        product_density = (
            _resolve_string_field("product_density", asset, rule)
            if field_owner_clean
            else _resolve_product_density(asset, rule)
        )
        imperfection = (
            _resolve_string_field("imperfection", asset, rule)
            if field_owner_clean
            else _resolve_imperfection(asset, rule, item_no=item_no)
        )
        product_action_surface = (
            None
            if asset.asset_key == CURRENT_WANGYUE_ARTICLE_ASSET_KEY
            and resolved_rule_prompt_mode == "rule_corpus_as_prompt"
            else _resolve_product_action_surface(asset, rule, item_no=item_no)
        )
        title_shape_mode = _resolve_title_shape_mode(asset, rule, item_no=item_no)
        title_emoji_mode = _resolve_title_emoji_mode(asset, rule)
        scene_motive_bucket = (
            None
            if asset.asset_key == CURRENT_WANGYUE_ARTICLE_ASSET_KEY
            and resolved_rule_prompt_mode == "rule_corpus_as_prompt"
            else _resolve_scene_motive_bucket(asset, rule, item_no=item_no)
        )
        structure_slot = _resolve_structure_slot(asset, rule)
        story_spine = _resolve_story_spine(asset, rule)
        scene_constraint = _resolve_scene_constraint(asset, rule)
        product_position_mode = (
            _resolve_string_field("product_position_mode", asset, rule)
            if field_owner_clean
            else _resolve_product_position_mode(
                asset,
                rule,
                item_no=item_no,
                ugc_post_type=ugc_post_type,
            )
        )
        ending_mode = _resolve_ending_mode(
            asset,
            rule,
            item_no=item_no,
            ugc_post_type=ugc_post_type,
        )
        corpus = _corpus_for_ugc_post_type(
            rule.get("corpus"),
            ugc_post_type,
            product_position_mode=product_position_mode,
            include_ugc_post_type_guard=resolved_rule_prompt_mode != "rule_corpus_as_prompt",
            include_product_position_guard=resolved_rule_prompt_mode != "rule_corpus_as_prompt",
        )
        variation_slots = _resolve_rule_variation_slots(
            asset,
            rule,
            item_no=variation_item_no if variation_item_no is not None else item_no,
            batch_item_no=item_no,
            batch_seed=variation_batch_seed,
            selling_painpoint_expression=selling_painpoint_expression,
        )
        plan = {
            "rule_type": rule_type,
            "item_no": item_no,
            "asset_key": asset.asset_key,
            "keyword_asset_key": keyword_asset_key,
            "prompt_mode": resolved_rule_prompt_mode,
            "quality_guard_profile_key": quality_guard_profile_key,
            "keyword_selection": _resolve_keyword_selection(asset),
            "generation_requirements": _resolve_prompt_lines_field(
                "generation_requirements",
                asset,
                rule,
            ),
            "content_path_control": content_path_control,
            "rule_asset_id": asset.id,
            "rule_asset_version": asset.version_no,
            "rule_id": rule.get("rule_id"),
            "draft_rule_override": rule.get("draft_rule_override"),
            "business_rule": business_rule,
            "product_name": product_name,
            "post_type": post_type,
            "product_appearance_mode": product_appearance_mode,
            "ugc_post_type": ugc_post_type,
            "painpoint": painpoint,
            "selling_point": selling_point,
            "selling_painpoint_group": selling_painpoint_group,
            "selling_painpoint_expression": (
                selling_painpoint_expression.get("expression")
                if selling_painpoint_expression
                else None
            ),
            "selling_painpoint_expression_source_row_no": (
                selling_painpoint_expression.get("source_row_no")
                if selling_painpoint_expression
                else None
            ),
            "selling_painpoint_expression_group": (
                selling_painpoint_expression.get("selling_painpoint_group")
                if selling_painpoint_expression
                else None
            ),
            "selling_painpoint_expression_inspiration_mode": (
                "none"
                if selling_painpoint_expression
                and _int_or_none(selling_painpoint_expression.get("source_row_no"))
                in {
                    _int_or_none(value)
                    for value in rule.get("inspiration_none_source_row_nos") or []
                }
                else "auto"
                if selling_painpoint_expression
                else None
            ),
            "selling_painpoint_expression_inspiration_clue": (
                _inspiration_clue_for_expression(rule, selling_painpoint_expression)
                if selling_painpoint_expression
                else None
            ),
            "positive_evidence": positive_evidence,
            "selling_description": selling_description,
            "selling_point_surface": selling_point_surface,
            "ingredient_surface": ingredient_surface,
            "benefit_surface": benefit_surface,
            "selling_kernel": selling_kernel,
            "expression_mechanism": expression_mechanism,
            "expression_reference_paths": _resolve_string_list_field("expression_reference_paths", asset, rule),
            "expression_reference_phrases": _resolve_string_list_field("expression_reference_phrases", asset, rule),
            "life_trigger": life_trigger,
            "product_role": product_role,
            "product_relation": product_relation,
            "product_density": product_density,
            "imperfection": imperfection,
            "product_action_surface": product_action_surface,
            "title_shape_mode": title_shape_mode,
            "title_emoji_mode": title_emoji_mode,
            "scene_motive_bucket": scene_motive_bucket,
            "structure_slot": structure_slot,
            "story_spine": story_spine,
            "scene_constraint": scene_constraint,
            "product_position_mode": product_position_mode,
            "ending_mode": ending_mode,
            "corpus": corpus,
            "generation_instruction": _resolve_string_field("generation_instruction", asset, rule),
            "content_direction": _resolve_string_field("content_direction", asset, rule),
            "activity_material": rule.get("activity_material"),
            "selling_expression": rule.get("selling_expression"),
            "selling_expression_note": rule.get("selling_expression_note"),
            "hard_boundaries": _resolve_prompt_lines_field("hard_boundaries", asset, rule),
            "writing_requirements": _resolve_prompt_lines_field("writing_requirements", asset, rule),
            "variation_slots": variation_slots,
            "variation_slot_selection_mode": _resolve_variation_slot_selection_mode(asset),
            "inspiration_usage_interval": _resolve_inspiration_usage_interval(asset),
            "examples": selected_examples,
            "supplements": [],
            **example_meta,
            "title_reference_all_examples": title_reference_all_examples,
            "title_reference_examples": title_reference_examples,
            "synthetic_title_examples": _synthetic_title_examples_pool(
                asset,
                rule,
                real_user_pool_config=resolved_real_user_pool_config,
            ),
            "real_user_examples": real_user_examples,
            "real_user_pool": real_user_meta,
            "mouth_phrase_budget": _mouth_phrase_budget_for_rule(rule, mouth_phrase_budget),
            "source_row_no": rule.get("source_row_no"),
            **rule_override_meta,
            "output_fields": ["title", "body"],
            "brief_constraints": {
                "word_count": asset_content.get("word_count")
                or asset_metadata.get("word_count")
                or ("50-90" if rule_type == "article_business" else DEFAULT_CONTENT_WORD_COUNT),
                "emoji": DEFAULT_CONTENT_EMOJI,
                "output_fields": ["title", "body"],
            },
            "model_config": resolved_model_config,
        }
        if selling_painpoint_group:
            plan.pop("painpoint", None)
            plan.pop("selling_point", None)
        return plan

    def _selected_real_user_examples(
        self,
        rule: dict[str, Any],
        *,
        real_user_pool_asset: AssetRegistry | None,
        real_user_pool_items: list[dict[str, Any]],
        real_user_pool_config: dict[str, Any],
        used_real_user_hashes: set[str] | None = None,
        used_real_user_route_families: dict[str, int] | set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        if real_user_pool_asset is None or not real_user_pool_items:
            return [], None
        route_count = _int_or_none(real_user_pool_config.get("route_count"))
        detail_count = _int_or_none(real_user_pool_config.get("detail_count"))
        title_shape_count = _int_or_none(real_user_pool_config.get("title_shape_count"))
        opening_count = _int_or_none(real_user_pool_config.get("opening_count"))
        opening_or_ending_count = _int_or_none(real_user_pool_config.get("opening_or_ending_count"))
        texture_count = _int_or_none(real_user_pool_config.get("texture_count"))
        ending_count = _int_or_none(real_user_pool_config.get("ending_count"))
        if any(
            count is not None
            for count in (
                route_count,
                detail_count,
                title_shape_count,
                opening_count,
                opening_or_ending_count,
                texture_count,
                ending_count,
            )
        ):
            default_note_count = (
                max(0, int(route_count or 0))
                + max(0, int(detail_count or 0))
                + max(0, int(title_shape_count or 0))
                + max(0, int(opening_count or 0))
                + max(0, int(opening_or_ending_count or 0))
                + max(0, int(texture_count or 0))
                + max(0, int(ending_count or 0))
            )
        else:
            default_note_count = DEFAULT_NOTE_SAMPLE_COUNT
        note_count = _non_negative_int(real_user_pool_config.get("note_count"), default_note_count)
        comment_count = _non_negative_int(real_user_pool_config.get("comment_count"), DEFAULT_COMMENT_SAMPLE_COUNT)
        query_text = " ".join(
            str(value or "")
            for value in (
                rule.get("business_rule"),
                rule.get("corpus"),
            )
        )
        selected, selection_meta = select_real_user_examples(
            real_user_pool_items,
            query_text=query_text,
            note_count=note_count,
            comment_count=comment_count,
            route_count=route_count,
            detail_count=detail_count,
            title_shape_count=title_shape_count,
            opening_count=opening_count,
            opening_or_ending_count=opening_or_ending_count,
            texture_count=texture_count,
            ending_count=ending_count,
            exclude_risk_tags=_string_list(real_user_pool_config.get("exclude_risk_tags")),
            exclude_terms=_string_list(real_user_pool_config.get("exclude_terms")),
            route_family_include=_string_list(real_user_pool_config.get("route_family_include")),
            route_family_exclude=_string_list(real_user_pool_config.get("route_family_exclude")),
            detail_family_include=_string_list(real_user_pool_config.get("detail_family_include")),
            detail_family_exclude=_string_list(real_user_pool_config.get("detail_family_exclude")),
            route_prompt_include_terms=_string_list(real_user_pool_config.get("route_prompt_include_terms")),
            route_prompt_exclude_terms=_string_list(real_user_pool_config.get("route_prompt_exclude_terms")),
            detail_prompt_include_terms=_string_list(real_user_pool_config.get("detail_prompt_include_terms")),
            detail_prompt_exclude_terms=_string_list(real_user_pool_config.get("detail_prompt_exclude_terms")),
            layer_source_keyword_include=_string_list_map(real_user_pool_config.get("layer_source_keyword_include")),
            layer_source_keyword_exclude=_string_list_map(real_user_pool_config.get("layer_source_keyword_exclude")),
            prompt_family_include=_string_list(real_user_pool_config.get("prompt_family_include")),
            prompt_family_exclude=_string_list(real_user_pool_config.get("prompt_family_exclude")),
            prompt_family_stack_avoid=_string_list(real_user_pool_config.get("prompt_family_stack_avoid")),
            used_dedupe_hashes=used_real_user_hashes,
            used_route_families=used_real_user_route_families,
        )
        return selected, {
            "asset_key": real_user_pool_asset.asset_key,
            "asset_id": real_user_pool_asset.id,
            "asset_version": real_user_pool_asset.version_no,
            **selection_meta,
        }

    def _selected_title_shape_fallback_examples(
        self,
        rule: dict[str, Any],
        *,
        title_shape_pool_asset: AssetRegistry | None,
        title_shape_pool_items: list[dict[str, Any]],
        real_user_pool_config: dict[str, Any],
        used_real_user_hashes: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        count = _int_or_none(real_user_pool_config.get("title_shape_count"))
        if count is None or count <= 0 or title_shape_pool_asset is None or not title_shape_pool_items:
            return [], None
        query_text = " ".join(
            str(value or "")
            for value in (
                rule.get("business_rule"),
                rule.get("corpus"),
            )
        )
        selected, selection_meta = select_real_user_examples(
            title_shape_pool_items,
            query_text=query_text,
            note_count=count,
            comment_count=0,
            route_count=0,
            detail_count=0,
            title_shape_count=count,
            opening_count=0,
            opening_or_ending_count=0,
            texture_count=0,
            ending_count=0,
            exclude_risk_tags=_string_list(real_user_pool_config.get("title_shape_exclude_risk_tags"))
            or _string_list(real_user_pool_config.get("exclude_risk_tags")),
            exclude_terms=_string_list(real_user_pool_config.get("exclude_terms")),
            used_dedupe_hashes=used_real_user_hashes,
            used_route_families=set(),
        )
        return selected, {
            "asset_key": title_shape_pool_asset.asset_key,
            "asset_id": title_shape_pool_asset.id,
            "asset_version": title_shape_pool_asset.version_no,
            **selection_meta,
        }

    def _article_business_model_config(
        self,
        asset: AssetRegistry,
        request_model_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        asset_content = asset.content_json or {}
        asset_metadata = asset.metadata_json or {}
        asset_model_config = {}
        for source in (asset_content, asset_metadata):
            value = source.get("model_config")
            if isinstance(value, dict):
                asset_model_config.update(value)
        return {
            **asset_model_config,
            **(request_model_config or {}),
        }

    def _article_business_example_sample_count(
        self,
        asset: AssetRegistry,
        rule: dict[str, Any],
    ) -> int:
        asset_content = asset.content_json or {}
        asset_metadata = asset.metadata_json or {}
        for source in (rule, asset_content, asset_metadata):
            count = _int_or_none(source.get("example_sample_count"))
            if count is not None:
                return min(max(count, 0), ARTICLE_RULE_MAX_EXAMPLE_SAMPLE_COUNT)
        return ARTICLE_RULE_EXAMPLE_SAMPLE_COUNT

    def _selected_rule_examples(
        self,
        rule: dict[str, Any],
        *,
        sample_count: int = ARTICLE_RULE_EXAMPLE_SAMPLE_COUNT,
    ) -> tuple[list[str], dict[str, Any]]:
        examples = [str(item).strip() for item in rule.get("examples") or [] if str(item).strip()]
        supplements = [str(item).strip() for item in rule.get("supplements") or [] if str(item).strip()]
        pool = examples or supplements
        selected_indices = _sample_indices(len(pool), sample_count)
        # 重要逻辑：业务规则资产保留完整示例池，计划层只抽少量例句进入 prompt，
        # 避免模型把全量真人语料平均成模板或复刻原句。
        selected = [pool[index] for index in selected_indices]
        return selected, {
            "example_pool_count": len(examples),
            "supplement_pool_count": len(supplements),
            "example_sample_count": len(selected),
            "selected_example_source": "examples" if examples else ("supplements" if supplements else "none"),
            "selected_example_indices": selected_indices,
        }

    def _asset_indices(
        self,
        zero: int,
        *,
        painpoint_count: int,
        selling_point_count: int,
        example_count: int,
        used_asset_combo_keys: set[str],
    ) -> tuple[int, int, int, str | None]:
        combo_count = painpoint_count * selling_point_count * example_count
        base = self._combo_indices(zero, painpoint_count, selling_point_count, example_count)
        base_key = self._asset_combo_key(*base)
        if base_key not in used_asset_combo_keys or len(used_asset_combo_keys) >= combo_count:
            reason = "素材组合池已用完，按轮换策略复用" if base_key in used_asset_combo_keys else None
            return (*base, reason)

        for offset in range(combo_count):
            candidate = self._combo_indices(zero + offset, painpoint_count, selling_point_count, example_count)
            if self._asset_combo_key(*candidate) not in used_asset_combo_keys:
                return (*candidate, None)
        return (*base, "素材组合池已用完，按轮换策略复用")

    @staticmethod
    def _combo_indices(seed: int, painpoint_count: int, selling_point_count: int, example_count: int) -> tuple[int, int, int]:
        pain_idx = seed % painpoint_count
        selling_idx = (seed // painpoint_count) % selling_point_count
        example_idx = (seed // (painpoint_count * selling_point_count)) % example_count
        return pain_idx, selling_idx, example_idx

    @staticmethod
    def _asset_combo_key(pain_idx: int, selling_idx: int, example_idx: int) -> str:
        return f"pain:{pain_idx}|sell:{selling_idx}|example:{example_idx}"

    @staticmethod
    def _writing_pattern_index(
        zero: int,
        *,
        writing_patterns: list[dict[str, Any]],
        product_topic: str,
        target_audience: str | None,
        style: str | None,
    ) -> int | None:
        if not writing_patterns:
            return None
        scored = []
        for index, pattern in enumerate(writing_patterns):
            score = _pattern_match_score(pattern, product_topic=product_topic, target_audience=target_audience, style=style)
            # The zero-based offset keeps equal-score patterns rotating across items.
            scored.append((score, -((index - zero) % len(writing_patterns)), index))
        scored.sort(reverse=True)
        return scored[0][2]

    @staticmethod
    def _items(asset: AssetRegistry | None) -> list[dict[str, Any]]:
        if asset is None or not asset.content_json:
            return []
        items = asset.content_json.get("items", [])
        return [item for item in items if isinstance(item, dict)]

    @classmethod
    def _painpoint_items(cls, asset: AssetRegistry | None) -> list[dict[str, Any]]:
        if asset is None or not asset.content_json:
            return []
        topics = asset.content_json.get("topics")
        if isinstance(topics, list) and topics:
            return [_topic_to_plan_item(item) for item in topics if isinstance(item, dict)]
        return cls._items(asset)

    @staticmethod
    def _ref(asset_type: str, asset_key: str, index: int, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "asset_type": asset_type,
            "asset_key": asset_key,
            "item_index": index,
            "item_id": item.get("asset_steward_id")
            or item.get("pattern_id")
            or item.get("example_id")
            or f"{asset_type}_{index + 1}",
            "snapshot": item,
        }


def _topic_to_plan_item(topic: dict[str, Any]) -> dict[str, Any]:
    descriptions = [str(item).strip() for item in topic.get("descriptions") or [] if str(item).strip()]
    selling_points = [
        item
        for item in topic.get("selling_points") or []
        if isinstance(item, dict) and (item.get("selling_point") or item.get("name"))
    ]
    selling_point_names = [item.get("selling_point") or item.get("name") for item in selling_points]
    # Keep flattened fields because rule packages may use either topic-tree
    # names or direct rule-row names for the same business concept.
    return {
        **topic,
        "painpoint": topic.get("painpoint") or topic.get("topic"),
        "description": "；".join(descriptions) if descriptions else topic.get("description"),
        "selling_point": topic.get("selling_point") or (selling_point_names[0] if selling_point_names else None),
        "selling_points": selling_point_names,
    }


def _filter_rules(
    rules: list[dict[str, Any]],
    *,
    rule_id: str | None,
    source_row_no: int | None,
) -> list[dict[str, Any]]:
    normalized_rule_id = str(rule_id or "").strip()
    normalized_source_row_no = _int_or_none(source_row_no)
    if not normalized_rule_id and normalized_source_row_no is None:
        return rules
    return [
        rule
        for rule in rules
        if (not normalized_rule_id or str(rule.get("rule_id") or "") == normalized_rule_id)
        and (normalized_source_row_no is None or _int_or_none(rule.get("source_row_no")) == normalized_source_row_no)
    ]


def _normalize_article_draft_rule_override(
    *,
    draft_corpus: str | None,
    draft_selling_painpoint_group: str | None = None,
    draft_rule_id: str | None,
    draft_source_row_no: int | None,
) -> dict[str, Any] | None:
    corpus = str(draft_corpus or "").strip()
    selling_painpoint_group = str(draft_selling_painpoint_group or "").strip()
    if not corpus and not selling_painpoint_group:
        return None
    rule_id = str(draft_rule_id or "").strip() or None
    source_row_no = _int_or_none(draft_source_row_no)
    if not rule_id and source_row_no is None:
        raise ValueError(
            "draft rule override requires draft_rule_id, draft_source_row_no, rule_id, or source_row_no"
        )
    override = {"rule_id": rule_id, "source_row_no": source_row_no}
    if corpus:
        override["corpus"] = corpus
    if selling_painpoint_group:
        override["selling_painpoint_group"] = selling_painpoint_group
    return override


def _article_rules_with_draft_override(
    rules: list[dict[str, Any]],
    draft_override: dict[str, Any],
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    matched = False
    for rule in rules:
        if not _article_rule_matches_draft_override(rule, draft_override):
            updated.append(rule)
            continue
        next_rule = dict(rule)
        if "corpus" in draft_override:
            next_corpus = str(draft_override.get("corpus") or "").strip()
            next_rule["corpus"] = next_corpus
            if "content_direction" in next_rule:
                next_rule["content_direction"] = next_corpus
        if "selling_painpoint_group" in draft_override:
            next_rule["selling_painpoint_group"] = str(
                draft_override.get("selling_painpoint_group") or ""
            ).strip()
        next_rule["draft_rule_override"] = _article_draft_override_summary(draft_override)
        updated.append(next_rule)
        matched = True
    if not matched:
        raise ValueError(
            "draft corpus target rule not found; pass draft_rule_id or "
            "draft_source_row_no matching the selected rule"
        )
    return updated


def _article_rule_matches_draft_override(rule: dict[str, Any], draft_override: dict[str, Any]) -> bool:
    rule_id = draft_override.get("rule_id")
    source_row_no = draft_override.get("source_row_no")
    return (not rule_id or str(rule.get("rule_id") or "").strip() == rule_id) and (
        source_row_no is None or _int_or_none(rule.get("source_row_no")) == source_row_no
    )


def _article_draft_override_summary(draft_override: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "enabled": True,
        "rule_id": draft_override.get("rule_id"),
        "source_row_no": draft_override.get("source_row_no"),
    }
    if "selling_painpoint_group" in draft_override:
        summary["selling_painpoint_group"] = draft_override.get("selling_painpoint_group")
    return summary


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _positive_int(value: Any, default: int) -> int:
    parsed = _int_or_none(value)
    if parsed is None or parsed <= 0:
        return default
    return parsed


def _non_negative_int(value: Any, default: int) -> int:
    parsed = _int_or_none(value)
    if parsed is None or parsed < 0:
        return default
    return parsed


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _string_list_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for raw_key, raw_terms in value.items():
        key = str(raw_key or "").strip()
        terms = _string_list(raw_terms)
        if key and terms:
            result[key] = terms
    return result


def _resolve_real_user_pool_asset_key(asset: AssetRegistry) -> str | None:
    asset_content = asset.content_json or {}
    asset_metadata = asset.metadata_json or {}
    for source in (asset_content, asset_metadata):
        value = str(source.get("real_user_pool_asset_key") or "").strip()
        if value:
            return value
    return None


def _resolve_real_user_pool_config(asset: AssetRegistry) -> dict[str, Any]:
    asset_content = asset.content_json or {}
    asset_metadata = asset.metadata_json or {}
    config: dict[str, Any] = {}
    for source in (asset_content, asset_metadata):
        value = source.get("real_user_pool_sampling")
        if isinstance(value, dict):
            config.update(value)
    return config


def _apply_source_row_rule_override(
    asset: AssetRegistry,
    rule: dict[str, Any],
    *,
    item_no: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    overrides = (asset.content_json or {}).get("source_row_rule_overrides")
    if not isinstance(overrides, dict):
        return rule, {}

    source_row_no = _int_or_none(rule.get("source_row_no"))
    if source_row_no is None:
        return rule, {}

    override_key = str(source_row_no)
    variants = overrides.get(override_key)
    if isinstance(variants, dict):
        variants = [variants]
    if not isinstance(variants, list):
        return rule, {}

    valid_variants = [variant for variant in variants if isinstance(variant, dict)]
    if not valid_variants:
        return rule, {}

    variant_index = (max(1, item_no) - 1) % len(valid_variants)
    variant = valid_variants[variant_index]
    resolved_rule = dict(rule)
    for field in SOURCE_ROW_RULE_OVERRIDE_FIELDS:
        if field in variant:
            resolved_rule[field] = variant[field]

    variant_key = str(variant.get("variant_key") or variant.get("key") or variant_index + 1).strip()
    return resolved_rule, {
        "source_row_rule_override_key": override_key,
        "source_row_rule_variant_key": variant_key,
    }


def _resolve_rule_variation_slots(
    asset: AssetRegistry | None,
    rule: dict[str, Any],
    *,
    item_no: int,
    batch_item_no: int | None = None,
    batch_seed: int | None = None,
    selling_painpoint_expression: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    raw_slots = _merged_variation_slot_definitions(asset, rule)
    selection_mode = _resolve_variation_slot_selection_mode(asset)
    inspiration_usage_interval = _resolve_inspiration_usage_interval(asset)

    selected: list[dict[str, str]] = []
    zero = max(1, item_no) - 1
    for slot_index, raw_slot in enumerate(raw_slots):
        if not isinstance(raw_slot, dict):
            continue
        options = [
            option
            for value in raw_slot.get("options") or []
            if (option := _normalize_variation_slot_option(value)) is not None
        ]
        if not options:
            continue
        slot_code = str(raw_slot.get("slot_code") or raw_slot.get("code") or slot_index + 1).strip()
        slot_name = str(raw_slot.get("slot_name") or raw_slot.get("name") or "变化条件").strip()
        is_inspiration_slot = slot_code == "inspiration_material" or "灵感" in slot_name
        if is_inspiration_slot and inspiration_usage_interval > 1:
            batch_position = max(1, batch_item_no or item_no)
            batch_offset = max(1, batch_seed or 1) - 1
            if (batch_offset + batch_position - 1) % inspiration_usage_interval != 0:
                continue
        if is_inspiration_slot and selling_painpoint_expression:
            source_row_no = _int_or_none(selling_painpoint_expression.get("source_row_no"))
            none_rows = {
                _int_or_none(value)
                for value in rule.get("inspiration_none_source_row_nos") or []
            }
            if source_row_no is not None and source_row_no in none_rows:
                continue
            exact_clue = _inspiration_clue_for_expression(rule, selling_painpoint_expression)
            if exact_clue:
                exact_option = next(
                    (option for option in options if option[0] == exact_clue),
                    None,
                )
                if exact_option is None:
                    raise ValueError("configured inspiration clue is not present in the variation slot")
                selected.append(
                    {
                        "slot_code": slot_code,
                        "slot_name": slot_name,
                        "value": exact_clue,
                        **({"item_id": exact_option[1]} if exact_option[1] else {}),
                    }
                )
                continue
        offset = _int_or_none(raw_slot.get("offset"))
        if selection_mode == "batch_item_cycle" and batch_seed is not None:
            selected_index = (
                max(1, batch_seed)
                - 1
                + max(1, batch_item_no or item_no)
                - 1
                + slot_index
                + (offset or 0)
            ) % len(options)
        else:
            selected_index = (
                zero + (offset if offset is not None else slot_index)
            ) % len(options)
        selected_value, selected_item_id = options[selected_index]
        if is_inspiration_slot and selected_value == NO_INSPIRATION_CLUE:
            continue
        selected.append(
            {
                "slot_code": slot_code,
                "slot_name": slot_name,
                "value": selected_value,
                **({"item_id": selected_item_id} if selected_item_id else {}),
            }
        )
    return selected


def _normalize_variation_slot_option(value: Any) -> tuple[str, str | None] | None:
    if isinstance(value, dict):
        text = str(value.get("text") or "").strip()
        item_id = str(value.get("id") or "").strip() or None
    else:
        text = str(value).strip()
        item_id = None
    if not text:
        return None
    return text, item_id


def _resolve_variation_slot_selection_mode(asset: AssetRegistry | None) -> str:
    if asset is None:
        return "occurrence_cycle"
    metadata = asset.metadata_json or {}
    content = asset.content_json or {}
    mode = str(
        content.get("variation_slot_selection_mode")
        or metadata.get("variation_slot_selection_mode")
        or "occurrence_cycle"
    ).strip()
    return mode if mode in {"occurrence_cycle", "batch_item_cycle"} else "occurrence_cycle"


def _resolve_inspiration_usage_interval(asset: AssetRegistry | None) -> int:
    if asset is None:
        return 1
    metadata = asset.metadata_json or {}
    content = asset.content_json or {}
    raw_interval = content.get("inspiration_usage_interval")
    if raw_interval is None:
        raw_interval = metadata.get("inspiration_usage_interval")
    interval = _int_or_none(raw_interval)
    return interval if interval is not None and interval > 0 else 1


def _merged_variation_slot_definitions(
    asset: AssetRegistry | None,
    rule: dict[str, Any],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    indexes: dict[str, int] = {}
    sources = [
        (asset.content_json or {}).get("variation_slots") if asset else None,
        rule.get("variation_slots"),
    ]
    for raw_slots in sources:
        if not isinstance(raw_slots, list):
            continue
        for slot_index, raw_slot in enumerate(raw_slots):
            if not isinstance(raw_slot, dict):
                continue
            key = str(
                raw_slot.get("slot_code")
                or raw_slot.get("code")
                or raw_slot.get("slot_name")
                or raw_slot.get("name")
                or slot_index
            ).strip()
            if key in indexes:
                merged[indexes[key]] = dict(raw_slot)
            else:
                indexes[key] = len(merged)
                merged.append(dict(raw_slot))
    return merged


def _real_user_pool_config_for_rule(config: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(config)
    overrides = resolved.get("source_row_overrides")
    if not isinstance(overrides, dict):
        return resolved

    candidate_keys = []
    source_row_no = _int_or_none(rule.get("source_row_no"))
    if source_row_no is not None:
        candidate_keys.append(str(source_row_no))
    for key in ("rule_id", "business_rule"):
        value = str(rule.get(key) or "").strip()
        if value:
            candidate_keys.append(value)

    for key in candidate_keys:
        row_override = overrides.get(key)
        if isinstance(row_override, dict):
            resolved.update(row_override)
            resolved["source_row_override_key"] = key
            break
    return resolved


def _real_user_pool_config_with_content_path_control(
    config: dict[str, Any],
    content_path_control: dict[str, Any] | str | None,
) -> dict[str, Any]:
    if not isinstance(content_path_control, dict):
        return config
    exclude_terms = _string_list(content_path_control.get("exclude_example_terms"))
    if not exclude_terms:
        return config
    resolved = dict(config)
    # Keep this at planner level so examples that contradict the requested
    # content path are not selected into report metadata or rendered prompt.
    for key in (
        "exclude_terms",
        "route_prompt_exclude_terms",
        "detail_prompt_exclude_terms",
    ):
        resolved[key] = _unique_strings([*_string_list(resolved.get(key)), *exclude_terms])
    return resolved


def _merge_real_user_fallback_meta(
    base_meta: dict[str, Any] | None,
    fallback_meta: dict[str, Any] | None,
    *,
    fallback_key: str,
) -> dict[str, Any] | None:
    if not fallback_meta:
        return base_meta
    if base_meta is None:
        base_meta = {}
    merged = {**base_meta}
    fallback_pools = dict(merged.get("fallback_pools") or {})
    fallback_pools[fallback_key] = {
        "asset_key": fallback_meta.get("asset_key"),
        "asset_id": fallback_meta.get("asset_id"),
        "asset_version": fallback_meta.get("asset_version"),
        "requested": fallback_meta.get("requested"),
        "selected": fallback_meta.get("selected"),
        "fallback_reused_dedupe_hashes": fallback_meta.get("fallback_reused_dedupe_hashes") or [],
    }
    merged["fallback_pools"] = fallback_pools
    for key in ("source_type_counts", "layer_counts", "tag_counts", "risk_tag_counts", "route_family_counts"):
        merged[key] = dict(Counter(merged.get(key) or {}) + Counter(fallback_meta.get(key) or {}))
    for key in ("dedupe_hashes", "route_families", "fallback_reused_dedupe_hashes"):
        merged[key] = _unique_strings([*(merged.get(key) or []), *(fallback_meta.get(key) or [])])
    prompt_text_by_layer = dict(merged.get("prompt_text_by_layer") or {})
    for layer, values in (fallback_meta.get("prompt_text_by_layer") or {}).items():
        prompt_text_by_layer[str(layer)] = _unique_strings([*(prompt_text_by_layer.get(str(layer)) or []), *(values or [])])
    merged["prompt_text_by_layer"] = prompt_text_by_layer
    selected = dict(merged.get("selected") or {})
    for key, value in (fallback_meta.get("selected") or {}).items():
        selected[str(key)] = int(selected.get(str(key)) or 0) + int(value or 0)
    merged["selected"] = selected
    requested = dict(merged.get("requested") or {})
    for key, value in (fallback_meta.get("requested") or {}).items():
        requested[str(key)] = max(int(requested.get(str(key)) or 0), int(value or 0))
    merged["requested"] = requested
    return merged


def _resolve_mouth_phrase_budget_config(asset: AssetRegistry) -> dict[str, Any]:
    asset_content = asset.content_json or {}
    asset_metadata = asset.metadata_json or {}
    config: dict[str, Any] = {}
    groups_by_code: dict[str, dict[str, Any]] = {}
    anonymous_group_index = 0
    # Metadata may lag behind the editable asset content. Merge groups instead of
    # allowing an older metadata block to drop newer content-side budget groups.
    for source in (asset_metadata, asset_content):
        value = source.get("mouth_phrase_budget")
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "groups":
                    continue
                config[key] = item
            for raw_group in value.get("groups") or []:
                if not isinstance(raw_group, dict):
                    continue
                code = str(raw_group.get("code") or "").strip()
                if not code:
                    anonymous_group_index += 1
                    code = f"__anonymous_{anonymous_group_index}"
                groups_by_code[code] = dict(raw_group)
    if groups_by_code:
        config["groups"] = list(groups_by_code.values())
    return config


def _build_mouth_phrase_budget_items(config: dict[str, Any], *, item_count: int) -> list[dict[str, Any] | None]:
    if not item_count or not isinstance(config, dict) or config.get("enabled") is not True:
        return [None] * max(item_count, 0)
    groups = _resolve_mouth_phrase_budget_groups(config, item_count=item_count)
    if not groups:
        return [None] * item_count
    allowed_by_item: list[list[str]] = [[] for _ in range(item_count)]
    all_terms = _unique_strings(term for group in groups for term in group["terms"])
    for group_index, group in enumerate(groups):
        terms = group["terms"]
        if not terms:
            continue
        term_limits = group.get("term_limits") or {}
        if term_limits:
            for term_index, term in enumerate(terms):
                count = max(0, int(term_limits.get(term) or 0))
                for item_index in _spread_item_indexes(item_count, count, offset=group_index + term_index):
                    allowed_by_item[item_index].append(term)
            continue
        count = max(0, int(group.get("max_count") or 0))
        for hit_index, item_index in enumerate(_spread_item_indexes(item_count, count, offset=group_index)):
            allowed_by_item[item_index].append(terms[hit_index % len(terms)])
    items: list[dict[str, Any] | None] = []
    for item_terms in allowed_by_item:
        allowed_terms = _unique_strings(item_terms)
        avoid_terms = [term for term in all_terms if term not in set(allowed_terms)]
        items.append(
            {
                "enabled": True,
                "allowed_terms": allowed_terms,
                "avoid_terms": avoid_terms,
                "groups": groups,
                "batch_item_count": item_count,
            }
        )
    return items


def _mouth_phrase_budget_for_rule(
    rule: dict[str, Any],
    mouth_phrase_budget: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(mouth_phrase_budget, dict):
        return mouth_phrase_budget
    no_allow_groups = set(_string_list(rule.get("mouth_phrase_budget_no_allow_groups")))
    if not no_allow_groups:
        return mouth_phrase_budget

    groups = [group for group in mouth_phrase_budget.get("groups") or [] if isinstance(group, dict)]
    no_allow_terms = set(
        term
        for group in groups
        if str(group.get("code") or "").strip() in no_allow_groups
        for term in _string_list(group.get("terms"))
    )
    if not no_allow_terms:
        return mouth_phrase_budget

    resolved = dict(mouth_phrase_budget)
    resolved["allowed_terms"] = [
        term for term in _string_list(mouth_phrase_budget.get("allowed_terms")) if term not in no_allow_terms
    ]
    resolved["avoid_terms"] = _unique_strings([*_string_list(mouth_phrase_budget.get("avoid_terms")), *no_allow_terms])
    return resolved


def _resolve_mouth_phrase_budget_groups(config: dict[str, Any], *, item_count: int) -> list[dict[str, Any]]:
    base_count = _positive_int(config.get("base_count") or config.get("batch_size"), MOUTH_PHRASE_BUDGET_DEFAULT_BASE)
    groups: list[dict[str, Any]] = []
    for raw_group in config.get("groups") or []:
        if not isinstance(raw_group, dict):
            continue
        terms = _unique_strings(_string_list(raw_group.get("terms")))
        if not terms:
            continue
        group: dict[str, Any] = {
            "code": str(raw_group.get("code") or "").strip() or f"group_{len(groups) + 1}",
            "name": str(raw_group.get("name") or raw_group.get("code") or "").strip(),
            "terms": terms,
        }
        max_per_term = _int_or_none(raw_group.get("max_per_term_per_20") or raw_group.get("max_per_term"))
        if max_per_term is not None:
            group["term_limits"] = {
                term: _scaled_budget(max_per_term, item_count=item_count, base_count=base_count)
                for term in terms
            }
        else:
            max_per_base = _int_or_none(raw_group.get("max_per_20") or raw_group.get("max_count"))
            group["max_count"] = _scaled_budget(max_per_base or 0, item_count=item_count, base_count=base_count)
        groups.append(group)
    return groups


def _scaled_budget(value: int, *, item_count: int, base_count: int) -> int:
    if value <= 0 or item_count <= 0:
        return 0
    return min(item_count, max(1, math.ceil(value * item_count / max(base_count, 1))))


def _spread_item_indexes(item_count: int, count: int, *, offset: int = 0) -> list[int]:
    if item_count <= 0 or count <= 0:
        return []
    if count >= item_count:
        return list(range(item_count))
    indexes = []
    for index in range(count):
        position = math.floor((index + 0.5) * item_count / count)
        indexes.append((position + offset) % item_count)
    return sorted(set(indexes))


def _unique_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _real_user_pool_items(asset: AssetRegistry | None) -> list[dict[str, Any]]:
    if asset is None:
        return []
    items = (asset.content_json or {}).get("items")
    return [
        item
        for item in items or []
        if isinstance(item, dict)
        and item.get("source_type") in {"note", "comment"}
        and str(item.get("text") or "").strip()
    ]


def _sample_indices(pool_size: int, sample_count: int) -> list[int]:
    if pool_size <= 0 or sample_count <= 0:
        return []
    if pool_size <= sample_count:
        return list(range(pool_size))
    return sorted(SystemRandom().sample(range(pool_size), sample_count))


def _rotated_model_config(
    item_no: int,
    base_model_config: dict[str, Any] | None,
    model_config_rotation: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not model_config_rotation:
        return base_model_config
    rotation_item = model_config_rotation[(item_no - 1) % len(model_config_rotation)]
    return {**(base_model_config or {}), **rotation_item}


def _pattern_match_score(
    pattern: dict[str, Any],
    *,
    product_topic: str,
    target_audience: str | None,
    style: str | None,
) -> int:
    score = 0
    haystacks = {
        "topic_fit": product_topic,
        "audience_fit": target_audience or "",
        "style_fit": style or "",
    }
    for key, needle in haystacks.items():
        if not needle:
            continue
        for value in pattern.get(key) or []:
            text = str(value).strip()
            if text and (text in needle or needle in text):
                score += 2
            elif text and _has_overlap(text, needle):
                score += 1
    if pattern.get("review_status") == "approved":
        score += 1
    return score


def _has_overlap(left: str, right: str) -> bool:
    left_terms = {left[index : index + 2] for index in range(max(len(left) - 1, 0))}
    right_terms = {right[index : index + 2] for index in range(max(len(right) - 1, 0))}
    return bool(left_terms & right_terms)


def _resolve_keyword_asset_key(explicit_key: str | None, asset: AssetRegistry | None) -> str:
    normalized = _normalize_keyword_asset_key(explicit_key)
    if normalized:
        return normalized
    for source in ((asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        normalized = _normalize_keyword_asset_key(source.get("keyword_asset_key"))
        if normalized:
            return normalized
    return DEFAULT_SYSTEM_KEYWORD_ASSET_KEY


def _resolve_prompt_mode(explicit_mode: str | None, asset: AssetRegistry | None) -> str | None:
    normalized = _normalize_prompt_mode(explicit_mode)
    if normalized:
        return normalized
    for source in ((asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        normalized = _normalize_prompt_mode(source.get("prompt_mode") or source.get("generation_prompt_mode"))
        if normalized:
            return normalized
    if asset and asset.asset_key == "royal_friso_ugc_post_rules_v1":
        return "royal_compact"
    return None


def _resolve_quality_guard_profile_key(asset: AssetRegistry | None) -> str | None:
    for source in ((asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        normalized = _normalize_keyword_asset_key(source.get("quality_guard_profile_key"))
        if normalized:
            return normalized
    return None


def _resolve_keyword_selection(asset: AssetRegistry | None) -> dict[str, Any]:
    for source in ((asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        value = source.get("keyword_selection")
        if isinstance(value, dict):
            return dict(value)
    return {}


def _resolve_generation_requirements(asset: AssetRegistry | None) -> str | None:
    for source in ((asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        normalized = str(source.get("generation_requirements") or "").strip()
        if normalized:
            return normalized
    return None


def _resolve_post_type(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("post_type", asset, rule)


def _resolve_product_appearance_mode(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("product_appearance_mode", asset, rule)


def _resolve_product_name(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    explicit = _resolve_string_field("product_name", asset, rule)
    if explicit:
        return explicit
    text = " ".join(
        str(part or "")
        for part in (
            getattr(asset, "asset_key", None),
            getattr(asset, "display_name", None),
            rule,
        )
    )
    if "wangyue" in text.lower() or "旺玥" in text:
        return "旺玥"
    return None


def _corpus_for_ugc_post_type(
    corpus: str | None,
    ugc_post_type: str | None,
    *,
    product_position_mode: str | None = None,
    include_ugc_post_type_guard: bool = True,
    include_product_position_guard: bool = True,
) -> str | None:
    base = str(corpus or "").strip()
    guards: list[str] = []
    if include_ugc_post_type_guard and str(ugc_post_type or "") == "轻复盘型":
        guards.append(
            "本篇是阶段性回看，不写成求问帖、攻略或购买替换决策；"
            "围绕一段使用后的观察、取舍或家里安排展开；"
            "不要在标题或正文里直接写“轻复盘”这个内部类型词。"
        )
    if include_product_position_guard and str(product_position_mode or "") in {
        "先抛问题后出现",
        "同龄对照后出现",
        "纠结标准后出现",
        "反馈背景后出现",
        "后段才说到产品",
        "中段回看时出现",
        "观察之后出现",
        "后段作为当前安排",
        "取舍之后轻带",
        "结尾前轻轻落到产品",
    }:
        guards.append(
            "本篇 planner 指定产品不要前置：上面的前置产品表述只作为背景，不要照搬为正文开头。"
            "正文第一句不要出现产品名或品牌名；"
            "先写问题、同龄对照、正餐安排、家里消耗、开罐记录或阶段观察，第二句之后再让产品出现。"
        )
    if not guards:
        return corpus
    guard_text = "\n\n".join(guards)
    return f"{base}\n\n{guard_text}" if base else guard_text


def _resolve_title_shape_mode(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("title_shape_mode", asset, rule)
    if explicit:
        return explicit
    modes = _resolve_title_shape_modes(asset, rule)
    if modes:
        return modes[(max(1, item_no) - 1) % len(modes)]
    post_type = _resolve_post_type(asset, rule)
    product_appearance_mode = _resolve_product_appearance_mode(asset, rule)
    if not post_type and not product_appearance_mode:
        return None
    normalized_post_type = str(post_type or "")
    if "补货" in normalized_post_type or "清单" in normalized_post_type:
        modes = ["物件名短标题", "动作短标题", "清单/库存标签", "开罐/到货记录", "轻吐槽碎片"]
    elif "求问" in normalized_post_type and "复盘" in normalized_post_type:
        modes = ["普通短问题", "使用阶段短标题", "纠结碎片", "记录短标题", "消耗记录短标题"]
    elif "求问" in normalized_post_type or "复盘" in normalized_post_type:
        modes = ["普通短问题", "品类/品牌名短标题", "纠结碎片", "使用阶段短标题"]
    elif "使用记录" in normalized_post_type or "记录" in normalized_post_type:
        modes = ["时间/场景碎片", "动作短标题", "物件在场短标题", "轻吐槽碎片"]
    else:
        modes = ["名词短标题", "动作短标题", "普通短问题", "时间/场景碎片", "轻吐槽碎片"]
    return modes[(max(1, item_no) - 1) % len(modes)]


def _resolve_title_shape_modes(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> list[str]:
    for source in (rule or {}, (asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        if not isinstance(source, dict):
            continue
        value = source.get("title_shape_modes")
        if isinstance(value, list):
            modes = [str(item or "").strip() for item in value if str(item or "").strip()]
            if modes:
                return modes
        if isinstance(value, str):
            modes = [
                item.strip()
                for item in re.split(r"[,，、/|｜\n]+", value)
                if item.strip()
            ]
            if modes:
                return modes
    return []


def _resolve_title_emoji_mode(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("title_emoji_mode", asset, rule)


def _resolve_scene_motive_bucket(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("scene_motive_bucket", asset, rule)
    if explicit:
        return explicit
    buckets = _resolve_scene_motive_buckets(asset, rule)
    if buckets:
        return buckets[(max(1, item_no) - 1) % len(buckets)]
    post_type = _resolve_post_type(asset, rule)
    product_appearance_mode = _resolve_product_appearance_mode(asset, rule)
    if not post_type and not product_appearance_mode:
        return None
    normalized_post_type = str(post_type or "")
    if "补货" in normalized_post_type or "清单" in normalized_post_type:
        buckets = [
            "快递到货拆箱",
            "月底清单/购物车清理",
            "超市顺手补刚需",
            "家人提醒快没了",
            "早餐区/厨房台面整理",
            "常用位置顺手放好",
            "库存盘点",
            "临出门发现某样东西没了",
        ]
    elif "求问" in normalized_post_type and "复盘" in normalized_post_type:
        buckets = [
            "喝到几岁",
            "喝了一阵轻复盘",
            "儿童奶粉和正餐怎么平衡",
            "同龄家庭怎么安排",
            "消耗速度有点纠结",
            "4段和儿童奶粉怎么选",
            "饭量波动时要不要继续",
            "开罐记录",
        ]
    elif "求问" in normalized_post_type or "复盘" in normalized_post_type:
        buckets = [
            "喝到几岁",
            "开罐记录",
            "儿童奶粉和正餐怎么平衡",
            "同龄家庭怎么安排",
            "喝了一阵轻复盘",
            "4段和儿童奶粉怎么选",
            "饭量波动时要不要继续",
            "消耗速度有点纠结",
        ]
    elif "使用记录" in normalized_post_type or "记录" in normalized_post_type:
        buckets = [
            "早上赶时间",
            "晚饭后收拾桌子",
            "放学回家玄关旁",
            "周末在家磨蹭",
            "出门前检查东西",
            "早餐旁边那杯",
            "写作业间隙",
            "新开一听记录",
        ]
    else:
        buckets = [
            "早上赶时间",
            "晚饭后收拾",
            "家里库存",
            "同龄求问",
            "顺手记录",
        ]
    return buckets[(max(1, item_no) - 1) % len(buckets)]


def _resolve_scene_motive_buckets(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> list[str]:
    for source in (rule or {}, (asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        if not isinstance(source, dict):
            continue
        value = source.get("scene_motive_buckets")
        if isinstance(value, list):
            buckets = [str(item or "").strip() for item in value if str(item or "").strip()]
            if buckets:
                return buckets
        if isinstance(value, str):
            buckets = [
                item.strip()
                for item in re.split(r"[,，、/|｜\n]+", value)
                if item.strip()
            ]
            if buckets:
                return buckets
    return []


def _resolve_structure_slot(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("structure_slot", asset, rule)


def _resolve_story_spine(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("story_spine", asset, rule)


def _resolve_scene_constraint(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("scene_constraint", asset, rule)


def _resolve_positive_evidence(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("positive_evidence", asset, rule)


def _resolve_selling_description(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("selling_description", asset, rule)


def _resolve_selling_point_surface(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("selling_point_surface", asset, rule)


def _resolve_ingredient_surface(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("ingredient_surface", asset, rule)


def _resolve_benefit_surface(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("benefit_surface", asset, rule)


def _resolve_selling_kernel(
    asset: AssetRegistry | None,
    rule: dict[str, Any] | None,
    *,
    painpoint: str | None,
    selling_point: str | None,
    positive_evidence: str | None,
    selling_description: str | None,
    selling_point_surface: str | None,
    ingredient_surface: str | None,
    benefit_surface: str | None,
) -> str | None:
    explicit = _resolve_string_field("selling_kernel", asset, rule)
    if explicit:
        return explicit
    parts: list[str] = []
    for label, value in [
        ("痛点", painpoint),
        ("卖点", selling_point),
        ("正向证据", positive_evidence),
        ("卖点描述", selling_description),
        ("卖点表达", selling_point_surface),
        ("成分承接", ingredient_surface),
        ("好处表达", benefit_surface),
    ]:
        text = str(value or "").strip().rstrip("。；;，, ")
        if text:
            parts.append(f"{label}：{text}")
    return "；".join(parts) if parts else None


def _resolve_expression_mechanism(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    return _resolve_string_field("expression_mechanism", asset, rule)


def _is_field_owner_clean_rule(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> bool:
    asset_key = str(getattr(asset, "asset_key", "") or "").lower()
    corpus = str((rule or {}).get("corpus") or "")
    return (
        "field_owner_cleanup" in asset_key
        or "selling_description" in asset_key
        or "product_relation_dedupe" in asset_key
        or "selling_kernel_dedupe" in asset_key
        or "prompt_corpus_dedupe" in asset_key
        or "不提供新的痛点、卖点、成分、正向变化或产品动作" in corpus
        or "本篇的痛点、卖点和产品价值以本篇信息和卖点描述为准" in corpus
        or "产品入场和产品价值按上方字段" in corpus
    )


def _resolve_product_position_mode(
    asset: AssetRegistry | None,
    rule: dict[str, Any] | None,
    *,
    item_no: int,
    ugc_post_type: str | None = None,
) -> str | None:
    explicit = _resolve_string_field("product_position_mode", asset, rule)
    if explicit:
        return explicit
    modes = _resolve_string_list_field("product_position_modes", asset, rule)
    if modes:
        return modes[(max(1, item_no) - 1) % len(modes)]
    post_type = str(_resolve_post_type(asset, rule) or "")
    product_appearance_mode = str(_resolve_product_appearance_mode(asset, rule) or "")
    if not post_type and not product_appearance_mode:
        return None
    if "补货" in post_type or "清单" in post_type:
        modes = [
            "清单项中出现",
            "中段跟其他刚需并列",
            "后段才补一句",
            "拆箱核对时出现",
            "放回常用位置时出现",
            "清单里轻带",
        ]
    elif "求问" in post_type or "复盘" in post_type:
        if str(ugc_post_type or "") == "轻复盘型":
            modes = [
                "中段回看时出现",
                "观察之后出现",
                "后段作为当前安排",
                "取舍之后轻带",
                "结尾前轻轻落到产品",
            ]
        else:
            modes = [
                "先抛问题后出现",
                "同龄对照后出现",
                "纠结标准后出现",
                "反馈背景后出现",
                "后段才说到产品",
            ]
    elif "使用记录" in post_type or "记录" in post_type or "日常动作" in product_appearance_mode:
        modes = [
            "开头生活现场里顺带出现",
            "中段桌面物件里出现",
            "后段收拾动作里出现",
            "只在一个动作里轻带",
        ]
    else:
        modes = ["中段自然出现", "后段轻带", "清单项中出现"]
    return modes[(max(1, item_no) - 1) % len(modes)]


def _resolve_ending_mode(
    asset: AssetRegistry | None,
    rule: dict[str, Any] | None,
    *,
    item_no: int,
    ugc_post_type: str | None = None,
) -> str | None:
    explicit = _resolve_string_field("ending_mode", asset, rule)
    if explicit:
        return explicit
    modes = _resolve_string_list_field("ending_modes", asset, rule)
    if modes:
        return modes[(max(1, item_no) - 1) % len(modes)]
    post_type = str(_resolve_post_type(asset, rule) or "")
    if not post_type:
        return None
    if "补货" in post_type or "清单" in post_type:
        modes = [
            "放回位置",
            "漏买小遗憾",
            "普通收尾不总结",
            "家里乱但先补上",
            "家里习惯轻带",
            "下次再看",
            "收纳未完成",
            "顺路带回",
            "家人提醒收口",
            "东西先归位",
        ]
    elif "求问" in post_type or "复盘" in post_type:
        if str(ugc_post_type or "") == "轻复盘型":
            modes = ["先看反馈", "暂时安排", "后面再看", "取舍收口", "普通记录"]
        else:
            modes = ["问别人经验", "保留不确定", "同龄对照", "具体场景求经验", "不急着下结论"]
    elif "使用记录" in post_type or "记录" in post_type:
        modes = ["乱着出门", "先收一半", "普通收尾", "没总结", "具体现场收尾"]
    else:
        modes = ["普通收尾不总结", "后面再看", "具体现场收尾"]
    return modes[(max(1, item_no) - 1) % len(modes)]


def _resolve_product_action_surface(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("product_action_surface", asset, rule)
    if explicit:
        return explicit
    surfaces = _resolve_product_action_surfaces(asset, rule)
    if surfaces:
        return surfaces[(max(1, item_no) - 1) % len(surfaces)]
    post_type = _resolve_post_type(asset, rule)
    product_appearance_mode = _resolve_product_appearance_mode(asset, rule)
    normalized_post_type = str(post_type or "")
    normalized_product_mode = str(product_appearance_mode or "")
    if "使用记录" not in normalized_post_type and "日常动作" not in normalized_product_mode:
        return None
    surfaces = [
        "物件在场",
        "物件在场",
        "物件在场",
        "物件在场",
        "物件在场",
        "妈妈顺手挪放",
        "妈妈顺手挪放",
        "孩子轻微使用",
        "孩子轻微使用",
        "完整喝奶动作",
    ]
    return surfaces[(max(1, item_no) - 1) % len(surfaces)]


def _resolve_product_action_surfaces(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> list[str]:
    for source in (rule or {}, (asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        if not isinstance(source, dict):
            continue
        value = source.get("product_action_surfaces")
        if isinstance(value, list):
            surfaces = [str(item or "").strip() for item in value if str(item or "").strip()]
            if surfaces:
                return surfaces
        if isinstance(value, str):
            surfaces = [
                item.strip()
                for item in re.split(r"[,，、/|｜\n]+", value)
                if item.strip()
            ]
            if surfaces:
                return surfaces
    return []


def _resolve_ugc_post_type(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("ugc_post_type", asset, rule)
    if explicit:
        return explicit
    post_type = str(_resolve_post_type(asset, rule) or "")
    if "补货" in post_type or "清单" in post_type:
        return "复购/囤货型"
    if "求问" in post_type and "复盘" in post_type:
        types = ["求建议后的反馈型", "轻复盘型", "求建议后的反馈型", "轻复盘型", "轻复盘型"]
        return types[(max(1, item_no) - 1) % len(types)]
    if "求问" in post_type:
        return "求建议后的反馈型"
    if "复盘" in post_type:
        return "轻复盘型"
    if "使用记录" in post_type or "记录" in post_type:
        return "日常使用记录型"
    return None


def _resolve_painpoint(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("painpoint", asset, rule)
    if explicit:
        return explicit
    painpoints = _resolve_string_list_field("painpoints", asset, rule)
    if painpoints:
        return painpoints[(max(1, item_no) - 1) % len(painpoints)]
    return None


def _resolve_selling_painpoint_expression(
    asset: AssetRegistry | None,
    group: str | None,
    *,
    post_type: str | None = None,
    item_no: int,
) -> dict[str, Any] | None:
    normalized_group = str(group or "").strip()
    normalized_post_type = str(post_type or "").strip()
    if asset is None or not normalized_group:
        return None
    candidate_groups = {normalized_group}
    if not normalized_group.endswith("-ugc"):
        candidate_groups.add(f"{normalized_group}-ugc")
    raw_items = (asset.content_json or {}).get("selling_painpoint_expressions")
    candidates = [
        item
        for item in raw_items or []
        if isinstance(item, dict)
        and str(item.get("selling_painpoint_group") or "").strip() in candidate_groups
        and str(item.get("expression") or "").strip()
        and _selling_painpoint_expression_applies_to_post_type(
            item,
            normalized_post_type,
        )
    ]
    if not candidates:
        return None
    if asset.asset_key == CURRENT_WANGYUE_ARTICLE_ASSET_KEY:
        return SystemRandom().choice(candidates)
    return candidates[(max(1, item_no) - 1) % len(candidates)]


def _selling_painpoint_expression_applies_to_post_type(
    expression: dict[str, Any],
    post_type: str,
) -> bool:
    if "applicable_post_types" not in expression:
        return True
    applicable_post_types = set(_string_list(expression.get("applicable_post_types")))
    return bool(post_type) and post_type in applicable_post_types


def _inspiration_clue_for_expression(
    rule: dict[str, Any],
    expression: dict[str, Any],
) -> str | None:
    source_row_no = _int_or_none(expression.get("source_row_no"))
    if source_row_no is None:
        return None
    raw_mapping = rule.get("inspiration_clue_by_source_row_no")
    if not isinstance(raw_mapping, dict):
        return None
    for key, value in raw_mapping.items():
        if _int_or_none(key) == source_row_no:
            normalized = str(value or "").strip()
            return normalized or None
    return None


def _resolve_selling_point(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("selling_point", asset, rule)
    if explicit:
        return explicit
    selling_points = _resolve_string_list_field("selling_points", asset, rule)
    if selling_points:
        return selling_points[(max(1, item_no) - 1) % len(selling_points)]
    return None


def _resolve_life_trigger(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("life_trigger", asset, rule)
    if explicit:
        return explicit
    triggers = _resolve_string_list_field("life_triggers", asset, rule)
    if triggers:
        return triggers[(max(1, item_no) - 1) % len(triggers)]
    post_type = str(_resolve_post_type(asset, rule) or "")
    if "补货" in post_type or "清单" in post_type:
        triggers = ["家里快没了", "月底清清单", "顺路买刚需", "家人随口提醒", "收拾台面时归位"]
    elif "求问" in post_type and "复盘" in post_type:
        triggers = ["喝到几岁有点拿不准", "喝了一阵后回看", "正餐和奶粉怎么平衡", "同龄群聊后自己整理", "家里消耗速度复盘"]
    elif "求问" in post_type or "复盘" in post_type:
        triggers = ["喝到几岁有点拿不准", "新开一听后看家里安排", "正餐和奶粉怎么平衡", "同龄家庭怎么安排", "家里消耗速度有点纠结"]
    elif "使用记录" in post_type or "记录" in post_type:
        triggers = ["早上赶时间", "饭后收拾桌子", "放学回来一地东西", "在家磨蹭", "出门前检查东西"]
    else:
        return None
    return triggers[(max(1, item_no) - 1) % len(triggers)]


def _resolve_product_role(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("product_role", asset, rule)
    if explicit:
        return explicit
    post_type = str(_resolve_post_type(asset, rule) or "")
    if "补货" in post_type or "清单" in post_type:
        return "库存物件/补货清单一项"
    if "求问" in post_type and "复盘" in post_type:
        roles = ["讨论对象/求建议对象", "观察对象/反馈对象", "讨论对象/求建议对象", "观察对象/反馈对象", "观察对象/反馈对象"]
        return roles[(max(1, item_no) - 1) % len(roles)]
    if "求问" in post_type:
        return "讨论对象/求建议对象"
    if "复盘" in post_type:
        return "观察对象/反馈对象"
    if "使用记录" in post_type or "记录" in post_type:
        return "低浓度在场物件"
    return None


def _resolve_product_relation(
    asset: AssetRegistry | None,
    rule: dict[str, Any] | None,
    *,
    product_appearance_mode: str | None,
    product_role: str | None,
) -> str | None:
    explicit = _resolve_string_field("product_relation", asset, rule)
    if explicit:
        return explicit
    parts: list[str] = []
    appearance = str(product_appearance_mode or "").strip().rstrip("。；;，, ")
    role = str(product_role or "").strip().rstrip("。；;，, ")
    if appearance:
        parts.append(f"出现方式：{appearance}")
    if role:
        parts.append(f"角色：{role}")
    return "；".join(parts) if parts else None


def _resolve_product_density(asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    explicit = _resolve_string_field("product_density", asset, rule)
    if explicit:
        return explicit
    post_type = str(_resolve_post_type(asset, rule) or "")
    if "补货" in post_type or "清单" in post_type:
        return "中低"
    if "求问" in post_type or "复盘" in post_type:
        return "中"
    if "使用记录" in post_type or "记录" in post_type:
        return "低"
    return None


def _resolve_imperfection(asset: AssetRegistry | None, rule: dict[str, Any] | None, *, item_no: int) -> str | None:
    explicit = _resolve_string_field("imperfection", asset, rule)
    if explicit:
        return explicit
    imperfections = _resolve_string_list_field("imperfections", asset, rule)
    if imperfections:
        return imperfections[(max(1, item_no) - 1) % len(imperfections)]
    post_type = str(_resolve_post_type(asset, rule) or "")
    if "补货" in post_type or "清单" in post_type:
        imperfections = ["总有东西忘买", "家里还是很乱", "只是刚需补上", "东西总堆在一起"]
    elif "求问" in post_type or "复盘" in post_type:
        if "wangyue" in str(getattr(asset, "asset_key", "") or "").lower() or "旺玥" in str(rule or ""):
            imperfections = ["饭桌还是会乱一阵", "孩子当天也有小脾气", "家里安排没那么整齐", "还有一堆琐事要处理"]
        else:
            imperfections = ["不确定是不是每家都适合", "我也还在摸索", "价格和习惯都要算一下", "不是标准答案"]
    elif "使用记录" in post_type or "记录" in post_type:
        imperfections = ["当天还是一地乱", "孩子也没完全按计划来", "杯子还放在桌边", "没什么漂亮总结"]
    else:
        return None
    return imperfections[(max(1, item_no) - 1) % len(imperfections)]


def _resolve_string_list_field(field_name: str, asset: AssetRegistry | None, rule: dict[str, Any] | None) -> list[str]:
    for source in (rule or {}, (asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        if not isinstance(source, dict):
            continue
        value = source.get(field_name)
        if isinstance(value, list):
            items = [str(item or "").strip() for item in value if str(item or "").strip()]
            if items:
                return items
        if isinstance(value, str):
            items = [item.strip() for item in re.split(r"[,，、/|｜\n]+", value) if item.strip()]
            if items:
                return items
    return []


def _resolve_prompt_lines_field(
    field_name: str,
    asset: AssetRegistry | None,
    rule: dict[str, Any] | None,
) -> list[str]:
    for source in (rule or {}, (asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        if not isinstance(source, dict):
            continue
        value = source.get(field_name)
        if isinstance(value, list):
            items = [str(item or "").strip() for item in value if str(item or "").strip()]
            if items:
                return items
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _resolve_string_field(field_name: str, asset: AssetRegistry | None, rule: dict[str, Any] | None) -> str | None:
    for source in (rule or {}, (asset.content_json or {}) if asset else {}, (asset.metadata_json or {}) if asset else {}):
        value = source.get(field_name) if isinstance(source, dict) else None
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return None


def _resolve_content_path_control(asset: AssetRegistry | None, rule: dict[str, Any] | None = None) -> dict[str, Any] | str | None:
    merged: dict[str, Any] = {}
    found = False
    for source in ((asset.metadata_json or {}) if asset else {}, (asset.content_json or {}) if asset else {}, rule or {}):
        value = source.get("content_path_control") if isinstance(source, dict) else None
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
            continue
        if isinstance(value, dict):
            merged.update(value)
            found = True
    return merged if found else None


def _selected_title_reference_examples(
    asset: AssetRegistry,
    rule: dict[str, Any],
    *,
    used_title_reference_examples: set[str] | None = None,
    stack_avoid: list[str] | None = None,
    selected_real_user_meta: dict[str, Any] | None = None,
) -> list[str]:
    pool = [title for title in _title_reference_pool(asset, rule) if _is_usable_title_prompt_reference(title)]
    pool = _prefer_title_references_without_stacked_prompt_families(
        pool,
        stack_avoid=stack_avoid or [],
        selected_real_user_meta=selected_real_user_meta,
    )
    count = None
    for source in (rule, asset.content_json or {}, asset.metadata_json or {}):
        count = _int_or_none(source.get("title_reference_sample_count"))
        if count is not None:
            break
    sample_count = max(0, min(count or 8, 12))
    if not used_title_reference_examples or not pool:
        return [pool[index] for index in _sample_indices(len(pool), sample_count)]
    fresh_pool = [title for title in pool if title not in used_title_reference_examples]
    if len(fresh_pool) >= sample_count:
        return [fresh_pool[index] for index in _sample_indices(len(fresh_pool), sample_count)]
    selected = list(fresh_pool)
    refill_pool = [title for title in pool if title not in selected]
    refill_count = max(0, sample_count - len(selected))
    selected.extend(refill_pool[index] for index in _sample_indices(len(refill_pool), refill_count))
    return selected


def _prefer_title_references_without_stacked_prompt_families(
    titles: list[str],
    *,
    stack_avoid: list[str],
    selected_real_user_meta: dict[str, Any] | None,
) -> list[str]:
    if not titles or not stack_avoid or not selected_real_user_meta:
        return titles
    selected_families = set((selected_real_user_meta.get("prompt_family_counts") or {}).keys()) & set(stack_avoid)
    if not selected_families:
        return titles
    filtered = [title for title in titles if not (_title_prompt_families(title) & selected_families)]
    return filtered or titles


def _title_prompt_families(title: str) -> set[str]:
    text = _normalize_title_reference_match_text(title)
    families: set[str] = set()
    if any(
        term in text
        for term in (
            "选奶",
            "挑奶",
            "换奶",
            "对比",
            "做功课",
            "备选",
            "纠结",
            "配方",
            "成分",
            "下手",
            "入手",
            "看了好几",
        )
    ):
        families.add("selection_process")
    if "保护力" in text and any(term in text for term in ("眼脑", "dha", "燕窝酸", "营养")):
        families.add("sellpoint_pairing")
    return families


def _selected_real_user_title_reference_examples(
    items: list[dict[str, Any]],
    rule: dict[str, Any],
    real_user_pool_config: dict[str, Any],
    *,
    selected_examples: list[dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    count = _non_negative_int(real_user_pool_config.get("title_reference_count"), 3)
    if count <= 0 or not items:
        return [], {"requested": 0, "selected": 0}
    query_text = " ".join(
            str(value or "")
            for value in (
                rule.get("business_rule"),
                rule.get("corpus"),
            )
        )
    query_tags = set(infer_real_user_tags(query_text))
    exclude_terms = _normalized_terms(_string_list(real_user_pool_config.get("exclude_terms")))
    exclude_risk_tags = set(_string_list(real_user_pool_config.get("title_exclude_risk_tags"))) or set(
        _string_list(real_user_pool_config.get("exclude_risk_tags"))
    )
    selected_hashes = {str(item.get("dedupe_hash") or "") for item in selected_examples if item.get("dedupe_hash")}
    candidates: list[tuple[float, str]] = []
    for item in items:
        title = str(item.get("title") or "").strip()
        if not _is_usable_real_user_title_reference(title):
            continue
        if str(item.get("source_type") or "") != "note":
            continue
        if str(item.get("example_layer") or "") == "reject":
            continue
        if exclude_risk_tags and set(item.get("risk_tags") or []) & exclude_risk_tags:
            continue
        match_text = _normalize_title_reference_match_text(title)
        if exclude_terms and any(term in match_text for term in exclude_terms):
            continue
        tags = set(item.get("tags") or [])
        score = float(item.get("quality_score") or 0)
        score += len(tags & query_tags) * 10
        if str(item.get("dedupe_hash") or "") in selected_hashes:
            score += 8
        score += _real_user_title_shape_score(title)
        candidates.append((score, title))
    ranked_titles = _unique_strings(
        title for _score, title in sorted(candidates, key=lambda pair: (-pair[0], pair[1]))
    )
    sample_pool = ranked_titles[: max(count * 4, count)]
    selected = [sample_pool[index] for index in _sample_indices(len(sample_pool), count)]
    return selected, {
        "requested": count,
        "selected": len(selected),
        "query_tags": sorted(query_tags),
        "selected_titles": selected,
    }


def _title_reference_pool(asset: AssetRegistry, rule: dict[str, Any]) -> list[str]:
    asset_content = asset.content_json or {}
    asset_metadata = asset.metadata_json or {}
    pool: list[str] = []
    for source in (rule, asset_content, asset_metadata):
        for item in source.get("title_reference_examples") or []:
            title = str(item.get("title") if isinstance(item, dict) else item or "").strip()
            if title and title not in pool:
                pool.append(title)
    return pool


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _is_usable_real_user_title_reference(title: str) -> bool:
    text = str(title or "").strip()
    compact_len = len(re.sub(r"\s+", "", text))
    if compact_len < 4 or compact_len > 24:
        return False
    if re.search(r"[0-9一二三四五六七八九十]+个?月|[0-9一二三四五六七八九十]+(?:周)?岁|[一二三四五六七八九十]段|[1234]段", text):
        return False
    return _is_usable_title_prompt_reference(text)


def _is_usable_title_prompt_reference(title: str) -> bool:
    text = str(title or "").strip()
    compact = re.sub(r"\s+", "", text)
    compact_len = len(compact)
    if compact_len < 4 or compact_len > 24:
        return False
    if re.search(r"[0-9一二三四五六七八九十]+个?月|[0-9一二三四五六七八九十]+岁|[一二三四五六七八九十]段|[1234]段", text):
        return False
    product_only_terms = {
        "皇家美素佳儿旺玥",
        "美素佳儿旺玥",
        "儿童旺玥营养奶粉",
        "儿童成长奶粉",
        "儿童奶粉",
    }
    if compact in product_only_terms:
        return False
    bad_terms = (
        "皇家美素佳儿",
        "美素佳儿",
        "旺玥奶粉",
        "又开一听",
        "又开一罐",
        "终于找到",
        "怎么选",
        "听劝",
        "成分和原料",
        "最坚定的选择",
        "为什么推荐",
        "感谢皇家",
        "感谢",
        "哪家好",
        "营养奶粉",
        "攻略",
        "闭眼入",
        "一篇看懂",
        "不踩坑",
        "真实体验",
        "测评",
        "推荐",
        "安利",
        "哪里买",
        "私信",
        "奶瓶",
        "自己冲",
        "自己泡",
        "塞书包",
        "即饮",
        "湿",
        "潮湿",
        "保护小课堂",
        "课堂开课",
        "品牌大比较",
        "配方奶粉品牌",
        "补脑感受记录",
        "学生奶粉",
    )
    return not any(term in text for term in bad_terms)


def _real_user_title_shape_score(title: str) -> int:
    score = 0
    compact_len = len(re.sub(r"\s+", "", title))
    if 6 <= compact_len <= 16:
        score += 3
    if any(term in title for term in ("我", "娃", "孩子", "当妈", "谁懂", "头大", "纠结", "肉疼")):
        score += 2
    if any(term in title for term in ("奶粉", "成分", "配方", "营养", "保护力", "皇家", "旺玥")):
        score -= 2
    return score


def _normalized_terms(values: list[str]) -> list[str]:
    return [_normalize_title_reference_match_text(value) for value in values if value]


def _normalize_title_reference_match_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _synthetic_title_examples_pool(
    asset: AssetRegistry,
    rule: dict[str, Any],
    *,
    real_user_pool_config: dict[str, Any] | None = None,
) -> list[str]:
    config = real_user_pool_config or {}
    if config.get("disable_synthetic_title_examples") is True:
        return []
    include_terms = _normalized_terms(_string_list(config.get("synthetic_title_include_terms")))
    exclude_terms = _normalized_terms(_string_list(config.get("synthetic_title_exclude_terms")))
    asset_content = asset.content_json or {}
    asset_metadata = asset.metadata_json or {}
    pool: list[str] = []
    growth_rule = str(rule.get("business_rule") or "").startswith("营养不足/成长发育需求")
    for source in (rule, asset_content, asset_metadata):
        for item in source.get("synthetic_title_examples") or []:
            title = str(item.get("title") if isinstance(item, dict) else item or "").strip()
            match_text = _normalize_title_reference_match_text(title)
            if (
                title
                and _is_usable_synthetic_title_example(title)
                and (not growth_rule or _is_usable_wangyue_growth_synthetic_title(title))
                and (not include_terms or any(term in match_text for term in include_terms))
                and not any(term in match_text for term in exclude_terms)
                and title not in pool
            ):
                pool.append(title)
    return pool


def _is_usable_wangyue_growth_synthetic_title(title: str) -> bool:
    text = str(title or "").strip()
    blocked_terms = (
        "喝",
        "开罐",
        "又开",
        "空了",
        "空罐",
        "见底",
        "补了一罐",
        "囤",
        "补了一罐",
        "再买一罐",
        "口感",
        "粉质",
        "顺口",
        "味道",
        "绿叶菜",
        "不爱吃菜",
        "挑食",
        "吃饭",
        "顶一顶",
        "杯",
        "户外",
        "幼儿园",
        "上学",
        "接触",
        "请假",
        "精力",
        "跑了一天",
        "玩回来",
        "写作业",
        "画画",
        "看书",
        "身高",
        "背上",
        "摸着",
    )
    return not any(term in text for term in blocked_terms)


def _is_usable_synthetic_title_example(title: str) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    if re.search(r"[0-9一二三四五六七八九十]+个?月|[0-9一二三四五六七八九十]+(?:周)?岁|[一二三四五六七八九十]段|[1234]段", text):
        return False
    route_leak_terms = (
        "校服",
        "裤子",
        "裤腿",
        "衣服",
        "袖子",
        "早上那杯奶",
        "晚上那杯奶",
        "幼儿园回来那杯",
        "接娃回来先喝奶",
        "出门前那杯奶",
        "杯子又空了",
    )
    return not any(term in text for term in route_leak_terms)


def _normalize_keyword_asset_key(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_prompt_mode(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "rule_corpus_as_prompt": "rule_corpus_as_prompt",
        "minimal_rule_prompt": "rule_corpus_as_prompt",
        "rule_as_prompt": "rule_corpus_as_prompt",
        "royal_compact": "royal_compact",
        "royal_compact_prompt": "royal_compact",
        "layered_article": "layered_article",
    }
    return aliases.get(normalized, normalized or None)


def _article_multi_output_rule_key(rule: dict[str, Any]) -> str:
    rule_id = str(rule.get("rule_id") or "").strip()
    source_row_no = _int_or_none(rule.get("source_row_no"))
    if rule_id:
        return f"rule:{rule_id}"
    if source_row_no is not None:
        return f"row:{source_row_no}"
    text = re.sub(r"\s+", "", str(rule.get("business_rule") or "default"))
    return "rule_text:" + (text[:40] or "default")


def _select_article_business_rules_for_generation(
    rules: list[dict[str, Any]],
    *,
    limit: int,
    allow_repeat: bool,
    articles_per_prompt: int,
    randomize_order: bool = False,
) -> list[dict[str, Any]]:
    if not rules or limit <= 0:
        return []
    output_count = max(1, min(int(articles_per_prompt or 1), 2))
    rule_count = limit if output_count <= 1 else math.ceil(limit / output_count)
    if randomize_order:
        randomized_rules: list[dict[str, Any]] = []
        randomizer = SystemRandom()
        while len(randomized_rules) < rule_count:
            cycle = list(rules)
            randomizer.shuffle(cycle)
            randomized_rules.extend(cycle)
            if not allow_repeat:
                break
        base_rules = randomized_rules[:rule_count]
    else:
        base_rules = (
            [rules[index % len(rules)] for index in range(rule_count)]
            if allow_repeat
            else rules[:rule_count]
        )
    if output_count <= 1:
        return base_rules

    selected: list[dict[str, Any]] = []
    for rule in base_rules:
        for _ in range(output_count):
            if len(selected) >= limit:
                break
            selected.append(rule)
    return selected


def _normalize_postprocess_mode(value: str | None) -> str | None:
    mode = str(value or "").strip()
    if not mode:
        return None
    if mode not in {"audit_only", "generate_only"}:
        raise ValueError(f"unsupported postprocess_mode: {mode}")
    return mode


def _resolve_postprocess_mode(asset_key: str, value: str | None) -> str | None:
    mode = _normalize_postprocess_mode(value)
    if mode is None and str(asset_key or "").strip() in AUDIT_ONLY_DEFAULT_ASSET_KEYS:
        return "audit_only"
    return mode


def _article_business_asset_allows_repeat(asset: AssetRegistry) -> bool:
    metadata = asset.metadata_json or {}
    content = asset.content_json or {}
    return bool(
        metadata.get("allow_repeat_generation")
        or metadata.get("allow_rule_repeat")
        or content.get("allow_repeat_generation")
        or content.get("allow_rule_repeat")
    )
