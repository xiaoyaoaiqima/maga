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
        keyword_asset_key: str | None = None,
        model_config: dict[str, Any] | None = None,
        model_config_rotation: list[dict[str, Any]] | None = None,
        created_by: str | None = None,
    ) -> ContentBatchJob:
        if count <= 0:
            raise ValueError("count must be positive")

        rule_asset = await self._latest_article_business_rule_asset(asset_key)
        if rule_asset is not None:
            return await self._create_article_business_rule_plan(
                rule_asset,
                requested_count=count,
                rule_id=rule_id,
                source_row_no=source_row_no,
                keyword_asset_key=keyword_asset_key,
                model_config=model_config,
                model_config_rotation=model_config_rotation,
                created_by=created_by,
            )
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
        model_config: dict[str, Any] | None,
        model_config_rotation: list[dict[str, Any]] | None,
        created_by: str | None,
    ) -> ContentBatchJob:
        rules = self._article_business_rule_items(asset)
        focus_rules = _filter_rules(rules, rule_id=rule_id, source_row_no=source_row_no)
        if rule_id or source_row_no is not None:
            rules = focus_rules
        if not rules:
            raise ValueError(f"article_business_rule_set is empty for {asset.asset_key}")
        focus_single_rule = bool(rule_id) or source_row_no is not None
        limit = self._article_business_generation_limit(
            asset,
            rules,
            requested_count=requested_count,
            allow_repeat=focus_single_rule,
        )
        product_topic = (
            (asset.content_json or {}).get("activity_name")
            or asset.display_name
            or DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME
        )
        resolved_keyword_asset_key = _resolve_keyword_asset_key(keyword_asset_key, asset)
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
                "keyword_asset_key": resolved_keyword_asset_key,
                "quality_guard_profile_key": quality_guard_profile_key,
                "real_user_pool_asset_key": real_user_pool_asset.asset_key if real_user_pool_asset else None,
                "real_user_pool_asset_id": real_user_pool_asset.id if real_user_pool_asset else None,
                "real_user_pool_asset_version": real_user_pool_asset.version_no if real_user_pool_asset else None,
                "title_shape_pool_asset_key": title_shape_pool_asset.asset_key if title_shape_pool_asset else None,
                "title_shape_pool_asset_id": title_shape_pool_asset.id if title_shape_pool_asset else None,
                "title_shape_pool_asset_version": title_shape_pool_asset.version_no if title_shape_pool_asset else None,
                "rule_id_filter": rule_id,
                "source_row_no_filter": source_row_no,
            },
            diversity_plan_json={},
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()

        selected_rules = [rules[index % len(rules)] for index in range(limit)] if focus_single_rule else rules[:limit]
        used_real_user_hashes: set[str] = set()
        used_real_user_route_families: dict[str, int] = {}
        used_title_reference_examples: set[str] = set()
        mouth_phrase_budget_items = _build_mouth_phrase_budget_items(
            _resolve_mouth_phrase_budget_config(asset),
            item_count=limit,
        )
        for index, rule in enumerate(selected_rules):
            self.db.add(
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=index + 1,
                    status="planned",
                    plan_json=self._product_experience_plan_from_rule(
                        rule,
                        asset=asset,
                        item_no=index + 1,
                        keyword_asset_key=resolved_keyword_asset_key,
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
                    ),
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
            and item.get("corpus")
            and (item.get("business_rule") or item.get("article_rule"))
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
        keyword_asset_key: str,
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
        rule_type = (
            rule.get("rule_type")
            or asset_content.get("rule_type")
            or "business_rule"
        )
        selected_examples, example_meta = self._selected_rule_examples(
            rule,
            sample_count=self._article_business_example_sample_count(asset, rule),
        )
        business_rule = (
            rule.get("business_rule")
            or rule.get("article_rule")
            or rule.get("topic")
        )
        resolved_model_config = self._article_business_model_config(asset, model_config)
        resolved_real_user_pool_config = _real_user_pool_config_for_rule(
            real_user_pool_config or _default_real_user_pool_config(asset),
            rule,
        )
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
        return {
            "rule_type": rule_type,
            "item_no": item_no,
            "asset_key": asset.asset_key,
            "keyword_asset_key": keyword_asset_key,
            "quality_guard_profile_key": quality_guard_profile_key,
            "keyword_selection": _resolve_keyword_selection(asset),
            "generation_requirements": _resolve_generation_requirements(asset),
            "content_path_control": content_path_control,
            "rule_asset_id": asset.id,
            "rule_asset_version": asset.version_no,
            "rule_id": rule.get("rule_id"),
            "business_rule": business_rule,
            "article_rule": rule.get("article_rule"),
            "topic": rule.get("topic"),
            "corpus": rule.get("corpus"),
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
                rule.get("article_rule"),
                rule.get("topic"),
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
                rule.get("article_rule"),
                rule.get("topic"),
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
        if asset.asset_key == "wangyue_article_business_rules" and _resolve_real_user_pool_asset_key(asset):
            return 1
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
    config: dict[str, Any] = _default_real_user_pool_config(asset)
    for source in (asset_content, asset_metadata):
        value = source.get("real_user_pool_sampling")
        if isinstance(value, dict):
            config.update(value)
    return config


def _real_user_pool_config_for_rule(config: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(config)
    overrides = resolved.get("source_row_overrides")
    if not isinstance(overrides, dict):
        return resolved

    candidate_keys = []
    source_row_no = _int_or_none(rule.get("source_row_no"))
    if source_row_no is not None:
        candidate_keys.append(str(source_row_no))
    for key in ("rule_id", "business_rule", "topic"):
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


def _default_real_user_pool_config(asset: AssetRegistry) -> dict[str, Any]:
    if asset.asset_key != "wangyue_article_business_rules":
        return {}
    return {
        "route_count": 1,
        "texture_count": 2,
        "title_shape_count": 0,
        "opening_or_ending_count": 1,
        "comment_count": 0,
        "title_reference_count": 0,
        "disable_static_title_reference": True,
    }


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
            rule.get("article_rule"),
            rule.get("topic"),
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
    row4_growth_rule = (
        asset.asset_key == "wangyue_article_business_rules"
        and (rule.get("source_row_no") == 4 or str(rule.get("business_rule") or "").startswith("营养不足/成长发育需求"))
    )
    for source in (rule, asset_content, asset_metadata):
        for item in source.get("synthetic_title_examples") or []:
            title = str(item.get("title") if isinstance(item, dict) else item or "").strip()
            match_text = _normalize_title_reference_match_text(title)
            if (
                title
                and _is_usable_synthetic_title_example(title)
                and (not row4_growth_rule or _is_usable_wangyue_growth_synthetic_title(title))
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
