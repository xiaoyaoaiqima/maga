"""Plan and execute comment batches from uploaded comment-angle rules."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
import re
from random import SystemRandom
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

COMMENT_SIMILARITY_REWRITE_THRESHOLD = 0.30
MAX_COMMENT_SIMILARITY_REWRITE_ROUNDS = 2
COMMENT_HISTORY_SIMILARITY_LOOKBACK_LIMIT = 80


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
        selected_rules = self._select_rules(rules, limit)
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
                "selection_mode": "balanced_random" if len(rules) > limit else "all",
                "selected_source_row_nos": [rule.get("source_row_no") for rule in selected_rules],
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

    def _select_rules(self, rules: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if len(rules) <= limit:
            return list(rules)

        rng = SystemRandom()
        # Keep each batch spread across comment angles instead of repeatedly taking the first rows.
        groups: dict[str, list[dict[str, Any]]] = {}
        for rule in rules:
            key = str(rule.get("comment_angle") or "").strip() or str(rule.get("source_row_no") or "")
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
                comment = self._fit_comment_length(comment)
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
                await self._review_and_rewrite_similarity(
                    db=db,
                    item=item,
                    orchestrator=orchestrator,
                )
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
        item.body = self._fit_comment_length(comment)
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
                "只输出一条20字以内的评论正文",
                "避开相似评论的开头、核心短语和句式",
                "换一个生活细节或提问入口，不要只做同义词替换",
                "保留当前评论切角和合规边界，不扩大功效表达",
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

    def _fit_comment_length(self, comment: str, *, max_chars: int = 20) -> str:
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
                break
            return part[:max_chars].rstrip("，。！？,!?；;、 ")
        return candidate or comment[:max_chars].rstrip("，。！？,!?；;、 ")
