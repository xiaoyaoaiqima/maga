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
from app.services.content_rewrite_context import rewrite_business_rule_context
from app.services.executor_invocation_service import ExecutorInvocationClient
from app.services.activity_quality_guard_service import ActivityQualityGuardService
from app.services.forbidden_term_review_service import ForbiddenTermReviewService
from app.services.product_experience_phrase_guard_service import (
    ProductExperiencePhraseReview,
    review_product_experience_phrase,
    sanitize_adult_self_drinking_phrases,
    sanitize_baby_milk_action_phrases,
    sanitize_common_ai_closure,
    sanitize_odd_product_experience_phrases,
    sanitize_temporal_context,
    sanitize_wangyue_context_phrases,
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
    "【标题】",
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
    "4段",
    "没选错",
    "全靠",
    "防风",
    "身体也稳",
    "体质真靠",
    "体质稳",
    "小秘密",
    "秘密",
    "小卫士",
    "小守护",
    "守护",
    "撑住",
    "靠这招",
    "换到旺玥",
    "给娃选奶",
    "怎么选",
    "原来那罐",
    "选奶记录",
    "开始看旺玥",
)
TITLE_GUARD_BAD_PATTERNS = (
    re.compile(r"(?:我家|孩子|娃).{0,6}(?:快|刚)?[0-9一二三四五六七八九十]+个?月了"),
    re.compile(r"[0-9一二三四五六七八九十]+个月宝宝"),
    re.compile(r"[0-9一二三四五六七八九十]+个月\+?旺玥"),
)
TITLE_FORMAT_PATTERNS = (
    re.compile(r"^\s*#{1,6}\s*(?:标题[:：]\s*)?"),
    re.compile(r"^\s*[*_`~\s]*(?:标题|title)[:：]\s*", re.IGNORECASE),
    re.compile(r"[*_`~\s]+$"),
)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u27BF"
    "]+"
)
PERSONA_STYLE_REWRITE_PRESETS = (
    {
        "code": "roommate_direct",
        "prompt": "爽快、直给、不端着的熟人聊天口吻；句子短一点，可以有一点轻微吐槽感。",
    },
    {
        "code": "mother_soft_observer",
        "prompt": "像妈妈随手记孩子状态，温柔但不铺开；别堆场景，也别压成提纲。",
    },
    {
        "code": "yuuka_strict_friend",
        "prompt": "理性负责、带一点嘴硬吐槽的熟人聊天口吻，句子利落；可以调整叙述顺序。",
    },
    {
        "code": "amber_sunny_friend",
        "prompt": "轻快、有行动感的熟人聊天口吻，别太甜。",
    },
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
                item.diversity_json = {
                    "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                }
                await self._rewrite_item_for_persona_style(
                    item=item,
                    orchestrator=orchestrator,
                    run_id=result.run.id,
                )
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

    async def _rewrite_item_for_persona_style(
        self,
        *,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator,
        run_id: int,
    ) -> None:
        if not item.body or not _persona_style_rewrite_enabled(item.plan_json):
            return
        preset = _persona_style_preset_for_item(item)
        input_payload = _persona_style_rewrite_input(item, preset=preset)
        try:
            result = await orchestrator.run_content_rewrite_stage(
                run_id=run_id,
                executor_code=self.executor_code,
                input_payload=input_payload,
            )
            output = result.output or {}
            final = output.get("final") if isinstance(output.get("final"), dict) else {}
            title = str(output.get("title") or final.get("title") or "").strip()
            body = str(output.get("body") or final.get("body") or "").strip()
            if not title or not body:
                raise ValueError("content.rewrite returned empty article")
            before = {"title": item.title or "", "body": item.body or ""}
            item.title = title
            item.body = body
            quality = dict(item.quality_json or {})
            rewrites = list(quality.get("persona_style_rewrites") or [])
            rewrites.append(
                {
                    "preset_code": preset["code"],
                    "preset_prompt": preset["prompt"],
                    "before": before,
                    "after": {"title": item.title, "body": item.body},
                    "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                }
            )
            quality["persona_style_rewrites"] = rewrites
            quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + len(result.stage_calls)
            quality["run_status"] = result.run.status
            item.quality_json = quality
            await orchestrator.db.flush()
        except Exception as exc:  # noqa: BLE001 - keep generated content if style rewrite fails
            quality = dict(item.quality_json or {})
            failures = list(quality.get("persona_style_rewrite_failures") or [])
            failures.append(
                {
                    "preset_code": preset["code"],
                    "preset_prompt": preset["prompt"],
                    "error_message": str(exc),
                }
            )
            quality["persona_style_rewrite_failures"] = failures
            item.quality_json = quality
            await orchestrator.db.flush()

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
        if before_chars < min_chars:
            return {
                "kind": kind,
                "before_chars": before_chars,
                "after_chars": before_chars,
                "target_min": min_chars,
                "target_max": max_chars,
                "attempts": 0,
                "status": "too_short_unrepaired",
            }
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
                format_cleaned_title = _sanitize_generated_title_format(item.title or "")
                if format_cleaned_title and format_cleaned_title != (item.title or ""):
                    before = item.title or ""
                    item.title = format_cleaned_title
                    quality = dict(item.quality_json or {})
                    cleanups = list(quality.get("title_format_cleanups") or [])
                    cleanups.append({"before": before, "after": item.title})
                    quality["title_format_cleanups"] = cleanups
                    item.quality_json = quality
                    repair_count += 1

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
                if should_review_product_experience(item.plan_json):
                    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    self._mark_product_experience_phrase_review(item, review)
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
                if review.temporal_context_hits:
                    before = {"title": item.title or "", "body": item.body or ""}
                    item.title = sanitize_temporal_context(item.title)
                    item.body = sanitize_temporal_context(item.body)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    quality = dict(item.quality_json or {})
                    cleanups = list(quality.get("product_experience_temporal_context_cleanups") or [])
                    cleanups.append(
                        {
                            "before": before,
                            "after": {"title": item.title or "", "body": item.body or ""},
                            "pre_review": review.model_dump(),
                            "post_review": post_review.model_dump(),
                        }
                    )
                    quality["product_experience_temporal_context_cleanups"] = cleanups
                    item.quality_json = quality
                    review = post_review
                    rewrite_count += 1
                if "common_ai_closure_phrase" in review.reasons:
                    before = {"title": item.title or "", "body": item.body or ""}
                    item.title = sanitize_common_ai_closure(item.title)
                    item.body = sanitize_common_ai_closure(item.body)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    quality = dict(item.quality_json or {})
                    cleanups = list(quality.get("product_experience_common_ai_closure_cleanups") or [])
                    cleanups.append(
                        {
                            "before": before,
                            "after": {"title": item.title or "", "body": item.body or ""},
                            "pre_review": review.model_dump(),
                            "post_review": post_review.model_dump(),
                        }
                    )
                    quality["product_experience_common_ai_closure_cleanups"] = cleanups
                    item.quality_json = quality
                    review = post_review
                    rewrite_count += 1
                if "odd_product_experience_phrase" in review.reasons:
                    before = {"title": item.title or "", "body": item.body or ""}
                    item.title = sanitize_odd_product_experience_phrases(item.title)
                    item.body = sanitize_odd_product_experience_phrases(item.body)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    quality = dict(item.quality_json or {})
                    cleanups = list(quality.get("product_experience_odd_phrase_cleanups") or [])
                    cleanups.append(
                        {
                            "before": before,
                            "after": {"title": item.title or "", "body": item.body or ""},
                            "pre_review": review.model_dump(),
                            "post_review": post_review.model_dump(),
                        }
                    )
                    quality["product_experience_odd_phrase_cleanups"] = cleanups
                    item.quality_json = quality
                    review = post_review
                    rewrite_count += 1
                if "adult_self_drinking_child_formula" in review.reasons:
                    before = {"title": item.title or "", "body": item.body or ""}
                    item.title = sanitize_adult_self_drinking_phrases(item.title)
                    item.body = sanitize_adult_self_drinking_phrases(item.body)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    quality = dict(item.quality_json or {})
                    cleanups = list(quality.get("product_experience_adult_self_drinking_cleanups") or [])
                    cleanups.append(
                        {
                            "before": before,
                            "after": {"title": item.title or "", "body": item.body or ""},
                            "pre_review": review.model_dump(),
                            "post_review": post_review.model_dump(),
                        }
                    )
                    quality["product_experience_adult_self_drinking_cleanups"] = cleanups
                    item.quality_json = quality
                    review = post_review
                    rewrite_count += 1
                if "child_self_brewing_formula" in review.reasons:
                    rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    review = post_review
                    if rewritten:
                        rewrite_count += 1
                if "child_formula_bottle_context" in review.reasons:
                    before = {"title": item.title or "", "body": item.body or ""}
                    item.title = sanitize_baby_milk_action_phrases(item.title)
                    item.body = sanitize_baby_milk_action_phrases(item.body)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    quality = dict(item.quality_json or {})
                    cleanups = list(quality.get("product_experience_baby_milk_action_cleanups") or [])
                    cleanups.append(
                        {
                            "before": before,
                            "after": {"title": item.title or "", "body": item.body or ""},
                            "pre_review": review.model_dump(),
                            "post_review": post_review.model_dump(),
                        }
                    )
                    quality["product_experience_baby_milk_action_cleanups"] = cleanups
                    item.quality_json = quality
                    review = post_review
                    rewrite_count += 1
                if (
                    "wangyue_wrong_brand" in review.reasons
                    or "wangyue_explicit_age_context" in review.reasons
                    or "wangyue_portable_form_context" in review.reasons
                ):
                    before = {"title": item.title or "", "body": item.body or ""}
                    item.title = sanitize_wangyue_context_phrases(item.title)
                    item.body = sanitize_wangyue_context_phrases(item.body)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    quality = dict(item.quality_json or {})
                    cleanups = list(quality.get("product_experience_wangyue_context_cleanups") or [])
                    cleanups.append(
                        {
                            "before": before,
                            "after": {"title": item.title or "", "body": item.body or ""},
                            "pre_review": review.model_dump(),
                            "post_review": post_review.model_dump(),
                        }
                    )
                    quality["product_experience_wangyue_context_cleanups"] = cleanups
                    item.quality_json = quality
                    review = post_review
                    rewrite_count += 1
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
                    f"当前正文约{review.body_chars}字，偏短但不强制扩写；"
                    "只删除或替换命中的问题表达，不为了凑字数新增生活动作、观察或收口。"
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
        adult_self_drinking_instruction = (
            f"本轮出现成人自己喝儿童奶粉的错误场景：{'/'.join(review.adult_self_drinking_hits)}；直接删除或改成给孩子冲/孩子喝，不要扩写成新情节。"
            if review.adult_self_drinking_hits
            else "不要写妈妈自己喝、给自己冲或成人试喝旺玥；旺玥只作为给孩子喝的儿童奶粉出现。"
        )
        child_self_brewing_instruction = (
            "本轮出现孩子自己冲/泡/舀奶粉的不合理动作："
            f"{'/'.join(review.child_self_brewing_hits)}。"
            "请用模型改顺这句话的上下文：可以改成妈妈冲好递给孩子、孩子等着喝、孩子喝奶配合、喝完后放杯子等合理动作。"
            "不要硬塞固定替换短语，不要保留“自己冲/自己泡/自己舀/自己挖/自己催我泡奶粉”等动作，也不要新增奶粉盒、书包、随身带奶粉或成人试喝情节。"
            if review.child_self_brewing_hits
            else "不要写孩子自己冲奶粉、泡奶粉、舀粉、挖粉或自己操作奶粉罐；冲泡动作由妈妈完成，孩子只负责等、接、喝或喝完后的自然动作。"
        )
        return {
            "previous_content": {"title": item.title or "", "body": item.body or ""},
            "content_type": "article",
            "output_fields": ["title", "body"],
            "business_rule": rewrite_business_rule_context(item.plan_json),
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
                adult_self_drinking_instruction,
                child_self_brewing_instruction,
                "rewrite 优先删除问题内容或压缩问题句；不要为了多样化整段重写。只有删除后语义断裂时，才补极短连接。",
                "如果正文已经有购买过程、价格和孩子接受度，只保留其中一个观察点，其他改成放学、户外、换衣服、书包、妈妈观察这类生活细节；不要新增剩奶、杯子放置或冲泡奶保存动作。",
                "不要用“省心、踏实、固定下来、心里有数、先这样”作为统一收口。",
                "长个、少请假、不生病、保护力、坐不住这类真人强表达可以保留为观察或别人问，不能写成确定因果。",
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
            "business_rule": rewrite_business_rule_context(item.plan_json),
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
                "优先删除或压缩与相似文章重复的开头、段落顺序和表达，不要为了多样化扩写新情节。",
                "只在删除后语义断裂时补一句极短连接，优先使用当前文章已有信息。",
                "不要复用相似文章的标题模式、段首表达和内容角度；标题能保留就保留。",
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
    if before_chars > max_chars:
        action = (
            f"当前正文约{before_chars}个中文字符，偏长；删到{min_chars}-{max_chars}个中文字符。"
            "优先删重复解释、购买过程、价格纠结、统一收口和功效感强的句子；不要新增内容。"
        )
    elif kind == "中短文":
        action = (
            f"当前正文只有{before_chars}个中文字符，偏短但不强制扩写；"
            "除非原文语义不完整，否则保留原文，不要为了凑字数新增生活动作、饭桌、出门、放学或观察细节。"
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
        "business_rule": rewrite_business_rule_context(item.plan_json),
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
            f"rewrite 优先删除问题内容，不做多样化扩写；只有正文偏长时才必须落在{min_chars}-{max_chars}个中文字符。",
            "标题尽量不改；正文单段不换行。",
            "保持小红书真实用户语气，不写品牌介绍、攻略清单、专业科普或确定功效。",
            "只输出 JSON：title, body。",
        ],
    }


def _persona_style_rewrite_enabled(plan: dict[str, Any] | None) -> bool:
    if should_review_product_experience(plan):
        return False
    value = (plan or {}).get("persona_style_rewrite_enabled")
    return value is not False


def _persona_style_preset_for_item(item: ContentBatchItem) -> dict[str, str]:
    plan = item.plan_json or {}
    requested = str(plan.get("persona_style_rewrite_preset") or "").strip()
    if requested:
        for preset in PERSONA_STYLE_REWRITE_PRESETS:
            if preset["code"] == requested:
                return preset
    index = max(int(item.item_no or 1) - 1, 0) % len(PERSONA_STYLE_REWRITE_PRESETS)
    return PERSONA_STYLE_REWRITE_PRESETS[index]


def _persona_style_rewrite_input(item: ContentBatchItem, *, preset: dict[str, str]) -> dict[str, Any]:
    unified_generation = (item.plan_json or {}).get("unified_generation") or {}
    return {
        "previous_content": {"title": item.title or "", "body": item.body or ""},
        "content_type": "article",
        "output_fields": ["title", "body"],
        "business_rule": rewrite_business_rule_context(item.plan_json),
        "selected_keywords": unified_generation.get("selected_keywords") or [],
        "model_config": dict((item.plan_json or {}).get("model_config") or {}),
        "rewrite_source": "persona_style_rewrite",
        "rewrite_style_preset": preset["code"],
        "rewrite_round": len((item.quality_json or {}).get("persona_style_rewrites") or []) + 1,
        "review_report": {
            "rewrite_required": True,
            "rewrite_reason": "生成后人设风格改写",
            "rewrite_style_preset": preset["code"],
        },
        "rewrite_instructions": [
            "人设改写风格：" + preset["prompt"],
            "不要改变原文的发帖视角。",
            "可以调整叙述顺序和表达逻辑，让正文更像这个风格的人顺手发出来。",
            "这是生成后的风格改写，不要解释改写过程，只输出 JSON：title, body。",
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
    if _sanitize_generated_title_format(title) != title:
        reasons.append("generated_title_format")
    for phrase in TITLE_GUARD_FORBIDDEN_SUBSTRINGS:
        if phrase in title:
            reasons.append(f"forbidden_title_phrase:{phrase}")
    for pattern in TITLE_GUARD_BAD_PATTERNS:
        if pattern.search(title):
            reasons.append("ambiguous_age_or_duration")
            break
    return reasons


def _sanitize_generated_title_format(title: str | None) -> str:
    text = str(title or "").strip()
    if not text:
        return text
    for pattern in TITLE_FORMAT_PATTERNS:
        text = pattern.sub("", text).strip()
    text = EMOJI_PATTERN.sub("", text).strip()
    text = re.sub(r"^\s*(?:标题|title)[:：]\s*", "", text, flags=re.IGNORECASE).strip()
    text = text.strip(" *_`~#")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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
        "又开一听旺玥奶粉",
        "旺玥喝了一阵",
        "皇家美素佳儿旺玥",
        "最近还在喝旺玥",
        "今天继续记录旺玥",
        "家里那罐旺玥",
    ]
    if "幼儿园" in scene or "集体" in scene:
        candidates.extend(["上幼儿园后继续喝旺玥", "幼儿园回来照常喝奶"])
    if "户外" in scene:
        candidates.extend(["出去玩回来照样喝奶", "户外回来那杯奶"])
    if "挑食" in scene or "饭" in scene or "营养不足" in topic:
        candidates.extend(["挑食那阵子还在喝旺玥", "挑食娃的旺玥记录"])
    if "选奶" in scene or "纠结" in topic:
        candidates.extend(["旺玥喝了一阵的反馈", "家里继续喝旺玥"])
    if "注意" in topic or "眼脑" in topic:
        candidates.extend(["上学后继续喝旺玥", "写写画画多了以后的记录"])
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
