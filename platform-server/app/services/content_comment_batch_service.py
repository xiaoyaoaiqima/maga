"""Plan and execute comment batches from uploaded comment business rules."""
from __future__ import annotations

import asyncio
import copy
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from random import SystemRandom
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchItemVersion, ContentBatchJob
from app.models.maga_assets import AssetRegistry
from app.schemas.content_agent import ContentAgentTaskCreate
from app.services.business_rule_asset_types import COMMENT_BUSINESS_RULE_ASSET_TYPES
from app.services.comment_business_rule_service import (
    COMMENT_BUSINESS_RULE_ASSET_TYPE,
    DEFAULT_COMMENT_BUSINESS_RULE_ASSET_KEY,
    DEFAULT_COMMENT_BATCH_LIMIT,
    DEFAULT_COMMENT_BATCH_TOPIC,
    _clean_corpus_for_prompt,
    _split_examples_from_corpus,
    normalize_comment_prompt_bundle,
)
from app.services.comment_delivery_ledger_service import CommentDeliveryLedgerService, ledger_entry_to_dict
from app.services.activity_quality_guard_service import (
    A2_NEGATIVE_POST_COMMENT_PROFILE_KEY,
    A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY,
    A2_SENTIMENT_COMMENT_PROFILE_KEY,
    A2_SENTIMENT_POST_PROFILE_KEY,
    ActivityQualityGuardService,
    QualityGuardProfile,
    derive_profile_keyword_from_text,
    quality_guard_profile_key_from_asset,
    resolve_quality_guard_profile,
)
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.comment_realness_review_service import CommentRealnessReviewService
from app.services.comment_batch_variation_review_service import CommentBatchVariationReviewService
from app.services.comment_batch_delivery_selection_service import CommentBatchDeliverySelectionService
from app.services.executor_invocation_service import ExecutorInvocationClient
from app.services.forbidden_term_review_service import ForbiddenTermReviewService
from app.services.system_prompt_keyword_service import DEFAULT_SYSTEM_KEYWORD_ASSET_KEY
from app.services.unified_content_generation_service import (
    CONTENT_GENERATE_CAPABILITY,
    UnifiedContentGenerationService,
)

COMMENT_SIMILARITY_REWRITE_THRESHOLD = 0.30
MAX_COMMENT_SIMILARITY_REWRITE_ROUNDS = 2
MAX_COMMENT_DELIVERY_DUPLICATE_REWRITE_ROUNDS = 1
COMMENT_HISTORY_SIMILARITY_LOOKBACK_LIMIT = 80
COMMENT_BATCH_EXECUTION_CONCURRENCY = 5
COMMENT_BATCH_MAX_COUNT = 300
COMMENT_RULE_EXAMPLE_SAMPLE_COUNT = 3
COMMENT_GENERATION_MODEL_TIMEOUT_SECONDS = 18
COMMENT_GENERATION_MODEL_MAX_RETRIES = 2
COMMENT_GENERATION_MAX_TOKENS = 256
COMMENT_THREAD_SHORT_REPLY_FORMAT_CODE = "comment_thread_short_reply"
YUANYUE_COMMENT_ASSET_KEY = "yuanyue_comment_activity"
YUANYUE_COMPETITOR_BRAND_TERMS = [
    "星飞帆",
    "爱他美",
    "a2",
    "A2",
    "飞鹤",
    "君乐宝",
    "贝因美",
    "惠氏",
    "启赋",
    "雀巢",
    "美赞臣",
    "雅培",
    "合生元",
    "佳贝艾特",
    "金领冠",
    "皇家美素",
    "蓝河",
    "澳优",
    "海普诺凯",
    "可瑞康",
    "诺优能",
    "完达山",
    "圣元",
]
YUANYUE_COMPETITOR_BRAND_REPLACEMENT = "源悦"
LOW_INFORMATION_COMMENT_REWRITE_INSTRUCTIONS = [
    "上一轮评论只有空泛开头，信息量太低",
    "保留当前业务规则，从业务规则或参考示例里借一个具体观察点",
    "不要只输出“我们家”“我家”“同款”“加一”这类空短句",
]


@dataclass(frozen=True)
class CommentBatchExecutionResult:
    batch_id: int
    requested_limit: int
    generated_count: int
    failed_count: int
    item_ids: list[int]


@dataclass(frozen=True)
class CommentBatchReviewReplayResult:
    batch_id: int
    reviewed_count: int
    skipped_count: int
    reviewed_item_nos: list[int]
    skipped_item_nos: list[int]
    changed_pass_item_nos: list[int]
    body_changed_item_nos: list[int]


class ContentCommentBatchService:
    """Use a comment business-rule asset as the only operator input."""

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

    async def replay_review(
        self,
        batch_id: int,
        *,
        item_nos: list[int] | None = None,
        created_by: str | None = None,
    ) -> CommentBatchReviewReplayResult:
        await self._require_job(batch_id)
        selected_item_nos = {int(item_no) for item_no in item_nos or [] if int(item_no) > 0}
        result = await self.db.execute(
            select(ContentBatchItem)
            .where(ContentBatchItem.batch_id == batch_id)
            .order_by(ContentBatchItem.item_no)
        )
        all_items = list(result.scalars().all())
        if not any(_is_comment_review_item(item) for item in all_items):
            raise ValueError("batch is not a comment batch")
        review_items = [
            item
            for item in all_items
            if item.status == "generated"
            and str(item.body or "").strip()
            and _is_comment_review_item(item)
            and (not selected_item_nos or item.item_no in selected_item_nos)
        ]
        skipped_item_nos = [
            item.item_no
            for item in all_items
            if (not selected_item_nos or item.item_no in selected_item_nos) and item not in review_items
        ]
        if not review_items:
            return CommentBatchReviewReplayResult(
                batch_id=batch_id,
                reviewed_count=0,
                skipped_count=len(skipped_item_nos),
                reviewed_item_nos=[],
                skipped_item_nos=skipped_item_nos,
                changed_pass_item_nos=[],
                body_changed_item_nos=[],
            )

        before_by_item_id: dict[int, dict[str, Any]] = {}
        guard = ActivityQualityGuardService()
        for item in review_items:
            before_quality = copy.deepcopy(item.quality_json or {})
            before_by_item_id[item.id] = {
                "hard_pass": before_quality.get("hard_pass"),
                "body": item.body,
                "activity_quality_guard": copy.deepcopy(before_quality.get("activity_quality_guard")),
            }
            candidate = SimpleNamespace(
                item_no=item.item_no,
                status=item.status,
                title=item.title,
                body=item.body,
                plan_json=copy.deepcopy(item.plan_json or {}),
                quality_json=_quality_without_replayable_comment_reviews(before_quality),
            )
            candidate.plan_json["review_replay"] = True
            guard.review_item(candidate)
            item.body = candidate.body
            item.quality_json = candidate.quality_json
            flag_modified(item, "quality_json")

        CommentBatchVariationReviewService().review_batch(review_items)
        reviewed_at = datetime.now(timezone.utc).isoformat()
        changed_pass_item_nos: list[int] = []
        body_changed_item_nos: list[int] = []
        for item in review_items:
            before = before_by_item_id[item.id]
            quality = dict(item.quality_json or {})
            after_pass = quality.get("hard_pass")
            if before["hard_pass"] != after_pass:
                changed_pass_item_nos.append(item.item_no)
            if before["body"] != item.body:
                body_changed_item_nos.append(item.item_no)
            history = list(quality.get("review_replay_history") or [])
            history.append(
                {
                    "reviewed_at": reviewed_at,
                    "created_by": created_by,
                    "stages": ["activity_quality_guard", "comment_batch_variation_review"],
                    "before_hard_pass": before["hard_pass"],
                    "after_hard_pass": after_pass,
                    "body_changed": before["body"] != item.body,
                    "before_activity_quality_guard": before["activity_quality_guard"],
                    "after_activity_quality_guard": copy.deepcopy(quality.get("activity_quality_guard")),
                }
            )
            quality["review_replay_history"] = history
            item.quality_json = quality
            flag_modified(item, "quality_json")
            self.db.add(
                ContentBatchItemVersion(
                    item_id=item.id,
                    version_no=await self._next_item_version_no(item.id),
                    source_action="comment_review_replay",
                    review_status="generated",
                    title=item.title,
                    body=item.body,
                    feedback_text=None,
                    created_by=created_by,
                    metadata_json={
                        "batch_id": batch_id,
                        "item_no": item.item_no,
                        "task_id": item.task_id,
                        "run_id": item.run_id,
                        "body_changed": before["body"] != item.body,
                        "before_hard_pass": before["hard_pass"],
                        "after_hard_pass": after_pass,
                        "stages": ["activity_quality_guard", "comment_batch_variation_review"],
                    },
                )
            )
        await self.db.flush()
        return CommentBatchReviewReplayResult(
            batch_id=batch_id,
            reviewed_count=len(review_items),
            skipped_count=len(skipped_item_nos),
            reviewed_item_nos=[item.item_no for item in review_items],
            skipped_item_nos=skipped_item_nos,
            changed_pass_item_nos=changed_pass_item_nos,
            body_changed_item_nos=body_changed_item_nos,
        )

    async def _next_item_version_no(self, item_id: int) -> int:
        result = await self.db.execute(
            select(func.max(ContentBatchItemVersion.version_no)).where(ContentBatchItemVersion.item_id == item_id)
        )
        return int(result.scalar_one_or_none() or 0) + 1

    async def create_and_execute_batch(
        self,
        *,
        asset_key: str,
        scenario_code: str | None = None,
        keyword_asset_key: str | None = None,
        quality_guard_profile_key: str | None = None,
        business_rule: str | None = None,
        rule_id: str | None = None,
        rule_ids: list[str] | None = None,
        source_row_no: int | None = None,
        draft_corpus: str | None = None,
        draft_rule_id: str | None = None,
        draft_source_row_no: int | None = None,
        draft_comment_prompt_bundle: dict[str, Any] | None = None,
        comment_prompt_slots: dict[str, list[str]] | None = None,
        comment_batch_variation_review: dict[str, Any] | None = None,
        comment_delivery_selection: dict[str, Any] | None = None,
        comment_post_context: str | None = None,
        count: int | None = None,
        concurrency: int = COMMENT_BATCH_EXECUTION_CONCURRENCY,
        created_by: str | None = None,
    ) -> CommentBatchExecutionResult:
        asset = await self._require_rule_asset(asset_key)
        all_rules = self._rule_items(asset)
        scenario = _comment_scenario_from_asset(asset, scenario_code)
        focus_business_rule = _normalize_business_rule(business_rule)
        rules = self._rules_for_scenario(all_rules, scenario) if scenario else all_rules
        rules = self._rules_for_business_rule(rules, focus_business_rule) if focus_business_rule else rules
        focus_rule_id = str(rule_id or "").strip() or None
        focus_rule_ids = _normalized_rule_ids(rule_ids)
        if focus_rule_id and focus_rule_id not in focus_rule_ids:
            focus_rule_ids.insert(0, focus_rule_id)
        focus_source_row_no = _int_or_none(source_row_no)
        if focus_rule_ids:
            rules = self._rules_for_multiple_items(rules, rule_ids=focus_rule_ids)
        if focus_source_row_no is not None:
            rules = self._rules_for_single_item(
                rules,
                rule_id=None,
                source_row_no=focus_source_row_no,
            )
        draft_override = _normalize_draft_rule_override(
            draft_corpus=draft_corpus,
            draft_rule_id=draft_rule_id or focus_rule_id,
            draft_source_row_no=draft_source_row_no if draft_source_row_no is not None else focus_source_row_no,
            draft_comment_prompt_bundle=draft_comment_prompt_bundle,
        )
        if draft_override:
            rules = self._rules_with_draft_override(rules, draft_override)
        prompt_slots_override = _normalize_comment_prompt_slots_override(comment_prompt_slots)
        if prompt_slots_override:
            rules = self._rules_with_prompt_slots_override(rules, prompt_slots_override)
        batch_variation_review_override = _normalize_comment_batch_variation_review_override(
            comment_batch_variation_review
        )
        if batch_variation_review_override:
            rules = self._rules_with_batch_variation_review_override(
                rules,
                batch_variation_review_override,
            )
        delivery_selection_override = _normalize_comment_delivery_selection_override(
            comment_delivery_selection
        )
        if delivery_selection_override:
            rules = self._rules_with_delivery_selection_override(
                rules,
                delivery_selection_override,
            )
        post_context_override = _normalize_comment_post_context_override(comment_post_context)
        if post_context_override:
            rules = self._rules_with_post_context_override(rules, post_context_override)
        focus_single_rule = len(focus_rule_ids) == 1 or focus_source_row_no is not None
        focus_multiple_rules = len(focus_rule_ids) > 1
        limit = self._generation_limit(
            asset,
            rules,
            requested_count=count,
            allow_repeat=bool(focus_business_rule) or focus_single_rule or focus_multiple_rules or bool(scenario),
        )
        if delivery_selection_override:
            target_count = int(delivery_selection_override["target_count"])
            if target_count > limit:
                raise ValueError(
                    "comment_delivery_selection.target_count cannot exceed generated candidate count"
                )
        resolved_keyword_asset_key = _resolve_keyword_asset_key(keyword_asset_key, asset)
        resolved_quality_guard_profile_key = quality_guard_profile_key or quality_guard_profile_key_from_asset(asset)
        quality_guard_profile = resolve_quality_guard_profile(resolved_quality_guard_profile_key)
        if resolved_quality_guard_profile_key and not quality_guard_profile:
            raise ValueError(f"unknown quality_guard_profile_key: {resolved_quality_guard_profile_key}")
        if scenario:
            selected_rules, selection_mode = self._select_rules_for_scenario(rules, scenario, limit)
        elif focus_multiple_rules:
            selected_rules = self._select_rules_even_repetition_with_remainder(rules, limit)
            selection_mode = "focused_rule_ids_even_repetition"
        else:
            selected_rules, selection_mode = self._select_rules_for_batch(
                rules,
                limit,
                focus_business_rule=focus_business_rule,
                profile=quality_guard_profile,
            )
        if not selected_rules:
            suffix = f" for business_rule={focus_business_rule}" if focus_business_rule else ""
            raise ValueError(f"comment business rule set has no usable rules{suffix}")

        job = ContentBatchJob(
            batch_code=f"comment_{uuid.uuid4().hex[:12]}",
            asset_key=asset.asset_key,
            product_topic=_comment_batch_product_topic(asset),
            target_audience=None,
            style=None,
            count=len(selected_rules),
            status="planned",
            strategy_json={
                "mode": "business_rule_focus_test" if focus_business_rule else "business_rule",
                "rule_asset_id": asset.id,
                "rule_asset_version": asset.version_no,
                "keyword_asset_key": resolved_keyword_asset_key,
                "keyword_selection": _keyword_selection_from_asset(asset),
                "quality_guard_profile_key": resolved_quality_guard_profile_key,
                "scenario_code": scenario.get("scenario_code") if scenario else None,
                "scenario_name": scenario.get("scenario_name") if scenario else None,
                "scenario_policy": _comment_scenario_policy(scenario),
                "business_rule_filter": focus_business_rule,
                "rule_id_filter": focus_rule_id,
                "rule_ids_filter": focus_rule_ids,
                "source_row_no_filter": focus_source_row_no,
                "draft_rule_override": _draft_override_summary(draft_override),
                "comment_prompt_slots_override": prompt_slots_override,
                "comment_batch_variation_review_override": batch_variation_review_override,
                "comment_delivery_selection_override": delivery_selection_override,
                "comment_post_context_override": post_context_override,
                "execution_concurrency": concurrency,
                "executor": self.executor_code,
            },
            diversity_plan_json={
                "source": COMMENT_BUSINESS_RULE_ASSET_TYPE,
                "rule_count": len(all_rules),
                "filtered_rule_count": len(rules),
                "selected_count": len(selected_rules),
                "selection_mode": selection_mode,
                "scenario_code": scenario.get("scenario_code") if scenario else None,
                "scenario_name": scenario.get("scenario_name") if scenario else None,
                "scenario_directions": [
                    str(rule.get("scenario_direction") or "") for rule in selected_rules
                ],
                "business_rule_filter": focus_business_rule,
                "rule_id_filter": focus_rule_id,
                "rule_ids_filter": focus_rule_ids,
                "source_row_no_filter": focus_source_row_no,
                "draft_rule_override": _draft_override_summary(draft_override),
                "comment_prompt_slots_override": prompt_slots_override,
                "comment_batch_variation_review_override": batch_variation_review_override,
                "comment_delivery_selection_override": delivery_selection_override,
                "comment_post_context_override": post_context_override,
                "selected_source_row_nos": [rule.get("source_row_no") for rule in selected_rules],
            },
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()

        rule_occurrences: dict[str, int] = {}
        for item_no, rule in enumerate(selected_rules, start=1):
            occurrence_key = str(rule.get("rule_id") or rule.get("source_row_no") or "")
            rule_occurrence_no = rule_occurrences.get(occurrence_key, 0)
            rule_occurrences[occurrence_key] = rule_occurrence_no + 1
            self.db.add(
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=item_no,
                    status="planned",
                    plan_json=self._plan_from_rule(
                        rule,
                        asset=asset,
                        item_no=item_no,
                        rule_occurrence_no=rule_occurrence_no,
                        keyword_asset_key=resolved_keyword_asset_key,
                        quality_guard_profile_key=resolved_quality_guard_profile_key,
                    ),
                )
            )
        await self.db.flush()
        job_id = job.id
        item_ids = [item.id for item in await self._planned_items(job_id)]
        await self.db.commit()

        semaphore = asyncio.Semaphore(concurrency)

        async def run_item(item_id: int) -> bool:
            # 每条评论用独立 DB session；AsyncSession 不能在并发任务之间共享 flush/commit。
            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        self._execute_one_item(item_id, created_by=created_by),
                        timeout=_comment_item_soft_timeout_seconds(),
                    )
                except TimeoutError:
                    await self._mark_item_timeout(item_id)
                    return False

        requested_output_count = sum(_comment_plan_output_count(item.plan_json or {}) for item in await self._planned_items(job_id))
        results = await asyncio.gather(*(run_item(item_id) for item_id in item_ids))
        generated_seed_count = sum(1 for ok in results if ok)
        failed = sum(1 for ok in results if not ok)

        job = await self._require_job(job_id)
        job.status = "generated" if generated_seed_count == len(item_ids) else "partially_generated" if generated_seed_count else "failed"
        await self.db.flush()
        if generated_seed_count:
            await self._review_generated_batch_similarity(job_id)
            await self._review_generated_batch_delivery_duplicates(job_id)
        await self.db.commit()
        async with self.session_factory() as review_db:
            review_job_result = await review_db.execute(
                select(ContentBatchJob).where(ContentBatchJob.id == job_id)
            )
            review_job = review_job_result.scalar_one()
            review_items = await self._planned_items(job_id, db=review_db)
            ActivityQualityGuardService().review_batch(review_job, review_items)
            batch_variation_review = CommentBatchVariationReviewService().review_batch(review_items)
            delivery_selection = CommentBatchDeliverySelectionService().select_batch(review_items)
            if batch_variation_review or delivery_selection:
                for item in review_items:
                    flag_modified(item, "quality_json")
            await review_db.commit()
        # 并发 item 使用独立 session 写回；最终计数也用新 session 读取，避免主 session
        # 在 MySQL repeatable-read 事务里继续看到 planned 快照，出现正文已生成但计数为 0。
        async with self.session_factory() as result_db:
            persisted_items = list(
                (
                    await result_db.execute(
                        select(ContentBatchItem)
                        .where(ContentBatchItem.batch_id == job_id)
                        .order_by(ContentBatchItem.item_no)
                    )
                ).scalars().all()
            )
        generated_items = [item for item in persisted_items if item.status == "generated"]
        return CommentBatchExecutionResult(
            batch_id=job_id,
            requested_limit=requested_output_count,
            generated_count=len(generated_items),
            failed_count=failed,
            item_ids=[item.id for item in persisted_items],
        )

    async def _require_rule_asset(self, asset_key: str) -> AssetRegistry:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type.in_(COMMENT_BUSINESS_RULE_ASSET_TYPES),
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.status == "active",
                AssetRegistry.asset_stage == "production",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            raise ValueError(f"comment business rule set not found: {asset_key}")
        return asset

    async def _require_job(self, batch_id: int) -> ContentBatchJob:
        result = await self.db.execute(select(ContentBatchJob).where(ContentBatchJob.id == batch_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError("batch job not found")
        return job

    async def _planned_items(
        self,
        batch_id: int,
        *,
        db: AsyncSession | None = None,
    ) -> list[ContentBatchItem]:
        session = db or self.db
        result = await session.execute(
            select(ContentBatchItem)
            .where(ContentBatchItem.batch_id == batch_id)
            .order_by(ContentBatchItem.item_no)
        )
        return list(result.scalars().all())

    def _rule_items(self, asset: AssetRegistry) -> list[dict[str, Any]]:
        items = (asset.content_json or {}).get("items")
        return [item for item in items or [] if isinstance(item, dict) and _business_rule_name(item) and item.get("corpus")]

    def _generation_limit(
        self,
        asset: AssetRegistry,
        rules: list[dict[str, Any]],
        *,
        requested_count: int | None = None,
        allow_repeat: bool = False,
    ) -> int:
        metadata_limit = (asset.metadata_json or {}).get("default_generation_count")
        content_limit = (asset.content_json or {}).get("default_generation_count")
        value = requested_count or metadata_limit or content_limit or DEFAULT_COMMENT_BATCH_LIMIT
        try:
            limit = int(value)
        except (TypeError, ValueError):
            limit = DEFAULT_COMMENT_BATCH_LIMIT
        requested_repeat = requested_count is not None and limit > len(rules)
        upper_bound = COMMENT_BATCH_MAX_COUNT if allow_repeat or requested_repeat else len(rules)
        return max(1, min(limit, upper_bound))

    def _rules_for_business_rule(self, rules: list[dict[str, Any]], business_rule: str | None) -> list[dict[str, Any]]:
        if not business_rule:
            return list(rules)
        return [
            rule
            for rule in rules
            if _normalize_business_rule(_business_rule_name(rule)) == business_rule
        ]

    def _rules_for_scenario(
        self,
        rules: list[dict[str, Any]],
        scenario: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rule_ids = {
            str(rule_id).strip()
            for direction in scenario.get("directions") or []
            if isinstance(direction, dict)
            for rule_id in direction.get("rule_ids") or []
            if str(rule_id).strip()
        }
        return [rule for rule in rules if str(rule.get("rule_id") or "").strip() in rule_ids]

    def _rules_for_single_item(
        self,
        rules: list[dict[str, Any]],
        *,
        rule_id: str | None,
        source_row_no: int | None,
    ) -> list[dict[str, Any]]:
        # 重要逻辑：by case 调试要能只重复抽一个子方向，否则同一业务规则下的 11 个子方向会混在一起。
        return [
            rule
            for rule in rules
            if (not rule_id or str(rule.get("rule_id") or "").strip() == rule_id)
            and (source_row_no is None or _int_or_none(rule.get("source_row_no")) == source_row_no)
        ]

    def _rules_for_multiple_items(
        self,
        rules: list[dict[str, Any]],
        *,
        rule_ids: list[str],
    ) -> list[dict[str, Any]]:
        by_id = {str(rule.get("rule_id") or "").strip(): rule for rule in rules}
        missing = [rule_id for rule_id in rule_ids if rule_id not in by_id]
        if missing:
            raise ValueError(f"comment business rule ids not found: {', '.join(missing)}")
        return [by_id[rule_id] for rule_id in rule_ids]

    def _rules_with_draft_override(
        self,
        rules: list[dict[str, Any]],
        draft_override: dict[str, Any],
    ) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        matched = False
        for rule in rules:
            if not _rule_matches_draft_override(rule, draft_override):
                updated.append(rule)
                continue
            next_rule = dict(rule)
            draft_comment_prompt_bundle = draft_override.get("comment_prompt_bundle")
            if draft_comment_prompt_bundle:
                next_rule["prompt_mode"] = "comment_prompt_bundle"
                next_rule["comment_prompt_bundle"] = copy.deepcopy(draft_comment_prompt_bundle)
                next_rule["content_direction"] = draft_comment_prompt_bundle["content_direction"]
                next_rule["activity_material"] = list(draft_comment_prompt_bundle["activity_material"])
                next_rule["corpus"] = draft_comment_prompt_bundle["content_direction"]
            else:
                draft_corpus, draft_examples = _split_examples_from_corpus(draft_override["corpus"])
                next_rule["corpus"] = _clean_corpus_for_prompt(
                    draft_corpus,
                    business_rule=_business_rule_name(next_rule),
                )
                next_rule["examples"] = draft_examples
            next_rule["draft_rule_override"] = _draft_override_summary(draft_override)
            updated.append(next_rule)
            matched = True
        if not matched:
            raise ValueError("draft corpus target rule not found; pass draft_rule_id or draft_source_row_no matching the selected rule")
        return updated

    @staticmethod
    def _rules_with_prompt_slots_override(
        rules: list[dict[str, Any]],
        prompt_slots: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        return [
            {
                **rule,
                "prompt_slots": copy.deepcopy(prompt_slots),
                "prompt_slot_selection_mode": "round_robin",
                "bundle_prompt_slots_source": "batch_override",
            }
            for rule in rules
        ]

    @staticmethod
    def _rules_with_batch_variation_review_override(
        rules: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [{**rule, "batch_variation_review": copy.deepcopy(config)} for rule in rules]

    @staticmethod
    def _rules_with_delivery_selection_override(
        rules: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [{**rule, "delivery_selection": copy.deepcopy(config)} for rule in rules]

    @staticmethod
    def _rules_with_post_context_override(
        rules: list[dict[str, Any]],
        post_context: str,
    ) -> list[dict[str, Any]]:
        return [{**rule, "scenario_post_context": post_context} for rule in rules]

    def _select_rules_for_batch(
        self,
        rules: list[dict[str, Any]],
        limit: int,
        *,
        focus_business_rule: str | None,
        profile: QualityGuardProfile | None,
    ) -> tuple[list[dict[str, Any]], str]:
        use_replacement = bool(focus_business_rule) or limit > len(rules)
        if focus_business_rule:
            return self._select_rules_with_replacement(rules, limit), "random_with_replacement"
        if len(rules) <= limit:
            if not use_replacement:
                return list(rules), "all"
            if limit % len(rules) == 0:
                return self._select_rules_even_repetition(rules, limit), "even_rule_repetition"
        if profile and profile.context_keyword_allowlist:
            selected = self._select_rules_balanced_by_profile_keyword(
                rules,
                limit,
                profile,
                with_replacement=use_replacement,
            )
            if selected:
                mode = "keyword_balanced_random_with_replacement" if use_replacement else "keyword_balanced_random"
                return selected, mode
        if use_replacement:
            return self._select_rules_with_replacement(rules, limit), "random_with_replacement"
        return self._select_rules(rules, limit), "balanced_random"

    def _select_rules_for_scenario(
        self,
        rules: list[dict[str, Any]],
        scenario: dict[str, Any],
        limit: int,
    ) -> tuple[list[dict[str, Any]], str]:
        by_id = {str(rule.get("rule_id") or "").strip(): rule for rule in rules}
        eligible_directions: list[dict[str, Any]] = []
        for direction in scenario.get("directions") or []:
            if not isinstance(direction, dict):
                continue
            direction_rules = [
                by_id[rule_id]
                for raw_rule_id in direction.get("rule_ids") or []
                if (rule_id := str(raw_rule_id or "").strip()) in by_id
            ]
            if direction_rules:
                eligible_directions.append({**direction, "_rules": direction_rules})
        if not eligible_directions:
            return [], "scenario_no_eligible_rules"

        allocations = _weighted_comment_scenario_allocations(eligible_directions, limit)
        rng = SystemRandom()
        selected: list[dict[str, Any]] = []
        uses_seed_expansion = False
        for direction, count in zip(eligible_directions, allocations):
            bucket = list(direction["_rules"])
            rng.shuffle(bucket)
            output_batch_size = _comment_scenario_output_batch_size(direction)
            if output_batch_size <= 1:
                for index in range(count):
                    selected.append(_rule_with_comment_scenario(bucket[index % len(bucket)], scenario, direction))
                continue
            uses_seed_expansion = True
            remaining = count
            chunk_index = 0
            while remaining > 0:
                chunk_count = min(output_batch_size, remaining)
                selected_rule = _rule_with_comment_scenario(
                    bucket[chunk_index % len(bucket)],
                    scenario,
                    direction,
                )
                selected_rule["output_format_mode"] = "json_string_array"
                selected_rule["expansion_count"] = chunk_count
                selected.append(selected_rule)
                remaining -= chunk_count
                chunk_index += 1
        rng.shuffle(selected)
        return selected, "scenario_weighted_seed_expansion" if uses_seed_expansion else "scenario_weighted"

    def _select_rules_balanced_by_profile_keyword(
        self,
        rules: list[dict[str, Any]],
        limit: int,
        profile: QualityGuardProfile,
        *,
        with_replacement: bool = False,
    ) -> list[dict[str, Any]]:
        rng = SystemRandom()
        groups: dict[str, list[dict[str, Any]]] = {}
        for rule in rules:
            keyword = _rule_profile_keyword(rule, profile)
            groups.setdefault(keyword, []).append(rule)

        ordered_keys = [keyword for keyword in profile.context_keyword_allowlist if groups.get(keyword)]
        ordered_keys.extend(keyword for keyword in groups if keyword not in ordered_keys)
        if len(ordered_keys) < 2:
            return []

        original_groups = {keyword: list(bucket) for keyword, bucket in groups.items()}
        buckets = {keyword: list(bucket) for keyword, bucket in groups.items()}
        for bucket in buckets.values():
            rng.shuffle(bucket)
        rng.shuffle(ordered_keys)

        selected: list[dict[str, Any]] = []
        while ordered_keys and len(selected) < limit:
            next_keys: list[str] = []
            for keyword in ordered_keys:
                bucket = buckets.get(keyword) or []
                if not bucket and with_replacement:
                    bucket = list(original_groups.get(keyword) or [])
                    rng.shuffle(bucket)
                    buckets[keyword] = bucket
                if not bucket:
                    continue
                selected.append(bucket.pop())
                if len(selected) >= limit:
                    break
                if bucket or (with_replacement and original_groups.get(keyword)):
                    next_keys.append(keyword)
            rng.shuffle(next_keys)
            ordered_keys = next_keys
        return selected

    def _select_rules(self, rules: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if len(rules) <= limit:
            return list(rules)

        rng = SystemRandom()
        # Keep each batch spread across business rules instead of repeatedly taking the first rows.
        groups: dict[str, list[dict[str, Any]]] = {}
        for rule in rules:
            key = str(_business_rule_name(rule) or "").strip() or str(rule.get("source_row_no") or "")
            groups.setdefault(key, []).append(rule)

        buckets = [list(bucket) for bucket in groups.values()]
        for bucket in buckets:
            rng.shuffle(bucket)
        rng.shuffle(buckets)

        selected: list[dict[str, Any]] = []
        while buckets and len(selected) < limit:
            next_round: list[list[dict[str, Any]]] = []
            for bucket in buckets:
                if len(selected) >= limit:
                    break
                selected.append(bucket.pop())
                if bucket:
                    next_round.append(bucket)
            rng.shuffle(next_round)
            buckets = next_round
        return selected

    def _select_rules_with_replacement(self, rules: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not rules:
            return []
        rng = SystemRandom()
        # 单条业务规则测试批次会重复同一规则，但每个 item 仍会重新随机抽示例。
        return [rng.choice(rules) for _ in range(limit)]

    def _select_rules_even_repetition(self, rules: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not rules:
            return []
        repeat_count = max(1, limit // len(rules))
        # 活动抽样明确要求“每条业务规则 N 条”时，整轮重复规则，避免带放回抽样漏掉某个业务规则。
        return [rule for _ in range(repeat_count) for rule in rules][:limit]

    def _select_rules_even_repetition_with_remainder(
        self,
        rules: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not rules:
            return []
        selected = [rules[index % len(rules)] for index in range(limit)]
        SystemRandom().shuffle(selected)
        return selected

    def _plan_from_rule(
        self,
        rule: dict[str, Any],
        *,
        asset: AssetRegistry,
        item_no: int,
        rule_occurrence_no: int = 0,
        keyword_asset_key: str = DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
        quality_guard_profile_key: str | None = None,
    ) -> dict[str, Any]:
        uses_prompt_bundle = _uses_comment_prompt_bundle_rule(rule)
        bundle_prompt_slots_source = _bundle_prompt_slots_source(rule)
        if not uses_prompt_bundle or bundle_prompt_slots_source:
            rule = _rule_with_rotated_prompt_slots(rule, rule_occurrence_no=rule_occurrence_no)
        if not uses_prompt_bundle:
            rule = _rule_with_rotated_variation_slots(rule, rule_occurrence_no=rule_occurrence_no)
        if uses_prompt_bundle:
            selected_examples = []
            example_meta = {
                "example_pool_count": len(rule.get("examples") or []),
                "supplement_pool_count": len(rule.get("supplements") or []),
                "example_sample_count": 0,
                "selected_example_source": "none",
                "selected_example_indices": [],
            }
        else:
            selected_examples, example_meta = self._selected_prompt_examples(rule)
        keyword_rule = {
            **rule,
            "asset_key": asset.asset_key,
            "quality_guard_profile_key": quality_guard_profile_key,
        }
        if uses_prompt_bundle:
            keyword_selection, keyword_selection_meta = {}, {}
            comment_tone_options = []
        else:
            keyword_selection, keyword_selection_meta = _keyword_selection_with_rule_overrides(
                _keyword_selection_from_asset(asset),
                keyword_rule,
            )
            comment_tone_options = _comment_tone_options_from_asset(asset, keyword_rule)
        scenario_generation_requirements = (
            None
            if rule.get("activity_material")
            else rule.get("scenario_generation_requirements")
        )
        generation_requirements = _merge_comment_generation_requirements(
            _generation_requirements_from_asset(asset),
            rule.get("generation_requirements"),
            scenario_generation_requirements,
        )
        plan = {
            "rule_type": "business_rule",
            "render_reference_examples": not uses_prompt_bundle,
            "item_no": item_no,
            "asset_key": asset.asset_key,
            "keyword_asset_key": keyword_asset_key,
            "keyword_selection": keyword_selection,
            "generation_requirements": generation_requirements,
            "batch_variation_review": copy.deepcopy(
                rule.get("batch_variation_review") or _batch_variation_review_from_asset(asset)
            ),
            "delivery_selection": copy.deepcopy(
                rule.get("delivery_selection") or _delivery_selection_from_asset(asset)
            ),
            "quality_guard_profile_key": quality_guard_profile_key,
            "rule_asset_id": asset.id,
            "rule_asset_version": asset.version_no,
            "rule_id": rule.get("rule_id"),
            "business_rule": _business_rule_name(rule),
            "corpus": rule.get("corpus"),
            "content_direction": rule.get("content_direction"),
            "activity_material": rule.get("activity_material"),
            "prompt_mode": rule.get("prompt_mode"),
            "comment_prompt_bundle": copy.deepcopy(rule.get("comment_prompt_bundle")),
            "examples": selected_examples,
            "supplements": [],
            "draft_rule_override": rule.get("draft_rule_override"),
            **example_meta,
            **keyword_selection_meta,
            "source_row_no": rule.get("source_row_no"),
            "scenario_code": rule.get("scenario_code"),
            "scenario_name": rule.get("scenario_name"),
            "scenario_post_context": rule.get("scenario_post_context"),
            "scenario_direction": rule.get("scenario_direction"),
            "scenario_direction_name": rule.get("scenario_direction_name"),
            "scenario_sentiment": rule.get("scenario_sentiment"),
            "scenario_interaction_reply": bool(rule.get("scenario_interaction_reply")),
            "scenario_guard_keyword": rule.get("scenario_guard_keyword"),
            "output_fields": ["comment"],
        }
        if comment_tone_options:
            plan["comment_tone_options"] = comment_tone_options
        if isinstance(rule.get("model_config"), dict):
            plan["model_config"] = dict(rule["model_config"])
        output_config = _comment_generation_output_config(rule, asset)
        if output_config:
            plan["output_format"] = output_config
            plan["output_format_mode"] = output_config["mode"]
            plan["expansion_count"] = output_config["count"]
        for key in ("prompt_slots", "comment_prompt_slots", "preselected_prompt_slots"):
            if (not uses_prompt_bundle or bundle_prompt_slots_source) and rule.get(key):
                plan[key] = rule.get(key)
        for key in ("variation_slots", "preselected_variation_slots"):
            if not uses_prompt_bundle and rule.get(key):
                plan[key] = rule.get(key)
        if bundle_prompt_slots_source:
            plan["bundle_prompt_slots_source"] = bundle_prompt_slots_source
        return plan

    def _selected_prompt_examples(self, rule: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        examples = [str(item).strip() for item in rule.get("examples") or [] if str(item).strip()]
        supplements = [str(item).strip() for item in rule.get("supplements") or [] if str(item).strip()]
        scenario_examples = [
            str(item).strip() for item in rule.get("scenario_examples") or [] if str(item).strip()
        ]
        selected_gift = _selected_gift_prompt_slot_value(rule)
        if selected_gift:
            examples = _filter_selected_gift_prompt_examples(examples, selected_gift=selected_gift)
            supplements = _filter_selected_gift_prompt_examples(supplements, selected_gift=selected_gift)
            scenario_examples = _filter_selected_gift_prompt_examples(
                scenario_examples,
                selected_gift=selected_gift,
            )
        else:
            examples = _filter_member_rule_prompt_examples(rule, examples)
            supplements = _filter_member_rule_prompt_examples(rule, supplements)
        # 场景只补充帖子背景，不覆盖本条业务规则的参考示例；否则会把细规则
        # 拉回场景大类事实。只有底层规则完全没有示例时，才兜底使用场景示例。
        pool = examples or supplements or scenario_examples
        selected_indices = _sample_indices(len(pool), COMMENT_RULE_EXAMPLE_SAMPLE_COUNT)
        # 重要逻辑：评论也只把少量抽样示例放进 prompt，保留真人语气颗粒，
        # 避免旧式全量示例池把模型拉回模板复刻。
        selected = [pool[index] for index in selected_indices]
        return selected, {
            "example_pool_count": len(examples),
            "supplement_pool_count": len(supplements),
            "example_sample_count": len(selected),
            "selected_example_source": (
                "examples"
                if examples
                else "supplements"
                if supplements
                else "scenario_examples"
                if scenario_examples
                else "none"
            ),
            "selected_example_indices": selected_indices,
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
            model_config = dict((item.plan_json or {}).get("model_config") or {})
            model_config.setdefault("max_tokens", _comment_generation_max_tokens(item.plan_json or {}))
            model_config.setdefault("timeout", COMMENT_GENERATION_MODEL_TIMEOUT_SECONDS)
            model_config.setdefault("max_retries", COMMENT_GENERATION_MODEL_MAX_RETRIES)
            unified = await UnifiedContentGenerationService(db).build_snapshot(
                content_type="comment",
                business_rule=dict(item.plan_json or {}),
                item_no=item.item_no,
                output_fields=["comment"],
                keyword_asset_key=(item.plan_json or {}).get("keyword_asset_key"),
                model_config=model_config,
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
                    "comment_business_rule_set": {
                        "asset_key": (item.plan_json or {}).get("asset_key"),
                        "asset_id": (item.plan_json or {}).get("rule_asset_id"),
                        "version_no": (item.plan_json or {}).get("rule_asset_version"),
                    }
                },
                created_by=created_by,
            )
            expanded_items: list[ContentBatchItem] = []
            try:
                result = await orchestrator.run_single_capability(task_request, capability=CONTENT_GENERATE_CAPABILITY)
                comments = self._generated_comments_from_output(result.output or {})
                if not comments:
                    raise ValueError("content.generate returned empty comment")
                used_empty_fallback = False
                generated_items = [item]
                if len(comments) > 1:
                    expanded_items = await self._create_expanded_comment_items(
                        db=db,
                        seed_item=item,
                        comments=comments[1:],
                    )
                    generated_items.extend(expanded_items)
                for index, target_item in enumerate(generated_items):
                    await self._apply_generated_comment_to_item(
                        db=db,
                        item=target_item,
                        comment=comments[index],
                        result=result,
                        unified_input=unified.input_snapshot,
                        orchestrator=orchestrator,
                        used_empty_fallback=used_empty_fallback if index == 0 else False,
                    )
                item.error_message = None
                await db.commit()
                return True
            except Exception as exc:  # noqa: BLE001 - persist per-item failure for demo report
                for failed_item in [item, *expanded_items]:
                    failed_item.status = "failed"
                    if getattr(exc, "run_id", None):
                        failed_item.run_id = exc.run_id
                    failed_item.error_message = str(exc)
                await db.commit()
                return False

    @staticmethod
    def _generated_comments_from_output(output: dict[str, Any]) -> list[str]:
        raw_comments = output.get("comments")
        if raw_comments is None:
            raw_items = output.get("items")
            if isinstance(raw_items, list):
                raw_comments = [
                    raw_item.get("comment")
                    for raw_item in raw_items
                    if isinstance(raw_item, dict)
                ]
        if raw_comments is None:
            raw_comments = [output.get("comment")]
        return [str(comment).strip() for comment in raw_comments or [] if str(comment or "").strip()]

    async def _create_expanded_comment_items(
        self,
        *,
        db: AsyncSession,
        seed_item: ContentBatchItem,
        comments: list[str],
    ) -> list[ContentBatchItem]:
        created: list[ContentBatchItem] = []
        base_plan = dict(seed_item.plan_json or {})
        for index, _comment in enumerate(comments, start=2):
            plan = {
                **base_plan,
                "item_no": seed_item.item_no * 1000 + index,
                "expanded_from_item_id": seed_item.id,
                "expanded_from_item_no": seed_item.item_no,
                "expanded_index": index,
            }
            expanded_item = ContentBatchItem(
                batch_id=seed_item.batch_id,
                item_no=seed_item.item_no * 1000 + index,
                status="running",
                plan_json=plan,
            )
            db.add(expanded_item)
            created.append(expanded_item)
        await db.flush()
        return created

    async def _apply_generated_comment_to_item(
        self,
        *,
        db: AsyncSession,
        item: ContentBatchItem,
        comment: str,
        result: Any,
        unified_input: dict[str, Any],
        orchestrator: ContentAgentOrchestrator,
        used_empty_fallback: bool,
    ) -> None:
        comment = self._normalize_comment_length(item, comment)
        item.status = "generated"
        item.task_id = result.run.task_id
        item.run_id = result.run.id
        item.title = (item.plan_json or {}).get("business_rule")
        item.body = comment
        item.quality_json = {
            "executor": self._executor_label(result.stage_calls),
            "stage_call_count": len(result.stage_calls),
            "run_status": result.run.status,
            "rule_type": "business_rule",
            "selected_keywords": unified_input.get("selected_keywords") or [],
            "expert_config_code": (unified_input.get("expert") or {}).get("expert_config_code"),
            "hard_pass": True,
            "empty_generation_fallback": used_empty_fallback,
        }
        item.diversity_json = {
            "rule_type": "business_rule",
            "source_row_no": (item.plan_json or {}).get("source_row_no"),
            "business_rule": (item.plan_json or {}).get("business_rule"),
            "selected_keywords": unified_input.get("selected_keywords") or [],
        }
        await self._review_and_rewrite_low_information(
            item=item,
            orchestrator=orchestrator,
        )
        await CommentRealnessReviewService().review_and_rewrite_item(
            item=item,
            orchestrator=orchestrator,
            executor_code=self.executor_code,
        )
        item.body = self._normalize_comment_length(item, item.body or "")
        self._sanitize_brand_hallucinations(item)
        await ForbiddenTermReviewService(db).review_and_rewrite_item(
            item=item,
            asset_key=(item.plan_json or {}).get("asset_key"),
            orchestrator=orchestrator,
            executor_code=self.executor_code,
            content_type="comment",
        )
        item.body = self._normalize_comment_length(item, item.body or "")
        ActivityQualityGuardService().review_item(item)
        item.error_message = None

    async def _mark_item_timeout(self, item_id: int) -> None:
        async with self.session_factory() as db:
            item = await self._require_item(db, item_id)
            if item.status == "generated":
                return
            item.status = "failed"
            item.error_message = f"comment generation soft timeout after {_comment_item_soft_timeout_seconds():.1f}s"
            quality = dict(item.quality_json or {})
            quality["hard_pass"] = False
            quality["timeout_guard"] = {
                "source": "comment_batch_soft_timeout",
                "timeout_seconds": _comment_item_soft_timeout_seconds(),
            }
            item.quality_json = quality
            await db.commit()

    async def _review_generated_batch_similarity(self, batch_id: int) -> None:
        async with self.session_factory() as db:
            items = await self._planned_items(batch_id, db=db)
            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            for item in items:
                if item.status != "generated" or not item.body:
                    continue
                before_body = item.body
                await self._review_and_rewrite_similarity(db=db, item=item, orchestrator=orchestrator)
                if item.body != before_body:
                    await CommentRealnessReviewService().review_and_rewrite_item(
                        item=item,
                        orchestrator=orchestrator,
                        executor_code=self.executor_code,
                    )
                    await ForbiddenTermReviewService(db).review_and_rewrite_item(
                        item=item,
                        asset_key=(item.plan_json or {}).get("asset_key"),
                        orchestrator=orchestrator,
                        executor_code=self.executor_code,
                        content_type="comment",
                    )
                    item.body = self._normalize_comment_length(item, item.body or "")
                    ActivityQualityGuardService().review_item(item)
                    self._preserve_delivery_duplicate_failure(item)
                await db.commit()

    async def _review_generated_batch_delivery_duplicates(self, batch_id: int) -> None:
        async with self.session_factory() as db:
            items = await self._planned_items(batch_id, db=db)
            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            for item in items:
                if item.status != "generated" or not item.body:
                    continue
                before_body = item.body
                await self._review_and_rewrite_delivery_duplicate(db=db, item=item, orchestrator=orchestrator)
                if item.body != before_body:
                    await CommentRealnessReviewService().review_and_rewrite_item(
                        item=item,
                        orchestrator=orchestrator,
                        executor_code=self.executor_code,
                    )
                    await ForbiddenTermReviewService(db).review_and_rewrite_item(
                        item=item,
                        asset_key=(item.plan_json or {}).get("asset_key"),
                        orchestrator=orchestrator,
                        executor_code=self.executor_code,
                        content_type="comment",
                    )
                    item.body = self._normalize_comment_length(item, item.body or "")
                    ActivityQualityGuardService().review_item(item)
                await db.commit()

    async def _review_and_rewrite_low_information(
        self,
        *,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator,
    ) -> None:
        if not item.body or not item.run_id or not self._looks_low_information_comment(item.body):
            return
        input_payload = self._low_information_rewrite_input(item)
        result = await orchestrator.run_content_rewrite_stage(
            run_id=item.run_id,
            executor_code=self.executor_code,
            input_payload=input_payload,
        )
        final = result.output or {}
        final_content = final.get("final") if isinstance(final.get("final"), dict) else {}
        comment = str(final.get("comment") or final_content.get("comment") or final.get("body") or final_content.get("body") or "").strip()
        if not comment:
            raise ValueError("content.rewrite returned empty low-information comment")
        item.body = self._normalize_comment_length(item, comment)
        low_information_rewrite = {
            "rewrite_required": True,
            "rewrite_reason": "评论信息量太低，已触发自动改写",
            "previous_body": input_payload["previous_content"]["comment"],
            "final_body": item.body,
            "passed": not self._looks_low_information_comment(item.body),
        }
        quality = dict(item.quality_json or {})
        quality["low_information_rewrite"] = low_information_rewrite
        quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + len(result.stage_calls)
        quality["run_status"] = result.run.status
        quality["hard_pass"] = bool(low_information_rewrite["passed"])
        item.quality_json = quality
        if self._looks_low_information_comment(item.body):
            raise ValueError("content.generate returned low-information comment")

    def _low_information_rewrite_input(self, item: ContentBatchItem) -> dict[str, Any]:
        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        expert = unified_generation.get("expert") if isinstance(unified_generation, dict) else {}
        model_config = (expert or {}).get("model_config") if isinstance(expert, dict) else {}
        return {
            "previous_content": {"comment": item.body or ""},
            "content_type": "comment",
            "output_fields": ["comment"],
            "business_rule": dict(item.plan_json or {}),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "forbidden_hits": [],
            "forbidden_replacements": {},
            "rewrite_instructions": [
                f"只输出一条{self._comment_max_chars(item)}字以内的评论正文",
                *LOW_INFORMATION_COMMENT_REWRITE_INSTRUCTIONS,
            ],
            "model_config": model_config or {"temperature": 0.72, "max_tokens": 512},
        }

    def _sanitize_brand_hallucinations(self, item: ContentBatchItem) -> None:
        plan = item.plan_json or {}
        if plan.get("asset_key") != YUANYUE_COMMENT_ASSET_KEY or not item.body:
            return
        text = item.body
        hits = _find_yuanyue_competitor_brand_hits(text)
        if not hits:
            return
        item.body = _remove_yuanyue_competitor_brand_hits(text, hits)
        quality = dict(item.quality_json or {})
        quality["brand_hallucination_guard"] = {
            "hits": hits,
            "replacement": YUANYUE_COMPETITOR_BRAND_REPLACEMENT,
            "blocked_terms": list(YUANYUE_COMPETITOR_BRAND_TERMS),
            "scope": YUANYUE_COMMENT_ASSET_KEY,
        }
        item.quality_json = quality

    async def _review_and_rewrite_similarity(
        self,
        *,
        db: AsyncSession,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator,
    ) -> None:
        if not item.body or not item.run_id:
            return
        while self._similarity_rewrite_rounds(item) < MAX_COMMENT_SIMILARITY_REWRITE_ROUNDS:
            # 改写后的短评论可能避开了原命中句，却撞上另一条历史句；每轮都重新扫描候选池。
            previous_items = await self._previous_generated_items(db, item)
            history_items = await self._history_items_for_similarity(db, item)
            match = self._most_similar_candidate(item, [*previous_items, *history_items])
            if not match or match["score"] < COMMENT_SIMILARITY_REWRITE_THRESHOLD:
                return
            try:
                await self._rewrite_item_for_similarity(item=item, similar_item=match, orchestrator=orchestrator)
            except Exception as exc:  # noqa: BLE001 - keep generated comment if rewrite worker is flaky
                quality = dict(item.quality_json or {})
                failures = list(quality.get("similarity_rewrite_failures") or [])
                failures.append({**self._similarity_rewrite_meta(item, match), "error_message": str(exc)})
                quality["similarity_rewrite_failures"] = failures
                item.quality_json = quality
                return
        previous_items = await self._previous_generated_items(db, item)
        history_items = await self._history_items_for_similarity(db, item)
        match = self._most_similar_candidate(item, [*previous_items, *history_items])
        if not match or match["score"] < COMMENT_SIMILARITY_REWRITE_THRESHOLD:
            return
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        reason = f"{self._similarity_rewrite_meta(item, match)['reason']}，已达到相似度改写轮次上限"
        review_report.update(
            {
                "rewrite_required": True,
                "rewrite_reason": reason,
                "post_rewrite_similarity_score": round(float(match.get("score") or 0), 4),
                "similarity_rewrite_passed": False,
            }
        )
        quality.update({"review_report": review_report, "hard_pass": False})
        item.quality_json = quality

    async def _review_and_rewrite_delivery_duplicate(
        self,
        *,
        db: AsyncSession,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator,
    ) -> None:
        if not item.body:
            return
        ledger_service = CommentDeliveryLedgerService(db)
        hit = await self._delivery_duplicate_hit(ledger_service, item)
        if hit is None:
            return
        quality = dict(item.quality_json or {})
        attempts = list(quality.get("delivery_duplicate_rewrites") or [])
        if item.run_id and len(attempts) < MAX_COMMENT_DELIVERY_DUPLICATE_REWRITE_ROUNDS:
            input_payload = self._delivery_duplicate_rewrite_input(item, hit)
            try:
                result = await orchestrator.run_content_rewrite_stage(
                    run_id=item.run_id,
                    executor_code=self.executor_code,
                    input_payload=input_payload,
                )
                final = result.output or {}
                final_content = final.get("final") if isinstance(final.get("final"), dict) else {}
                comment = str(final.get("comment") or final_content.get("comment") or final.get("body") or final_content.get("body") or "").strip()
                if comment:
                    previous_body = item.body
                    item.body = self._normalize_comment_length(item, comment)
                    post_hit = await self._delivery_duplicate_hit(ledger_service, item)
                    attempts.append(
                        {
                            "previous_body": previous_body,
                            "final_body": item.body,
                            "duplicate_before": hit,
                            "duplicate_after": post_hit,
                            "passed": post_hit is None,
                        }
                    )
                    quality = dict(item.quality_json or {})
                    quality["delivery_duplicate_rewrites"] = attempts
                    quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + len(result.stage_calls)
                    quality["run_status"] = result.run.status
                    item.quality_json = quality
                    if post_hit is None:
                        return
                    hit = post_hit
            except Exception as exc:  # noqa: BLE001 - mark duplicate instead of failing the whole batch
                attempts.append({"duplicate_before": hit, "error_message": str(exc), "passed": False})

        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        reason = f"评论与已交付台账完全重复，来源：{hit.get('source_type') or '-'} {hit.get('source_uri') or ''}".strip()
        review_report.update(
            {
                "rewrite_required": True,
                "rewrite_reason": reason,
                "delivery_duplicate_passed": False,
            }
        )
        quality.update(
            {
                "delivery_duplicate_guard": {
                    "duplicate": True,
                    "match": hit,
                    "rewrite_rounds": len(attempts),
                },
                "delivery_duplicate_rewrites": attempts,
                "review_report": review_report,
                "hard_pass": False,
            }
        )
        item.quality_json = quality

    async def _delivery_duplicate_hit(
        self,
        ledger_service: CommentDeliveryLedgerService,
        item: ContentBatchItem,
    ) -> dict[str, Any] | None:
        existing = await ledger_service.exists_many(
            asset_key=(item.plan_json or {}).get("asset_key"),
            comments=[item.body or ""],
        )
        normalized = ledger_service.normalize_comment(item.body or "")
        match = existing.get(normalized)
        return ledger_entry_to_dict(match) if match is not None else None

    def _delivery_duplicate_rewrite_input(self, item: ContentBatchItem, hit: dict[str, Any]) -> dict[str, Any]:
        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        return {
            "previous_content": {"comment": item.body or ""},
            "content_type": "comment",
            "output_fields": ["comment"],
            "business_rule": dict(item.plan_json or {}),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "forbidden_hits": [],
            "review_report": {
                "hard_results": [],
                "soft_scores": [],
                "failed_aes": [
                    {
                        "ae_code": "comment_delivery_duplicate",
                        "feedback": "评论与已交付台账完全重复，需要换一句真实评论口吻重新表达",
                        "evidence": [hit],
                    }
                ],
                "rewrite_required": True,
                "rewrite_reason": "评论与已交付台账完全重复",
                "delivery_duplicate": hit,
            },
            "rewrite_round": 1,
            "rewrite_instructions": [
                f"只输出一条{self._comment_max_chars(item)}字以内的评论正文",
                "避开已交付评论的完整句子，不要只改标点或前后空格",
                "保留当前业务规则和合规边界，不扩大功效表达",
            ],
        }

    @staticmethod
    def _preserve_delivery_duplicate_failure(item: ContentBatchItem) -> None:
        quality = dict(item.quality_json or {})
        guard = quality.get("delivery_duplicate_guard") if isinstance(quality.get("delivery_duplicate_guard"), dict) else {}
        if not guard.get("duplicate"):
            return
        review_report = dict(quality.get("review_report") or {})
        review_report["rewrite_required"] = True
        review_report["delivery_duplicate_passed"] = False
        quality["review_report"] = review_report
        quality["hard_pass"] = False
        item.quality_json = quality

    async def _previous_generated_items(self, db: AsyncSession, item: ContentBatchItem) -> list[ContentBatchItem]:
        result = await db.execute(
            select(ContentBatchItem)
            .where(
                ContentBatchItem.batch_id == item.batch_id,
                ContentBatchItem.status == "generated",
                ContentBatchItem.item_no < item.item_no,
                ContentBatchItem.body.is_not(None),
            )
            .order_by(ContentBatchItem.item_no)
        )
        return list(result.scalars().all())

    async def _history_items_for_similarity(self, db: AsyncSession, item: ContentBatchItem) -> list[ContentBatchItem]:
        result = await db.execute(select(ContentBatchJob).where(ContentBatchJob.id == item.batch_id))
        job = result.scalar_one_or_none()
        if job is None:
            return []
        history_result = await db.execute(
            select(ContentBatchItem, ContentBatchJob)
            .join(ContentBatchJob, ContentBatchJob.id == ContentBatchItem.batch_id)
            .where(
                ContentBatchItem.batch_id != item.batch_id,
                ContentBatchItem.status == "generated",
                ContentBatchItem.body.is_not(None),
                ContentBatchJob.asset_key == job.asset_key,
                ContentBatchJob.product_topic == job.product_topic,
            )
            .order_by(ContentBatchItem.create_time.desc(), ContentBatchItem.id.desc())
            .limit(COMMENT_HISTORY_SIMILARITY_LOOKBACK_LIMIT)
        )
        history_items: list[ContentBatchItem] = []
        for previous, history_job in history_result.all():
            setattr(previous, "_similarity_batch_code", history_job.batch_code)
            history_items.append(previous)
        return history_items

    def _most_similar_candidate(self, item: ContentBatchItem, candidates: list[ContentBatchItem]) -> dict[str, Any] | None:
        scored = [
            {
                "item_id": previous.id,
                "batch_id": previous.batch_id,
                "batch_code": self._batch_code_from_context(previous),
                "item_no": previous.item_no,
                "title": previous.title,
                "body": previous.body,
                "score": round(self._jaccard_2gram(item.body or "", previous.body or ""), 4),
                "scope": "current_batch" if previous.batch_id == item.batch_id else "history",
            }
            for previous in candidates
            if previous.body
        ]
        if not scored:
            return None
        return max(scored, key=lambda candidate: candidate["score"])

    async def _rewrite_item_for_similarity(
        self,
        *,
        item: ContentBatchItem,
        similar_item: dict[str, Any],
        orchestrator: ContentAgentOrchestrator,
    ) -> None:
        input_payload = self._similarity_rewrite_input(item, similar_item)
        result = await orchestrator.run_content_rewrite_stage(
            run_id=item.run_id,
            executor_code=self.executor_code,
            input_payload=input_payload,
        )
        final = result.output or {}
        final_content = final.get("final") if isinstance(final.get("final"), dict) else {}
        comment = str(final.get("comment") or final_content.get("comment") or final.get("body") or final_content.get("body") or "").strip()
        if not comment:
            raise ValueError("content.rewrite returned empty comment")
        item.body = self._normalize_comment_length(item, comment)
        post_score = round(self._jaccard_2gram(item.body or "", similar_item.get("body") or ""), 4)
        passed = post_score < COMMENT_SIMILARITY_REWRITE_THRESHOLD
        similarity_rewrite = {
            **self._similarity_rewrite_meta(item, similar_item),
            "pre_rewrite_similarity_score": round(float(similar_item.get("score") or 0), 4),
            "post_rewrite_similarity_score": post_score,
            "similarity_rewrite_passed": passed,
        }
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        previous_rewrites = list(quality.get("similarity_rewrites") or [])
        previous_rewrites.append(similarity_rewrite)
        rewrite_reason = (
            similarity_rewrite["reason"]
            if passed
            else f"{similarity_rewrite['reason']}，自动改写后仍为 {post_score:.2f}，需要人工处理"
        )
        review_report.update(
            {
                "rewrite_required": not passed,
                "rewrite_reason": rewrite_reason,
                "rewrite_rounds": max(int(review_report.get("rewrite_rounds") or 0), self._similarity_rewrite_rounds(item) + 1),
                "post_rewrite_similarity_score": post_score,
                "similarity_rewrite_passed": passed,
            }
        )
        quality.update(
            {
                "review_report": review_report,
                "similarity_rewrites": previous_rewrites,
                "stage_call_count": int(quality.get("stage_call_count") or 0) + len(result.stage_calls),
                "run_status": result.run.status,
                "hard_pass": passed,
            }
        )
        item.quality_json = quality

    def _similarity_rewrite_input(self, item: ContentBatchItem, similar_item: dict[str, Any]) -> dict[str, Any]:
        similarity_meta = self._similarity_rewrite_meta(item, similar_item)
        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        return {
            "previous_content": {"comment": item.body or ""},
            "content_type": "comment",
            "output_fields": ["comment"],
            "business_rule": dict(item.plan_json or {}),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "forbidden_hits": [],
            "review_report": {
                "hard_results": [],
                "soft_scores": [],
                "failed_aes": [
                    {
                        "ae_code": "batch_comment_similarity",
                        "feedback": similarity_meta["reason"],
                        "evidence": [
                            {
                                "similar_item_no": similar_item.get("item_no"),
                                "score": similar_item.get("score"),
                            }
                        ],
                    }
                ],
                "rewrite_required": True,
                "rewrite_reason": similarity_meta["reason"],
                "similarity": similarity_meta,
            },
            "rewrite_round": self._similarity_rewrite_rounds(item) + 1,
            "rewrite_instructions": [
                f"只输出一条{self._comment_max_chars(item)}字以内的评论正文",
                "避开相似评论的开头、核心短语和句式",
                "换一个生活细节或提问入口，不要只做同义词替换",
                "保留当前业务规则和合规边界，不扩大功效表达",
            ],
        }

    def _similarity_rewrite_meta(self, item: ContentBatchItem, similar_item: dict[str, Any]) -> dict[str, Any]:
        score = float(similar_item.get("score") or 0)
        reason = (
            f"评论与历史批次第{similar_item.get('item_no')}条 2-gram 相似度 {score:.2f}，已触发自动改写"
            if similar_item.get("scope") == "history"
            else f"评论与第{similar_item.get('item_no')}条 2-gram 相似度 {score:.2f}，已触发自动改写"
        )
        return {
            "item_no": item.item_no,
            "similar_item_no": similar_item.get("item_no"),
            "similar_batch_id": similar_item.get("batch_id"),
            "similar_batch_code": similar_item.get("batch_code"),
            "scope": similar_item.get("scope") or "current_batch",
            "similarity_score": round(score, 4),
            "threshold": COMMENT_SIMILARITY_REWRITE_THRESHOLD,
            "reason": reason,
        }

    def _similarity_rewrite_rounds(self, item: ContentBatchItem) -> int:
        return len((item.quality_json or {}).get("similarity_rewrites") or [])

    def _jaccard_2gram(self, left: str, right: str) -> float:
        left_tokens = self._text_2grams(left)
        right_tokens = self._text_2grams(right)
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    @staticmethod
    def _looks_low_information_comment(value: str) -> bool:
        clean = re.sub(r"[，。！？、,.!?\s]+", "", value or "")
        if clean in {"我们家", "我家", "俺家", "同款", "加一", "蹲蹲", "求问", "还行", "不错"}:
            return True
        return bool(re.fullmatch(r"(?:我们|我|俺)?家", clean))

    @staticmethod
    def _text_2grams(text: str) -> set[str]:
        clean = re.sub(r"[，。！？、,.!?\s]+", "", text or "")
        return {clean[index : index + 2] for index in range(max(len(clean) - 1, 0)) if clean[index : index + 2].strip()}

    @staticmethod
    def _batch_code_from_context(item: ContentBatchItem) -> str | None:
        transient_value = getattr(item, "_similarity_batch_code", None)
        if isinstance(transient_value, str) and transient_value:
            return transient_value
        batch_context = ((item.plan_json or {}).get("batch_context") or {})
        value = batch_context.get("batch_code")
        return str(value) if value else None

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

    @staticmethod
    def _comment_max_chars(item: ContentBatchItem) -> int:
        plan = item.plan_json or {}
        # 5-8字短接话是运营侧明确选择的微评论格式，最终落库前再做一次硬上限保护。
        if _uses_comment_micro_reply_format(plan):
            return 10
        if _uses_comment_thread_short_reply_format(plan):
            return 12
        if str(plan.get("quality_guard_profile_key") or "").strip() == A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY:
            return 50
        if str(plan.get("quality_guard_profile_key") or "").strip() == A2_NEGATIVE_POST_COMMENT_PROFILE_KEY:
            return 45
        if str(plan.get("quality_guard_profile_key") or "").strip() == A2_SENTIMENT_COMMENT_PROFILE_KEY:
            return 80
        if str(plan.get("quality_guard_profile_key") or "").strip() == A2_SENTIMENT_POST_PROFILE_KEY:
            return 100
        return 35

    def _normalize_comment_length(self, item: ContentBatchItem, comment: str) -> str:
        normalized = comment.strip()
        if self._preserve_overlong_comment_for_guard(item):
            return normalized
        return self._fit_comment_length(normalized, max_chars=self._comment_max_chars(item))

    @staticmethod
    def _preserve_overlong_comment_for_guard(item: ContentBatchItem) -> bool:
        plan = item.plan_json or {}
        return str(plan.get("quality_guard_profile_key") or "").strip() in {
            A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY,
            A2_SENTIMENT_POST_PROFILE_KEY,
        }

    def _fit_comment_length(self, comment: str, *, max_chars: int = 35) -> str:
        comment = comment.strip()
        if len(comment) <= max_chars:
            return comment

        # Keep the first natural clause(s) so long generations still read like a real short comment.
        parts = [part.strip() for part in re.split(r"[，。！？,!?；;、]", comment) if part.strip()]
        candidate = ""
        for part in parts:
            next_candidate = f"{candidate}，{part}" if candidate else part
            if len(next_candidate) <= max_chars:
                candidate = next_candidate
                continue
            if candidate:
                if self._looks_incomplete_clause(candidate) and part:
                    return self._truncate_comment_preserving_context(next_candidate, max_chars=max_chars)
                break
            return self._truncate_comment_preserving_context(part, max_chars=max_chars)
        return candidate or self._truncate_comment_preserving_context(comment, max_chars=max_chars)

    @staticmethod
    def _looks_incomplete_clause(value: str) -> bool:
        text = value.strip(" ，。！？,!?；;、 ")
        if not text:
            return False
        dangling_suffixes = ("开始", "之后", "以后", "那会儿", "的时候", "这几天", "刚转", "刚换", "就", "还", "也")
        return text.endswith(dangling_suffixes) or bool(re.search(r"第[一二三四五六七八九十\d]+天$", text))

    @staticmethod
    def _truncate_comment_preserving_context(value: str, *, max_chars: int) -> str:
        text = value.strip()[:max_chars].rstrip("，。！？,!?；;、 ")
        dangling_suffixes = ("然后", "不过", "但是", "开始", "之后", "以后", "就", "还", "也")
        changed = True
        while changed:
            changed = False
            for suffix in dangling_suffixes:
                if text.endswith(suffix) and len(text) > len(suffix):
                    text = text[: -len(suffix)].rstrip("，。！？,!?；;、 ")
                    changed = True
                    break
        return text


def _resolve_keyword_asset_key(explicit_key: str | None, asset: AssetRegistry | None) -> str:
    normalized = _normalize_keyword_asset_key(explicit_key)
    if normalized:
        return normalized
    for source in _asset_json_sources(asset):
        normalized = _normalize_keyword_asset_key(source.get("keyword_asset_key"))
        if normalized:
            return normalized
    return DEFAULT_SYSTEM_KEYWORD_ASSET_KEY


def _keyword_selection_from_asset(asset: AssetRegistry | None) -> dict[str, Any] | None:
    for source in _asset_json_sources(asset):
        value = source.get("keyword_selection")
        if isinstance(value, dict):
            return value
    return None


def _keyword_selection_with_rule_overrides(
    keyword_selection: dict[str, Any] | None,
    rule: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    normalized = _copy_keyword_selection(keyword_selection)
    route_family = _a2_comment_route_family(rule)
    route_override = _a2_route_keyword_selection(route_family)
    route_meta: dict[str, Any] = {}
    if route_override:
        if normalized is None:
            normalized = {}
        normalized.update(route_override)
        route_meta = {
            "keyword_selection_override": {
                "reason": f"a2_{route_family}_route_only",
                **route_override,
            }
        }
    return normalized, route_meta


def _a2_comment_route_family(rule: dict[str, Any]) -> str | None:
    if not _is_a2_comment_rule(rule):
        return None
    guard_keyword = str(rule.get("scenario_guard_keyword") or "").strip()
    major = _business_rule_name(rule).split("-", 1)[0].strip()
    if guard_keyword == "会员权益" or major == "会员权益":
        return "member_benefit"
    if "转奶" in guard_keyword or major in {"转奶", "舆情缓和"}:
        return "transfer"
    if "批批检" in guard_keyword or major in {"批批检", "工艺", "舆情讨论"}:
        return "batch_check"
    if guard_keyword == "有货" or major == "有货":
        return "stock"
    return None


def _is_a2_comment_rule(rule: dict[str, Any]) -> bool:
    asset_key = str(rule.get("asset_key") or "").strip()
    profile_key = str(rule.get("quality_guard_profile_key") or "").strip()
    if asset_key == "a2_sentiment_comment_activity" or profile_key.startswith("a2_"):
        return True
    text = " ".join(str(rule.get(key) or "") for key in ("business_rule", "corpus"))
    return "a2" in text.lower() or "至初" in text


def _a2_route_keyword_selection(route_family: str | None) -> dict[str, list[str]]:
    if route_family not in {"member_benefit", "stock", "batch_check", "transfer"}:
        return {}
    return {"comment_writing_instruction": ["natural_comment"]}


def _comment_tone_options_from_asset(
    asset: AssetRegistry | None,
    rule: dict[str, Any],
) -> list[dict[str, str]]:
    route_family = _a2_comment_tone_family(rule)
    if not route_family:
        return []
    for source in _asset_json_sources(asset):
        configured = source.get("comment_tone_options") or source.get("comment_persona_options")
        if not isinstance(configured, dict):
            continue
        raw_options = configured.get(route_family) or configured.get("default")
        if not isinstance(raw_options, list):
            continue
        options: list[dict[str, str]] = []
        for index, raw_option in enumerate(raw_options, start=1):
            if isinstance(raw_option, str):
                prompt = raw_option.strip()
                if prompt:
                    options.append(
                        {
                            "tone_code": f"{route_family}_{index}",
                            "tone_label": prompt.split("：", 1)[0].strip() or f"语气{index}",
                            "prompt": prompt,
                        }
                    )
                continue
            if not isinstance(raw_option, dict):
                continue
            prompt = str(raw_option.get("prompt") or raw_option.get("text") or "").strip()
            if not prompt:
                continue
            options.append(
                {
                    "tone_code": str(
                        raw_option.get("tone_code")
                        or raw_option.get("persona_code")
                        or raw_option.get("code")
                        or f"{route_family}_{index}"
                    ).strip(),
                    "tone_label": str(
                        raw_option.get("tone_label")
                        or raw_option.get("persona_label")
                        or raw_option.get("label")
                        or f"语气{index}"
                    ).strip(),
                    "prompt": prompt,
                }
            )
        if options:
            return options
    return []


def _a2_comment_tone_family(rule: dict[str, Any]) -> str | None:
    if not _is_a2_comment_rule(rule):
        return None
    major = _business_rule_name(rule).split("-", 1)[0].strip()
    if major == "会员权益":
        return "member_benefit"
    if major == "有货":
        return "stock"
    if major in {"批批检", "工艺", "舆情讨论"}:
        return "batch_check"
    if major in {"转奶", "舆情缓和"}:
        return "transfer"
    guard_keyword = str(rule.get("scenario_guard_keyword") or "").strip()
    if guard_keyword == "会员权益":
        return "member_benefit"
    if "批批检" in guard_keyword:
        return "batch_check"
    if "转奶" in guard_keyword:
        return "transfer"
    if guard_keyword == "有货":
        return "stock"
    return None


def _copy_keyword_selection(keyword_selection: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(keyword_selection, dict):
        return None
    copied: dict[str, Any] = {}
    for key, value in keyword_selection.items():
        if isinstance(value, list):
            copied[key] = list(value)
        elif isinstance(value, dict):
            copied[key] = dict(value)
        else:
            copied[key] = value
    return copied


def _generation_requirements_from_asset(asset: AssetRegistry | None) -> str | None:
    for source in _asset_json_sources(asset):
        value = source.get("generation_requirements")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _comment_scenario_from_asset(
    asset: AssetRegistry,
    scenario_code: str | None,
) -> dict[str, Any] | None:
    code = str(scenario_code or "").strip()
    if not code:
        return None
    scenarios = (asset.content_json or {}).get("comment_scenarios")
    for scenario in scenarios or []:
        if not isinstance(scenario, dict):
            continue
        if str(scenario.get("scenario_code") or "").strip() == code:
            return scenario
    available = [
        str(scenario.get("scenario_code") or "").strip()
        for scenario in scenarios or []
        if isinstance(scenario, dict) and str(scenario.get("scenario_code") or "").strip()
    ]
    suffix = f"; available={','.join(available)}" if available else ""
    raise ValueError(f"comment scenario not found: {code}{suffix}")


def _comment_scenario_policy(scenario: dict[str, Any] | None) -> dict[str, Any] | None:
    if not scenario:
        return None
    return {
        "sentiment_mix": scenario.get("sentiment_mix") or {},
        "interaction_reply_ratio": scenario.get("interaction_reply_ratio") or 0,
        "style_hint": str(scenario.get("style_hint") or "").strip() or None,
    }


def _weighted_comment_scenario_allocations(
    directions: list[dict[str, Any]],
    limit: int,
) -> list[int]:
    weights = [max(0.0, float(direction.get("weight") or 0)) for direction in directions]
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * len(directions)
        total = float(len(directions))
    raw = [limit * weight / total for weight in weights]
    allocations = [int(value) for value in raw]
    remaining = limit - sum(allocations)
    order = sorted(range(len(raw)), key=lambda index: (raw[index] - allocations[index], -index), reverse=True)
    for index in order[:remaining]:
        allocations[index] += 1
    return allocations


def _comment_scenario_output_batch_size(direction: dict[str, Any]) -> int:
    raw_value = direction.get("output_batch_size")
    if raw_value in (None, ""):
        return 1
    return _comment_positive_int(raw_value, default=1, maximum=20)


def _rule_with_comment_scenario(
    rule: dict[str, Any],
    scenario: dict[str, Any],
    direction: dict[str, Any],
) -> dict[str, Any]:
    next_rule = dict(rule)
    scenario_name = str(scenario.get("scenario_name") or "").strip()
    direction_name = str(direction.get("direction_name") or "").strip()
    style_hint = str(scenario.get("style_hint") or "").strip()
    next_rule.update(
        {
            "scenario_code": str(scenario.get("scenario_code") or "").strip(),
            "scenario_name": scenario_name,
            "scenario_direction": str(direction.get("direction_code") or "").strip(),
            "scenario_direction_name": direction_name,
            "scenario_sentiment": str(direction.get("sentiment") or "positive").strip(),
            "scenario_interaction_reply": bool(direction.get("interaction_reply")),
            "scenario_guard_keyword": str(direction.get("guard_keyword") or "").strip() or None,
            "scenario_examples": [
                str(item).strip() for item in direction.get("examples") or [] if str(item).strip()
            ],
            "scenario_post_context": str(
                direction.get("post_context")
                or scenario.get("post_context")
                or rule.get("scenario_post_context")
                or ""
            ).strip()
            or None,
            "scenario_generation_requirements": str(
                direction.get("generation_requirements")
                or direction.get("prompt_hint")
                or style_hint
            ).strip()
            or None,
        }
    )
    if isinstance(direction.get("model_config"), dict):
        next_rule["model_config"] = dict(direction["model_config"])
    return next_rule


def _merge_comment_generation_requirements(*values: Any) -> str | None:
    parts: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts) or None


def _batch_variation_review_from_asset(asset: AssetRegistry | None) -> dict[str, Any] | None:
    for source in _asset_json_sources(asset):
        value = source.get("batch_variation_review")
        if isinstance(value, dict):
            return value
    return None


def _delivery_selection_from_asset(asset: AssetRegistry | None) -> dict[str, Any] | None:
    for source in _asset_json_sources(asset):
        value = source.get("delivery_selection")
        if isinstance(value, dict):
            return value
    return None


def _comment_generation_output_config(rule: dict[str, Any], asset: AssetRegistry | None) -> dict[str, Any] | None:
    sources = [rule, *_asset_json_sources(asset)]
    raw_mode: Any = None
    raw_count: Any = None
    for source in sources:
        output_format = source.get("output_format") if isinstance(source.get("output_format"), dict) else {}
        raw_mode = raw_mode or source.get("output_format_mode") or output_format.get("mode")
        raw_count = raw_count or source.get("expansion_count") or output_format.get("count") or output_format.get("expansion_count")
    mode = str(raw_mode or "plain_comment").strip()
    if mode not in {"json_string_array", "json_object_array"}:
        return None
    return {
        "mode": mode,
        "count": _comment_positive_int(raw_count, default=1, maximum=100),
    }


def _comment_plan_output_count(plan: dict[str, Any]) -> int:
    mode = str(plan.get("output_format_mode") or ((plan.get("output_format") or {}).get("mode") if isinstance(plan.get("output_format"), dict) else "")).strip()
    if mode not in {"json_string_array", "json_object_array"}:
        return 1
    return _comment_positive_int(
        plan.get("expansion_count")
        or ((plan.get("output_format") or {}).get("count") if isinstance(plan.get("output_format"), dict) else None),
        default=1,
        maximum=100,
    )


def _comment_generation_max_tokens(plan: dict[str, Any]) -> int:
    count = _comment_plan_output_count(plan)
    if count <= 1:
        return COMMENT_GENERATION_MAX_TOKENS
    return max(COMMENT_GENERATION_MAX_TOKENS, min(4096, count * 128))


def _comment_positive_int(value: Any, *, default: int = 1, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _asset_json_sources(asset: AssetRegistry | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if asset is None:
        return {}, {}
    content = getattr(asset, "content_json", None)
    metadata = getattr(asset, "metadata_json", None)
    return (
        content if isinstance(content, dict) else {},
        metadata if isinstance(metadata, dict) else {},
    )


def _normalize_keyword_asset_key(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_business_rule(value: Any) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return normalized or None


def _normalized_rule_ids(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        rule_id = str(value or "").strip()
        if rule_id and rule_id not in normalized:
            normalized.append(rule_id)
    return normalized


def _uses_comment_prompt_bundle_rule(rule: dict[str, Any]) -> bool:
    return (
        str(rule.get("prompt_mode") or "").strip() == "comment_prompt_bundle"
        and isinstance(rule.get("comment_prompt_bundle"), dict)
    )


def _bundle_prompt_slots_source(rule: dict[str, Any]) -> str | None:
    if not _uses_comment_prompt_bundle_rule(rule) or not isinstance(rule.get("prompt_slots"), dict):
        return None
    source = str(rule.get("bundle_prompt_slots_source") or "").strip()
    return source if source in {"batch_override", "rule_asset"} else None


def _normalize_comment_prompt_slots_override(
    value: dict[str, list[str]] | None,
) -> dict[str, list[str]] | None:
    if not value:
        return None
    normalized: dict[str, list[str]] = {}
    for raw_name, raw_entries in value.items():
        name = str(raw_name or "").strip()
        entries = [str(entry or "").strip() for entry in raw_entries or [] if str(entry or "").strip()]
        if name and entries:
            normalized[name] = entries
    if not normalized:
        raise ValueError("comment_prompt_slots must contain at least one non-empty slot")
    return normalized


def _normalize_comment_batch_variation_review_override(
    value: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not value:
        return None
    normalized = copy.deepcopy(value)
    normalized["enabled"] = normalized.get("enabled") is not False
    return normalized


def _normalize_comment_delivery_selection_override(
    value: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not value:
        return None
    normalized = copy.deepcopy(value)
    normalized["enabled"] = normalized.get("enabled") is not False
    if not normalized["enabled"]:
        return normalized
    try:
        target_count = int(normalized.get("target_count"))
    except (TypeError, ValueError) as exc:
        raise ValueError("comment_delivery_selection.target_count must be an integer") from exc
    if target_count < 1 or target_count > COMMENT_BATCH_MAX_COUNT:
        raise ValueError(
            f"comment_delivery_selection.target_count must be between 1 and {COMMENT_BATCH_MAX_COUNT}"
        )
    normalized["target_count"] = target_count
    if normalized.get("max_similarity") is not None:
        try:
            max_similarity = float(normalized["max_similarity"])
        except (TypeError, ValueError) as exc:
            raise ValueError("comment_delivery_selection.max_similarity must be a number") from exc
        if max_similarity < 0 or max_similarity > 1:
            raise ValueError("comment_delivery_selection.max_similarity must be between 0 and 1")
        normalized["max_similarity"] = max_similarity
    return normalized


def _normalize_comment_post_context_override(value: str | None) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return normalized or None


def _business_rule_name(rule: dict[str, Any]) -> str | None:
    value = rule.get("business_rule")
    if value is None:
        value = rule.get("comment_" + "angle")
    return _normalize_business_rule(value)


def _filter_member_rule_prompt_examples(rule: dict[str, Any], examples: list[str]) -> list[str]:
    business_rule = str(_business_rule_name(rule) or "")
    major, _, detail = business_rule.partition("-")
    if major.strip() != "会员权益" or not detail.strip():
        return examples

    detail_markers = {
        "集罐换礼": ("集罐", "空罐", "攒罐"),
        "积分换礼": ("积分",),
        "老客礼": ("老客", "老用户"),
        "抽奖活动": ("抽奖",),
        "活动礼品": ("礼品", "礼盒", "奖品"),
        "权益升级": ("权益升级", "升级", "加码"),
    }
    required_markers = detail_markers.get(detail)
    if not required_markers:
        return [example for example in examples if not _member_example_has_unconfirmed_claim(example)]

    other_markers = {
        "集罐换礼": ("积分", "抽奖", "老客", "检测", "报告"),
        "积分换礼": ("集罐", "空罐", "抽奖", "老客", "检测", "报告"),
        "老客礼": ("集罐", "空罐", "积分", "抽奖", "检测", "报告", "礼盒"),
        "抽奖活动": ("集罐", "空罐", "积分", "老客", "检测", "报告"),
        "活动礼品": ("集罐", "空罐", "积分", "抽奖", "老客", "检测", "报告"),
        "权益升级": ("集罐", "空罐", "积分", "抽奖", "老客", "检测", "报告"),
    }.get(detail, ())
    filtered = [
        example
        for example in examples
        if any(marker in example for marker in required_markers)
        and not any(marker in example for marker in other_markers)
        and not _member_example_has_unconfirmed_claim(example)
    ]
    return filtered or [example for example in examples if not _member_example_has_unconfirmed_claim(example)]


def _rule_with_rotated_prompt_slots(
    rule: dict[str, Any],
    *,
    rule_occurrence_no: int,
) -> dict[str, Any]:
    if str(rule.get("prompt_slot_selection_mode") or "").strip() != "round_robin":
        return rule
    raw_slots = rule.get("prompt_slots")
    if not isinstance(raw_slots, dict):
        return rule
    selected_slots: dict[str, list[str]] = {}
    selected_meta: dict[str, dict[str, Any]] = {}
    for raw_name, raw_entries in raw_slots.items():
        slot_name = str(raw_name or "").strip()
        entries = [str(item).strip() for item in raw_entries or [] if str(item).strip()]
        if not slot_name or not entries:
            continue
        selected_index = rule_occurrence_no % len(entries)
        selected_slots[slot_name] = [entries[selected_index]]
        selected_meta[slot_name] = {
            "selected_index": selected_index,
            "candidate_count": len(entries),
            "text": entries[selected_index],
        }
    if not selected_slots:
        return rule
    next_rule = dict(rule)
    next_rule["prompt_slots"] = selected_slots
    next_rule["preselected_prompt_slots"] = selected_meta
    return next_rule


def _rule_with_rotated_variation_slots(
    rule: dict[str, Any],
    *,
    rule_occurrence_no: int,
) -> dict[str, Any]:
    raw_slots = rule.get("variation_slots")
    if not isinstance(raw_slots, list):
        return rule
    selected_slots: list[dict[str, Any]] = []
    selected_meta: dict[str, dict[str, Any]] = {}
    for slot_offset, raw_slot in enumerate(raw_slots):
        if not isinstance(raw_slot, dict):
            continue
        slot_name = str(raw_slot.get("slot_name") or raw_slot.get("name") or "").strip()
        slot_code = str(raw_slot.get("slot_code") or raw_slot.get("code") or slot_name).strip()
        options = [str(item).strip() for item in raw_slot.get("options") or [] if str(item).strip()]
        if not slot_name or not options:
            continue
        cycle_shift = rule_occurrence_no // len(options)
        cycle_stride = slot_offset + 2
        selected_index = (
            rule_occurrence_no + slot_offset + cycle_shift * cycle_stride
        ) % len(options)
        selected_text = options[selected_index]
        selected_slots.append(
            {
                "slot_code": slot_code,
                "slot_name": slot_name,
                "options": [selected_text],
            }
        )
        selected_meta[slot_code] = {
            "slot_name": slot_name,
            "selected_index": selected_index,
            "candidate_count": len(options),
            "text": selected_text,
        }
    if not selected_slots:
        return rule
    next_rule = dict(rule)
    next_rule["variation_slots"] = selected_slots
    next_rule["preselected_variation_slots"] = selected_meta
    return next_rule


def _selected_gift_prompt_slot_value(rule: dict[str, Any]) -> str | None:
    raw_slots = rule.get("prompt_slots")
    if not isinstance(raw_slots, dict):
        return None
    for raw_name, raw_entries in raw_slots.items():
        slot_name = str(raw_name or "").strip()
        if (
            "礼品" not in slot_name
            and "奖品" not in slot_name
            and slot_name not in {"集罐可换", "本条活动事实"}
        ):
            continue
        entries = [str(item).strip() for item in raw_entries or [] if str(item).strip()]
        if len(entries) != 1:
            continue
        return entries[0].rsplit("：", 1)[-1].strip() or None
    return None


def _filter_selected_gift_prompt_examples(
    examples: list[str],
    *,
    selected_gift: str,
) -> list[str]:
    aliases = {
        "a2&小马宝莉黄金手串": ("小马宝莉黄金手串", "黄金手串"),
        "a2营养全家礼": ("a2营养全家礼", "营养全家礼"),
        "宝宝夏凉被": ("宝宝夏凉被", "夏凉被"),
    }.get(selected_gift, (selected_gift,))
    gift_markers = (
        "扭扭车",
        "自行车",
        "婴儿推车",
        "新西兰溯源",
        "黄金手串",
        "夏凉被",
        "营养全家礼",
        "积分",
    )
    matched = [example for example in examples if any(alias in example for alias in aliases)]
    if matched:
        return matched
    return [example for example in examples if not any(marker in example for marker in gift_markers)]


def _member_example_has_unconfirmed_claim(example: str) -> bool:
    return any(marker in example for marker in ("符合条件", "领取", "领礼盒", "积分翻倍", "正装", "门槛"))


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
    return SystemRandom().sample(range(pool_size), sample_count)


def _normalize_draft_rule_override(
    *,
    draft_corpus: str | None,
    draft_rule_id: str | None,
    draft_source_row_no: int | None,
    draft_comment_prompt_bundle: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    corpus = str(draft_corpus or "").strip()
    comment_prompt_bundle = normalize_comment_prompt_bundle(draft_comment_prompt_bundle)
    if not corpus and not comment_prompt_bundle:
        return None
    if comment_prompt_bundle:
        corpus = comment_prompt_bundle["content_direction"]
    rule_id = str(draft_rule_id or "").strip() or None
    source_row_no = _int_or_none(draft_source_row_no)
    if not rule_id and source_row_no is None:
        raise ValueError("draft_corpus requires draft_rule_id, draft_source_row_no, rule_id, or source_row_no")
    return {
        "corpus": corpus,
        "rule_id": rule_id,
        "source_row_no": source_row_no,
        "comment_prompt_bundle": comment_prompt_bundle,
    }


def _rule_matches_draft_override(rule: dict[str, Any], draft_override: dict[str, Any]) -> bool:
    rule_id = draft_override.get("rule_id")
    source_row_no = draft_override.get("source_row_no")
    return (not rule_id or str(rule.get("rule_id") or "").strip() == rule_id) and (
        source_row_no is None or _int_or_none(rule.get("source_row_no")) == source_row_no
    )


def _draft_override_summary(draft_override: dict[str, Any] | None) -> dict[str, Any] | None:
    if not draft_override:
        return None
    return {
        "enabled": True,
        "rule_id": draft_override.get("rule_id"),
        "source_row_no": draft_override.get("source_row_no"),
        "example_count": len(_extract_examples_from_corpus(str(draft_override.get("corpus") or ""))),
    }


def _extract_examples_from_corpus(corpus: str) -> list[str]:
    examples: list[str] = []
    in_examples = False
    for raw_line in corpus.splitlines():
        line = raw_line.strip()
        if line == "示例：":
            in_examples = True
            continue
        if in_examples and line.startswith("注意："):
            break
        if in_examples and line.startswith("- "):
            example = line[2:].strip()
            if example:
                examples.append(example)
    return examples


def _comment_batch_product_topic(asset: AssetRegistry) -> str:
    for source in (asset.content_json, asset.metadata_json):
        if not isinstance(source, dict):
            continue
        for key in ("activity_name", "product_topic", "topic"):
            value = str(source.get(key) or "").strip()
            if value == DEFAULT_COMMENT_BATCH_TOPIC and asset.asset_key != DEFAULT_COMMENT_BUSINESS_RULE_ASSET_KEY:
                continue
            if value:
                return value
    display_name = str(asset.display_name or "").strip()
    if display_name:
        normalized = re.sub(r"(?:评论)?业务规则(?:规则)?$", "评论", display_name).strip()
        return normalized or display_name
    return DEFAULT_COMMENT_BATCH_TOPIC


def _quality_without_replayable_comment_reviews(quality_json: dict[str, Any]) -> dict[str, Any]:
    quality = copy.deepcopy(quality_json or {})
    quality.pop("activity_quality_guard", None)
    quality.pop("batch_variation_review", None)
    review_report = dict(quality.get("review_report") or {})
    hard_results = [
        dict(result)
        for result in review_report.get("hard_results") or []
        if isinstance(result, dict)
        and not str(result.get("ae_code") or "").startswith("activity_quality_guard")
        and not str(result.get("ae_code") or "").startswith("batch_variation.")
    ]
    review_report["hard_results"] = hard_results
    if review_report.get("rewrite_reason") in {
        "活动专项质量守卫未通过",
        "批次表达同质化审核未通过",
    }:
        review_report.pop("rewrite_reason", None)
        review_report["rewrite_required"] = any(result.get("pass") is False for result in hard_results)
    quality["review_report"] = review_report
    quality["hard_pass"] = not any(result.get("pass") is False for result in hard_results)
    return quality


def _is_comment_review_item(item: ContentBatchItem) -> bool:
    plan = item.plan_json if isinstance(item.plan_json, dict) else {}
    return "comment" in {str(field or "").strip() for field in plan.get("output_fields") or []}


def _comment_item_soft_timeout_seconds() -> float:
    raw = os.getenv("MAGA_COMMENT_ITEM_SOFT_TIMEOUT_SECONDS", "35")
    try:
        value = float(raw)
    except ValueError:
        return 35.0
    return max(3.0, value)


def _uses_comment_micro_reply_format(plan: dict[str, Any]) -> bool:
    return _uses_comment_format_control(plan, "comment_micro_reply")


def _uses_comment_thread_short_reply_format(plan: dict[str, Any]) -> bool:
    return _uses_comment_format_control(plan, COMMENT_THREAD_SHORT_REPLY_FORMAT_CODE)


def _uses_comment_format_control(plan: dict[str, Any], keyword_code: str) -> bool:
    keyword_selection = plan.get("keyword_selection") if isinstance(plan, dict) else None
    if isinstance(keyword_selection, dict):
        selected = keyword_selection.get("comment_format_control") or []
        if any(str(code).strip() == keyword_code for code in selected):
            return True

    selected_keywords = plan.get("selected_keywords") if isinstance(plan, dict) else None
    if not isinstance(selected_keywords, list):
        selected_keywords = ((plan.get("unified_generation") or {}).get("selected_keywords") or []) if isinstance(plan, dict) else []
    return any(
        isinstance(item, dict)
        and item.get("category_code") == "comment_format_control"
        and item.get("keyword_code") == keyword_code
        for item in selected_keywords
    )


def _rule_profile_keyword(rule: dict[str, Any], profile: QualityGuardProfile) -> str:
    source = "\n".join(
        str(value or "")
        for value in (
            _business_rule_name(rule),
            rule.get("corpus"),
            " ".join(str(example) for example in rule.get("examples") or []),
        )
    )
    return derive_profile_keyword_from_text(source, profile) or "__default__"


def _find_yuanyue_competitor_brand_hits(text: str) -> list[str]:
    hits: list[str] = []
    for term in YUANYUE_COMPETITOR_BRAND_TERMS:
        if not term:
            continue
        if term.lower() == "a2":
            if term != "a2":
                continue
            # a2 常见大小写混写，源悦评论里只要出现都按其他品牌名处理。
            for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
                value = match.group(0)
                if value not in hits:
                    hits.append(value)
            continue
        if term in text and term not in hits:
            hits.append(term)
    return sorted(hits, key=len, reverse=True)


def _remove_yuanyue_competitor_brand_hits(text: str, hits: list[str]) -> str:
    sanitized = text
    for hit in hits:
        sanitized = sanitized.replace(hit, YUANYUE_COMPETITOR_BRAND_REPLACEMENT)
    # 兜底替换可能把“a2和爱他美”变成重复品牌，压成一个源悦，避免留下机械感。
    for duplicate in ("源悦和源悦", "源悦、源悦", "源悦，源悦", "源悦/源悦"):
        while duplicate in sanitized:
            sanitized = sanitized.replace(duplicate, YUANYUE_COMPETITOR_BRAND_REPLACEMENT)
    return sanitized.strip()
