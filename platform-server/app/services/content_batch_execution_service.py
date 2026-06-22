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
    sanitize_product_experience_format,
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
MAX_PRODUCT_EXPERIENCE_PHRASE_REWRITE_ROUNDS = 2
HISTORY_SIMILARITY_LOOKBACK_LIMIT = 50
TITLE_GUARD_HISTORY_LOOKBACK_LIMIT = 60
TITLE_GUARD_FORBIDDEN_SUBSTRINGS = (
    "【标题】",
    "这杯",
    "安排上",
    "不用纠结",
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
    "旺玥真实体验分享",
    "旺玥喝了一阵",
    "喝旺玥的日常",
    "真实体验分享",
    "体验分享",
    "真实体验",
    "美和健康，我选了后者",
    "这钱我掏了",
    "选到我心坎里",
)
TITLE_GUARD_BAD_PATTERNS = (
    re.compile(r"(?:我家|孩子|娃).{0,6}(?:快|刚)?[0-9一二三四五六七八九十]+个?月了"),
    re.compile(r"[0-9一二三四五六七八九十]+个月宝宝"),
    re.compile(r"[0-9一二三四五六七八九十]+个月\+?旺玥"),
)
TITLE_GUARD_MARKETING_CLAIM_PATTERNS = (
    re.compile(r"(?:[0-9０-９]+|[一二两三四五六七八九十百]+)[多+＋]?种.{0,8}(?:营养|成分|配方)"),
    re.compile(r"(?:[0-9０-９]+|[一二两三四五六七八九十百]+)[多+＋]?\\+.{0,8}(?:营养|成分|配方)"),
    re.compile(r"(?:[0-9０-９]+|[一二两三四五六七八九十百]+)[多+＋]?种.{0,8}(?:HMO|DHA|OPO|PS|磷脂酰丝氨酸)"),
    re.compile(r"(?:乳铁蛋白|免疫球蛋白|燕窝酸|DHA|HMO|OPO|钙铁锌).{0,10}(?:加持|拉满|守护|担当|天花板|答案|有门道)"),
    re.compile(r"(?:乳铁蛋白|免疫球蛋白|燕窝酸|DHA|HMO|OPO|PS|磷脂酰丝氨酸).{0,8}[+＋].{0,12}(?:乳铁蛋白|免疫球蛋白|燕窝酸|DHA|HMO|OPO|PS|磷脂酰丝氨酸)"),
    re.compile(r"(?:保护力|眼脑|营养|成分|配方).{0,10}(?:加持|拉满|守护|担当|天花板|答案|有门道)"),
    re.compile(r"(?:少跑医院|不跑医院|少去医院|不用跑医院|少请假|不请假|没请假|全勤).{0,10}(?:值|稳|赢|省心|划算)"),
    re.compile(r"(?:没白|不白).{0,10}(?:看成分表|看配料表|做功课|选奶|买|下单)"),
    re.compile(r"(?:真没白|真的没白).{0,12}(?:看|买|选|做)"),
    re.compile(r"(?:成分党|干货|科普|指南|攻略|一篇看懂|不踩坑|闭眼入|抄作业|听劝|种草|头秃)"),
    re.compile(r"(?:救星|神器|神仙奶粉|宝藏奶粉)"),
    re.compile(r"(?:一罐|奶粉|旺玥).{0,8}解决.{0,8}(?:营养|成长|问题)"),
    re.compile(r"营养超全(?:面)?"),
    re.compile(r"(?:挖到|发现|入手).{0,8}(?:营养超全|营养很全|儿童奶粉)"),
    re.compile(r"终于不用再.{0,4}(?:挑|选).{0,4}(?:儿童)?奶粉"),
    re.compile(r"选奶.{0,4}看它"),
    re.compile(r"(?:乳铁蛋白|免疫球蛋白|燕窝酸|DHA|HMO|OPO|PS|磷脂酰丝氨酸|胆碱|叶黄素|钙铁锌)"),
    re.compile(r"(?:智商税|没输过|补给站|选奶实录)"),
)
TITLE_GUARD_AWKWARD_PATTERNS = (
    re.compile(r"(?:请见谅|不恰当|比喻不恰当|欢迎|留言|评论区)"),
    re.compile(r"(?:全面考量|综合考量|深度解析|真实测评|亲测有效|使用心得)"),
    re.compile(r"(?:居然是因为这个|原因找到了|答案来了|秘密在这里)"),
    re.compile(r"(?:也有|也算|也能|也会|都有|还有)最近"),
    re.compile(r"^旺玥$"),
    re.compile(r"(?:开头直接|直接选奶)"),
    re.compile(r"包里.{0,8}(?:这罐|奶粉|旺玥)"),
    re.compile(r"包里.{0,12}(?:装|塞).{0,12}(?:什么|旺玥|奶粉)"),
    re.compile(r"摸.{0,6}罐子"),
    re.compile(r"(?:旺玥|奶粉).{0,8}好在哪"),
    re.compile(r"(?:保护力|眼脑|成长|状态).{0,8}观察$"),
    re.compile(r"第[0-9一二两三四五六七八九十]+个原因"),
    re.compile(r"被(?:奶粉|旺玥).{0,4}拿捏"),
    re.compile(r"(?:救了我|真给力|从内到外)"),
    re.compile(r"我的选择$"),
    re.compile(r"我换了奶粉$"),
    re.compile(r"只看脑子"),
    re.compile(r"每天泡奶"),
    re.compile(r"(?:递给孩子喝|喝一口)"),
    re.compile(r"(?:治住了|功劳吗|挑老公)"),
    re.compile(r"(?:正文里|标题里|文案里|这篇).{0,8}(?:观察|想说|记录)"),
    re.compile(r"观察记录"),
    re.compile(r"开罐.{0,8}湿"),
    re.compile(r"即饮"),
    re.compile(r"(?:眼脑|营养|成分).{0,8}太卷"),
    re.compile(r"主要看.{0,12}(?:保护力|眼脑|营养).{0,12}(?:照顾到|都顾上|都管了)"),
    re.compile(r"一这阵"),
    re.compile(r"一最近"),
    re.compile(r"的话"),
    re.compile(r"记录一下"),
    re.compile(r"开罐记录.{0,8}(?:皇家美素佳儿|旺玥)"),
    re.compile(r"成分.{0,12}心动"),
    re.compile(r"嘴巴严实"),
)
TITLE_MARKETING_CLAIM_TERMS = (
    "保护力",
    "眼脑",
    "营养",
    "成分",
    "配方",
    "乳铁蛋白",
    "免疫球蛋白",
    "HMO",
    "DHA",
    "PS",
    "磷脂酰丝氨酸",
    "燕窝酸",
    "OPO",
    "儿童奶粉",
    "成长奶粉",
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
        await self._rewrite_mouth_phrase_budget_items(batch_id, job)
        await self._repair_article_length_items(batch_id, job)
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

    async def _repair_article_length_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
                .order_by(ContentBatchItem.item_no)
            )
            items = list(result.scalars().all())
            repair_count = 0
            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            for item in items:
                if not item.run_id:
                    continue
                repair = await self._repair_article_length_if_needed(
                    item,
                    orchestrator=orchestrator,
                    run_id=item.run_id,
                )
                if not repair:
                    continue
                quality = dict(item.quality_json or {})
                quality["article_length_guard"] = repair
                item.quality_json = quality
                repair_count += 1
            if repair_count:
                await db.commit()
            return repair_count

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
            candidate_title = title or item.title or ""
            candidate_body = body or item.body or ""
            if should_review_product_experience(item.plan_json):
                product_review = review_product_experience_phrase(
                    title=candidate_title,
                    body=candidate_body,
                    plan=item.plan_json,
                )
                if product_review.rewrite_required:
                    fallback_applied = False
                    if _is_wangyue_growth_nutrition_plan(item.plan_json or {}):
                        fallback_title = item.title or "给孩子选旺玥这事"
                        fallback_body = _fallback_wangyue_growth_nutrition_body(item)
                        fallback_review = review_product_experience_phrase(
                            title=fallback_title,
                            body=fallback_body,
                            plan=item.plan_json,
                        )
                        fallback_chars = _compact_len(fallback_body)
                        if min_chars <= fallback_chars <= max_chars and not fallback_review.rewrite_required:
                            quality = dict(item.quality_json or {})
                            fallbacks = list(quality.get("article_length_product_guard_fallbacks") or [])
                            fallbacks.append(
                                {
                                    "rewrite_round": attempts,
                                    "blocked_review": product_review.model_dump(),
                                    "before": {"title": item.title or "", "body": item.body or ""},
                                    "after": {"title": fallback_title, "body": fallback_body},
                                    "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                                }
                            )
                            quality["article_length_product_guard_fallbacks"] = fallbacks
                            item.quality_json = quality
                            item.title = fallback_title
                            item.body = fallback_body
                            after_chars = fallback_chars
                            self._mark_product_experience_phrase_review(item, fallback_review)
                            fallback_applied = True
                    if fallback_applied:
                        break
                    last_error = "blocked_by_product_experience_phrase_guard"
                    quality = dict(item.quality_json or {})
                    failures = list(quality.get("article_length_repair_failures") or [])
                    failures.append(
                        {
                            "rewrite_round": attempts,
                            "error_message": last_error,
                            "product_experience_phrase_review": product_review.model_dump(),
                            "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                        }
                    )
                    quality["article_length_repair_failures"] = failures
                    item.quality_json = quality
                    break
            if title:
                item.title = title
            if body:
                item.body = body
            after_chars = _compact_len(item.body)
            if should_review_product_experience(item.plan_json):
                self._mark_product_experience_phrase_review(
                    item,
                    review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json),
                )
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

            history_titles = await self._recent_title_norms_for_title_guard(db, job, batch_id)
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

                reasons = _title_guard_reasons(item.title or "", used_titles | history_titles, item)
                if not reasons:
                    used_titles.add(_normalize_title(item.title or ""))
                    continue

                before = item.title or ""
                item.title = _fallback_title_for_item(item, used_titles, history_titles)
                used_titles.add(_normalize_title(item.title or ""))
                quality = dict(item.quality_json or {})
                repairs = list(quality.get("title_guard_repairs") or [])
                repairs.append({"before": before, "after": item.title, "reasons": reasons})
                quality["title_guard_repairs"] = repairs
                quality["title_guard"] = {
                    "pass": True,
                    "repair_count": len(repairs),
                    "history_title_count": len(history_titles),
                }
                item.quality_json = quality
                if should_review_product_experience(item.plan_json):
                    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    self._mark_product_experience_phrase_review(item, review)
                repair_count += 1
            if repair_count:
                await db.commit()
            return repair_count

    async def _recent_title_norms_for_title_guard(
        self,
        db: AsyncSession,
        job: ContentBatchJob,
        batch_id: int,
    ) -> set[str]:
        result = await db.execute(
            select(ContentBatchItem.title)
            .select_from(ContentBatchItem)
            .join(ContentBatchJob, ContentBatchJob.id == ContentBatchItem.batch_id)
            .where(
                ContentBatchItem.batch_id != batch_id,
                ContentBatchItem.status == "generated",
                ContentBatchItem.title.is_not(None),
                ContentBatchJob.asset_key == job.asset_key,
                ContentBatchJob.product_topic == job.product_topic,
            )
            .order_by(ContentBatchItem.id.desc())
            .limit(TITLE_GUARD_HISTORY_LOOKBACK_LIMIT)
        )
        return {
            normalized
            for title in result.scalars().all()
            if (normalized := _normalize_title(str(title or "")))
        }

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
                if "wangyue_growth_nutrition_drift_context" in review.reasons:
                    rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    review = post_review
                    if rewritten:
                        rewrite_count += 1
                    while (
                        "wangyue_growth_nutrition_drift_context" in review.reasons
                        and self._product_experience_phrase_rewrite_rounds(item) < MAX_PRODUCT_EXPERIENCE_PHRASE_REWRITE_ROUNDS
                    ):
                        rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review)
                        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                        review = post_review
                        if not rewritten:
                            break
                        rewrite_count += 1
                    if "wangyue_growth_nutrition_drift_context" in review.reasons:
                        cleaned = self._fallback_clean_wangyue_growth_nutrition_drift(item, review)
                        if cleaned:
                            post_review = review_product_experience_phrase(
                                title=item.title,
                                body=item.body,
                                plan=item.plan_json,
                            )
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
                    if "child_self_brewing_formula" in review.reasons:
                        before = {"title": item.title or "", "body": item.body or ""}
                        item.title = sanitize_baby_milk_action_phrases(item.title)
                        item.body = sanitize_baby_milk_action_phrases(item.body)
                        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                        quality = dict(item.quality_json or {})
                        cleanups = list(quality.get("product_experience_child_self_brewing_cleanups") or [])
                        cleanups.append(
                            {
                                "before": before,
                                "after": {"title": item.title or "", "body": item.body or ""},
                                "pre_review": review.model_dump(),
                                "post_review": post_review.model_dump(),
                            }
                        )
                        quality["product_experience_child_self_brewing_cleanups"] = cleanups
                        item.quality_json = quality
                        review = post_review
                        rewrite_count += 1
                if "wangyue_row2_drinking_action_context" in review.reasons:
                    rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    review = post_review
                    if rewritten:
                        rewrite_count += 1
                    while (
                        "wangyue_row2_drinking_action_context" in review.reasons
                        and self._product_experience_phrase_rewrite_rounds(item) < MAX_PRODUCT_EXPERIENCE_PHRASE_REWRITE_ROUNDS
                    ):
                        rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review)
                        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                        review = post_review
                        if not rewritten:
                            break
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
                    or "wangyue_digestive_effect_context" in review.reasons
                    or "wangyue_article_logic_drift_context" in review.reasons
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
                formatted_title = sanitize_product_experience_format(item.title)
                formatted_body = sanitize_product_experience_format(item.body)
                if formatted_title != (item.title or "") or formatted_body != (item.body or ""):
                    before = {"title": item.title or "", "body": item.body or ""}
                    item.title = formatted_title
                    item.body = formatted_body
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    quality = dict(item.quality_json or {})
                    cleanups = list(quality.get("product_experience_format_cleanups") or [])
                    cleanups.append(
                        {
                            "before": before,
                            "after": {"title": item.title or "", "body": item.body or ""},
                            "pre_review": review.model_dump(),
                            "post_review": post_review.model_dump(),
                        }
                    )
                    quality["product_experience_format_cleanups"] = cleanups
                    item.quality_json = quality
                    review = post_review
                    rewrite_count += 1
                if "long_unpunctuated_body_segment" in review.reasons:
                    rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review)
                    post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    review = post_review
                    if rewritten:
                        rewrite_count += 1
                self._mark_product_experience_phrase_review(item, review)
            if items:
                await db.commit()
            return rewrite_count

    async def _rewrite_mouth_phrase_budget_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
                .order_by(ContentBatchItem.item_no)
            )
            items = list(result.scalars().all())
            rewrite_count = 0
            for item in items:
                initial_hits = _mouth_phrase_budget_hits(item)
                if not initial_hits:
                    self._mark_mouth_phrase_budget_guard(item, initial_hits=[], final_hits=[])
                    continue
                hits = initial_hits
                for _ in range(2):
                    if not hits:
                        break
                    rewritten = await self._rewrite_item_for_mouth_phrase_budget(db, item, hits)
                    if not rewritten:
                        break
                    rewrite_count += 1
                    hits = _mouth_phrase_budget_hits(item)
                final_hits = _mouth_phrase_budget_hits(item)
                self._mark_mouth_phrase_budget_guard(
                    item,
                    initial_hits=initial_hits,
                    final_hits=final_hits,
                )
            if items:
                await db.commit()
            return rewrite_count

    async def _rewrite_item_for_mouth_phrase_budget(
        self,
        db: AsyncSession,
        item: ContentBatchItem,
        hits: list[str],
    ) -> bool:
        if not item.run_id or not item.body or not hits:
            return False
        orchestrator = ContentAgentOrchestrator(
            db,
            invocation_client=self.invocation_client,
            callback_base_url=self.callback_base_url,
        )
        try:
            input_payload = _mouth_phrase_budget_rewrite_input(item, hits)
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
            before = {"title": item.title or "", "body": item.body or ""}
            product_review = review_product_experience_phrase(title=title, body=body, plan=item.plan_json)
            if product_review.rewrite_required:
                quality = dict(item.quality_json or {})
                failures = list(quality.get("mouth_phrase_budget_rewrite_failures") or [])
                failures.append(
                    {
                        "initial_hits": hits,
                        "error_message": "blocked_by_product_experience_phrase_guard",
                        "product_experience_phrase_review": product_review.model_dump(),
                        "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                    }
                )
                quality["mouth_phrase_budget_rewrite_failures"] = failures
                quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + len(result.stage_calls)
                quality["run_status"] = result.run.status
                item.quality_json = quality
                await db.flush()
                return False
            item.title = title
            item.body = body
            final_hits = _mouth_phrase_budget_hits(item)
            quality = dict(item.quality_json or {})
            rewrites = list(quality.get("mouth_phrase_budget_rewrites") or [])
            rewrites.append(
                {
                    "before": before,
                    "after": {"title": item.title or "", "body": item.body or ""},
                    "initial_hits": hits,
                    "final_hits": final_hits,
                    "passed": not final_hits,
                    "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                }
            )
            quality["mouth_phrase_budget_rewrites"] = rewrites
            quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + len(result.stage_calls)
            quality["run_status"] = result.run.status
            item.quality_json = quality
            self._mark_product_experience_phrase_review(item, product_review)
            item.error_message = None
            await db.flush()
            return True
        except Exception as exc:  # pragma: no cover - defensive path for flaky external workers
            quality = dict(item.quality_json or {})
            failures = list(quality.get("mouth_phrase_budget_rewrite_failures") or [])
            failures.append({"initial_hits": hits, "error_message": str(exc)})
            quality["mouth_phrase_budget_rewrite_failures"] = failures
            item.quality_json = quality
            await db.flush()
            return False

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
        title_text = item.title or ""
        title_guard_hits = [
            hit
            for hit in (
                review.wangyue_row2_drinking_action_hits
                + review.child_self_brewing_hits
                + review.wangyue_article_logic_drift_hits
                + review.wangyue_growth_nutrition_drift_hits
                + review.odd_phrase_hits
                + review.malformed_fragment_hits
            )
            if hit and hit in title_text
        ]
        title_instruction = (
            "本轮标题也命中问题表达："
            f"{'/'.join(title_guard_hits)}。标题必须同步改掉这些词，改成普通真人标题，不要保留奶粉罐、囤货、冲泡或补给动作。"
            if title_guard_hits
            else "标题尽量不改；如果正文改写导致标题明显不顺，再做轻微调整。"
        )
        has_growth_nutrition_drift = bool(review.wangyue_growth_nutrition_drift_hits)
        if hit_summary:
            phrase_instruction = (
                f"本轮命中的口癖骨架是 {hit_summary}；至少删掉其中两个维度，尤其别把购买判断、价格、孩子接受、安心收口连在一起。"
            )
        elif has_growth_nutrition_drift:
            phrase_instruction = (
                "本轮是旺玥营养/成长规则漂移，只处理偏离业务内核的内容；不要为了改写新增购买过程、喝奶动作或妈妈总结。"
            )
        else:
            phrase_instruction = "如果没有完整口癖骨架，只处理本轮命中的长度或 AI 收口问题；长度是硬性验收，必须先满足字数范围。"
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
        row2_drinking_action_instruction = (
            "本轮命中旺玥 row2 的喝奶动作/补给路径残留："
            f"{'/'.join(review.wangyue_row2_drinking_action_hits)}。"
            "这条规则重点是孩子活动量大时，妈妈为什么选择皇家美素佳儿旺玥儿童奶粉；"
            "硬性验收：改写后的 title/body 不能再出现这些命中词，也不要换成同类的当早餐喝、放学先喝一杯、常备着、包里翻出来、翻出奶粉罐。"
            "请局部改顺命中的半句及相邻补给短句，把冲泡、每天几杯、孩子愿意喝、家里备着/常喝/囤货、放桌上自己倒这类路径删掉或改成选择理由/普通观察；"
            "如果不知道怎么接，就删掉命中词所在的后半句，保留前面的生活观察和旺玥选择理由。"
            "不要新增接娃放学模板、不要新增公园疯跑模板、不要把全文改成导购。"
            if review.wangyue_row2_drinking_action_hits
            else "旺玥 row2 不要把正文推进到冲泡、每天几杯、孩子愿意喝、活动后立刻补给；只把旺玥当儿童奶粉选择背景轻带。"
        )
        run_on_instruction = (
            "本轮正文出现很长的无标点口语串，像把多个示例碎片硬粘在一起："
            f"{'/'.join(review.run_on_fragment_hits)}。"
            "只做断句和删减，把照抄示例口气碎片删掉或改顺；不要新增卖点、不要扩写新剧情。"
            if review.run_on_fragment_hits
            else "正文保持自然断句，不要把多个示例口气碎片粘成一长串。"
        )
        malformed_fragment_instruction = (
            "本轮正文有半截引号或断裂句："
            f"{'/'.join(review.malformed_fragment_hits)}。"
            "只把断掉的对话改顺或删掉半截，不要新增新剧情、不要扩写卖点。"
            if review.malformed_fragment_hits
            else "正文不要出现半截引号、断掉的对话或读不通的残句。"
        )
        growth_nutrition_drift_instruction = (
            "本轮命中旺玥营养/成长规则漂移："
            f"{'/'.join(review.wangyue_growth_nutrition_drift_hits)}。"
            "请保留核心：给孩子选择皇家美素佳儿旺玥儿童奶粉，是为了补充营养、支持成长。"
            "硬性验收：改写后的 title/body 不能再出现这些命中词，也不能换成同类的喝完、好喝、主动提醒泡、精神好、状态不错、蹦蹦跳跳。"
            "去掉吃饭饭量、挑食、三餐补救、身高体重证明、固定喝奶动作、孩子自己喝/冲泡、选对了/一步搞定这类收口。"
            "改成自然短帖，正文40-130字，标题另写，正文一段不换行。"
            if has_growth_nutrition_drift
            else "如果写到营养/成长，保持在选择儿童奶粉的理由上，不展开饭量、身高体重证明或固定喝奶动作。"
        )
        wangyue_logic_drift_instruction = (
            "本轮命中旺玥帖子方向跑偏内容："
            f"{'/'.join(review.wangyue_article_logic_drift_hits)}。"
            "这些不是通用禁词，但会把帖子带成购买渠道、囤货、冲泡口感、眼脑具体效果或效果证明。"
            "硬性验收：改写后的 title/body 不能再出现这些命中词；"
            "直接删除对应半句，必要时用原业务规则里的卖点白话补一个很短连接，不要新增同类词如口粮、购物车、下单、护眼、眼睛、绘本、画画、脸色亮、奶香、不结块。"
            if review.wangyue_article_logic_drift_hits
            else "旺玥正文不要写成购买渠道、囤货、冲泡口感或效果证明；产品只作为儿童奶粉选择出现。"
        )
        wangyue_product_mention_instruction = (
            "本轮旺玥正文缺少产品名；只自然补一次“皇家美素佳儿旺玥”或“旺玥儿童奶粉”，不要因此扩写成导购或卖点清单。"
            if "wangyue_missing_product_mention" in review.reasons
            else "旺玥文章里产品名至少自然出现一次，避免只用“它/这款/里面”承接卖点。"
        )
        retry_instruction = (
            "这是同一条内容的再次改写：上一轮仍残留 row4 偏题表达。不要同义替换命中词，直接删掉偏题半句；"
            "正文只保留“选择旺玥儿童奶粉来补充成长阶段营养、支持成长”的自然表达。"
            if has_growth_nutrition_drift and self._product_experience_phrase_rewrite_rounds(item) > 0
            else (
                "这是同一条内容的再次改写：上一轮仍残留 row2 喝奶动作/补给路径。不要同义替换命中词，直接删掉命中词所在的后半句，保留生活观察和选择旺玥儿童奶粉的理由。"
                if review.wangyue_row2_drinking_action_hits
                and self._product_experience_phrase_rewrite_rounds(item) > 0
                else "如果本轮是首次改写，优先改顺，不要过度扩写。"
            )
        )
        skeleton_redirect_instruction = (
            "如果正文已经有购买过程、价格和孩子接受度，只保留其中一个观察点，其他改成放学、户外、换衣服、书包、妈妈观察这类生活细节；不要新增剩奶、杯子放置或冲泡奶保存动作。"
            if not has_growth_nutrition_drift
            else "本轮不要把问题内容改成放学、户外、书包、杯子放置或冲泡保存动作；只回到“儿童奶粉选择旺玥补充营养、支持成长”这个内核。"
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
                length_instruction or "正文长度服从业务规则，正文单段不换行。",
                title_instruction,
                phrase_instruction,
                ai_phrase_instruction,
                adult_self_drinking_instruction,
                child_self_brewing_instruction,
                row2_drinking_action_instruction,
                run_on_instruction,
                malformed_fragment_instruction,
                growth_nutrition_drift_instruction,
                wangyue_logic_drift_instruction,
                wangyue_product_mention_instruction,
                retry_instruction,
                "rewrite 优先删除问题内容或压缩问题句；不要为了多样化整段重写。只有删除后语义断裂时，才补极短连接。",
                skeleton_redirect_instruction,
                "不要用“省心、踏实、固定下来、心里有数、先这样”作为统一收口。",
                "长个、少请假、不生病、保护力、坐不住这类真人强表达可以保留为观察或别人问，不能写成确定因果。",
                "正文单段不换行；不要写成导购或品牌介绍。",
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

    def _fallback_clean_wangyue_growth_nutrition_drift(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> bool:
        hits = review.wangyue_growth_nutrition_drift_hits
        if not hits:
            return False
        before = {"title": item.title or "", "body": item.body or ""}
        title = _strip_growth_nutrition_drift_segments(item.title or "", hits)
        body = _strip_growth_nutrition_drift_segments(item.body or "", hits)
        if _compact_len(body) < 40:
            body = _fallback_wangyue_growth_nutrition_body(item)
        if not title:
            title = "给孩子选旺玥这事"
        if title == (item.title or "") and body == (item.body or ""):
            return False
        item.title = title
        item.body = body
        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
        quality = dict(item.quality_json or {})
        cleanups = list(quality.get("product_experience_growth_nutrition_fallback_cleanups") or [])
        cleanups.append(
            {
                "before": before,
                "after": {"title": item.title or "", "body": item.body or ""},
                "pre_review": review.model_dump(),
                "post_review": post_review.model_dump(),
            }
        )
        quality["product_experience_growth_nutrition_fallback_cleanups"] = cleanups
        item.quality_json = quality
        return True

    def _mark_mouth_phrase_budget_guard(
        self,
        item: ContentBatchItem,
        *,
        initial_hits: list[str],
        final_hits: list[str],
    ) -> None:
        quality = dict(item.quality_json or {})
        guard_payload = {
            "pass": not final_hits,
            "initial_hits": initial_hits,
            "final_hits": final_hits,
            "rewrite_required": bool(final_hits),
        }
        quality["mouth_phrase_budget_guard"] = guard_payload
        review_report = dict(quality.get("review_report") or {})
        review_report["mouth_phrase_budget_guard"] = guard_payload
        if final_hits:
            review_report["rewrite_required"] = True
            review_report["rewrite_reason"] = "批量口癖预算仍有未清理命中"
        elif review_report.get("rewrite_reason") == "批量口癖预算仍有未清理命中":
            review_report["rewrite_required"] = False
            review_report.pop("rewrite_reason", None)
        quality["hard_pass"] = bool(quality.get("hard_pass", True)) and not final_hits
        quality["review_report"] = review_report
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
    explicit = re.search(r"正文\s*(\d{2,3})\s*[-~—到至]\s*(\d{2,3})\s*字", corpus)
    if explicit:
        min_chars, max_chars = int(explicit.group(1)), int(explicit.group(2))
        if min_chars < max_chars:
            return "自定义", min_chars, max_chars
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
            f"rewrite 优先删除问题内容，不做多样化扩写；短文偏短时补到{min_chars}字以上即可，不要扩成中长文。",
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


def _mouth_phrase_budget_hits(item: ContentBatchItem) -> list[str]:
    avoid_terms = _mouth_phrase_budget_avoid_terms(item)
    text = f"{item.title or ''}\n{item.body or ''}"
    for allowed_term in _mouth_phrase_budget_allowed_terms(item):
        if allowed_term:
            text = text.replace(allowed_term, "")
    return [term for term in avoid_terms if term and term in text]


def _mouth_phrase_budget_rewrite_input(item: ContentBatchItem, hits: list[str]) -> dict[str, Any]:
    unified_generation = (item.plan_json or {}).get("unified_generation") or {}
    hit_text = "、".join(hits)
    avoid_terms = _mouth_phrase_budget_avoid_terms(item)
    avoid_text = "、".join(avoid_terms)
    return {
        "previous_content": {"title": item.title or "", "body": item.body or ""},
        "content_type": "article",
        "output_fields": ["title", "body"],
        "business_rule": rewrite_business_rule_context(item.plan_json),
        "selected_keywords": unified_generation.get("selected_keywords") or [],
        "model_config": dict((item.plan_json or {}).get("model_config") or {}),
        "rewrite_source": "mouth_phrase_budget_guard",
        "review_report": {
            "rewrite_required": True,
            "rewrite_reason": "本篇使用了未分配的批量高频口癖",
            "mouth_phrase_budget_hits": hits,
        },
        "rewrite_instructions": [
            f"只处理这些本篇未分配的批量高频口癖：{hit_text}。",
            f"硬性验收：改写后的 title/body 里不能再出现这些完整字符串：{hit_text}。",
            "优先把含口癖的收尾半句或整句删掉；只有删掉后句子断裂时，才改成具体动作、具体观察。",
            "如果命中“ 不用 ”或“不用”，删除包含“不用再……”的短句，不要保留“不用再纠结/不用操心/不用搭配”这类结构。",
            f"也不要把它们换成其他本篇未分配口癖：{avoid_text}。",
            "不要补新的妈妈总结套话，例如少操心、少纠结、定心、心里有数、选对了、没白挑。",
            "不要把时间口癖改成换季、春天、夏天、秋天、冬天、开学、放假、学期、寒假、暑假这类明确时间节点。",
            "不要为了多样化扩写，不要新增卖点、场景、时间、功效结论或新事实。",
            "优先保持原文逻辑、字数和真人口气；必要时只补一个很短的连接词。",
            "标题尽量不改；如果标题命中这些词，就换成更具体的生活记录式标题。",
            "只输出 JSON：title, body。",
        ],
    }


def _mouth_phrase_budget_avoid_terms(item: ContentBatchItem) -> list[str]:
    plan = item.plan_json if isinstance(item.plan_json, dict) else {}
    budget = plan.get("mouth_phrase_budget") if isinstance(plan.get("mouth_phrase_budget"), dict) else {}
    if budget.get("enabled") is not True:
        return []
    allowed_terms = set(_string_list(budget.get("allowed_terms")))
    return [term for term in _string_list(budget.get("avoid_terms")) if term not in allowed_terms]


def _mouth_phrase_budget_allowed_terms(item: ContentBatchItem) -> list[str]:
    plan = item.plan_json if isinstance(item.plan_json, dict) else {}
    budget = plan.get("mouth_phrase_budget") if isinstance(plan.get("mouth_phrase_budget"), dict) else {}
    if budget.get("enabled") is not True:
        return []
    return sorted(_string_list(budget.get("allowed_terms")), key=len, reverse=True)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _compact_len(value: str | None) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def _should_apply_title_guard(job: ContentBatchJob, items: list[ContentBatchItem]) -> bool:
    if "wangyue" in (job.asset_key or "").lower() or "旺玥" in (job.product_topic or ""):
        return True
    return any("0705旺玥活动" in str((item.plan_json or {}).get("corpus") or "") for item in items)


def _title_guard_reasons(title: str, used_titles: set[str], item: ContentBatchItem | None = None) -> list[str]:
    reasons: list[str] = []
    normalized = _normalize_title(title)
    if normalized and normalized in used_titles:
        reasons.append("duplicate_title")
    reference_titles = _title_reference_norms(item)
    if normalized and normalized in reference_titles:
        reasons.append("copied_reference_title")
    if _sanitize_generated_title_format(title) != title:
        reasons.append("generated_title_format")
    for phrase in TITLE_GUARD_FORBIDDEN_SUBSTRINGS:
        if phrase in title:
            reasons.append(f"forbidden_title_phrase:{phrase}")
    for pattern in TITLE_GUARD_BAD_PATTERNS:
        if pattern.search(title):
            reasons.append("ambiguous_age_or_duration")
            break
    if _is_marketing_claim_title(title):
        reasons.append("marketing_claim_title_pattern")
    if _is_awkward_title(title):
        reasons.append("awkward_title_pattern")
    if _is_low_natural_title_score(title):
        reasons.append("low_natural_title_score")
    return reasons


def _is_awkward_title(title: str) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    if any(pattern.search(text) for pattern in TITLE_GUARD_AWKWARD_PATTERNS):
        return True
    if _compact_len(text) >= 20 and not any(mark in text for mark in ("？", "?", "！", "!")):
        return True
    return False


def _is_marketing_claim_title(title: str) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    if any(pattern.search(text) for pattern in TITLE_GUARD_MARKETING_CLAIM_PATTERNS):
        return True
    term_hits = [term for term in TITLE_MARKETING_CLAIM_TERMS if term in text]
    compact_len = _compact_len(text)
    question_count = text.count("？") + text.count("?")
    if compact_len >= 24 and len(term_hits) >= 2:
        return True
    if question_count >= 2 and term_hits:
        return True
    if any(phrase in text for phrase in ("翻遍成分表", "看遍成分表", "翻遍配料表")) and any(
        term in text for term in ("放心", "值", "省心", "踏实")
    ):
        return True
    return False


TITLE_NATURAL_POSITIVE_TERMS = (
    "幼儿园",
    "上学",
    "放学",
    "吃饭",
    "绿叶菜",
    "公园",
    "户外",
    "翻账单",
    "咳嗽",
    "流鼻涕",
    "中招",
    "请假",
    "肉疼",
    "头大",
    "纠结",
    "谁懂",
)
TITLE_NATURAL_PERSONAL_TERMS = ("我", "娃", "孩子", "童童", "当妈")
TITLE_PRODUCTIZED_TERMS = (
    "皇家美素佳儿",
    "旺玥",
    "儿童奶粉",
    "成长奶粉",
    "奶粉",
    "保护力",
    "眼脑",
    "营养",
    "成分",
    "配方",
    "一罐搞定",
    "到位",
    "全面",
    "照顾到",
    "照顾到了",
    "支持",
)


def _title_naturalness_score(title: str) -> int:
    text = str(title or "").strip()
    if not text:
        return -99
    compact_len = _compact_len(text)
    score = 0
    if 6 <= compact_len <= 14:
        score += 2
    elif 15 <= compact_len <= 18:
        score += 1
    elif compact_len > 18:
        score -= 1
    if any(mark in text for mark in ("？", "?", "吗", "有没有", "谁懂", "怎么")):
        score += 2
    if any(term in text for term in TITLE_NATURAL_POSITIVE_TERMS):
        score += 2
    if any(term in text for term in TITLE_NATURAL_PERSONAL_TERMS):
        score += 1
    if any(term in text for term in ("啊", "吧", "呀", "有点", "还是", "真的")):
        score += 1
    if any(term in text for term in ("皇家美素佳儿", "儿童奶粉", "成长奶粉", "奶粉")):
        score -= 1
    if any(term in text for term in ("旺玥",)):
        score -= 1
    if any(term in text for term in ("保护力", "眼脑", "营养", "成分", "配方", "到位", "全面", "照顾到", "照顾到了", "支持")):
        score -= 2
    if any(term in text for term in ("一罐搞定", "搞定", "最稳", "放心", "实在", "值了")):
        score -= 1
    return score


def _is_low_natural_title_score(title: str) -> bool:
    text = str(title or "").strip()
    if not text:
        return True
    if not any(term in text for term in TITLE_PRODUCTIZED_TERMS):
        return False
    return _title_naturalness_score(text) <= -2


def _sanitize_generated_title_format(title: str | None) -> str:
    text = str(title or "").strip()
    if not text:
        return text
    for pattern in TITLE_FORMAT_PATTERNS:
        text = pattern.sub("", text).strip()
    text = EMOJI_PATTERN.sub("", text).strip()
    text = re.sub(r"[\u200d\ufe0f]", "", text).strip()
    text = re.sub(r"^\s*(?:标题|title)[:：]\s*", "", text, flags=re.IGNORECASE).strip()
    text = text.strip(" *_`~#")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fallback_title_for_item(
    item: ContentBatchItem,
    used_titles: set[str],
    history_titles: set[str] | None = None,
) -> str:
    plan = item.plan_json or {}
    corpus = str(plan.get("corpus") or "")
    scene = _corpus_field(corpus, "场景")
    topic = str(plan.get("topic") or plan.get("business_rule") or "")
    duration = str(_corpus_field(corpus, "喝旺玥时间"))
    duration_label = _duration_title_label(duration)
    candidate_groups = _title_candidate_groups(
        scene=scene,
        topic=topic,
        body=item.body or "",
        duration_label=duration_label,
        synthetic_titles=_string_list(plan.get("synthetic_title_examples")),
    )
    history_titles = history_titles or set()
    for candidates, title_pool in (
        (candidate_groups, used_titles | history_titles),
        (candidate_groups, used_titles),
    ):
        for group in candidates:
            for candidate in _rank_title_candidates(group, item):
                if not _title_guard_reasons(candidate, title_pool, item):
                    return candidate
    return "这罐旺玥先记两句"


def _rank_title_candidates(candidates: list[str], item: ContentBatchItem) -> list[str]:
    if not candidates:
        return []
    start = ((item.id or 0) + max((item.item_no or 1) - 1, 0)) % len(candidates)
    indexed = list(enumerate(candidates))
    return [
        candidate
        for index, candidate in sorted(
            indexed,
            key=lambda pair: (
                -_title_naturalness_score(pair[1]),
                (pair[0] - start) % len(candidates),
                pair[0],
            ),
        )
    ]


def _title_candidate_groups(
    *,
    scene: str,
    topic: str,
    body: str,
    duration_label: str,
    synthetic_titles: list[str] | None = None,
) -> list[list[str]]:
    body_candidates = _body_title_candidates(body)
    candidates: list[str] = []
    candidates.extend([
        "挑奶粉挑到眼花",
        "给娃挑奶粉太难了",
        "儿童奶粉挑到最后",
        "做功课做到头疼",
        "这次奶粉没白挑",
        "这罐旺玥先记一笔",
        "我家那罐旺玥",
        "旺玥这罐先记一下",
        "开罐后先记两句",
        "这罐奶粉有点意外",
        "又开一罐儿童奶粉",
        "这次先不换了",
        "奶粉这钱真省不了",
        "有点肉疼但还行",
    ])
    if any(phrase in body for phrase in ["少请假", "中招", "保护力", "小病小痛", "流鼻涕", "咳嗽"]):
        candidates.extend(["接触多了才认真看奶粉", "这罐奶粉先不乱换"])
    if any(phrase in body for phrase in ["户外", "出去玩", "疯跑", "活动量", "跑跳"]):
        candidates.extend(["出去玩多了以后", "活动量大以后才懂", "疯跑回来也要记一笔"])
    if any(phrase in body for phrase in ["写写画画", "绘本", "眼脑", "DHA", "看书"]):
        candidates.extend(["写写画画多了以后", "眼脑营养这块我开始看了", "看成分看到眼晕"])
    if any(phrase in body for phrase in ["挑食", "吃饭", "绿叶菜", "追着喂", "营养不够"]):
        candidates.extend(["挑食这事先记一下", "吃饭这事真会反复", "营养补充这块我认了"])
    if "幼儿园" in scene or "集体" in scene:
        candidates.extend(["上幼儿园后才认真看奶粉", "集体生活以后才懂"])
    if "户外" in scene:
        candidates.extend(["出去玩多了以后", "户外回来照样吃喝"])
    if "挑食" in scene or "饭" in scene or "营养不足" in topic:
        candidates.extend(["挑食这事先记录一下", "吃饭这事真会反复"])
    if "选奶" in scene or "纠结" in topic:
        candidates.extend(["选奶粉选到头大", "挑来挑去先这样"])
    if "注意" in topic or "眼脑" in topic:
        candidates.extend(["写写画画多了以后", "看成分看到眼晕"])
    candidates.extend([*(synthetic_titles or [])])
    groups = [_dedupe_titles(body_candidates), _dedupe_titles(candidates)]
    return [group for group in groups if group]


def _body_title_candidates(body: str) -> list[str]:
    candidates: list[str] = []
    for raw in re.split(r"[。！？!?；;\n]", body or ""):
        text = raw.strip(" ，,。；;：:")
        if not text:
            continue
        clauses = [part.strip(" ，,。；;：:") for part in re.split(r"[，,]", text) if part.strip(" ，,。；;：:")]
        for clause in [*clauses, text]:
            compact = re.sub(r"\s+", "", clause)
            if not 6 <= len(compact) <= 18:
                continue
            if any(phrase in compact for phrase in TITLE_GUARD_FORBIDDEN_SUBSTRINGS):
                continue
            if _is_bad_body_title_candidate(compact):
                continue
            if _is_marketing_claim_title(compact) or _is_awkward_title(compact):
                continue
            candidates.append(compact)
            if len(candidates) >= 12:
                return candidates
    return candidates


def _strip_growth_nutrition_drift_segments(value: str, hits: list[str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    extra_bad_phrases = (
        "关键点都覆盖",
        "关键点都挺到位",
        "该有的都有",
        "都管到",
        "都覆盖",
        "挺合适",
        "挺对路",
        "专业",
        "发育期",
        "日常冲",
        "冲奶",
        "喝着",
    )
    blocked = tuple(hit for hit in hits if hit) + extra_bad_phrases
    kept_sentences: list[str] = []
    for sentence in re.split(r"[。！？!?；;\n]", text):
        sentence = sentence.strip(" ，,。；;：:")
        if not sentence:
            continue
        clauses = [part.strip(" ，,。；;：:") for part in re.split(r"[，,]", sentence) if part.strip(" ，,。；;：:")]
        kept_clauses = [clause for clause in clauses if not any(phrase in clause for phrase in blocked)]
        if kept_clauses:
            kept_sentences.append("，".join(kept_clauses))
    return "。".join(kept_sentences).strip(" ，,。；;")


def _fallback_wangyue_growth_nutrition_body(item: ContentBatchItem) -> str:
    route_prompt = _fallback_wangyue_growth_nutrition_route_prompt(item)
    if route_prompt:
        return _join_growth_nutrition_fallback(route_prompt, item)
    variants = (
        "给孩子选皇家美素佳儿旺玥儿童奶粉，想法挺简单，日常营养这块认真一点，先这样记着。",
        "我给孩子定旺玥，主要是想把日常营养这件事先顾上，不想来回换来换去，就先这么定了。",
        "儿童奶粉最后选旺玥，是觉得这罐更适合家里现在的想法，先放着观察，别急着下结论。我先记着。",
        "旺玥先放进家里的选择里，别的先不夸太满，日常营养这块先顾住，后面有变化再看。我先记着。",
        "给孩子看儿童奶粉看了一圈，旺玥这罐先记下来，后面有变化再补，不写得太满。这条先留着。",
        "选旺玥不是想写攻略，就是把这次选择简单记一笔，营养这块先别悬着，其他慢慢看。这条先留着。",
    )
    try:
        index = (int(item.item_no or 1) - 1) % len(variants)
    except (TypeError, ValueError):
        index = 0
    return variants[index]


def _join_growth_nutrition_fallback(route_prompt: str, item: ContentBatchItem) -> str:
    endings = (
        "我选旺玥，主要就是想把孩子日常营养这块认真顾上。",
        "旺玥先放进家里的儿童奶粉选择里，图的是营养补充这件事少点乱。",
        "说到底就是给孩子补日常营养、支持成长，别的先不夸太满。",
        "这罐先记下来，至少补营养这个方向和我想的一致。",
        "我没有研究得很复杂，就是觉得它适合拿来做日常营养补充。",
        "后面再慢慢看，先把儿童奶粉这件事定得简单一点。",
    )
    try:
        index = (int(item.item_no or 1) - 1) % len(endings)
    except (TypeError, ValueError):
        index = 0
    return f"{route_prompt}{endings[index]}"


def _fallback_wangyue_growth_nutrition_route_prompt(item: ContentBatchItem) -> str:
    plan = item.plan_json or {}
    if not isinstance(plan, dict):
        return ""
    pool = plan.get("real_user_pool")
    if not isinstance(pool, dict):
        return ""
    prompt_text_by_layer = pool.get("prompt_text_by_layer")
    if not isinstance(prompt_text_by_layer, dict):
        return ""
    routes = prompt_text_by_layer.get("route")
    if not isinstance(routes, list):
        return ""
    for route in routes:
        text = str(route or "").strip(" \t，,。；;")
        if 8 <= _compact_len(text) <= 80:
            return text + "。"
    return ""


def _is_wangyue_growth_nutrition_plan(plan: dict[str, Any]) -> bool:
    if not isinstance(plan, dict):
        return False
    plan_text = "\n".join(
        str(plan.get(key) or "")
        for key in ("asset_key", "business_rule", "topic", "corpus", "rule_name")
    )
    if "旺玥" not in plan_text and not str(plan.get("asset_key") or "").startswith("wangyue_"):
        return False
    try:
        if plan.get("source_row_no") is not None and int(plan.get("source_row_no")) == 4:
            return True
    except (TypeError, ValueError):
        pass
    return (
        "营养不足/成长发育需求" in plan_text
        or ("营养不足" in plan_text and "成长发育需求" in plan_text)
        or ("补充营养" in plan_text and "支持成长" in plan_text)
    )


def _is_bad_body_title_candidate(text: str) -> bool:
    if not text:
        return True
    if text.endswith(("的话", "就看它", "就选它")):
        return True
    if text.startswith(("可以", "建议", "推荐", "我会先")):
        return True
    if any(phrase in text for phrase in ("罐身", "粉质", "不结块", "冲起来", "装备", "泡奶")):
        return True
    if any(phrase in text for phrase in ("HMO", "DHA", "OPO", "PS", "磷脂酰丝氨酸", "乳铁蛋白", "免疫球蛋白", "胆碱", "叶黄素", "钙铁锌")):
        return True
    return False


def _dedupe_titles(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for candidate in candidates:
        normalized = _normalize_title(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(candidate)
    return deduped


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


def _title_reference_norms(item: ContentBatchItem | None) -> set[str]:
    if item is None or not isinstance(item.plan_json, dict):
        return set()
    source = item.plan_json.get("title_reference_all_examples") or item.plan_json.get("title_reference_examples") or []
    return {
        _normalize_title(str(title or ""))
        for title in source
        if str(title or "").strip()
    }
