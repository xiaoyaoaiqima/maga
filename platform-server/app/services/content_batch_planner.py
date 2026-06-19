"""Batch planning service for MAGA content generation."""
from __future__ import annotations

import uuid
from secrets import SystemRandom
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.models.maga_assets import AssetRegistry
from app.services.business_rule_asset_types import ARTICLE_BUSINESS_RULE_ASSET_TYPES
from app.services.product_experience_rule_service import DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME
from app.services.system_prompt_keyword_service import DEFAULT_SYSTEM_KEYWORD_ASSET_KEY

DEFAULT_CONTENT_WORD_COUNT = "150-250"
DEFAULT_CONTENT_EMOJI = "少量"
ARTICLE_RULE_EXAMPLE_SAMPLE_COUNT = 3


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
                "rule_id_filter": rule_id,
                "source_row_no_filter": source_row_no,
            },
            diversity_plan_json={},
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()

        selected_rules = [rules[index % len(rules)] for index in range(limit)] if focus_single_rule else rules[:limit]
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
    ) -> dict[str, Any]:
        asset_content = asset.content_json or {}
        asset_metadata = asset.metadata_json or {}
        rule_type = (
            rule.get("rule_type")
            or asset_content.get("rule_type")
            or "business_rule"
        )
        selected_examples, example_meta = self._selected_rule_examples(rule)
        business_rule = (
            rule.get("business_rule")
            or rule.get("article_rule")
            or rule.get("topic")
        )
        resolved_model_config = self._article_business_model_config(asset, model_config)
        return {
            "rule_type": rule_type,
            "item_no": item_no,
            "asset_key": asset.asset_key,
            "keyword_asset_key": keyword_asset_key,
            "quality_guard_profile_key": quality_guard_profile_key,
            "keyword_selection": _resolve_keyword_selection(asset),
            "generation_requirements": _resolve_generation_requirements(asset),
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

    def _selected_rule_examples(self, rule: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        examples = [str(item).strip() for item in rule.get("examples") or [] if str(item).strip()]
        supplements = [str(item).strip() for item in rule.get("supplements") or [] if str(item).strip()]
        pool = examples or supplements
        selected_indices = _sample_indices(len(pool), ARTICLE_RULE_EXAMPLE_SAMPLE_COUNT)
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


def _normalize_keyword_asset_key(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
