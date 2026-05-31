"""Plan and execute comment batches from uploaded comment-angle rules."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.models.maga_assets import AssetRegistry
from app.schemas.content_agent import ContentAgentTaskCreate
from app.services.comment_angle_rule_service import (
    COMMENT_ANGLE_RULE_ASSET_TYPE,
    DEFAULT_COMMENT_BATCH_LIMIT,
    DEFAULT_COMMENT_BATCH_TOPIC,
)
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.executor_invocation_service import ExecutorInvocationClient
from app.services.forbidden_term_review_service import ForbiddenTermReviewService
from app.services.unified_content_generation_service import (
    CONTENT_GENERATE_CAPABILITY,
    UnifiedContentGenerationService,
)

@dataclass(frozen=True)
class CommentBatchExecutionResult:
    batch_id: int
    requested_limit: int
    generated_count: int
    failed_count: int
    item_ids: list[int]


class ContentCommentBatchService:
    """Use a comment-angle rule-set asset as the only operator input."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        invocation_client: ExecutorInvocationClient | None = None,
        callback_base_url: str,
        executor_code: str = DEFAULT_EXECUTOR_CODE,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ):
        self.db = db
        self.invocation_client = invocation_client
        self.callback_base_url = callback_base_url
        self.executor_code = executor_code
        self.session_factory = session_factory or async_sessionmaker(
            db.bind,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    async def create_and_execute_batch(
        self,
        *,
        asset_key: str,
        created_by: str | None = None,
    ) -> CommentBatchExecutionResult:
        asset = await self._require_rule_asset(asset_key)
        rules = self._rule_items(asset)
        limit = self._generation_limit(asset, rules)
        selected_rules = rules[:limit]
        if not selected_rules:
            raise ValueError("comment angle rule set has no usable rules")

        job = ContentBatchJob(
            batch_code=f"comment_{uuid.uuid4().hex[:12]}",
            asset_key=asset.asset_key,
            product_topic=DEFAULT_COMMENT_BATCH_TOPIC,
            target_audience=None,
            style=None,
            count=len(selected_rules),
            status="planned",
            strategy_json={
                "mode": "comment_angle",
                "rule_asset_id": asset.id,
                "rule_asset_version": asset.version_no,
                "executor": self.executor_code,
            },
            diversity_plan_json={
                "source": "comment_angle_rule_set",
                "rule_count": len(rules),
                "selected_count": len(selected_rules),
            },
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()

        for item_no, rule in enumerate(selected_rules, start=1):
            self.db.add(
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=item_no,
                    status="planned",
                    plan_json=self._plan_from_rule(rule, asset=asset, item_no=item_no),
                )
            )
        await self.db.flush()
        job_id = job.id
        item_ids = [item.id for item in await self._planned_items(job_id)]
        await self.db.commit()

        generated = 0
        failed = 0
        for item_id in item_ids:
            ok = await self._execute_one_item(item_id, created_by=created_by)
            generated += 1 if ok else 0
            failed += 0 if ok else 1

        job = await self._require_job(job_id)
        job.status = "generated" if generated == len(item_ids) else "partially_generated" if generated else "failed"
        await self.db.flush()
        return CommentBatchExecutionResult(
            batch_id=job_id,
            requested_limit=len(item_ids),
            generated_count=generated,
            failed_count=failed,
            item_ids=item_ids,
        )

    async def _require_rule_asset(self, asset_key: str) -> AssetRegistry:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == COMMENT_ANGLE_RULE_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            raise ValueError(f"comment angle rule set not found: {asset_key}")
        return asset

    async def _require_job(self, batch_id: int) -> ContentBatchJob:
        result = await self.db.execute(select(ContentBatchJob).where(ContentBatchJob.id == batch_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError("batch job not found")
        return job

    async def _planned_items(self, batch_id: int) -> list[ContentBatchItem]:
        result = await self.db.execute(
            select(ContentBatchItem)
            .where(ContentBatchItem.batch_id == batch_id)
            .order_by(ContentBatchItem.item_no)
        )
        return list(result.scalars().all())

    def _rule_items(self, asset: AssetRegistry) -> list[dict[str, Any]]:
        items = (asset.content_json or {}).get("items")
        return [item for item in items or [] if isinstance(item, dict) and item.get("comment_angle") and item.get("corpus")]

    def _generation_limit(self, asset: AssetRegistry, rules: list[dict[str, Any]]) -> int:
        metadata_limit = (asset.metadata_json or {}).get("default_generation_count")
        content_limit = (asset.content_json or {}).get("default_generation_count")
        value = metadata_limit or content_limit or DEFAULT_COMMENT_BATCH_LIMIT
        try:
            limit = int(value)
        except (TypeError, ValueError):
            limit = DEFAULT_COMMENT_BATCH_LIMIT
        return max(1, min(limit, len(rules)))

    def _plan_from_rule(self, rule: dict[str, Any], *, asset: AssetRegistry, item_no: int) -> dict[str, Any]:
        return {
            "rule_type": "comment_angle",
            "item_no": item_no,
            "asset_key": asset.asset_key,
            "rule_asset_id": asset.id,
            "rule_asset_version": asset.version_no,
            "rule_id": rule.get("rule_id"),
            "comment_angle": rule.get("comment_angle"),
            "corpus": rule.get("corpus"),
            "examples": rule.get("examples") or [],
            "supplements": rule.get("supplements") or [],
            "source_row_no": rule.get("source_row_no"),
            "output_fields": ["comment"],
        }

    async def _execute_one_item(self, item_id: int, *, created_by: str | None = None) -> bool:
        async with self.session_factory() as db:
            item = await self._require_item(db, item_id)
            item.status = "running"
            await db.commit()

            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            unified = await UnifiedContentGenerationService(db).build_snapshot(
                content_type="comment",
                business_rule=dict(item.plan_json or {}),
                item_no=item.item_no,
                output_fields=["comment"],
            )
            item.plan_json = {
                **(item.plan_json or {}),
                "unified_generation": {
                    "capability": CONTENT_GENERATE_CAPABILITY,
                    "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                    "keyword_asset": unified.input_snapshot.get("keyword_asset") or {},
                    "expert": unified.input_snapshot.get("expert") or {},
                    "rendered_prompt": unified.input_snapshot.get("rendered_prompt") or "",
                },
            }
            await db.flush()
            task_request = ContentAgentTaskCreate(
                task_type="content_generate",
                executor_code=self.executor_code,
                input_snapshot=unified.input_snapshot,
                asset_refs={
                    **unified.asset_refs,
                    "comment_angle_rule_set": {
                        "asset_key": (item.plan_json or {}).get("asset_key"),
                        "asset_id": (item.plan_json or {}).get("rule_asset_id"),
                        "version_no": (item.plan_json or {}).get("rule_asset_version"),
                    }
                },
                created_by=created_by,
            )
            try:
                result = await orchestrator.run_single_capability(task_request, capability=CONTENT_GENERATE_CAPABILITY)
                comment = str((result.output or {}).get("comment") or "").strip()
                if not comment:
                    raise ValueError("content.generate returned empty comment")
                item.status = "generated"
                item.task_id = result.run.task_id
                item.run_id = result.run.id
                item.title = (item.plan_json or {}).get("comment_angle")
                item.body = comment
                item.quality_json = {
                    "executor": self._executor_label(result.stage_calls),
                    "stage_call_count": len(result.stage_calls),
                    "run_status": result.run.status,
                    "rule_type": "comment_angle",
                    "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                    "expert_config_code": (unified.input_snapshot.get("expert") or {}).get("expert_config_code"),
                    "hard_pass": True,
                }
                item.diversity_json = {
                    "rule_type": "comment_angle",
                    "source_row_no": (item.plan_json or {}).get("source_row_no"),
                    "comment_angle": (item.plan_json or {}).get("comment_angle"),
                    "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                }
                await ForbiddenTermReviewService(db).review_and_rewrite_item(
                    item=item,
                    asset_key=(item.plan_json or {}).get("asset_key"),
                    orchestrator=orchestrator,
                    executor_code=self.executor_code,
                    content_type="comment",
                )
                item.error_message = None
                await db.commit()
                return True
            except Exception as exc:  # noqa: BLE001 - persist per-item failure for demo report
                item.status = "failed"
                if getattr(exc, "run_id", None):
                    item.run_id = exc.run_id
                item.error_message = str(exc)
                await db.commit()
                return False

    async def _require_item(self, db: AsyncSession, item_id: int) -> ContentBatchItem:
        result = await db.execute(select(ContentBatchItem).where(ContentBatchItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError("batch item not found")
        return item

    def _executor_label(self, stage_calls: list[Any]) -> str:
        for stage_call in stage_calls:
            output = getattr(stage_call, "output_snapshot", None) or {}
            runtime_mode = (output.get("runtime_result") or {}).get("mode")
            if runtime_mode:
                return str(runtime_mode)
        return "content_generate"
