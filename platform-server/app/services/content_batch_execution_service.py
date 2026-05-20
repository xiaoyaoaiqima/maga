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
from app.services.content_batch_snapshot_adapter import build_xhs_generation_snapshot_from_plan
from app.services.executor_invocation_service import ExecutorInvocationClient
from app.services.prompt_bundle_service import PromptBundleService

SIMILARITY_REWRITE_THRESHOLD = 0.42
HISTORY_SIMILARITY_REWRITE_THRESHOLD = 0.48
MAX_SIMILARITY_REWRITE_ROUNDS = 2
HISTORY_SIMILARITY_LOOKBACK_LIMIT = 50


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
            snapshot = build_xhs_generation_snapshot_from_plan(
                item.plan_json,
                batch_id=job_context["id"],
                batch_code=job_context["batch_code"],
                prompt_bundle_snapshot=await PromptBundleService(db).build_xhs_writer_prompt_bundle_snapshot(),
            )
            task_input = self._task_input_from_snapshot(snapshot)
            task_request = ContentAgentTaskCreate(
                task_type="xhs_generate",
                executor_code=self.executor_code,
                input_snapshot=task_input,
                asset_refs=snapshot.get("asset_refs") or {},
                created_by=created_by,
            )
            try:
                result = await orchestrator.run_mvp_generation_chain(task_request)
                final = result.final_content
                item.status = "generated"
                item.task_id = result.run.task_id
                item.run_id = result.run.id
                item.title = final["title"]
                item.body = final["body"]
                review_report = self._review_report_from_stage_calls(result.stage_calls)
                item.quality_json = {
                    "executor": self._executor_label(result.stage_calls),
                    "stage_call_count": len(result.stage_calls),
                    "run_status": result.run.status,
                    "review_report": review_report,
                    "hard_pass": self._hard_pass(review_report),
                    "soft_score_avg": self._soft_score_avg(review_report),
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
                }
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

    def _review_report_from_stage_calls(self, stage_calls: list[Any]) -> dict[str, Any]:
        review_rewrite_report = self._review_report_for_capability(stage_calls, "xhs.review_and_rewrite")
        if review_rewrite_report:
            return review_rewrite_report

        ae_review_report = self._review_report_for_capability(stage_calls, "xhs.run_ae_review")
        if ae_review_report:
            return ae_review_report

        runtime_fast_report = self._review_report_for_capability(stage_calls, "xhs.generate_draft", require_runtime_fast=True)
        if runtime_fast_report:
            return runtime_fast_report

        draft_report = self._review_report_for_capability(stage_calls, "xhs.generate_draft")
        if draft_report:
            return draft_report

        return {"hard_results": [], "soft_scores": [], "failed_aes": [], "rewrite_required": True}

    def _review_report_for_capability(
        self,
        stage_calls: list[Any],
        capability: str,
        *,
        require_runtime_fast: bool = False,
    ) -> dict[str, Any] | None:
        for stage_call in stage_calls:
            if getattr(stage_call, "capability", None) != capability:
                continue
            output = getattr(stage_call, "output_snapshot", None) or {}
            if require_runtime_fast and ((output.get("runtime_result") or {}).get("mode") != "runtime_fast"):
                continue
            report = output.get("review_report")
            if self._is_meaningful_review_report(report):
                return report
            if output.get("hard_results") is not None or output.get("soft_scores") is not None:
                return {
                    "hard_results": output.get("hard_results") or [],
                    "soft_scores": output.get("soft_scores") or [],
                    "failed_aes": output.get("failed_aes") or [],
                    "rewrite_required": bool(output.get("failed_aes")),
                }
        return None

    def _is_meaningful_review_report(self, report: Any) -> bool:
        if not isinstance(report, dict):
            return False
        return any(
            key in report
            for key in ["hard_results", "soft_scores", "failed_aes", "rewrite_required", "suggestions", "raw"]
        )

    def _executor_label(self, stage_calls: list[Any]) -> str:
        for stage_call in stage_calls:
            output = getattr(stage_call, "output_snapshot", None) or {}
            runtime_mode = (output.get("runtime_result") or {}).get("mode")
            if runtime_mode:
                return str(runtime_mode)
        return "mock_or_skeleton"

    def _hard_pass(self, review_report: dict[str, Any]) -> bool:
        hard_results = review_report.get("hard_results") or []
        return bool(hard_results) and all(item.get("pass") is True for item in hard_results if isinstance(item, dict))

    def _soft_score_avg(self, review_report: dict[str, Any]) -> float | None:
        scores = [
            float(item["score"])
            for item in (review_report.get("soft_scores") or [])
            if isinstance(item, dict) and isinstance(item.get("score"), (int, float))
        ]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)

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
                input_payload = self._similarity_rewrite_input(
                    item,
                    similar_item,
                    prompt_bundle_snapshot=await PromptBundleService(db).build_xhs_writer_prompt_bundle_snapshot(),
                )
                result = await orchestrator.run_rewrite_stage(
                    run_id=item.run_id,
                    executor_code=self.executor_code,
                    input_payload=input_payload,
                )
                final = result.final_content
                item.title = final["title"]
                item.body = final["body"]
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
        *,
        prompt_bundle_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = build_xhs_generation_snapshot_from_plan(
            item.plan_json,
            batch_id=item.batch_id,
            batch_code=None,
            prompt_bundle_snapshot=prompt_bundle_snapshot,
        )
        similarity_meta = self._similarity_rewrite_meta(item, similar_item)
        return {
            "previous_draft": {"title": item.title, "body": item.body},
            "structured_brief": {
                "product_topic": item.plan_json.get("product_topic"),
                "target_audience": item.plan_json.get("target_audience"),
                "style": item.plan_json.get("style"),
            },
            "analyses": {},
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
            "generation_snapshot": snapshot,
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

    def _task_input_from_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        brief = snapshot.get("brief") or {}
        return {
            "brief_type": "xhs_product_seeding",
            "product_topic": self._topic_for_diversity(brief, snapshot),
            "target_audience": brief.get("target_audience"),
            "persona_target": brief.get("persona_target"),
            "style": brief.get("style"),
            "generation_snapshot": snapshot,
        }

    def _topic_for_diversity(self, brief: dict[str, Any], snapshot: dict[str, Any]) -> str:
        topic = brief.get("product_topic") or "源悦"
        batch_context = snapshot.get("batch_context") or {}
        item_no = batch_context.get("item_no")
        diversity = snapshot.get("diversity_slot") or {}
        opening = diversity.get("opening_type")
        structure = diversity.get("structure_type")
        suffix_parts = [part for part in [f"第{item_no}篇" if item_no else None, opening, structure] if part]
        return topic if not suffix_parts else f"{topic}｜{'/'.join(suffix_parts)}"
