"""Batch planning service for MAGA content generation."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.models.maga_assets import AssetRegistry


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


class ContentBatchPlanner:
    """Create item-level generation plans from MAGA asset snapshots."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_batch_plan(
        self,
        *,
        asset_key: str,
        product_topic: str,
        target_audience: str | None,
        style: str | None,
        count: int,
        created_by: str | None = None,
    ) -> ContentBatchJob:
        if count <= 0:
            raise ValueError("count must be positive")

        painpoints_asset = await self._latest_asset("painpoint_model", asset_key)
        selling_asset = await self._latest_asset("product_selling_points", asset_key)
        examples_asset = await self._latest_asset("reference_examples", asset_key)
        compliance_asset = await self._latest_asset("compliance_rules", asset_key)

        painpoints = self._items(painpoints_asset)
        selling_points = self._items(selling_asset)
        examples = self._items(examples_asset)
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
            },
            diversity_plan_json={
                "opening_types": OPENING_TYPES,
                "structure_types": STRUCTURE_TYPES,
                "emotion_pool": EMOTIONS,
                "cta_types": CTA_TYPES,
            },
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()

        for index in range(count):
            plan = self._build_item_plan(
                item_no=index + 1,
                asset_key=asset_key,
                product_topic=product_topic,
                target_audience=target_audience,
                style=style,
                painpoints=painpoints,
                selling_points=selling_points,
                examples=examples,
                compliance_rules=compliance_rules,
            )
            self.db.add(ContentBatchItem(batch_id=job.id, item_no=index + 1, status="planned", plan_json=plan))
        await self.db.flush()
        return job

    async def _latest_asset(self, asset_type: str, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == asset_type,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
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
        style: str | None,
        painpoints: list[dict[str, Any]],
        selling_points: list[dict[str, Any]],
        examples: list[dict[str, Any]],
        compliance_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        zero = item_no - 1
        pain_idx = zero % len(painpoints)
        selling_idx = (zero * 3 + zero // max(len(painpoints), 1)) % len(selling_points)
        example_idx = (zero * 5 + zero // 7) % len(examples)
        compliance_idx = zero % max(len(compliance_rules), 1)
        opening = OPENING_TYPES[zero % len(OPENING_TYPES)]
        structure = STRUCTURE_TYPES[(zero // len(OPENING_TYPES) + zero) % len(STRUCTURE_TYPES)]
        emotion = EMOTIONS[(zero * 2 + zero // 11) % len(EMOTIONS)]
        cta = CTA_TYPES[(zero * 3 + zero // 13) % len(CTA_TYPES)]

        return {
            "item_no": item_no,
            "asset_key": asset_key,
            "product_topic": product_topic,
            "target_audience": target_audience,
            "style": style,
            "painpoint_ref": self._ref("painpoint_model", asset_key, pain_idx, painpoints[pain_idx]),
            "selling_point_ref": self._ref("product_selling_points", asset_key, selling_idx, selling_points[selling_idx]),
            "reference_example_refs": [self._ref("reference_examples", asset_key, example_idx, examples[example_idx])],
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
                "forbidden_overlap_group": f"G{(zero % 20) + 1:02d}",
            },
            "brief_constraints": {
                "must_use_painpoint": True,
                "must_reference_example_without_copying": True,
                "output_fields": ["title", "body"],
            },
        }

    @staticmethod
    def _items(asset: AssetRegistry | None) -> list[dict[str, Any]]:
        if asset is None or not asset.content_json:
            return []
        items = asset.content_json.get("items", [])
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _ref(asset_type: str, asset_key: str, index: int, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "asset_type": asset_type,
            "asset_key": asset_key,
            "item_index": index,
            "item_id": item.get("asset_steward_id") or item.get("example_id") or f"{asset_type}_{index + 1}",
            "snapshot": item,
        }
