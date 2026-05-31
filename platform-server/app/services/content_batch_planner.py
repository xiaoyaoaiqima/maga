"""Batch planning service for MAGA content generation."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.models.maga_assets import AssetRegistry
from app.services.content_batch_snapshot_adapter import DEFAULT_XHS_EMOJI, DEFAULT_XHS_WORD_COUNT
from app.services.product_experience_rule_service import (
    DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME,
    PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
)


OPENING_TYPES = [
    "过来人提醒",
    "真实经历",
    "误区澄清",
    "场景共鸣",
    "清单式建议",
    "反焦虑安抚",
    "对比选择",
    "观察记录",
]

STRUCTURE_TYPES = [
    "痛点-观察-建议",
    "经历-转折-选择",
    "误区-解释-推荐",
    "清单-理由-收束",
    "问题-判断-行动",
    "场景-感受-种草",
]

EMOTIONS = ["稳", "懂行", "不焦虑", "温和", "真实", "细致"]
CTA_TYPES = ["轻建议", "经验提醒", "收藏提示", "评论互动", "选择建议"]
NARRATIVE_FOCUSES = [
    "先共情",
    "先避坑",
    "先清单",
    "先经验记录",
    "先反焦虑",
    "先对比选择",
    "先观察判断",
    "先误区澄清",
]

CONTENT_ANGLES = [
    "误区澄清",
    "真实使用场景",
    "便便观察清单",
    "反焦虑安抚",
    "产品选择对比",
    "换奶适应记录",
    "喂养节奏建议",
    "边界提醒",
]

PERSONA_LENSES = ["新手妈妈", "谨慎型妈妈", "二胎妈妈", "过来人妈妈", "细节控妈妈", "容易焦虑的妈妈"]
SCENE_TYPES = ["日常喂养", "便便观察", "夜间照护", "换季适应", "转奶过渡", "外出照护"]
EVIDENCE_TYPES = ["经验记录", "清单建议", "对比判断", "边界提醒", "观察指标", "场景复盘"]


class ContentBatchPlanner:
    """Create item-level generation plans from MAGA asset snapshots."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_batch_plan(
        self,
        *,
        asset_key: str,
        product_topic: str | None,
        target_audience: str | None,
        persona_target: str | None = None,
        style: str | None,
        count: int,
        model_config: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> ContentBatchJob:
        if count <= 0:
            raise ValueError("count must be positive")

        rule_asset = await self._latest_product_experience_rule_asset(asset_key)
        if rule_asset is not None:
            return await self._create_product_experience_rule_plan(
                rule_asset,
                requested_count=count,
                model_config=model_config,
                created_by=created_by,
            )
        if not product_topic:
            raise ValueError(f"missing product_experience_rule_set for {asset_key}")

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
            diversity_plan_json={
                "opening_types": OPENING_TYPES,
                "structure_types": STRUCTURE_TYPES,
                "emotion_pool": EMOTIONS,
                "cta_types": CTA_TYPES,
                "narrative_focuses": NARRATIVE_FOCUSES,
            },
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
                painpoints=painpoints,
                selling_points=selling_points,
                examples=examples,
                writing_patterns=writing_patterns,
                compliance_rules=compliance_rules,
                model_config=model_config,
                used_asset_combo_keys=used_asset_combo_keys,
            )
            used_asset_combo_keys.add(plan["asset_combo_key"])
            self.db.add(ContentBatchItem(batch_id=job.id, item_no=index + 1, status="planned", plan_json=plan))
        await self.db.flush()
        return job

    async def _latest_product_experience_rule_asset(self, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _create_product_experience_rule_plan(
        self,
        asset: AssetRegistry,
        *,
        requested_count: int,
        model_config: dict[str, Any] | None,
        created_by: str | None,
    ) -> ContentBatchJob:
        rules = self._product_experience_rule_items(asset)
        if not rules:
            raise ValueError(f"product_experience_rule_set is empty for {asset.asset_key}")
        limit = self._product_experience_generation_limit(asset, rules, requested_count=requested_count)
        product_topic = (asset.content_json or {}).get("activity_name") or DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME
        job = ContentBatchJob(
            batch_code=f"batch_{uuid.uuid4().hex[:12]}",
            asset_key=asset.asset_key,
            product_topic=product_topic,
            target_audience=None,
            style=None,
            count=limit,
            status="planned",
            strategy_json={
                "source": PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
                "rule_asset_id": asset.id,
                "rule_asset_version": asset.version_no,
                "executor": DEFAULT_EXECUTOR_CODE,
                "generation_mode": "unified_content_generate",
            },
            diversity_plan_json={
                "opening_types": OPENING_TYPES,
                "structure_types": STRUCTURE_TYPES,
                "emotion_pool": EMOTIONS,
                "cta_types": CTA_TYPES,
                "narrative_focuses": NARRATIVE_FOCUSES,
            },
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()

        for index, rule in enumerate(rules[:limit]):
            self.db.add(
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=index + 1,
                    status="planned",
                    plan_json=self._product_experience_plan_from_rule(
                        rule,
                        asset=asset,
                        item_no=index + 1,
                        model_config=model_config,
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
        opening = OPENING_TYPES[zero % len(OPENING_TYPES)]
        structure = STRUCTURE_TYPES[(zero // len(OPENING_TYPES) + zero) % len(STRUCTURE_TYPES)]
        emotion = EMOTIONS[(zero * 2 + zero // 11) % len(EMOTIONS)]
        cta = CTA_TYPES[(zero * 3 + zero // 13) % len(CTA_TYPES)]
        # Stagger with the opening cycle so adjacent items do not share the same narrative angle.
        narrative_focus = NARRATIVE_FOCUSES[(zero + zero // len(OPENING_TYPES)) % len(NARRATIVE_FOCUSES)]
        content_angle = CONTENT_ANGLES[(zero * 3 + zero // len(OPENING_TYPES)) % len(CONTENT_ANGLES)]
        persona_lens = PERSONA_LENSES[(zero + zero // len(PERSONA_LENSES)) % len(PERSONA_LENSES)]
        scene_type = SCENE_TYPES[(zero * 2 + zero // len(SCENE_TYPES)) % len(SCENE_TYPES)]
        evidence_type = EVIDENCE_TYPES[(zero * 5 + zero // len(EVIDENCE_TYPES)) % len(EVIDENCE_TYPES)]
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
            "diversity_slot": {
                "opening_type": opening,
                "structure_type": structure,
                "emotion": emotion,
                "cta_type": cta,
                "narrative_focus": narrative_focus,
                "content_angle": content_angle,
                "persona_lens": persona_lens,
                "scene_type": scene_type,
                "evidence_type": evidence_type,
                "forbidden_overlap_group": f"G{(zero % 20) + 1:02d}",
            },
            "brief_constraints": {
                "word_count": DEFAULT_XHS_WORD_COUNT,
                "emoji": DEFAULT_XHS_EMOJI,
                "must_use_painpoint": True,
                "must_reference_example_without_copying": True,
                "output_fields": ["title", "body"],
            },
            "model_config": model_config or {},
        }

    def _product_experience_rule_items(self, asset: AssetRegistry) -> list[dict[str, Any]]:
        items = (asset.content_json or {}).get("items")
        return [
            item
            for item in items or []
            if isinstance(item, dict) and item.get("product_experience") and item.get("corpus")
        ]

    def _product_experience_generation_limit(
        self,
        asset: AssetRegistry,
        rules: list[dict[str, Any]],
        *,
        requested_count: int,
    ) -> int:
        metadata_limit = (asset.metadata_json or {}).get("default_generation_count")
        content_limit = (asset.content_json or {}).get("default_generation_count")
        value = metadata_limit or content_limit or requested_count
        try:
            limit = int(value)
        except (TypeError, ValueError):
            limit = requested_count
        return max(1, min(limit, len(rules)))

    def _product_experience_plan_from_rule(
        self,
        rule: dict[str, Any],
        *,
        asset: AssetRegistry,
        item_no: int,
        model_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        zero = item_no - 1
        return {
            "rule_type": "product_experience",
            "item_no": item_no,
            "asset_key": asset.asset_key,
            "rule_asset_id": asset.id,
            "rule_asset_version": asset.version_no,
            "rule_id": rule.get("rule_id"),
            "product_experience": rule.get("product_experience"),
            "baby_stage": rule.get("baby_stage"),
            "use_duration": rule.get("use_duration"),
            "topic": rule.get("topic"),
            "corpus": rule.get("corpus"),
            "examples": rule.get("examples") or [],
            "source_row_no": rule.get("source_row_no"),
            "output_fields": ["title", "body"],
            "diversity_slot": {
                "opening_type": OPENING_TYPES[zero % len(OPENING_TYPES)],
                "structure_type": STRUCTURE_TYPES[(zero // len(OPENING_TYPES) + zero) % len(STRUCTURE_TYPES)],
                "emotion": EMOTIONS[(zero * 2 + zero // 11) % len(EMOTIONS)],
                "cta_type": CTA_TYPES[(zero * 3 + zero // 13) % len(CTA_TYPES)],
                "narrative_focus": NARRATIVE_FOCUSES[(zero + zero // len(OPENING_TYPES)) % len(NARRATIVE_FOCUSES)],
                "content_angle": CONTENT_ANGLES[(zero * 3 + zero // len(OPENING_TYPES)) % len(CONTENT_ANGLES)],
                "persona_lens": PERSONA_LENSES[(zero + zero // len(PERSONA_LENSES)) % len(PERSONA_LENSES)],
                "scene_type": SCENE_TYPES[(zero * 2 + zero // len(SCENE_TYPES)) % len(SCENE_TYPES)],
                "evidence_type": EVIDENCE_TYPES[(zero * 5 + zero // len(EVIDENCE_TYPES)) % len(EVIDENCE_TYPES)],
                "forbidden_overlap_group": f"G{(zero % 20) + 1:02d}",
            },
            "brief_constraints": {
                "word_count": DEFAULT_XHS_WORD_COUNT,
                "emoji": DEFAULT_XHS_EMOJI,
                "output_fields": ["title", "body"],
            },
            "model_config": model_config or {},
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
    # Keep legacy snapshot fields so xhs-writer prompts can consume the upgraded
    # topic tree without needing a simultaneous runtime contract migration.
    return {
        **topic,
        "painpoint": topic.get("painpoint") or topic.get("topic"),
        "description": "；".join(descriptions) if descriptions else topic.get("description"),
        "selling_point": topic.get("selling_point") or (selling_point_names[0] if selling_point_names else None),
        "selling_points": selling_point_names,
    }


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
