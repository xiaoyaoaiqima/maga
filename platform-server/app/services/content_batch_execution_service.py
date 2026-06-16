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
from app.services.activity_quality_guard_service import ActivityQualityGuardService
from app.services.forbidden_term_review_service import ForbiddenTermReviewService
from app.services.product_experience_phrase_guard_service import (
    ProductExperiencePhraseReview,
    review_product_experience_phrase,
    should_review_product_experience,
)
from app.services.unified_content_generation_service import (
    CONTENT_GENERATE_CAPABILITY,
    UnifiedContentGenerationService,
)

SIMILARITY_REWRITE_THRESHOLD = 0.42
HISTORY_SIMILARITY_REWRITE_THRESHOLD = 0.48
MAX_SIMILARITY_REWRITE_ROUNDS = 2
MAX_PRODUCT_EXPERIENCE_PHRASE_REWRITE_ROUNDS = 1
HISTORY_SIMILARITY_LOOKBACK_LIMIT = 50
TITLE_GUARD_FORBIDDEN_SUBSTRINGS = (
    "这杯",
    "安排上",
    "留着",
    "省心",
    "踏实",
    "安心",
    "老母亲",
    "搭子",
    "别踩坑",
    "我这样",
    "选对了",
    "悄悄",
    "成长关键期",
    "日常保护力",
    "营养后路",
    "精力不够别硬撑",
    "妈妈坦白说",
    "幼儿园季",
    "户外放电",
    "看过来",
    "跟风",
    "坐得住了",
    "坐不住",
    "专注力提升",
    "少请假",
    "不生病",
    "长高",
    "窜个",
    "旺玥4段",
)
TITLE_GUARD_BAD_PATTERNS = (
    re.compile(r"(?:我家|孩子|娃).{0,6}(?:快|刚)?[0-9一二三四五六七八九十]+个?月了"),
    re.compile(r"[0-9一二三四五六七八九十]+个月宝宝"),
    re.compile(r"[0-9一二三四五六七八九十]+个月\+?旺玥"),
)


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
        await self._rewrite_product_experience_phrase_items(batch_id, job)
        await self._repair_generated_titles(batch_id, job)
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
                keyword_asset_key=(item.plan_json or {}).get("keyword_asset_key"),
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
                ActivityQualityGuardService().review_item(item)
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

    async def _repair_article_length_if_needed(
        self,
        item: ContentBatchItem,
        *,
        orchestrator: ContentAgentOrchestrator,
        run_id: int,
    ) -> dict[str, Any] | None:
        target = _article_length_target(item.plan_json or {})
        if not target:
            return None
        kind, min_chars, max_chars = target
        before_chars = _compact_len(item.body)
        if min_chars <= before_chars <= max_chars:
            return None
        after_chars = before_chars
        attempts = 0
        last_error = None
        for attempts in range(1, 3):
            rewrite_input = _length_rewrite_input(
                item,
                kind=kind,
                min_chars=min_chars,
                max_chars=max_chars,
                before_chars=after_chars,
                rewrite_round=attempts,
            )
            try:
                result = await orchestrator.run_content_rewrite_stage(
                    run_id=run_id,
                    executor_code=self.executor_code,
                    input_payload=rewrite_input,
                )
            except Exception as exc:  # noqa: BLE001 - keep generated item when optional repair fails
                last_error = str(exc)
                break
            output = result.output or {}
            final = output.get("final") if isinstance(output.get("final"), dict) else {}
            title = str(output.get("title") or final.get("title") or "").strip()
            body = str(output.get("body") or final.get("body") or "").strip()
            if title:
                item.title = title
            if body:
                item.body = body
            after_chars = _compact_len(item.body)
            if min_chars <= after_chars <= max_chars:
                break
        return {
            "kind": kind,
            "before_chars": before_chars,
            "after_chars": after_chars,
            "target_min": min_chars,
            "target_max": max_chars,
            "attempts": attempts,
            **({"error": last_error} if last_error else {}),
            "status": "passed" if min_chars <= after_chars <= max_chars else "still_out_of_range",
        }

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

    async def _repair_generated_titles(self, batch_id: int, job: ContentBatchJob) -> int:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
                .order_by(ContentBatchItem.item_no)
            )
            items = list(result.scalars().all())
            if not _should_apply_title_guard(job, items):
                return 0

            used_titles: set[str] = set()
            repair_count = 0
            for item in items:
                reasons = _title_guard_reasons(item.title or "", used_titles)
                if not reasons:
                    used_titles.add(_normalize_title(item.title or ""))
                    continue

                before = item.title or ""
                item.title = _fallback_title_for_item(item, used_titles)
                used_titles.add(_normalize_title(item.title or ""))
                quality = dict(item.quality_json or {})
                repairs = list(quality.get("title_guard_repairs") or [])
                repairs.append({"before": before, "after": item.title, "reasons": reasons})
                quality["title_guard_repairs"] = repairs
                quality["title_guard"] = {"pass": True, "repair_count": len(repairs)}
                item.quality_json = quality
                repair_count += 1
            if repair_count:
                await db.commit()
            return repair_count

    async def _rewrite_product_experience_phrase_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
                .order_by(ContentBatchItem.item_no)
            )
            items = list(result.scalars().all())
            rewrite_count = 0
            for item in items:
                if not should_review_product_experience(item.plan_json):
                    continue
                review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                rewrite_rounds = self._product_experience_phrase_rewrite_rounds(item)
                while review.rewrite_required and item.run_id and rewrite_rounds < MAX_PRODUCT_EXPERIENCE_PHRASE_REWRITE_ROUNDS:
                    rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review)
                    if not rewritten:
                        break
                    rewrite_count += 1
                    rewrite_rounds += 1
                    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                self._mark_product_experience_phrase_review(item, review)
            if items:
                await db.commit()
            return rewrite_count

    async def _rewrite_item_for_product_experience_phrase(
        self,
        db: AsyncSession,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> bool:
        if not item.run_id or not item.body:
            return False
        orchestrator = ContentAgentOrchestrator(
            db,
            invocation_client=self.invocation_client,
            callback_base_url=self.callback_base_url,
        )
        try:
            input_payload = self._product_experience_phrase_rewrite_input(item, review)
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
            post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
            quality = dict(item.quality_json or {})
            rewrites = list(quality.get("product_experience_phrase_rewrites") or [])
            rewrite_round = self._product_experience_phrase_rewrite_rounds(item) + 1
            rewrites.append(
                {
                    "rewrite_round": rewrite_round,
                    "pre_review": review.model_dump(),
                    "post_review": post_review.model_dump(),
                    "passed": post_review.pass_,
                }
            )
            quality["product_experience_phrase_rewrites"] = rewrites
            quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + len(result.stage_calls)
            quality["run_status"] = result.run.status
            item.quality_json = quality
            self._mark_product_experience_phrase_review(item, post_review)
            item.error_message = None
            await db.flush()
            return True
        except Exception as exc:  # pragma: no cover - defensive path for flaky external workers
            quality = dict(item.quality_json or {})
            failures = list(quality.get("product_experience_phrase_rewrite_failures") or [])
            failures.append({"review": review.model_dump(), "error_message": str(exc)})
            quality["product_experience_phrase_rewrite_failures"] = failures
            item.quality_json = quality
            await db.flush()
            return False

    def _product_experience_phrase_rewrite_input(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> dict[str, Any]:
        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        target = review.length_target
        length_instruction = ""
        if target:
            kind, min_chars, max_chars = target
            if review.body_chars < min_chars:
                length_instruction = (
                    f"当前正文约{review.body_chars}字，偏短；补到{min_chars}-{max_chars}字，"
                    "直接重写成4个自然短句：场景、孩子动作、妈妈观察、收住；不补购买过程和功效结论。"
                )
            elif review.body_chars > max_chars:
                length_instruction = (
                    f"当前正文约{review.body_chars}字，偏长；删到{min_chars}-{max_chars}字，"
                    "优先删解释、重复观察和统一收口，不要再扩写。"
                )
            else:
                length_instruction = f"{kind}正文保持在{min_chars}-{max_chars}字内，不要为了改写额外扩写。"
        hit_summary = "；".join(
            f"{part}:{'/'.join(hits)}" for part, hits in review.skeleton_hits.items() if hits
        )
        phrase_instruction = (
            f"本轮命中的口癖骨架是 {hit_summary}；至少删掉其中两个维度，尤其别把购买判断、价格、孩子接受、安心收口连在一起。"
            if hit_summary
            else "如果没有完整口癖骨架，只处理本轮命中的长度或 AI 收口问题；长度是硬性验收，必须先满足字数范围。"
        )
        ai_phrase_instruction = (
            f"本轮命中的 AI 收口词是 {'/'.join(review.ai_phrase_hits)}；改写后不要再出现这些词。"
            if review.ai_phrase_hits
            else "不要新增省心、踏实、心里有数、先这样、固定下来这类统一收口词。"
        )
        return {
            "previous_content": {"title": item.title or "", "body": item.body or ""},
            "content_type": "article",
            "output_fields": ["title", "body"],
            "business_rule": dict(item.plan_json or {}),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "model_config": dict((item.plan_json or {}).get("model_config") or {}),
            "rewrite_source": "product_experience_phrase_guard",
            "rewrite_round": self._product_experience_phrase_rewrite_rounds(item) + 1,
            "review_report": {
                "rewrite_required": True,
                "rewrite_reason": "业务规则口癖骨架或长度超限",
                "product_experience_phrase_review": review.model_dump(),
            },
        "rewrite_instructions": [
                length_instruction or "正文长度服从业务规则，标题尽量不改；正文单段不换行。",
                phrase_instruction,
                ai_phrase_instruction,
                "返回的 body 必须和原 body 不同；必要时可以整段重写，不要逐句改写原文。",
                "如果正文已经有购买过程、价格和孩子接受度，只保留其中一个观察点，其他改成放学、饭桌、户外、杯子、剩半杯这类生活细节。",
                "不要用“省心、踏实、固定下来、心里有数、先这样”作为统一收口。",
                "长个、少请假、不生病、抵抗力、坐不住这类真人强表达可以保留为观察或别人问，不能写成确定因果。",
                "标题尽量不改；正文单段不换行；不要写成导购或品牌介绍。",
                "只输出 JSON：title, body。",
            ],
        }

    def _mark_product_experience_phrase_review(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> None:
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        review_report["product_experience_phrase_review"] = review.model_dump()
        if review.rewrite_required:
            review_report.update(
                {
                    "rewrite_required": True,
                    "rewrite_reason": "业务规则口癖骨架或长度仍需人工处理",
                }
            )
        elif review_report.get("rewrite_reason") == "业务规则口癖骨架或长度仍需人工处理":
            review_report["rewrite_required"] = False
            review_report.pop("rewrite_reason", None)
        quality["review_report"] = review_report
        quality["product_experience_phrase_guard"] = {
            "pass": review.pass_,
            "rewrite_required": review.rewrite_required,
            "reasons": review.reasons,
        }
        item.quality_json = quality

    @staticmethod
    def _product_experience_phrase_rewrite_rounds(item: ContentBatchItem) -> int:
        quality = item.quality_json or {}
        return len(quality.get("product_experience_phrase_rewrites") or [])

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


def _article_length_target(plan: dict[str, Any]) -> tuple[str, int, int] | None:
    corpus = str(plan.get("corpus") or "")
    if "篇幅类型：中短文" in corpus:
        return "中短文", 120, 150
    if "篇幅类型：短文" in corpus:
        return "短文", 40, 80
    return None


def _length_rewrite_input(
    item: ContentBatchItem,
    *,
    kind: str,
    min_chars: int,
    max_chars: int,
    before_chars: int,
    rewrite_round: int,
) -> dict[str, Any]:
    missing_chars = max(min_chars - before_chars, 0)
    if before_chars > max_chars:
        action = (
            f"当前正文约{before_chars}个中文字符，偏长；删到{min_chars}-{max_chars}个中文字符。"
            "优先删重复解释、购买过程、价格纠结、统一收口和功效感强的句子；不要新增内容。"
        )
    elif kind == "中短文":
        action = (
            f"当前正文只有{before_chars}个中文字符，至少还要补{missing_chars + 8}个中文字符；"
            f"把正文补到{min_chars}-{max_chars}个中文字符，优先补具体生活动作、饭桌/出门/放学后的观察、"
            "还在观望的语气；不要补购买过程、价格纠结、孩子愿意喝或统一收口，也不要新增功效结论。"
        )
    else:
        action = (
            f"当前正文只有{before_chars}个中文字符；把正文调整到{min_chars}-{max_chars}个中文字符，"
            "保留一个生活瞬间和一句选择理由。"
        )
    return {
        "previous_content": {"title": item.title or "", "body": item.body or ""},
        "content_type": "article",
        "output_fields": ["title", "body"],
        "business_rule": dict(item.plan_json or {}),
        "selected_keywords": ((item.plan_json or {}).get("unified_generation") or {}).get("selected_keywords") or [],
        "model_config": dict((item.plan_json or {}).get("model_config") or {}),
        "rewrite_source": "article_length_guard",
        "rewrite_round": rewrite_round,
        "review_report": {
            "rewrite_required": True,
            "rewrite_reason": f"{kind}正文长度不在{min_chars}-{max_chars}字",
        },
        "rewrite_instructions": [
            action,
            f"返回的 body 必须和原 body 不同，且正文必须落在{min_chars}-{max_chars}个中文字符。",
            "标题尽量不改；正文单段不换行。",
            "保持小红书真实用户语气，不写品牌介绍、攻略清单、专业科普或确定功效。",
            "只输出 JSON：title, body。",
        ],
    }


def _compact_len(value: str | None) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def _should_apply_title_guard(job: ContentBatchJob, items: list[ContentBatchItem]) -> bool:
    if "wangyue" in (job.asset_key or "").lower() or "旺玥" in (job.product_topic or ""):
        return True
    return any("0705旺玥活动" in str((item.plan_json or {}).get("corpus") or "") for item in items)


def _title_guard_reasons(title: str, used_titles: set[str]) -> list[str]:
    reasons: list[str] = []
    normalized = _normalize_title(title)
    if normalized and normalized in used_titles:
        reasons.append("duplicate_title")
    for phrase in TITLE_GUARD_FORBIDDEN_SUBSTRINGS:
        if phrase in title:
            reasons.append(f"forbidden_title_phrase:{phrase}")
    for pattern in TITLE_GUARD_BAD_PATTERNS:
        if pattern.search(title):
            reasons.append("ambiguous_age_or_duration")
            break
    return reasons


def _fallback_title_for_item(item: ContentBatchItem, used_titles: set[str]) -> str:
    plan = item.plan_json or {}
    corpus = str(plan.get("corpus") or "")
    scene = _corpus_field(corpus, "场景")
    topic = str(plan.get("topic") or plan.get("business_rule") or "")
    duration = str(_corpus_field(corpus, "喝旺玥时间"))
    duration_label = _duration_title_label(duration)
    candidates = _title_candidates(scene=scene, topic=topic, duration_label=duration_label)
    start = max((item.item_no or 1) - 1, 0)
    for offset in range(len(candidates)):
        candidate = candidates[(start + offset) % len(candidates)]
        if not _title_guard_reasons(candidate, used_titles):
            return candidate
    return f"旺玥喝了{duration_label}记录"


def _title_candidates(*, scene: str, topic: str, duration_label: str) -> list[str]:
    candidates = [
        f"旺玥喝了{duration_label}记录",
        "给娃选奶纠结了一阵",
        "儿童奶粉换到旺玥",
        "又开一听旺玥奶粉",
        "喝了一阵旺玥来聊聊",
        "皇家美素佳儿旺玥",
        "三岁后奶粉怎么选",
        "旺玥和原来那罐怎么选",
    ]
    if "幼儿园" in scene or "集体" in scene:
        candidates.extend(["上幼儿园后开始看旺玥", "幼儿园后的选奶记录"])
    if "户外" in scene:
        candidates.extend(["户外玩得多后的选奶记录", "出去玩多了开始看旺玥"])
    if "挑食" in scene or "饭" in scene or "营养不足" in topic:
        candidates.extend(["挑食那阵子开始看旺玥", "挑食娃的旺玥记录"])
    if "选奶" in scene or "纠结" in topic:
        candidates.extend(["选儿童奶粉纠结了一圈", "旺玥喝了一阵的反馈"])
    if "注意" in topic or "眼脑" in topic:
        candidates.extend(["上学后看儿童奶粉", "写写画画多了以后看奶粉"])
    return candidates


def _duration_title_label(duration: str) -> str:
    if "6个月以上" in duration:
        return "大半年"
    if "3-6个月" in duration:
        return "几个月"
    if "3个月内" in duration:
        return "一阵"
    return "一阵"


def _corpus_field(corpus: str, field_name: str) -> str:
    match = re.search(rf"{re.escape(field_name)}[:：]([^；\n]+)", corpus)
    return match.group(1).strip() if match else ""


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", title or "").strip().lower()
