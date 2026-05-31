"""Execute planned MAGA content batch items through the content-agent chain."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.schemas.content_agent import ContentAgentTaskCreate
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.executor_invocation_service import ExecutorInvocationClient
from app.services.forbidden_term_review_service import ForbiddenTermReviewService
from app.services.unified_content_generation_service import (
    CONTENT_GENERATE_CAPABILITY,
    UnifiedContentGenerationService,
)

SIMILARITY_REWRITE_THRESHOLD = 0.42
HISTORY_SIMILARITY_REWRITE_THRESHOLD = 0.48
MAX_SIMILARITY_REWRITE_ROUNDS = 2
HISTORY_SIMILARITY_LOOKBACK_LIMIT = 50


def _default_unified_review_report() -> dict[str, Any]:
    return {
        "source": "maga_unified_content_generate",
        "hard_results": [],
        "soft_scores": [],
        "failed_aes": [],
        "rewrite_required": False,
    }


@dataclass(frozen=True)
class BatchExecutionResult:
    batch_id: int
    requested_limit: int
    generated_count: int
    failed_count: int
    item_ids: list[int]


@dataclass(frozen=True)
class _ItemExecutionResult:
    item_id: int
    generated: bool
    failed: bool


class ContentBatchExecutionService:
    """Small-batch executor for planned ContentBatchItem rows.

    MVP deliberately runs a limited number of items synchronously. The service
    creates normal ContentAgentTask/Run/StageCall rows for each item so later UI,
    audit, artifact, and executor protocol behavior stays consistent with single
    generation.
    """

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

    async def execute_batch_items(
        self,
        batch_id: int,
        *,
        limit: int,
        concurrency: int = 5,
        created_by: str | None = None,
    ) -> BatchExecutionResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        job = await self._require_job(batch_id)
        items = await self._planned_items(batch_id, limit)
        item_ids = [item.id for item in items]
        job_context = {"id": job.id, "batch_code": job.batch_code, "count": job.count}
        semaphore = asyncio.Semaphore(concurrency)

        async def run_item(item_id: int) -> _ItemExecutionResult:
            # Each item owns a DB session because AsyncSession is not safe for
            # concurrent flush/commit while five executor calls are in flight.
            async with semaphore:
                return await self._execute_one_item(item_id, job_context, created_by=created_by)

        results = await asyncio.gather(*(run_item(item_id) for item_id in item_ids))
        await self._rewrite_similar_generated_items(batch_id, job)
        generated = sum(1 for result in results if result.generated)
        failed = sum(1 for result in results if result.failed)

        if generated:
            job.status = "partially_generated" if generated < job.count else "generated"
        elif failed:
            job.status = "failed"
        await self.db.flush()
        return BatchExecutionResult(
            batch_id=batch_id,
            requested_limit=limit,
            generated_count=generated,
            failed_count=failed,
            item_ids=item_ids,
        )

    async def _require_job(self, batch_id: int) -> ContentBatchJob:
        result = await self.db.execute(select(ContentBatchJob).where(ContentBatchJob.id == batch_id))
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError("batch job not found")
        return job

    async def _planned_items(self, batch_id: int, limit: int) -> list[ContentBatchItem]:
        result = await self.db.execute(
            select(ContentBatchItem)
            .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "planned")
            .order_by(ContentBatchItem.item_no)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _execute_one_item(
        self,
        item_id: int,
        job_context: dict[str, Any],
        *,
        created_by: str | None = None,
    ) -> _ItemExecutionResult:
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
                content_type="article",
                business_rule=dict(item.plan_json or {}),
                item_no=item.item_no,
                output_fields=["title", "body"],
                model_config=(item.plan_json or {}).get("model_config") or {},
            )
            item.plan_json = {
                **(item.plan_json or {}),
                "batch_context": {
                    "batch_id": job_context["id"],
                    "batch_code": job_context["batch_code"],
                    "item_no": item.item_no,
                },
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
                asset_refs=unified.asset_refs,
                created_by=created_by,
            )
            try:
                result = await orchestrator.run_single_capability(task_request, capability=CONTENT_GENERATE_CAPABILITY)
                final = result.output or {}
                title = str(final.get("title") or "").strip()
                body = str(final.get("body") or "").strip()
                if not title or not body:
                    raise ValueError("content.generate returned empty article")
                item.status = "generated"
                item.task_id = result.run.task_id
                item.run_id = result.run.id
                item.title = title
                item.body = body
                review_report = _default_unified_review_report()
                item.quality_json = {
                    "executor": self._executor_label(result.stage_calls),
                    "stage_call_count": len(result.stage_calls),
                    "run_status": result.run.status,
                    "review_report": review_report,
                    "hard_pass": True,
                    "soft_score_avg": None,
                    "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                    "expert_config_code": (unified.input_snapshot.get("expert") or {}).get("expert_config_code"),
                }
                diversity_slot = item.plan_json.get("diversity_slot") or {}
                item.diversity_json = {
                    "opening_type": diversity_slot.get("opening_type"),
                    "structure_type": diversity_slot.get("structure_type"),
                    "narrative_focus": diversity_slot.get("narrative_focus"),
                    "emotion": diversity_slot.get("emotion"),
                    "cta_type": diversity_slot.get("cta_type"),
                    "content_angle": diversity_slot.get("content_angle"),
                    "persona_lens": diversity_slot.get("persona_lens"),
                    "scene_type": diversity_slot.get("scene_type"),
                    "evidence_type": diversity_slot.get("evidence_type"),
                    "forbidden_overlap_group": diversity_slot.get("forbidden_overlap_group"),
                    "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                }
                await ForbiddenTermReviewService(db).review_and_rewrite_item(
                    item=item,
                    asset_key=item.plan_json.get("asset_key"),
                    orchestrator=orchestrator,
                    executor_code=self.executor_code,
                    content_type="article",
                )
                item.error_message = None
                await db.commit()
                return _ItemExecutionResult(item_id=item_id, generated=True, failed=False)
            except Exception as exc:  # pragma: no cover - concrete paths are covered by API/runtime tests
                item.status = "failed"
                if getattr(exc, "run_id", None):
                    item.run_id = exc.run_id
                item.error_message = str(exc)
                await db.commit()
                return _ItemExecutionResult(item_id=item_id, generated=False, failed=True)

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
        return "mock_or_skeleton"

    async def _rewrite_similar_generated_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
                .order_by(ContentBatchItem.item_no)
            )
            items = list(result.scalars().all())
            history_items = await self._history_items_for_similarity(db, job)
            rewrite_count = 0
            for index, item in enumerate(items):
                while item.body and item.run_id and self._similarity_rewrite_rounds(item) < MAX_SIMILARITY_REWRITE_ROUNDS:
                    best_match = self._most_similar_candidate(item, [*items[:index], *history_items])
                    if not best_match or best_match["score"] < self._similarity_threshold(best_match):
                        break
                    rewritten = await self._rewrite_item_for_similarity(item.id, best_match)
                    if not rewritten:
                        break
                    rewrite_count += 1
                    await db.refresh(item)
                    review_report = ((item.quality_json or {}).get("review_report") or {})
                    if review_report.get("similarity_rewrite_passed") is True:
                        break
            return rewrite_count

    async def _history_items_for_similarity(self, db: AsyncSession, job: ContentBatchJob) -> list[ContentBatchItem]:
        result = await db.execute(
            select(ContentBatchItem, ContentBatchJob)
            .join(ContentBatchJob, ContentBatchJob.id == ContentBatchItem.batch_id)
            .where(
                ContentBatchItem.batch_id != job.id,
                ContentBatchItem.status == "generated",
                ContentBatchItem.body.is_not(None),
                ContentBatchJob.asset_key == job.asset_key,
                ContentBatchJob.product_topic == job.product_topic,
            )
            .order_by(ContentBatchItem.create_time.desc(), ContentBatchItem.id.desc())
            .limit(HISTORY_SIMILARITY_LOOKBACK_LIMIT)
        )
        history_items: list[ContentBatchItem] = []
        for item, history_job in result.all():
            if not self._same_optional_segment(job.target_audience, history_job.target_audience):
                continue
            if not self._same_optional_segment(job.style, history_job.style):
                continue
            setattr(item, "_similarity_batch_code", history_job.batch_code)
            history_items.append(item)
        return history_items

    def _most_similar_candidate(self, item: ContentBatchItem, candidates: list[ContentBatchItem]) -> dict[str, Any] | None:
        candidates = [
            {
                "item_id": previous.id,
                "batch_id": previous.batch_id,
                "batch_code": self._batch_code_from_plan(previous),
                "item_no": previous.item_no,
                "title": previous.title,
                "body": previous.body,
                "score": round(self._jaccard_2gram(item.body or "", previous.body or ""), 4),
                "scope": "current_batch" if previous.batch_id == item.batch_id else "history",
            }
            for previous in candidates
            if previous.body
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate["score"])

    async def _rewrite_item_for_similarity(
        self,
        item_id: int,
        similar_item: dict[str, Any],
    ) -> bool:
        async with self.session_factory() as db:
            item = await self._require_item(db, item_id)
            if not item.run_id or not item.body:
                return False
            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            try:
                input_payload = self._similarity_rewrite_input(item, similar_item)
                result = await orchestrator.run_content_rewrite_stage(
                    run_id=item.run_id,
                    executor_code=self.executor_code,
                    input_payload=input_payload,
                )
                final = result.output or {}
                final_content = final.get("final") if isinstance(final.get("final"), dict) else {}
                title = str(final.get("title") or final_content.get("title") or "").strip()
                body = str(final.get("body") or final_content.get("body") or "").strip()
                if not title or not body:
                    raise ValueError("content.rewrite returned empty article")
                item.title = title
                item.body = body
                post_score = round(self._jaccard_2gram(item.body or "", similar_item.get("body") or ""), 4)
                passed = post_score < self._similarity_threshold(similar_item)
                quality = dict(item.quality_json or {})
                review_report = dict(quality.get("review_report") or {})
                similarity_rewrite = {
                    **self._similarity_rewrite_meta(item, similar_item),
                    "pre_rewrite_similarity_score": round(float(similar_item.get("score") or 0), 4),
                    "post_rewrite_similarity_score": post_score,
                    "similarity_rewrite_passed": passed,
                }
                previous_rewrites = list(quality.get("similarity_rewrites") or [])
                previous_rewrites.append(similarity_rewrite)
                rewrite_rounds = self._similarity_rewrite_rounds(item) + 1
                rewrite_reason = similarity_rewrite["reason"] if passed else f"{similarity_rewrite['reason']}，自动改写后仍为 {post_score:.2f}，需要人工处理"
                review_report.update(
                    {
                        "rewrite_required": not passed,
                        "rewrite_reason": rewrite_reason,
                        "rewrite_rounds": rewrite_rounds,
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
                    }
                )
                item.quality_json = quality
                item.error_message = None
                await db.commit()
                return True
            except Exception as exc:  # pragma: no cover - defensive path for flaky external workers
                quality = dict(item.quality_json or {})
                failures = list(quality.get("similarity_rewrite_failures") or [])
                failures.append({**self._similarity_rewrite_meta(item, similar_item), "error_message": str(exc)})
                quality["similarity_rewrite_failures"] = failures
                item.quality_json = quality
                await db.commit()
                return False

    def _similarity_rewrite_input(
        self,
        item: ContentBatchItem,
        similar_item: dict[str, Any],
    ) -> dict[str, Any]:
        similarity_meta = self._similarity_rewrite_meta(item, similar_item)
        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        return {
            "previous_content": {"title": item.title, "body": item.body},
            "content_type": "article",
            "output_fields": ["title", "body"],
            "business_rule": dict(item.plan_json or {}),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "forbidden_hits": [],
            "review_report": {
                "hard_results": [],
                "soft_scores": [],
                "failed_aes": [
                    {
                        "ae_code": "batch_similarity",
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
                "避免复用相似文章的开头句式和段落顺序",
                "更换叙事切入点，优先使用当前文章的 diversity_slot",
                "不要复用相似文章的标题模式、段首表达和内容角度",
                "保留事实、卖点和合规约束，不要扩大功效表达",
            ],
        }

    def _similarity_rewrite_meta(self, item: ContentBatchItem, similar_item: dict[str, Any]) -> dict[str, Any]:
        score = float(similar_item.get("score") or 0)
        return {
            "item_no": item.item_no,
            "similar_item_no": similar_item.get("item_no"),
            "similar_batch_id": similar_item.get("batch_id"),
            "similar_batch_code": similar_item.get("batch_code"),
            "scope": similar_item.get("scope") or "current_batch",
            "similarity_score": round(score, 4),
            "threshold": self._similarity_threshold(similar_item),
            "reason": self._similarity_reason(similar_item, score),
        }

    def _similarity_rewrite_rounds(self, item: ContentBatchItem) -> int:
        quality = item.quality_json or {}
        return len(quality.get("similarity_rewrites") or [])

    def _jaccard_2gram(self, left: str, right: str) -> float:
        left_tokens = self._text_2grams(left)
        right_tokens = self._text_2grams(right)
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    @staticmethod
    def _text_2grams(text: str) -> set[str]:
        clean = re.sub(r"\s+", "", text or "")
        return {clean[i : i + 2] for i in range(max(len(clean) - 1, 0)) if clean[i : i + 2].strip()}

    @staticmethod
    def _similarity_threshold(similar_item: dict[str, Any]) -> float:
        return HISTORY_SIMILARITY_REWRITE_THRESHOLD if similar_item.get("scope") == "history" else SIMILARITY_REWRITE_THRESHOLD

    @staticmethod
    def _similarity_reason(similar_item: dict[str, Any], score: float) -> str:
        if similar_item.get("scope") == "history":
            return f"正文与历史批次第{similar_item.get('item_no')}篇 2-gram 相似度 {score:.2f}，已触发自动改写"
        return f"正文与第{similar_item.get('item_no')}篇 2-gram 相似度 {score:.2f}，已触发自动改写"

    @staticmethod
    def _same_optional_segment(left: str | None, right: str | None) -> bool:
        return (left or "").strip() == (right or "").strip()

    @staticmethod
    def _batch_code_from_plan(item: ContentBatchItem) -> str | None:
        transient_value = getattr(item, "_similarity_batch_code", None)
        if isinstance(transient_value, str) and transient_value:
            return transient_value
        batch_context = ((item.plan_json or {}).get("batch_context") or {})
        value = batch_context.get("batch_code")
        return value if isinstance(value, str) and value else None
