"""Execute planned MAGA content batch items through the content-agent chain."""
from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.schemas.content_agent import ContentAgentTaskCreate
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_rewrite_context import rewrite_business_rule_context
from app.services.executor_invocation_service import ExecutorInvocationClient
from app.services.activity_quality_guard_service import ActivityQualityGuardService
from app.services.ai_flavor_humanizer_service import AIFlavorReview, review_ai_flavor
from app.services.forbidden_term_review_service import (
    WANGYUE_STATIC_FORBIDDEN_TERMS,
    ForbiddenTermReviewService,
    find_forbidden_hits,
)
from app.services.product_experience_phrase_guard_service import (
    ProductExperiencePhraseReview,
    SEMANTIC_ODD_PRODUCT_EXPERIENCE_PHRASES,
    review_product_experience_phrase,
    sanitize_adult_self_drinking_phrases,
    sanitize_baby_milk_action_phrases,
    sanitize_common_ai_closure,
    sanitize_formula_dry_powder_ingestion,
    sanitize_odd_product_experience_phrases,
    sanitize_product_experience_format,
    sanitize_temporal_context,
    sanitize_wangyue_context_phrases,
    sanitize_wangyue_formula_usage_form,
    sanitize_wangyue_time_event_context,
    should_review_product_experience,
)
from app.services.product_experience_llm_review_service import (
    ProductExperienceLLMIssue,
    ProductExperienceLLMReview,
    ProductExperienceLLMReviewService,
)
from app.services.royal_friso_ugc_structure_guard_service import (
    RoyalFrisoUGCStructureGuardService,
    RoyalFrisoUGCStructureReview,
)
from app.services.rewrite_quality_validator_service import (
    REWRITE_QUALITY_MODEL_CODE,
    RewriteQualityJudgment,
    RewriteQualityValidatorService,
)
from app.services.unified_content_generation_service import (
    CONTENT_GENERATE_CAPABILITY,
    UnifiedContentGenerationService,
)
from app.services.wangyue_claim_public_disease_judge_service import (
    CLAIM_PUBLIC_DISEASE_MODEL_CODE,
    WangyueClaimPublicDiseaseJudgeService,
)
from app.services.wangyue_content_fit_judge_service import (
    CONTENT_FIT_MODEL_CODE,
    WangyueContentFitJudgeService,
)
from app.services.wangyue_fluency_judge_service import (
    FLUENCY_JUDGE_MODEL_CODE,
    WangyueFluencyJudgeService,
)
from app.services.wangyue_focused_review_aggregator_service import (
    FOCUSED_REVIEW_DIMENSIONS,
    aggregate_wangyue_focused_reviews,
    compare_focused_review_with_legacy,
)
from app.services.wangyue_temporal_logic_judge_service import (
    TEMPORAL_LOGIC_MODEL_CODE,
    WangyueTemporalLogicJudgeService,
)

SIMILARITY_REWRITE_THRESHOLD = 0.42
HISTORY_SIMILARITY_REWRITE_THRESHOLD = 0.48
MAX_SIMILARITY_REWRITE_ROUNDS = 2
MAX_PRODUCT_EXPERIENCE_PHRASE_REWRITE_ROUNDS = 2
MAX_PRODUCT_EXPERIENCE_LLM_REWRITE_ROUNDS = 1
MAX_AI_FLAVOR_REWRITE_ROUNDS = 2
POSTPROCESS_REWRITE_CONCURRENCY = 10
POST_DELETE_CLEANUP_FLUENCY_REASON = "post_delete_cleanup_fluency_check"
HISTORY_SIMILARITY_LOOKBACK_LIMIT = 50
TITLE_GUARD_HISTORY_LOOKBACK_LIMIT = 60
TITLE_GUARD_FORBIDDEN_SUBSTRINGS = (
    "【标题】",
    "这杯",
    "安排上",
    "留着",
    "老母亲",
    "搭子",
    "别踩坑",
    "我这样",
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

CURRENT_WANGYUE_ARTICLE_ASSET_KEY = "wangyue_v3_core_storyline_article_rules"
PERSONA_STYLE_REWRITE_DISABLED_ASSET_KEYS = {
    "a2_momclass_month_center",
}
PRODUCT_EXPERIENCE_COMPLIANCE_ISSUE_CODES = {
    "claim_risk",
    "public_disease_contrast",
    "wangyue_age_stage_error",
    "child_formula_operation_error",
    "formula_dry_powder_ingestion",
    "formula_usage_form_error",
    "portable_product_error",
    "supplement_replacement_error",
    "product_fact_number_drift",
}
PRODUCT_EXPERIENCE_FLUENCY_ISSUE_CODES = {
    "unnatural_product_appearance",
    "brief_translation_tone",
}
TITLE_GUARD_WATCH_ONLY_SUBSTRINGS = (
    "不用纠结",
)
TITLE_GUARD_WATCH_ONLY_CLOSURE_TERMS = (
    "省心",
    "踏实",
    "安心",
    "放心",
    "心里有底",
    "心里有数",
    "选对了",
    "没选错",
    "选对",
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
    re.compile(r"^\s*[{\[]"),
    re.compile(r"\"(?:title|body)\"\s*:"),
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
    re.compile(r"(?:今天|昨天|上午|下午|今晚|这次|刚才).{0,8}(?:出奇地|真是)?.{0,8}(?:没怎么|没咋|不怎么|少).{0,4}请假"),
    re.compile(r"停课"),
    re.compile(r"(?:他们班|班里).{0,6}班里"),
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
    re.compile(r"^我那时候"),
    re.compile(r"^尤其看"),
    re.compile(r"^价格差.{0,8}(?:大|不算大)$"),
    re.compile(r"^先继续喝着吧$"),
    re.compile(r"^省得我天天纠结"),
    re.compile(r"^旺玥这(?:两样|几个).{0,6}都有$"),
    re.compile(r"^给孩子喝了一段时间$"),
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
TITLE_SURFACE_ALLOWED_EMOJIS = frozenset("😂🥲🙃🤏🙂🤣")
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


def _focused_judge_model_code(dimension: str) -> str:
    if dimension == "temporal_logic":
        return TEMPORAL_LOGIC_MODEL_CODE
    if dimension == "claim_public_disease":
        return CLAIM_PUBLIC_DISEASE_MODEL_CODE
    if dimension == "content_fit":
        return CONTENT_FIT_MODEL_CODE
    if dimension == "fluency":
        return FLUENCY_JUDGE_MODEL_CODE
    raise ValueError(f"unsupported focused review dimension: {dimension}")


@dataclass(frozen=True)
class BatchExecutionResult:
    batch_id: int
    requested_limit: int
    generated_count: int
    failed_count: int
    item_ids: list[int]


@dataclass(frozen=True)
class BatchBusinessUsabilityReviewResult:
    batch_id: int
    reviewed_count: int
    skipped_count: int
    failed_count: int
    reviewed_item_nos: list[int]
    skipped_item_nos: list[int]
    failed_items: list[dict[str, Any]]
    tier_counts: dict[str, int]


@dataclass(frozen=True)
class BatchFocusedShadowReviewResult:
    batch_id: int
    reviewed_count: int
    skipped_count: int
    failed_count: int
    reviewed_item_nos: list[int]
    skipped_item_nos: list[int]
    failed_items: list[dict[str, Any]]
    label_counts: dict[str, int]
    usage_totals: dict[str, int]
    latency_totals: dict[str, int]


@dataclass(frozen=True)
class BatchFocusedPipelineShadowResult:
    batch_id: int
    reviewed_count: int
    skipped_count: int
    failed_count: int
    reviewed_item_nos: list[int]
    skipped_item_nos: list[int]
    failed_items: list[dict[str, Any]]
    decision_counts: dict[str, int]
    rewrite_mode_counts: dict[str, int]
    comparison_counts: dict[str, int]
    mismatch_item_nos: list[int]
    action_comparison_counts: dict[str, int]
    action_mismatch_item_nos: list[int]
    rewrite_rehearsal_counts: dict[str, int]
    accepted_rewrite_item_nos: list[int]
    manual_review_item_nos: list[int]
    usage_totals: dict[str, int]
    latency_totals: dict[str, int]


@dataclass(frozen=True)
class _ItemExecutionResult:
    item_id: int
    generated: bool
    failed: bool
    generated_count: int | None = None
    failed_count: int | None = None

    @property
    def effective_generated_count(self) -> int:
        return self.generated_count if self.generated_count is not None else int(self.generated)

    @property
    def effective_failed_count(self) -> int:
        return self.failed_count if self.failed_count is not None else int(self.failed)


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
        product_experience_llm_reviewer: ProductExperienceLLMReviewService | None = None,
        rewrite_quality_validator: RewriteQualityValidatorService | None = None,
        temporal_logic_judge: WangyueTemporalLogicJudgeService | None = None,
        claim_public_disease_judge: WangyueClaimPublicDiseaseJudgeService | None = None,
        content_fit_judge: WangyueContentFitJudgeService | None = None,
        fluency_judge: WangyueFluencyJudgeService | None = None,
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
        self.product_experience_llm_reviewer = (
            product_experience_llm_reviewer or ProductExperienceLLMReviewService()
        )
        self.rewrite_quality_validator = rewrite_quality_validator or RewriteQualityValidatorService()
        self.temporal_logic_judge = temporal_logic_judge or WangyueTemporalLogicJudgeService()
        self.claim_public_disease_judge = (
            claim_public_disease_judge or WangyueClaimPublicDiseaseJudgeService()
        )
        self.content_fit_judge = content_fit_judge or WangyueContentFitJudgeService()
        self.fluency_judge = fluency_judge or WangyueFluencyJudgeService()

    async def execute_batch_items(
        self,
        batch_id: int,
        *,
        limit: int,
        concurrency: int = 10,
        created_by: str | None = None,
    ) -> BatchExecutionResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        job = await self._require_job(batch_id)
        items = await self._planned_items(batch_id, limit)
        item_ids = [item.id for item in items]
        execution_groups = _multi_output_execution_groups(items)
        job_context = {
            "id": job.id,
            "batch_code": job.batch_code,
            "count": job.count,
            "postprocess_mode": _postprocess_mode(job),
        }
        semaphore = asyncio.Semaphore(concurrency)

        async def run_group(group_item_ids: list[int]) -> _ItemExecutionResult:
            # Each item owns a DB session because AsyncSession is not safe for
            # concurrent flush/commit while executor calls are in flight.
            async with semaphore:
                if len(group_item_ids) == 1:
                    return await self._execute_one_item(group_item_ids[0], job_context, created_by=created_by)
                return await self._execute_multi_output_item_group(
                    group_item_ids,
                    job_context,
                    created_by=created_by,
                )

        results = await asyncio.gather(*(run_group(group_item_ids) for group_item_ids in execution_groups))
        generated = sum(result.effective_generated_count for result in results)
        failed = sum(result.effective_failed_count for result in results)

        if generated:
            job.status = "partially_generated" if generated < job.count else "generated"
        elif failed:
            job.status = "failed"
        await self.db.flush()

        if _generate_only_postprocess_enabled(job):
            return BatchExecutionResult(
                batch_id=batch_id,
                requested_limit=limit,
                generated_count=generated,
                failed_count=failed,
                item_ids=item_ids,
            )

        if _audit_only_postprocess_enabled(job):
            await self._watch_similar_generated_items(batch_id, job)
            return BatchExecutionResult(
                batch_id=batch_id,
                requested_limit=limit,
                generated_count=generated,
                failed_count=failed,
                item_ids=item_ids,
            )

        postprocess_errors = []
        product_experience_review_step = (
            self._run_wangyue_focused_pipeline_postprocess
            if str(job.asset_key or "") == CURRENT_WANGYUE_ARTICLE_ASSET_KEY
            else self._rewrite_product_experience_llm_quality_items
        )
        postprocess_steps = [
            ("similarity_watch", self._watch_similar_generated_items),
            ("product_experience_phrase_rewrite", self._rewrite_product_experience_phrase_items),
            ("mouth_phrase_budget_rewrite", self._rewrite_mouth_phrase_budget_items),
            ("article_length_repair", self._repair_article_length_items),
            ("ai_flavor_rewrite", self._rewrite_ai_flavor_items),
            ("product_experience_review", product_experience_review_step),
            ("royal_friso_structure_review", self._review_royal_friso_structure_items),
            ("title_repair", self._repair_generated_titles),
            ("product_experience_phrase_refresh", self._refresh_product_experience_phrase_reviews),
        ]
        for step_name, step in postprocess_steps:
            try:
                await step(batch_id, job)
            except Exception as exc:  # noqa: BLE001 - postprocess must not hide generated items
                postprocess_errors.append(
                    {
                        "step": step_name,
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                    }
                )
        if postprocess_errors:
            strategy = dict(job.strategy_json or {})
            existing_errors = list(strategy.get("postprocess_errors") or [])
            strategy["postprocess_errors"] = [*existing_errors, *postprocess_errors]
            job.strategy_json = strategy
            await self.db.flush()

        return BatchExecutionResult(
            batch_id=batch_id,
            requested_limit=limit,
            generated_count=generated,
            failed_count=failed,
            item_ids=item_ids,
        )

    async def review_business_usability_items(
        self,
        batch_id: int,
        *,
        force: bool = False,
        limit: int | None = None,
        concurrency: int = POSTPROCESS_REWRITE_CONCURRENCY,
    ) -> BatchBusinessUsabilityReviewResult:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        job = await self._require_job(batch_id)
        use_focused_pipeline = str(job.asset_key or "") == CURRENT_WANGYUE_ARTICLE_ASSET_KEY
        result = await self.db.execute(
            select(ContentBatchItem.id)
            .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
            .order_by(ContentBatchItem.item_no)
            .limit(limit)
        )
        item_ids = [int(item_id) for item_id in result.scalars().all()]
        if not item_ids:
            return BatchBusinessUsabilityReviewResult(
                batch_id=batch_id,
                reviewed_count=0,
                skipped_count=0,
                failed_count=0,
                reviewed_item_nos=[],
                skipped_item_nos=[],
                failed_items=[],
                tier_counts={},
            )

        semaphore = asyncio.Semaphore(concurrency)

        async def run_item(item_id: int) -> dict[str, Any]:
            async with semaphore:
                if use_focused_pipeline:
                    result = await self._review_wangyue_focused_pipeline_item(
                        item_id,
                        force=force,
                    )
                    if result.get("status") == "skipped":
                        return result
                    return {
                        "status": "reviewed",
                        "item_no": result["item_no"],
                        "focused_status": result.get("status"),
                    }
                return await self._review_business_usability_item(item_id, force=force)

        results = await asyncio.gather(*(run_item(item_id) for item_id in item_ids))
        reviewed = [item for item in results if item.get("status") == "reviewed"]
        skipped = [item for item in results if item.get("status") == "skipped"]
        failed = [item for item in results if item.get("status") == "failed"]
        tier_counts = Counter(str(item.get("business_usability_tier") or "") for item in reviewed)
        tier_counts.pop("", None)
        return BatchBusinessUsabilityReviewResult(
            batch_id=batch_id,
            reviewed_count=len(reviewed),
            skipped_count=len(skipped),
            failed_count=len(failed),
            reviewed_item_nos=[int(item["item_no"]) for item in reviewed],
            skipped_item_nos=[int(item["item_no"]) for item in skipped],
            failed_items=[
                {"item_no": int(item["item_no"]), "error_message": str(item.get("error_message") or "")}
                for item in failed
            ],
            tier_counts=dict(tier_counts),
        )

    async def review_temporal_logic_shadow_items(
        self,
        batch_id: int,
        *,
        force: bool = False,
        limit: int | None = None,
        concurrency: int = POSTPROCESS_REWRITE_CONCURRENCY,
    ) -> BatchFocusedShadowReviewResult:
        return await self._review_focused_shadow_items(
            batch_id,
            force=force,
            limit=limit,
            concurrency=concurrency,
            worker=self._review_temporal_logic_shadow_item,
        )

    async def _run_wangyue_focused_pipeline_postprocess(
        self,
        batch_id: int,
        _job: ContentBatchJob,
    ) -> int:
        async def worker(item_id: int) -> int:
            result = await self._review_wangyue_focused_pipeline_item(item_id, force=True)
            return int(result.get("status") == "rewritten")

        return await self._run_generated_item_workers(batch_id, worker)

    async def _review_wangyue_focused_pipeline_item(
        self,
        item_id: int,
        *,
        force: bool,
    ) -> dict[str, Any]:
        quality_key = "wangyue_focused_pipeline_review"
        async with self.session_factory() as db:
            item = await self._require_item(db, item_id)
            if item.status != "generated" or not _is_current_wangyue_article_plan(item.plan_json):
                return {"status": "skipped", "item_no": item.item_no}

            quality = dict(item.quality_json or {})
            if not force and isinstance(quality.get(quality_key), dict):
                return {"status": "skipped", "item_no": item.item_no}

            review_report = dict(quality.get("review_report") or {})
            quality.pop("product_experience_llm_quality_review", None)
            quality.pop("product_experience_llm_quality_failures", None)
            quality.pop("product_experience_llm_quality_review_unavailable_mark_only", None)
            review_report.pop("product_experience_llm_review", None)
            if str(review_report.get("rewrite_reason") or "").startswith("LLM 判断产品出现"):
                review_report["rewrite_required"] = False
                review_report.pop("rewrite_reason", None)

            if quality.get("hard_pass") is False:
                payload = {
                    "decision": "block",
                    "issues": [],
                    "unavailable_dimensions": [],
                    "rewrite_modes": [],
                    "requires_rewrite": False,
                    "can_auto_pool": False,
                    "blocked_by_code_hard": True,
                    "status": "hard_block",
                    "affects_pool": True,
                }
                quality[quality_key] = payload
                review_report[quality_key] = dict(payload)
                quality["review_report"] = review_report
                item.quality_json = quality
                flag_modified(item, "quality_json")
                await db.commit()
                return {"status": "hard_block", "item_no": item.item_no}

            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            initial_reviews = await self._review_focused_dimensions_with_unavailable(
                item=item,
                orchestrator=orchestrator,
                title=item.title or "",
                body=item.body or "",
            )
            aggregate = aggregate_wangyue_focused_reviews(
                initial_reviews,
                hard_pass=quality.get("hard_pass"),
            )
            final_reviews = initial_reviews
            rewrite_result: dict[str, Any] | None = None
            status = aggregate.decision

            if aggregate.unavailable_dimensions:
                status = "hold"
            elif aggregate.requires_rewrite:
                try:
                    rewrite_result = await self._rehearse_focused_rewrite_candidate(
                        item=item,
                        aggregate=aggregate.model_dump(),
                        orchestrator=orchestrator,
                        rewrite_source_prefix="wangyue_focused_pipeline",
                        shadow=False,
                    )
                except Exception as exc:  # noqa: BLE001 - failed focused rewrite must hold the item
                    rewrite_result = {
                        "status": "manual_review",
                        "reason": f"focused rewrite unavailable: {exc}",
                        "original": {"title": item.title or "", "body": item.body or ""},
                        "attempts": [],
                        "shadow": False,
                        "affects_content": False,
                    }

                if rewrite_result.get("status") == "accepted":
                    candidate = rewrite_result.get("accepted_candidate") or {}
                    final_reviews = await self._review_focused_dimensions_with_unavailable(
                        item=item,
                        orchestrator=orchestrator,
                        title=str(candidate.get("title") or ""),
                        body=str(candidate.get("body") or ""),
                    )
                    final_aggregate = aggregate_wangyue_focused_reviews(
                        final_reviews,
                        hard_pass=quality.get("hard_pass"),
                    )
                    aggregate = final_aggregate
                    if final_aggregate.can_auto_pool:
                        item.title = str(candidate.get("title") or "")
                        item.body = str(candidate.get("body") or "")
                        item.error_message = None
                        status = "rewritten"
                    else:
                        status = "hold"
                else:
                    status = "manual_review"
            elif aggregate.decision == "block":
                status = "manual_review"

            for dimension, review in final_reviews.items():
                quality[f"wangyue_{dimension}_review"] = dict(review)
            payload = {
                **aggregate.model_dump(),
                "status": status,
                "affects_pool": True,
                "initial_reviews": initial_reviews,
            }
            if rewrite_result is not None:
                payload["rewrite_result"] = rewrite_result
                payload["post_rewrite_reviews"] = final_reviews
            quality[quality_key] = payload
            review_report[quality_key] = dict(payload)
            quality["review_report"] = review_report
            item.quality_json = quality
            flag_modified(item, "quality_json")
            await db.commit()
            return {"status": status, "item_no": item.item_no}

    async def _review_focused_dimensions_with_unavailable(
        self,
        *,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator,
        title: str,
        body: str,
    ) -> dict[str, dict[str, Any]]:
        reviews: dict[str, dict[str, Any]] = {}
        for dimension in FOCUSED_REVIEW_DIMENSIONS:
            try:
                reviews.update(
                    await self._review_focused_candidate_dimensions(
                        item=item,
                        orchestrator=orchestrator,
                        title=title,
                        body=body,
                        dimensions=[dimension],
                    )
                )
            except Exception as exc:  # noqa: BLE001 - one unavailable judge must hold, not abort, the item
                reviews[dimension] = {
                    "status": "unavailable",
                    "error_message": str(exc),
                }
        return reviews

    async def _review_temporal_logic_shadow_item(self, item_id: int, *, force: bool) -> dict[str, Any]:
        return await self._review_focused_judge_shadow_item(
            item_id,
            force=force,
            quality_key="wangyue_temporal_logic_shadow_review",
            judge=self.temporal_logic_judge,
            model_code=_focused_judge_model_code("temporal_logic"),
        )

    async def review_claim_public_disease_shadow_items(
        self,
        batch_id: int,
        *,
        force: bool = False,
        limit: int | None = None,
        concurrency: int = POSTPROCESS_REWRITE_CONCURRENCY,
    ) -> BatchFocusedShadowReviewResult:
        return await self._review_focused_shadow_items(
            batch_id,
            force=force,
            limit=limit,
            concurrency=concurrency,
            worker=self._review_claim_public_disease_shadow_item,
        )

    async def review_content_fit_shadow_items(
        self,
        batch_id: int,
        *,
        force: bool = False,
        limit: int | None = None,
        concurrency: int = POSTPROCESS_REWRITE_CONCURRENCY,
    ) -> BatchFocusedShadowReviewResult:
        return await self._review_focused_shadow_items(
            batch_id,
            force=force,
            limit=limit,
            concurrency=concurrency,
            worker=self._review_content_fit_shadow_item,
        )

    async def review_fluency_shadow_items(
        self,
        batch_id: int,
        *,
        force: bool = False,
        limit: int | None = None,
        concurrency: int = POSTPROCESS_REWRITE_CONCURRENCY,
    ) -> BatchFocusedShadowReviewResult:
        return await self._review_focused_shadow_items(
            batch_id,
            force=force,
            limit=limit,
            concurrency=concurrency,
            worker=self._review_fluency_shadow_item,
        )

    async def review_focused_pipeline_shadow_items(
        self,
        batch_id: int,
        *,
        force: bool = False,
        limit: int | None = None,
        concurrency: int = POSTPROCESS_REWRITE_CONCURRENCY,
        rehearse_rewrites: bool = False,
    ) -> BatchFocusedPipelineShadowResult:
        dimension_results = []
        for dimension, reviewer in (
            ("temporal_logic", self.review_temporal_logic_shadow_items),
            ("claim_public_disease", self.review_claim_public_disease_shadow_items),
            ("content_fit", self.review_content_fit_shadow_items),
            ("fluency", self.review_fluency_shadow_items),
        ):
            result = await reviewer(
                batch_id,
                force=force,
                limit=limit,
                concurrency=concurrency,
            )
            dimension_results.append((dimension, result))

        result = await self.db.execute(
            select(ContentBatchItem.id)
            .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
            .order_by(ContentBatchItem.item_no)
            .limit(limit)
        )
        item_ids = [int(item_id) for item_id in result.scalars().all()]
        aggregate_results = [
            await self._aggregate_focused_pipeline_shadow_item(item_id, force=force)
            for item_id in item_ids
        ]
        reviewed = [item for item in aggregate_results if item.get("status") == "reviewed"]
        skipped = [item for item in aggregate_results if item.get("status") == "skipped"]
        rehearsal_results: list[dict[str, Any]] = []
        if rehearse_rewrites:
            semaphore = asyncio.Semaphore(concurrency)

            async def rehearse(item_id: int) -> dict[str, Any]:
                async with semaphore:
                    return await self._rehearse_focused_pipeline_shadow_item(
                        item_id,
                        force=force,
                    )

            rehearsal_results = await asyncio.gather(
                *(rehearse(int(item["item_id"])) for item in reviewed)
            )
        decision_counts = Counter(str(item.get("decision") or "") for item in reviewed)
        decision_counts.pop("", None)
        rewrite_mode_counts: Counter[str] = Counter()
        comparison_counts: Counter[str] = Counter()
        mismatch_item_nos: list[int] = []
        action_comparison_counts: Counter[str] = Counter()
        action_mismatch_item_nos: list[int] = []
        for item in reviewed:
            rewrite_mode_counts.update(item.get("rewrite_modes") or [])
            comparison = item.get("comparison") or {}
            if not comparison.get("legacy_available"):
                comparison_counts["legacy_unavailable"] += 1
            elif comparison.get("rewrite_decision_match"):
                comparison_counts["match"] += 1
            else:
                comparison_counts["mismatch"] += 1
                mismatch_item_nos.append(int(item["item_no"]))
            if not comparison.get("legacy_available"):
                action_comparison_counts["legacy_unavailable"] += 1
            elif comparison.get("action_match") is None:
                action_comparison_counts["out_of_scope_hard_block"] += 1
            elif comparison.get("action_match"):
                action_comparison_counts["match"] += 1
            else:
                action_comparison_counts["mismatch"] += 1
                action_mismatch_item_nos.append(int(item["item_no"]))

        failed_items = []
        for dimension, dimension_result in dimension_results:
            failed_items.extend(
                {**failed_item, "dimension": dimension}
                for failed_item in dimension_result.failed_items
            )
        failed_item_nos = {int(item["item_no"]) for item in failed_items}
        rehearsal_counts = Counter(str(item.get("status") or "") for item in rehearsal_results)
        rehearsal_counts.pop("", None)
        usage_totals = {
            key: sum(int(result.usage_totals.get(key) or 0) for _, result in dimension_results)
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }
        total_latency_ms = sum(
            int(result.latency_totals.get("total_latency_ms") or 0)
            for _, result in dimension_results
        )
        dimension_call_count = sum(result.reviewed_count for _, result in dimension_results)
        max_latency_ms = max(
            (int(result.latency_totals.get("max_latency_ms") or 0) for _, result in dimension_results),
            default=0,
        )
        return BatchFocusedPipelineShadowResult(
            batch_id=batch_id,
            reviewed_count=len(reviewed),
            skipped_count=len(skipped),
            failed_count=len(failed_item_nos),
            reviewed_item_nos=[int(item["item_no"]) for item in reviewed],
            skipped_item_nos=[int(item["item_no"]) for item in skipped],
            failed_items=failed_items,
            decision_counts=dict(decision_counts),
            rewrite_mode_counts=dict(rewrite_mode_counts),
            comparison_counts=dict(comparison_counts),
            mismatch_item_nos=mismatch_item_nos,
            action_comparison_counts=dict(action_comparison_counts),
            action_mismatch_item_nos=action_mismatch_item_nos,
            rewrite_rehearsal_counts=dict(rehearsal_counts),
            accepted_rewrite_item_nos=[
                int(item["item_no"])
                for item in rehearsal_results
                if item.get("status") == "accepted"
            ],
            manual_review_item_nos=[
                int(item["item_no"])
                for item in rehearsal_results
                if item.get("status") == "manual_review"
            ],
            usage_totals=usage_totals,
            latency_totals={
                "total_latency_ms": total_latency_ms,
                "average_latency_ms": (
                    round(total_latency_ms / dimension_call_count) if dimension_call_count else 0
                ),
                "max_latency_ms": max_latency_ms,
            },
        )

    async def _run_focused_pipeline_shadow_postprocess(
        self,
        batch_id: int,
        _job: ContentBatchJob,
    ) -> int:
        result = await self.review_focused_pipeline_shadow_items(
            batch_id,
            force=True,
            concurrency=POSTPROCESS_REWRITE_CONCURRENCY,
        )
        return result.reviewed_count

    async def _aggregate_focused_pipeline_shadow_item(
        self,
        item_id: int,
        *,
        force: bool,
    ) -> dict[str, Any]:
        quality_key = "wangyue_focused_pipeline_shadow_review"
        async with self.session_factory() as db:
            item = await self._require_item(db, item_id)
            quality = dict(item.quality_json or {})
            if item.status != "generated" or not _is_current_wangyue_article_plan(item.plan_json):
                return {"status": "skipped", "item_no": item.item_no}
            if not force and isinstance(quality.get(quality_key), dict):
                return {"status": "skipped", "item_no": item.item_no}

            judgments = {
                "temporal_logic": quality.get("wangyue_temporal_logic_shadow_review"),
                "claim_public_disease": quality.get("wangyue_claim_public_disease_shadow_review"),
                "content_fit": quality.get("wangyue_content_fit_shadow_review"),
                "fluency": quality.get("wangyue_fluency_shadow_review"),
            }
            aggregate = aggregate_wangyue_focused_reviews(
                judgments,
                hard_pass=quality.get("hard_pass"),
            )
            comparison = compare_focused_review_with_legacy(
                aggregate,
                quality.get("product_experience_llm_quality_review"),
            )
            payload = {
                **aggregate.model_dump(),
                "comparison": comparison,
                "shadow": True,
                "affects_hard_pass": False,
            }
            quality[quality_key] = payload
            review_report = dict(quality.get("review_report") or {})
            review_report[quality_key] = dict(payload)
            quality["review_report"] = review_report
            item.quality_json = quality
            flag_modified(item, "quality_json")
            await db.commit()
            return {
                "status": "reviewed",
                "item_id": item.id,
                "item_no": item.item_no,
                "decision": aggregate.decision,
                "rewrite_modes": aggregate.rewrite_modes,
                "comparison": comparison,
            }

    async def _rehearse_focused_pipeline_shadow_item(
        self,
        item_id: int,
        *,
        force: bool,
    ) -> dict[str, Any]:
        quality_key = "wangyue_focused_pipeline_cutover_rehearsal"
        async with self.session_factory() as db:
            item = await self._require_item(db, item_id)
            quality = dict(item.quality_json or {})
            if item.status != "generated" or not _is_current_wangyue_article_plan(item.plan_json):
                return {"status": "skipped", "item_no": item.item_no}
            if not force and isinstance(quality.get(quality_key), dict):
                return {"status": "skipped", "item_no": item.item_no}

            aggregate = quality.get("wangyue_focused_pipeline_shadow_review")
            if not isinstance(aggregate, dict):
                return {
                    "status": "failed",
                    "item_no": item.item_no,
                    "error_message": "focused pipeline aggregate is unavailable",
                }

            if quality.get("hard_pass") is False:
                payload = {
                    "status": "hard_block",
                    "reason": "code hard review already failed; LLM rewrite is not allowed to revive it",
                    "shadow": True,
                    "affects_content": False,
                }
            elif not aggregate.get("rewrite_modes"):
                payload = {
                    "status": (
                        "manual_review" if aggregate.get("decision") == "block" else "not_required"
                    ),
                    "reason": (
                        "focused block has no safe local rewrite route"
                        if aggregate.get("decision") == "block"
                        else "focused aggregate does not require rewrite"
                    ),
                    "shadow": True,
                    "affects_content": False,
                }
            else:
                orchestrator = ContentAgentOrchestrator(
                    db,
                    invocation_client=self.invocation_client,
                    callback_base_url=self.callback_base_url,
                )
                try:
                    payload = await self._rehearse_focused_rewrite_candidate(
                        item=item,
                        aggregate=aggregate,
                        orchestrator=orchestrator,
                    )
                except Exception as exc:  # noqa: BLE001 - rehearsal must never alter production content
                    payload = {
                        "status": "manual_review",
                        "reason": f"focused rewrite rehearsal unavailable: {exc}",
                        "shadow": True,
                        "affects_content": False,
                    }

            quality[quality_key] = payload
            review_report = dict(quality.get("review_report") or {})
            review_report[quality_key] = dict(payload)
            quality["review_report"] = review_report
            item.quality_json = quality
            flag_modified(item, "quality_json")
            await db.commit()
            return {"status": payload["status"], "item_no": item.item_no}

    async def _rehearse_focused_rewrite_candidate(
        self,
        *,
        item: ContentBatchItem,
        aggregate: dict[str, Any],
        orchestrator: ContentAgentOrchestrator,
        rewrite_source_prefix: str = "wangyue_focused_pipeline_shadow",
        shadow: bool = True,
    ) -> dict[str, Any]:
        original = {"title": item.title or "", "body": item.body or ""}
        current = dict(original)
        attempts: list[dict[str, Any]] = []

        for rewrite_mode in aggregate.get("rewrite_modes") or []:
            focused_issues = [
                issue
                for issue in aggregate.get("issues") or []
                if issue.get("label") == "block" and issue.get("rewrite_mode") == rewrite_mode
            ]
            if not focused_issues:
                continue
            review = _focused_issues_as_rewrite_review(focused_issues, rewrite_mode=rewrite_mode)
            target_dimensions = list(
                dict.fromkeys(str(issue.get("dimension") or "") for issue in focused_issues)
            )
            validator_feedback = ""
            accepted = False

            for attempt_no in range(1, 3):
                candidate_item = ContentBatchItem(
                    run_id=item.run_id,
                    title=current["title"],
                    body=current["body"],
                    plan_json=item.plan_json,
                    quality_json=item.quality_json,
                )
                if rewrite_mode == "compliance_cleanup":
                    input_payload = self._product_experience_compliance_cleanup_input(
                        candidate_item,
                        review,
                    )
                else:
                    input_payload = self._product_experience_fluency_humanize_input(
                        candidate_item,
                        review,
                    )
                input_payload["rewrite_source"] = f"{rewrite_source_prefix}_{rewrite_mode}"
                if validator_feedback:
                    input_payload["rewrite_instructions"] = [
                        *list(input_payload.get("rewrite_instructions") or []),
                        f"上一个候选未通过验收：{validator_feedback}。本轮只修正这个问题，不要扩写。",
                    ]

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
                body = _preserve_rewrite_paragraphs(current["body"], body, item.plan_json)
                after = {"title": title, "body": body}
                code_hard_review = _focused_rewrite_candidate_code_hard_review(
                    item=item,
                    after=after,
                )
                if not code_hard_review["pass"]:
                    attempts.append(
                        {
                            "rewrite_mode": rewrite_mode,
                            "attempt": attempt_no,
                            "before": dict(current),
                            "after": after,
                            "code_hard_review": code_hard_review,
                            "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                        }
                    )
                    return {
                        "status": "manual_review",
                        "reason": "rewrite candidate failed deterministic hard review",
                        "original": original,
                        "attempts": attempts,
                        "shadow": shadow,
                        "affects_content": False,
                    }
                if _rewrite_removed_required_wangyue_product(current, after, item.plan_json):
                    validation = RewriteQualityJudgment(
                        label="reject",
                        issue_code="required_fact_loss",
                        evidence="改写后删除了原文已有的旺玥产品信息",
                    )
                else:
                    validation = await self._validate_product_experience_llm_rewrite_candidate(
                        item=item,
                        orchestrator=orchestrator,
                        before=current,
                        after=after,
                        review=review,
                        rewrite_source=str(input_payload["rewrite_source"]),
                    )

                attempt_payload: dict[str, Any] = {
                    "rewrite_mode": rewrite_mode,
                    "attempt": attempt_no,
                    "before": dict(current),
                    "after": after,
                    "code_hard_review": code_hard_review,
                    "rewrite_quality_validation": validation.model_dump(),
                    "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                }
                if validation.label == "reject":
                    attempts.append(attempt_payload)
                    return {
                        "status": "manual_review",
                        "reason": validation.evidence or validation.issue_code,
                        "original": original,
                        "attempts": attempts,
                        "shadow": shadow,
                        "affects_content": False,
                    }
                if validation.label == "retry":
                    validator_feedback = validation.evidence or validation.issue_code
                    attempts.append(attempt_payload)
                    continue

                target_reviews = await self._review_focused_candidate_dimensions(
                    item=item,
                    orchestrator=orchestrator,
                    title=after["title"],
                    body=after["body"],
                    dimensions=target_dimensions,
                )
                attempt_payload["target_reviews"] = target_reviews
                attempts.append(attempt_payload)
                remaining_blocks = [
                    review_payload
                    for review_payload in target_reviews.values()
                    if review_payload.get("label") == "block"
                ]
                if remaining_blocks:
                    validator_feedback = "；".join(
                        str(review_payload.get("evidence") or review_payload.get("issue_code") or "")
                        for review_payload in remaining_blocks
                    )
                    continue

                current = after
                accepted = True
                break

            if not accepted:
                return {
                    "status": "manual_review",
                    "reason": "focused target issue remained after two local rewrite attempts",
                    "original": original,
                    "attempts": attempts,
                    "shadow": shadow,
                    "affects_content": False,
                }

        return {
            "status": "accepted",
            "reason": "rewrite quality and affected focused judges accepted the candidate",
            "original": original,
            "accepted_candidate": current,
            "attempts": attempts,
            "shadow": shadow,
            "affects_content": not shadow,
        }

    async def _review_focused_candidate_dimensions(
        self,
        *,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator,
        title: str,
        body: str,
        dimensions: list[str],
    ) -> dict[str, dict[str, Any]]:
        reviews: dict[str, dict[str, Any]] = {}
        for dimension in dimensions:
            if dimension == "temporal_logic":
                judge = self.temporal_logic_judge
            elif dimension == "claim_public_disease":
                judge = self.claim_public_disease_judge
            elif dimension == "content_fit":
                judge = self.content_fit_judge
            elif dimension == "fluency":
                judge = self.fluency_judge
            else:
                raise ValueError(f"unsupported focused review dimension: {dimension}")
            model_code = _focused_judge_model_code(dimension)
            source_plan = {"model_config": {"model_code": model_code}}
            review_plan = await self._plan_with_provider_config_for_llm_review(
                source_plan,
                orchestrator=orchestrator,
            )
            if (review_plan.get("model_config") or {}).get("route_model_code") != model_code:
                raise RuntimeError(f"dedicated judge model route not found: {model_code}")
            review_kwargs: dict[str, Any] = {
                "title": title,
                "body": body,
                "model_config": review_plan.get("model_config") or {},
            }
            if dimension == "content_fit":
                review_kwargs["post_type"] = str(
                    (item.plan_json or {}).get("post_type")
                    or (item.plan_json or {}).get("ugc_post_type")
                    or ""
                )
            judgment = await judge.review(**review_kwargs)
            reviews[dimension] = {
                **judgment.model_dump(),
                "runtime_metadata": dict(judgment.runtime_metadata or {}),
            }
        return reviews

    async def _review_focused_shadow_items(
        self,
        batch_id: int,
        *,
        force: bool,
        limit: int | None,
        concurrency: int,
        worker: Callable[..., Awaitable[dict[str, Any]]],
    ) -> BatchFocusedShadowReviewResult:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        await self._require_job(batch_id)
        result = await self.db.execute(
            select(ContentBatchItem.id)
            .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
            .order_by(ContentBatchItem.item_no)
            .limit(limit)
        )
        item_ids = [int(item_id) for item_id in result.scalars().all()]
        if not item_ids:
            return BatchFocusedShadowReviewResult(
                batch_id=batch_id,
                reviewed_count=0,
                skipped_count=0,
                failed_count=0,
                reviewed_item_nos=[],
                skipped_item_nos=[],
                failed_items=[],
                label_counts={},
                usage_totals={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                latency_totals={"total_latency_ms": 0, "average_latency_ms": 0, "max_latency_ms": 0},
            )

        semaphore = asyncio.Semaphore(concurrency)

        async def run_item(item_id: int) -> dict[str, Any]:
            async with semaphore:
                return await worker(item_id, force=force)

        results = await asyncio.gather(*(run_item(item_id) for item_id in item_ids))
        reviewed = [item for item in results if item.get("status") == "reviewed"]
        skipped = [item for item in results if item.get("status") == "skipped"]
        failed = [item for item in results if item.get("status") == "failed"]
        label_counts = Counter(str(item.get("label") or "") for item in reviewed)
        label_counts.pop("", None)
        usage_totals = {
            key: sum(int((item.get("usage") or {}).get(key) or 0) for item in reviewed)
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }
        latencies = [int(item.get("latency_ms") or 0) for item in reviewed]
        total_latency_ms = sum(latencies)
        return BatchFocusedShadowReviewResult(
            batch_id=batch_id,
            reviewed_count=len(reviewed),
            skipped_count=len(skipped),
            failed_count=len(failed),
            reviewed_item_nos=[int(item["item_no"]) for item in reviewed],
            skipped_item_nos=[int(item["item_no"]) for item in skipped],
            failed_items=[
                {"item_no": int(item["item_no"]), "error_message": str(item.get("error_message") or "")}
                for item in failed
            ],
            label_counts=dict(label_counts),
            usage_totals=usage_totals,
            latency_totals={
                "total_latency_ms": total_latency_ms,
                "average_latency_ms": round(total_latency_ms / len(latencies)) if latencies else 0,
                "max_latency_ms": max(latencies, default=0),
            },
        )

    async def _review_claim_public_disease_shadow_item(
        self,
        item_id: int,
        *,
        force: bool,
    ) -> dict[str, Any]:
        return await self._review_focused_judge_shadow_item(
            item_id,
            force=force,
            quality_key="wangyue_claim_public_disease_shadow_review",
            judge=self.claim_public_disease_judge,
            model_code=_focused_judge_model_code("claim_public_disease"),
        )

    async def _review_content_fit_shadow_item(self, item_id: int, *, force: bool) -> dict[str, Any]:
        return await self._review_focused_judge_shadow_item(
            item_id,
            force=force,
            quality_key="wangyue_content_fit_shadow_review",
            judge=self.content_fit_judge,
            include_post_type=True,
            model_code=_focused_judge_model_code("content_fit"),
        )

    async def _review_fluency_shadow_item(self, item_id: int, *, force: bool) -> dict[str, Any]:
        return await self._review_focused_judge_shadow_item(
            item_id,
            force=force,
            quality_key="wangyue_fluency_shadow_review",
            judge=self.fluency_judge,
            model_code=_focused_judge_model_code("fluency"),
        )

    async def _review_focused_judge_shadow_item(
        self,
        item_id: int,
        *,
        force: bool,
        quality_key: str,
        judge: Any,
        include_post_type: bool = False,
        model_code: str | None = None,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            item = await self._require_item(db, item_id)
            quality = dict(item.quality_json or {})
            if item.status != "generated" or not _is_current_wangyue_article_plan(item.plan_json):
                return {"status": "skipped", "item_no": item.item_no}
            if not force and isinstance(quality.get(quality_key), dict):
                return {"status": "skipped", "item_no": item.item_no}

            async def mark_unavailable(error_message: str) -> dict[str, Any]:
                payload = {
                    "status": "unavailable",
                    "error_message": error_message,
                    "shadow": True,
                    "affects_hard_pass": False,
                }
                quality[quality_key] = payload
                review_report = dict(quality.get("review_report") or {})
                review_report[quality_key] = dict(payload)
                quality["review_report"] = review_report
                item.quality_json = quality
                flag_modified(item, "quality_json")
                await db.commit()
                return {
                    "status": "failed",
                    "item_no": item.item_no,
                    "error_message": error_message,
                }

            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            try:
                source_plan = (
                    {"model_config": {"model_code": model_code}}
                    if model_code
                    else item.plan_json
                )
                review_plan = await self._plan_with_provider_config_for_llm_review(
                    source_plan,
                    orchestrator=orchestrator,
                )
                review_model_config = review_plan.get("model_config") or {}
                if model_code and review_model_config.get("route_model_code") != model_code:
                    return await mark_unavailable(f"dedicated judge model route not found: {model_code}")
                review_kwargs = {
                    "title": item.title,
                    "body": item.body,
                    "model_config": review_model_config,
                }
                if include_post_type:
                    review_kwargs["post_type"] = str(
                        (item.plan_json or {}).get("post_type")
                        or (item.plan_json or {}).get("ugc_post_type")
                        or ""
                    )
                judgment = await judge.review(
                    **review_kwargs,
                )
            except Exception as exc:  # noqa: BLE001 - shadow review must never alter production decisions
                return await mark_unavailable(str(exc))

            payload = {
                **judgment.model_dump(),
                "runtime_metadata": dict(judgment.runtime_metadata or {}),
                "shadow": True,
                "affects_hard_pass": False,
            }
            quality[quality_key] = payload
            review_report = dict(quality.get("review_report") or {})
            review_report[quality_key] = dict(payload)
            quality["review_report"] = review_report
            item.quality_json = quality
            flag_modified(item, "quality_json")
            await db.commit()
            runtime_metadata = judgment.runtime_metadata or {}
            return {
                "status": "reviewed",
                "item_no": item.item_no,
                "label": judgment.label,
                "usage": runtime_metadata.get("usage") or {},
                "latency_ms": int(runtime_metadata.get("latency_ms") or 0),
            }

    async def _review_business_usability_item(self, item_id: int, *, force: bool) -> dict[str, Any]:
        async with self.session_factory() as db:
            item = await self._require_item(db, item_id)
            quality = dict(item.quality_json or {})
            if item.status != "generated" or not _should_review_product_experience_llm_quality(item.plan_json):
                return {"status": "skipped", "item_no": item.item_no}
            if not force and isinstance(quality.get("product_experience_llm_quality_review"), dict):
                return {"status": "skipped", "item_no": item.item_no}

            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            phrase_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
            ai_flavor_review = review_ai_flavor(title=item.title, body=item.body, plan=item.plan_json)
            self._mark_ai_flavor_review(item, ai_flavor_review)
            review_plan = await self._plan_with_provider_config_for_llm_review(
                item.plan_json,
                orchestrator=orchestrator,
            )
            try:
                review = await self.product_experience_llm_reviewer.review(
                    title=item.title,
                    body=item.body,
                    plan=review_plan,
                    phrase_review=phrase_review,
                    ai_flavor_review=ai_flavor_review,
                )
            except Exception as exc:  # noqa: BLE001 - reviewer failure should be visible but non-destructive
                self._mark_product_experience_llm_review_failure(item, str(exc))
                flag_modified(item, "quality_json")
                await db.commit()
                return {"status": "failed", "item_no": item.item_no, "error_message": str(exc)}

            self._mark_product_experience_llm_review(item, review, mark_rewrite_required=False)
            flag_modified(item, "quality_json")
            await db.commit()
            return {
                "status": "reviewed",
                "item_no": item.item_no,
                "business_usability_tier": review.business_usability_tier,
            }

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

    async def _generated_item_ids(self, batch_id: int) -> list[int]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem.id)
                .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
                .order_by(ContentBatchItem.item_no)
            )
            return [int(item_id) for item_id in result.scalars().all()]

    async def _run_generated_item_workers(
        self,
        batch_id: int,
        worker: Callable[[int], Awaitable[int]],
        *,
        concurrency: int = POSTPROCESS_REWRITE_CONCURRENCY,
    ) -> int:
        item_ids = await self._generated_item_ids(batch_id)
        if not item_ids:
            return 0
        semaphore = asyncio.Semaphore(concurrency)

        async def run_item(item_id: int) -> int:
            async with semaphore:
                return await worker(item_id)

        results = await asyncio.gather(*(run_item(item_id) for item_id in item_ids))
        return sum(results)

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
                    "model_config": unified.input_snapshot.get("model_config") or {},
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
                multi_output_items = _generated_article_items(final)
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
                if multi_output_items:
                    item.quality_json["multi_output"] = {
                        "mode": "items_json",
                        "returned_count": len(multi_output_items),
                        "selected_index": 0,
                        "items": multi_output_items,
                    }
                item.diversity_json = {
                    "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                }
                if _generate_only_postprocess_enabled_for_context(job_context):
                    item.quality_json["postprocess_mode"] = "generate_only"
                    item.quality_json["hard_pass"] = False
                    item.quality_json["audit_skipped"] = True
                    item.quality_json["review_report"]["audit_skipped"] = True
                else:
                    audit_only = _audit_only_postprocess_enabled_for_context(job_context)
                    if audit_only:
                        item.quality_json["postprocess_mode"] = "audit_only"
                    else:
                        await self._rewrite_item_for_persona_style(
                            item=item,
                            orchestrator=orchestrator,
                            run_id=result.run.id,
                        )
                    forbidden_review = await ForbiddenTermReviewService(db).review_and_rewrite_item(
                        item=item,
                        asset_key=item.plan_json.get("asset_key"),
                        orchestrator=orchestrator,
                        executor_code=self.executor_code,
                        content_type="article",
                        allow_rewrite=not audit_only,
                    )
                    if forbidden_review.get("final_hits"):
                        if not audit_only:
                            self._mark_forbidden_term_blocking_failure(
                                item,
                                list(forbidden_review.get("final_hits") or []),
                            )
                        await db.commit()
                        return _ItemExecutionResult(item_id=item_id, generated=True, failed=False)
                    if not audit_only:
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

    async def _execute_multi_output_item_group(
        self,
        item_ids: list[int],
        job_context: dict[str, Any],
        *,
        created_by: str | None = None,
    ) -> _ItemExecutionResult:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.id.in_(item_ids))
                .order_by(ContentBatchItem.item_no)
            )
            items = list(result.scalars().all())
            if not items:
                return _ItemExecutionResult(item_id=0, generated=False, failed=True, failed_count=len(item_ids))
            for item in items:
                item.status = "running"
            await db.commit()

            leader = items[0]
            item_id = int(leader.id or 0)
            output_count = len(items)
            orchestrator = ContentAgentOrchestrator(
                db,
                invocation_client=self.invocation_client,
                callback_base_url=self.callback_base_url,
            )
            leader_plan = dict(leader.plan_json or {})
            leader_plan["multi_output_count"] = output_count
            leader_plan["article_output_count"] = output_count
            leader_plan["items_per_prompt"] = output_count
            unified = await UnifiedContentGenerationService(db).build_snapshot(
                content_type="article",
                business_rule=leader_plan,
                item_no=leader.item_no,
                output_fields=["title", "body"],
                keyword_asset_key=leader_plan.get("keyword_asset_key"),
                model_config=leader_plan.get("model_config") or {},
            )
            unified_generation = {
                "capability": CONTENT_GENERATE_CAPABILITY,
                "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                "keyword_asset": unified.input_snapshot.get("keyword_asset") or {},
                "expert": unified.input_snapshot.get("expert") or {},
                "model_config": unified.input_snapshot.get("model_config") or {},
                "rendered_prompt": unified.input_snapshot.get("rendered_prompt") or "",
            }
            for index, item in enumerate(items):
                group = dict(((item.plan_json or {}).get("multi_output_group") or {}))
                group.update({"actual_count": output_count, "selected_index": index})
                item.plan_json = {
                    **(item.plan_json or {}),
                    "multi_output_group": group,
                    "batch_context": {
                        "batch_id": job_context["id"],
                        "batch_code": job_context["batch_code"],
                        "item_no": item.item_no,
                    },
                    "unified_generation": unified_generation,
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
                generated_items = _generated_article_items(final)
                if not generated_items:
                    raise ValueError(f"content.generate returned 0 articles for {output_count} planned items")
                generated_count = 0
                failed_count = 0
                for index, item in enumerate(items):
                    if index >= len(generated_items):
                        item.status = "failed"
                        item.task_id = result.run.task_id
                        item.run_id = result.run.id
                        item.error_message = (
                            f"content.generate returned {len(generated_items)} articles for "
                            f"{output_count} planned items"
                        )
                        item.quality_json = _multi_output_parse_failure_quality(
                            executor=self._executor_label(result.stage_calls),
                            stage_call_count=len(result.stage_calls),
                            run_status=result.run.status,
                            selected_keywords=unified.input_snapshot.get("selected_keywords") or [],
                            expert_config_code=(unified.input_snapshot.get("expert") or {}).get("expert_config_code"),
                            returned_items=generated_items,
                            selected_index=index,
                        )
                        failed_count += 1
                        continue
                    article = generated_items[index]
                    title = str(article.get("title") or "").strip()
                    body = str(article.get("body") or "").strip()
                    if not title or not body:
                        item.status = "failed"
                        item.task_id = result.run.task_id
                        item.run_id = result.run.id
                        item.error_message = "content.generate returned empty article in multi-output group"
                        item.quality_json = _multi_output_parse_failure_quality(
                            executor=self._executor_label(result.stage_calls),
                            stage_call_count=len(result.stage_calls),
                            run_status=result.run.status,
                            selected_keywords=unified.input_snapshot.get("selected_keywords") or [],
                            expert_config_code=(unified.input_snapshot.get("expert") or {}).get("expert_config_code"),
                            returned_items=generated_items,
                            selected_index=index,
                        )
                        failed_count += 1
                        continue
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
                        "multi_output": {
                            "mode": "items_json",
                            "returned_count": len(generated_items),
                            "selected_index": index,
                            "items": generated_items,
                            "materialized_to_batch_items": True,
                        },
                    }
                    item.diversity_json = {
                        "selected_keywords": unified.input_snapshot.get("selected_keywords") or [],
                    }
                    if _generate_only_postprocess_enabled_for_context(job_context):
                        item.quality_json["postprocess_mode"] = "generate_only"
                        item.quality_json["hard_pass"] = False
                        item.quality_json["audit_skipped"] = True
                        item.quality_json["review_report"]["audit_skipped"] = True
                    else:
                        audit_only = _audit_only_postprocess_enabled_for_context(job_context)
                        if audit_only:
                            item.quality_json["postprocess_mode"] = "audit_only"
                        else:
                            await self._rewrite_item_for_persona_style(
                                item=item,
                                orchestrator=orchestrator,
                                run_id=result.run.id,
                            )
                        forbidden_review = await ForbiddenTermReviewService(db).review_and_rewrite_item(
                            item=item,
                            asset_key=item.plan_json.get("asset_key"),
                            orchestrator=orchestrator,
                            executor_code=self.executor_code,
                            content_type="article",
                            allow_rewrite=not audit_only,
                        )
                        if forbidden_review.get("final_hits"):
                            if not audit_only:
                                self._mark_forbidden_term_blocking_failure(
                                    item,
                                    list(forbidden_review.get("final_hits") or []),
                                )
                        elif not audit_only:
                            ActivityQualityGuardService().review_item(item)
                    item.error_message = None
                    generated_count += 1
                await db.commit()
                return _ItemExecutionResult(
                    item_id=item_id,
                    generated=generated_count > 0,
                    failed=failed_count > 0,
                    generated_count=generated_count,
                    failed_count=failed_count,
                )
            except Exception as exc:  # noqa: BLE001 - persist failed status for operator inspection
                for item in items:
                    item.status = "failed"
                    if "result" in locals():
                        item.task_id = result.run.task_id
                        item.run_id = result.run.id
                        item.quality_json = _multi_output_parse_failure_quality(
                            executor=self._executor_label(result.stage_calls),
                            stage_call_count=len(result.stage_calls),
                            run_status=result.run.status,
                            selected_keywords=unified.input_snapshot.get("selected_keywords") or [],
                            expert_config_code=(unified.input_snapshot.get("expert") or {}).get("expert_config_code"),
                            returned_items=[],
                            selected_index=int(
                                ((item.plan_json or {}).get("multi_output_group") or {}).get("selected_index") or 0
                            ),
                        )
                    item.error_message = str(exc)
                await db.commit()
                return _ItemExecutionResult(
                    item_id=item_id,
                    generated=False,
                    failed=True,
                    generated_count=0,
                    failed_count=output_count,
                )

    async def _watch_similar_generated_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == batch_id, ContentBatchItem.status == "generated")
                .order_by(ContentBatchItem.item_no)
            )
            items = list(result.scalars().all())
            history_items = await self._history_items_for_similarity(db, job)
            watch_count = 0
            for index, item in enumerate(items):
                if _is_postprocess_blocked(item) or not item.body:
                    continue
                best_match = self._most_similar_candidate(item, [*items[:index], *history_items])
                if not best_match or best_match["score"] < self._similarity_threshold(best_match):
                    continue
                quality = dict(item.quality_json or {})
                watches = list(quality.get("similarity_watch") or [])
                watch_payload = {
                    **self._similarity_rewrite_meta(item, best_match),
                    "watch": True,
                    "rewrite_required": False,
                }
                if not any(
                    isinstance(existing, dict)
                    and existing.get("similar_item_no") == watch_payload["similar_item_no"]
                    and existing.get("scope") == watch_payload["scope"]
                    and existing.get("similar_batch_id") == watch_payload["similar_batch_id"]
                    for existing in watches
                ):
                    watches.append(watch_payload)
                quality["similarity_watch"] = watches
                review_report = dict(quality.get("review_report") or {})
                review_report["similarity_watch"] = watches
                quality["review_report"] = review_report
                item.quality_json = quality
                watch_count += 1
            if watch_count:
                await db.commit()
            return watch_count

    async def _repair_article_length_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async def worker(item_id: int) -> int:
            async with self.session_factory() as db:
                item = await self._require_item(db, item_id)
                if item.status != "generated" or not item.run_id:
                    return 0
                repair = self._repair_article_length_if_needed(item)
                if not repair:
                    return 0
                quality = dict(item.quality_json or {})
                quality["article_length_guard"] = repair
                item.quality_json = quality
                await db.commit()
                return 1

        return await self._run_generated_item_workers(batch_id, worker)

    async def _rewrite_ai_flavor_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async def worker(item_id: int) -> int:
            async with self.session_factory() as db:
                item = await self._require_item(db, item_id)
                if item.status != "generated":
                    return 0
                if _is_postprocess_blocked(item):
                    return 0
                if (
                    _should_review_product_experience_llm_quality(item.plan_json)
                    and not _is_current_wangyue_article_plan(item.plan_json)
                ):
                    return 0
                rewrite_count = 0
                review_count = 0
                orchestrator = ContentAgentOrchestrator(
                    db,
                    invocation_client=self.invocation_client,
                    callback_base_url=self.callback_base_url,
                )
                review = review_ai_flavor(title=item.title, body=item.body, plan=item.plan_json)
                self._mark_ai_flavor_review(item, review)
                review_count += 1
                while review.rewrite_required and self._ai_flavor_rewrite_rounds(item) < MAX_AI_FLAVOR_REWRITE_ROUNDS:
                    if not item.run_id or not item.body:
                        break
                    rewritten = await self._rewrite_item_for_ai_flavor(
                        item,
                        review,
                        orchestrator=orchestrator,
                    )
                    if not rewritten:
                        break
                    rewrite_count += 1
                    review = review_ai_flavor(title=item.title, body=item.body, plan=item.plan_json)
                if review_count or rewrite_count:
                    await db.commit()
                return rewrite_count

        return await self._run_generated_item_workers(batch_id, worker)

    async def _rewrite_item_for_ai_flavor(
        self,
        item: ContentBatchItem,
        review: AIFlavorReview,
        *,
        orchestrator: ContentAgentOrchestrator,
    ) -> bool:
        if not item.run_id or not item.body:
            return False
        try:
            input_payload = self._ai_flavor_rewrite_input(item, review)
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
            if _is_ai_flavor_title_only_review(review):
                body = before["body"]
            body = _preserve_rewrite_paragraphs(before["body"], body, item.plan_json)
            after = {"title": title, "body": body}
            if _rewrite_removed_required_wangyue_product(before, after, item.plan_json):
                raise ValueError("rewrite_removed_required_wangyue_product")
            item.title = title
            item.body = body
            post_review = review_ai_flavor(title=item.title, body=item.body, plan=item.plan_json)
            quality = dict(item.quality_json or {})
            rewrites = list(quality.get("ai_flavor_humanizer_rewrites") or [])
            rewrites.append(
                {
                    "pre_review": review.model_dump(),
                    "post_review": post_review.model_dump(),
                    "before": before,
                    "after": {"title": item.title, "body": item.body},
                    "passed": post_review.pass_,
                    "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                }
            )
            quality["ai_flavor_humanizer_rewrites"] = rewrites
            quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + len(result.stage_calls)
            quality["run_status"] = result.run.status
            item.quality_json = quality
            self._mark_ai_flavor_review(item, post_review)
            forbidden_review = await self._repair_forbidden_terms_after_post_rewrite(
                item,
                orchestrator=orchestrator,
            )
            if forbidden_review and forbidden_review.get("final_hits"):
                self._mark_forbidden_term_blocking_failure(
                    item,
                    list(forbidden_review.get("final_hits") or []),
                )
                await orchestrator.db.flush()
                return False
            if forbidden_review and forbidden_review.get("initial_hits"):
                post_review = review_ai_flavor(title=item.title, body=item.body, plan=item.plan_json)
                self._mark_ai_flavor_review(item, post_review)
            blocked = False
            if should_review_product_experience(item.plan_json):
                phrase_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                phrase_review = await self._repair_product_experience_phrase_after_post_rewrite(
                    orchestrator.db,
                    item,
                    phrase_review,
                    cleanup_key_prefix="ai_flavor",
                )
                if _has_blocking_product_experience_phrase_review(phrase_review):
                    self._mark_product_experience_blocking_failure(
                        item,
                        phrase_review,
                        source="ai_flavor_humanizer",
                    )
                    blocked = True
                else:
                    self._mark_product_experience_phrase_review(item, phrase_review)
            if not blocked:
                item.error_message = None
            await orchestrator.db.flush()
            return not blocked
        except Exception as exc:  # noqa: BLE001 - keep generated content if humanizer fails
            quality = dict(item.quality_json or {})
            failures = list(quality.get("ai_flavor_humanizer_failures") or [])
            failures.append({"review": review.model_dump(), "error_message": str(exc)})
            quality["ai_flavor_humanizer_failures"] = failures
            item.quality_json = quality
            await orchestrator.db.flush()
            return False

    async def _repair_forbidden_terms_after_post_rewrite(
        self,
        item: ContentBatchItem,
        *,
        orchestrator: ContentAgentOrchestrator,
    ) -> dict[str, Any] | None:
        service = ForbiddenTermReviewService(orchestrator.db)
        audit = await service.audit_text(
            asset_key=item.plan_json.get("asset_key"),
            title=item.title,
            body=item.body,
        )
        if not audit.hits:
            return None
        return await service.review_and_rewrite_item(
            item=item,
            asset_key=item.plan_json.get("asset_key"),
            orchestrator=orchestrator,
            executor_code=self.executor_code,
            content_type="article",
        )

    async def _repair_product_experience_phrase_after_post_rewrite(
        self,
        db: AsyncSession,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
        *,
        cleanup_key_prefix: str,
    ) -> ProductExperiencePhraseReview:
        if _has_no_rewrite_product_experience_phrase_review(review):
            return review
        cleanup_applied = False
        if review.temporal_context_hits:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key=f"{cleanup_key_prefix}_temporal_context_cleanups",
                title=sanitize_temporal_context(item.title or ""),
                body=sanitize_temporal_context(item.body or ""),
            )
            cleanup_applied = True
        if "formula_dry_powder_ingestion" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key=f"{cleanup_key_prefix}_formula_dry_powder_cleanups",
                title=sanitize_formula_dry_powder_ingestion(item.title or ""),
                body=sanitize_formula_dry_powder_ingestion(item.body or ""),
            )
            cleanup_applied = True
        if "formula_usage_form_error" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key=f"{cleanup_key_prefix}_formula_usage_form_cleanups",
                title=sanitize_wangyue_formula_usage_form(item.title or ""),
                body=sanitize_wangyue_formula_usage_form(item.body or ""),
            )
            cleanup_applied = True
        if "wangyue_time_event_context" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key=f"{cleanup_key_prefix}_wangyue_time_event_cleanups",
                title=sanitize_wangyue_time_event_context(item.title or ""),
                body=sanitize_wangyue_time_event_context(item.body or ""),
            )
            cleanup_applied = True
        if "wangyue_digestive_effect_context" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key=f"{cleanup_key_prefix}_wangyue_digestive_effect_cleanups",
                title=sanitize_wangyue_context_phrases(item.title or ""),
                body=sanitize_wangyue_context_phrases(item.body or ""),
            )
            cleanup_applied = True

        review_for_llm = (
            _append_product_experience_review_reason(review, POST_DELETE_CLEANUP_FLUENCY_REASON)
            if cleanup_applied
            else review
        )
        should_model_repair = cleanup_applied or _has_blocking_product_experience_phrase_review(review_for_llm)
        if (
            should_model_repair
            and review_for_llm.rewrite_required
            and self._product_experience_phrase_rewrite_rounds(item) < MAX_PRODUCT_EXPERIENCE_PHRASE_REWRITE_ROUNDS
        ):
            rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review_for_llm)
            if rewritten:
                return review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
            return review_for_llm
        return review

    def _ai_flavor_rewrite_input(self, item: ContentBatchItem, review: AIFlavorReview) -> dict[str, Any]:
        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        rewrite_round = self._ai_flavor_rewrite_rounds(item) + 1
        return {
            "previous_content": {"title": item.title or "", "body": item.body or ""},
            "content_type": "article",
            "output_fields": ["title", "body"],
            "business_rule": rewrite_business_rule_context(item.plan_json),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "model_config": dict((item.plan_json or {}).get("model_config") or {}),
            "rewrite_source": "ai_flavor_humanizer",
            "review_report": {
                "rewrite_required": True,
                "rewrite_reason": "AI 味 / 解释腔 / 标题卖点前置",
                "ai_flavor_review": review.model_dump(),
            },
            "rewrite_round": rewrite_round,
            "rewrite_instructions": [
                "按 great-writer humanizer 四步改：口语检验、密度与节奏、AI 痕迹清除、反风格检查。",
                "硬性验收：改写后的 title/body 不能再命中本轮 ai_flavor_review 里的 title_hits/body_hits；如果 title_hits 有词，标题必须避开这些词。",
                "标题只写生活入口、孩子动作、妈妈状态或一个很短的场景碎片；标题不要出现产品卖点词、成分词、风险结果词，也不要写“选奶看了XX/关注XX”这种运营概括。",
                "正文保留原业务意图、产品事实和合规边界；不要新增功效承诺、治疗、预防、确定改善、少请假、不生病、注意力变好、长高长肉。",
                "不可新增清单：不要新增时间/季节/季节性活动节点，不要新增疾病或大环境，不要新增产品使用动作，不要新增成分到效果的新因果，不要新增年龄阶段事实，不要新增购买/囤货/复购链路。",
                "硬性验收：如果原文已经出现本篇产品名或品牌名，改写后正文必须仍明确保留；真人润色只改表达，不能把产品从正文里洗掉。",
                "删掉审核腔和自我辩解句，例如“不是说喝了就怎样/没指望喝了就/不会说喝了就/目前还在观察/说不上有没有用/不能指望一罐奶粉”。合规边界靠不写功效承诺解决，不要在正文里显性声明。",
                "改写后仍要正面表达产品：只保留原文已有的一个真实可用产品依据或使用感；不要新增产品动作、补货动作或价格取舍。",
                "把解释腔改成生活场景：少解释为什么好，多写一个具体处境、动作或妈妈当时怎么想。",
                "罗列太密时只保留一个最强产品依据，其余删掉或变成一句背景；不要堆参数和成分。",
                "节奏打散：长短句交错，允许一点省略和补充，不要每句都完整闭环。",
                "如果是选奶/选择复盘型，正文压成一个生活入口 + 一个正向选择依据 + 一个非价格的现实细节；不要写完整广告复盘，也不要用“不敢说有效”来制造真实感。",
                "标题不要替正文交代选择逻辑；把“我认真看了阶段/选择依据/重点关注”这类高解释义务标题，改成低义务生活碎片或名词短语。",
                "正文结尾不要太会总结，不要用“只能说/不算满分推荐/每家情况不一样/看自己需求/有个底/心里稳点/没觉得选错/后面再看/继续观察”连续收束；能停在生活动作、补货动作或一个正向细节就停。",
                "正文段落服从业务规则；原文已有自然换行时尽量保留，不要为了改写压成单段，也不要为了换行硬拆句。",
                "只输出 JSON：title, body。",
            ],
        }

    def _ai_flavor_rewrite_rounds(self, item: ContentBatchItem) -> int:
        quality = dict(item.quality_json or {})
        return len(quality.get("ai_flavor_humanizer_rewrites") or [])

    async def _rewrite_product_experience_llm_quality_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async def worker(item_id: int) -> int:
            async with self.session_factory() as db:
                item = await self._require_item(db, item_id)
                if item.status != "generated" or not _should_review_product_experience_llm_quality(item.plan_json):
                    return 0
                if _is_postprocess_blocked(item):
                    return 0
                rewrite_count = 0
                review_count = 0
                orchestrator = ContentAgentOrchestrator(
                    db,
                    invocation_client=self.invocation_client,
                    callback_base_url=self.callback_base_url,
                )
                phrase_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                ai_flavor_review = review_ai_flavor(title=item.title, body=item.body, plan=item.plan_json)
                self._mark_ai_flavor_review(item, ai_flavor_review)
                review_plan = await self._plan_with_provider_config_for_llm_review(
                    item.plan_json,
                    orchestrator=orchestrator,
                )
                try:
                    review = await self.product_experience_llm_reviewer.review(
                        title=item.title,
                        body=item.body,
                        plan=review_plan,
                        phrase_review=phrase_review,
                        ai_flavor_review=ai_flavor_review,
                    )
                except Exception as exc:  # noqa: BLE001 - keep generated content if reviewer is unavailable
                    self._mark_product_experience_llm_review_failure(item, str(exc))
                    review_count += 1
                    if ai_flavor_review.rewrite_required and item.run_id and item.body:
                        rewritten = await self._rewrite_item_for_ai_flavor(
                            item,
                            ai_flavor_review,
                            orchestrator=orchestrator,
                        )
                        if rewritten:
                            rewrite_count += 1
                    await db.commit()
                    return rewrite_count
                self._mark_product_experience_llm_review(
                    item,
                    review,
                    mark_rewrite_required=_should_repair_product_experience_llm_quality(item.plan_json, review),
                )
                review_count += 1

                async def refresh_reviews() -> bool:
                    nonlocal ai_flavor_review, review, review_count
                    phrase_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                    ai_flavor_review = review_ai_flavor(title=item.title, body=item.body, plan=item.plan_json)
                    self._mark_ai_flavor_review(item, ai_flavor_review)
                    review_plan = await self._plan_with_provider_config_for_llm_review(
                        item.plan_json,
                        orchestrator=orchestrator,
                    )
                    try:
                        review = await self.product_experience_llm_reviewer.review(
                            title=item.title,
                            body=item.body,
                            plan=review_plan,
                            phrase_review=phrase_review,
                            ai_flavor_review=ai_flavor_review,
                        )
                    except Exception as exc:  # noqa: BLE001 - keep rewritten content if re-review fails
                        self._mark_product_experience_llm_review_failure(item, str(exc))
                        return False
                    self._mark_product_experience_llm_review(
                        item,
                        review,
                        mark_rewrite_required=_should_repair_product_experience_llm_quality(item.plan_json, review),
                    )
                    review_count += 1
                    return True

                while True:
                    if _should_repair_product_experience_llm_quality(item.plan_json, review):
                        if self._product_experience_llm_rewrite_rounds(item) >= _max_product_experience_llm_rewrite_rounds(
                            item.plan_json
                        ):
                            break
                        if not item.run_id or not item.body:
                            break
                        rewritten = await self._rewrite_item_for_product_experience_llm_quality(
                            item,
                            review,
                            orchestrator=orchestrator,
                        )
                        if not rewritten:
                            break
                        rewrite_count += 1
                        if not await refresh_reviews():
                            break
                        continue
                    if not ai_flavor_review.rewrite_required:
                        break
                    if self._ai_flavor_rewrite_rounds(item) >= MAX_AI_FLAVOR_REWRITE_ROUNDS:
                        break
                    if not item.run_id or not item.body:
                        break
                    rewritten = await self._rewrite_item_for_ai_flavor(
                        item,
                        ai_flavor_review,
                        orchestrator=orchestrator,
                    )
                    if not rewritten:
                        break
                    rewrite_count += 1
                    if not await refresh_reviews():
                        break
                if review_count or rewrite_count:
                    await db.commit()
                return rewrite_count

        return await self._run_generated_item_workers(batch_id, worker)

    async def _review_royal_friso_structure_items(self, batch_id: int, job: ContentBatchJob) -> int:
        guard = RoyalFrisoUGCStructureGuardService()

        async def worker(item_id: int) -> int:
            async with self.session_factory() as db:
                item = await self._require_item(db, item_id)
                if item.status != "generated" or _is_postprocess_blocked(item):
                    return 0
                review = guard.review(title=item.title, body=item.body, plan=item.plan_json)
                if review is None:
                    return 0
                self._mark_royal_friso_structure_review(item, review)
                if review.rewrite_required:
                    self._mark_royal_friso_structure_blocking_failure(item, review)
                await db.commit()
                return 0

        return await self._run_generated_item_workers(batch_id, worker)

    async def _plan_with_provider_config_for_llm_review(
        self,
        plan: dict[str, Any] | None,
        *,
        orchestrator: ContentAgentOrchestrator,
    ) -> dict[str, Any]:
        """Attach transient provider credentials for the LLM reviewer only."""
        plan = dict(plan or {})
        unified_generation = plan.get("unified_generation") or {}
        expert = unified_generation.get("expert") or {}
        model_config = dict(
            plan.get("model_config")
            or unified_generation.get("model_config")
            or expert.get("model_config")
            or {}
        )
        if not model_config:
            return plan
        payload = await orchestrator._input_payload_with_provider_config({"model_config": model_config})
        hydrated_model_config = payload.get("model_config") if isinstance(payload, dict) else None
        if not isinstance(hydrated_model_config, dict):
            return plan
        return {**plan, "model_config": hydrated_model_config}

    async def _rewrite_item_for_product_experience_llm_quality(
        self,
        item: ContentBatchItem,
        review: ProductExperienceLLMReview,
        *,
        orchestrator: ContentAgentOrchestrator,
    ) -> bool:
        if not item.run_id or not item.body:
            return False
        before = {"title": item.title or "", "body": item.body or ""}
        input_payload = self._product_experience_llm_quality_rewrite_input(item, review)
        validator_feedback = ""
        stage_call_count = 0
        try:
            for attempt in range(1, 3):
                attempt_payload = input_payload
                if validator_feedback:
                    attempt_payload = {
                        **input_payload,
                        "rewrite_instructions": [
                            *list(input_payload.get("rewrite_instructions") or []),
                            f"上一个候选未通过改写验收：{validator_feedback}。本轮只修正这个问题，不要扩写。",
                        ],
                    }
                result = await orchestrator.run_content_rewrite_stage(
                    run_id=item.run_id,
                    executor_code=self.executor_code,
                    input_payload=attempt_payload,
                )
                stage_call_count += len(result.stage_calls)
                final = result.output or {}
                final_content = final.get("final") if isinstance(final.get("final"), dict) else {}
                title = str(final.get("title") or final_content.get("title") or "").strip()
                body = str(final.get("body") or final_content.get("body") or "").strip()
                if not title or not body:
                    raise ValueError("content.rewrite returned empty article")
                body = _preserve_rewrite_paragraphs(before["body"], body, item.plan_json)
                after = {"title": title, "body": body}
                if _rewrite_removed_required_wangyue_product(before, after, item.plan_json):
                    raise ValueError("rewrite_removed_required_wangyue_product")
                try:
                    validation = await self._validate_product_experience_llm_rewrite_candidate(
                        item=item,
                        orchestrator=orchestrator,
                        before=before,
                        after=after,
                        review=review,
                        rewrite_source=str(attempt_payload.get("rewrite_source") or ""),
                    )
                except Exception as exc:  # noqa: BLE001 - unavailable validator must not auto-accept
                    self._mark_rewrite_quality_validation_failure(
                        item,
                        reason="改写后验收不可用，禁止自动写回",
                    )
                    raise ValueError(f"rewrite_quality_validation_unavailable: {exc}") from exc
                self._record_rewrite_quality_validation(
                    item,
                    validation=validation,
                    before=before,
                    after=after,
                    attempt=attempt,
                    stage_call_ids=[stage.stage_call_id for stage in result.stage_calls],
                )
                if validation.label == "reject":
                    self._mark_rewrite_quality_validation_failure(
                        item,
                        reason="改写候选引入流畅性、语义连续或事实保留问题，需要人工复核",
                    )
                    await orchestrator.db.flush()
                    return False
                if validation.label == "retry":
                    validator_feedback = validation.evidence or validation.issue_code
                    continue

                item.title = title
                item.body = body
                phrase_review = review_product_experience_phrase(
                    title=item.title,
                    body=item.body,
                    plan=item.plan_json,
                )
                quality = dict(item.quality_json or {})
                rewrites = list(quality.get("product_experience_llm_quality_rewrites") or [])
                rewrites.append(
                    {
                        "pre_review": review.model_dump(),
                        "before": before,
                        "after": {"title": item.title, "body": item.body},
                        "rewrite_source": attempt_payload.get("rewrite_source"),
                        "rewrite_mode": attempt_payload.get("rewrite_mode"),
                        "rewrite_quality_validation": validation.model_dump(),
                        "phrase_review_after_rewrite": phrase_review.model_dump(),
                        "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                    }
                )
                quality["product_experience_llm_quality_rewrites"] = rewrites
                quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + stage_call_count
                quality["run_status"] = result.run.status
                item.quality_json = quality
                self._mark_product_experience_phrase_review(item, phrase_review)
                item.error_message = None
                await orchestrator.db.flush()
                return True

            self._mark_rewrite_quality_validation_failure(
                item,
                reason="改写候选连续两次未通过验收，需要人工复核",
            )
            await orchestrator.db.flush()
            return False
        except Exception as exc:  # noqa: BLE001 - keep generated content if quality rewrite fails
            quality = dict(item.quality_json or {})
            failures = list(quality.get("product_experience_llm_quality_failures") or [])
            failures.append({"review": review.model_dump(), "error_message": str(exc)})
            quality["product_experience_llm_quality_failures"] = failures
            item.quality_json = quality
            await orchestrator.db.flush()
            return False

    async def _validate_product_experience_llm_rewrite_candidate(
        self,
        *,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator,
        before: dict[str, str],
        after: dict[str, str],
        review: ProductExperienceLLMReview,
        rewrite_source: str,
    ) -> RewriteQualityJudgment:
        review_plan = await self._rewrite_quality_plan_with_provider_config(
            orchestrator=orchestrator,
        )
        return await self.rewrite_quality_validator.review(
            before=before,
            after=after,
            rewrite_source=rewrite_source,
            target_issue="、".join(issue.code for issue in review.issues),
            plan=review_plan,
        )

    async def _rewrite_quality_plan_with_provider_config(
        self,
        *,
        orchestrator: ContentAgentOrchestrator,
    ) -> dict[str, Any]:
        return await self._plan_with_provider_config_for_llm_review(
            {"model_config": {"model_code": REWRITE_QUALITY_MODEL_CODE}},
            orchestrator=orchestrator,
        )

    def _product_experience_llm_quality_rewrite_input(
        self,
        item: ContentBatchItem,
        review: ProductExperienceLLMReview,
    ) -> dict[str, Any]:
        if _is_current_wangyue_article_plan(item.plan_json):
            mode = _product_experience_rewrite_mode(review)
            if mode == "compliance_cleanup":
                return self._product_experience_compliance_cleanup_input(item, review)
            if mode == "fluency_humanize":
                return self._product_experience_fluency_humanize_input(item, review)

        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        issue_lines = [
            f"{issue.code}: {issue.evidence}；原因：{issue.reason}"
            for issue in review.issues
        ]
        issue_codes = {issue.code for issue in review.issues}
        age_stage_instruction = (
            "本轮命中产品年龄事实硬错误：必须把孩子使用、购买或备着产品的时间关系改到业务规则允许的年龄阶段。"
            "删除断奶、辅食、一两岁、未满三岁、三岁前开始喝这类链路；保留原文一个正向产品价值或效果证明。"
            "不要机械替换年龄词导致残句，也不要完整复述成“3岁以上4段儿童奶粉”。"
            if "wangyue_age_stage_error" in issue_codes
            else "产品年龄事实必须按业务规则正确：不要新增低龄、断奶、辅食、前序段位或未到适用年龄就开始喝的链路。"
        )
        return {
            "previous_content": {"title": item.title or "", "body": item.body or ""},
            "content_type": "article",
            "output_fields": ["title", "body"],
            "business_rule": rewrite_business_rule_context(item.plan_json),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "model_config": dict((item.plan_json or {}).get("model_config") or {}),
            "rewrite_source": "product_experience_llm_quality_review",
            "review_report": {
                "rewrite_required": True,
                "rewrite_reason": "LLM 判断产品出现/决策链/真人感需要改写",
                "product_experience_llm_review": review.model_dump(),
            },
            "rewrite_round": self._product_experience_llm_rewrite_rounds(item) + 1,
            "rewrite_instructions": [
                "按 LLM 质检意见局部改写，不要整篇重写成新广告。",
                "本轮问题：" + ("；".join(issue_lines) if issue_lines else review.overall_reason),
                f"业务入池档位：{review.business_usability_tier}；原因：{review.business_usability_reason or review.overall_reason}。",
                "如果是 light_fix_usable，只做轻修：修错字、断句、病句、旧模板词、轻微强因果或安全降调；保留原种草内核和强正向产品价值，不要整篇重写。",
                "如果是 hold_out，优先修事实错误、产品形态错误、医疗/保证倾向或文本断裂；修不顺就宁可保留问题标记，不要编新事实。",
                "质检问题只用于定位，不要照搬质检里的压缩式改写方向；尤其不要因为有完整链路问题就机械删到只剩产品和一个反馈。",
                age_stage_instruction,
                "核心目标：保留本篇产品一个明确、正向、可种草的产品价值；效果证明可以保留为主种草点。改写只处理已被质检指出的广告链、突兀产品出现或模板腔，不把正文压缩成提纲。",
                "硬性验收：如果原文已经出现本篇产品名或品牌名，改写后正文必须仍明确保留；可以删多余解释，但不能把产品从正文里洗掉。",
                "删除节点要克制：优先删多余产品解释、重复卖点、妈妈安心收口或促销式结论；保留生活入口、发帖动作、一个具体场景细节和一个正向反馈。",
                "不要新增冲泡、加进牛奶、早餐搭配、每天喝、孩子喝完、孩子接受这类产品动作；如果原文没有这些动作，不要为了自然感补出来。",
                "不要用“还在观察、不能指望一罐奶粉、每家孩子不一样、不敢说有效”这类不确定声明替代产品价值。",
                "按帖子类型纠偏，而不是削短：复购/长期使用围绕补货和一个没断原因；问题解决保留生活困扰和产品作为处理链路一环；使用反馈保留当前安排、场景细节和一个感受；轻测评保留一个观察点和提到它的生活语境；对比选择保留一个选择依据和一个取舍。",
                "如果原正文已经超过80字，改写后也尽量保持80字以上；需要删广告链时，用生活细节或发帖动作补回自然密度，但不要新增第二个产品卖点或第二个效果证明。",
                "标题低义务，优先生活入口、短名词、动作碎片；不要把卖点和完整决策写进标题。",
                "正文段落服从业务规则；原文已有自然换行时尽量保留，不要为了改写压成单段，也不要为了换行硬拆句。",
                "只输出 JSON：title, body。",
            ],
        }

    def _product_experience_compliance_cleanup_input(
        self,
        item: ContentBatchItem,
        review: ProductExperienceLLMReview,
    ) -> dict[str, Any]:
        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        issue_lines = [
            f"{issue.code}: {issue.evidence}；原因：{issue.reason}"
            for issue in review.issues
            if issue.code in PRODUCT_EXPERIENCE_COMPLIANCE_ISSUE_CODES
        ]
        return {
            "previous_content": {"title": item.title or "", "body": item.body or ""},
            "content_type": "article",
            "output_fields": ["title", "body"],
            "business_rule": rewrite_business_rule_context(item.plan_json),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "model_config": dict((item.plan_json or {}).get("model_config") or {}),
            "rewrite_source": "product_experience_compliance_cleanup",
            "rewrite_mode": "compliance_cleanup",
            "review_report": {
                "rewrite_required": True,
                "rewrite_reason": "删除明确不合规内容",
                "product_experience_llm_review": review.model_dump(),
            },
            "rewrite_round": self._product_experience_llm_rewrite_rounds(item) + 1,
            "rewrite_instructions": [
                "只处理下面明确指出的不合规片段，不做文风优化，不重写整篇。",
                "本轮问题：" + ("；".join(issue_lines) if issue_lines else review.overall_reason),
                "优先直接删除违规短语、分句或错误事实连接；删掉后句子不通时，只补最短的连接词。",
                "不得新增生活场景、产品动作、使用频次、孩子反馈、妈妈情绪、成分功效或任何原文没有的事实。",
                "保留原文标题、叙事顺序、正常口语、产品名和正确产品依据；不顺手处理广告感、模板感或表达风格。",
                "公共疾病环境对照直接删除；睡眠等卖点错配只删除对应效果；产品动作或事实错误只修错误处。",
                "硬违禁词不在本阶段改写范围内；如果输入仍含硬违禁词，不要用同义词绕过。",
                "正文段落服从业务规则；原文已有自然换行时尽量保留，不要为了改写压成单段，也不要为了换行硬拆句。",
                "只输出 JSON：title, body。",
            ],
        }

    def _product_experience_fluency_humanize_input(
        self,
        item: ContentBatchItem,
        review: ProductExperienceLLMReview,
    ) -> dict[str, Any]:
        unified_generation = (item.plan_json or {}).get("unified_generation") or {}
        issue_lines = [
            f"{issue.code}: {issue.evidence}；原因：{issue.reason}"
            for issue in review.issues
            if issue.code in PRODUCT_EXPERIENCE_FLUENCY_ISSUE_CODES
        ]
        return {
            "previous_content": {"title": item.title or "", "body": item.body or ""},
            "content_type": "article",
            "output_fields": ["title", "body"],
            "business_rule": rewrite_business_rule_context(item.plan_json),
            "selected_keywords": unified_generation.get("selected_keywords") or [],
            "model_config": dict((item.plan_json or {}).get("model_config") or {}),
            "rewrite_source": "product_experience_fluency_humanize",
            "rewrite_mode": "fluency_humanize",
            "review_report": {
                "rewrite_required": True,
                "rewrite_reason": "局部流畅性改写",
                "product_experience_llm_review": review.model_dump(),
            },
            "rewrite_round": self._product_experience_llm_rewrite_rounds(item) + 1,
            "rewrite_instructions": [
                "按‘说人话’的 minimal + in-place 方式局部改写，只修病句、任务腔、翻译腔、突兀转折或生硬产品出现。",
                "本轮问题：" + ("；".join(issue_lines) if issue_lines else review.overall_reason),
                "保护原文事实：品牌、成分、人物、时间、数量、产品动作、生活事件和正向反馈都不能新增、删除或改义。",
                "尽量保持原句序、段落和叙事节奏；不把整篇抛光成统一模板，不补新的开头、结尾、感叹或总结。",
                "具体动作优先于抽象总结；删除元话术和任务说明感，但允许普通句子、轻微口语和不完全对称的节奏存在。",
                "不要用同义词替换制造假口语，不新增‘省心、踏实、选对了、值得、继续喝’等收口。",
                "正文段落服从业务规则；原文已有自然换行时尽量保留，不要为了改写压成单段，也不要为了换行硬拆句。",
                "只输出 JSON：title, body。",
            ],
        }

    def _product_experience_llm_rewrite_rounds(self, item: ContentBatchItem) -> int:
        quality = dict(item.quality_json or {})
        return len(quality.get("product_experience_llm_quality_rewrites") or [])

    def _mark_product_experience_llm_review(
        self,
        item: ContentBatchItem,
        review: ProductExperienceLLMReview,
        *,
        mark_rewrite_required: bool | None = None,
    ) -> None:
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        review_report["product_experience_llm_review"] = review.model_dump()
        should_mark_rewrite = review.rewrite_required if mark_rewrite_required is None else mark_rewrite_required
        if should_mark_rewrite:
            review_report.update(
                {
                    "rewrite_required": True,
                    "rewrite_reason": "LLM 判断产品出现/决策链/真人感需要改写",
                }
            )
        elif str(review_report.get("rewrite_reason") or "").startswith("LLM 判断产品出现"):
            review_report["rewrite_required"] = False
            review_report.pop("rewrite_reason", None)
        quality["review_report"] = review_report
        quality["product_experience_llm_quality_review"] = {
            "pass": review.pass_,
            "rewrite_required": review.rewrite_required,
            "mark_rewrite_required": should_mark_rewrite,
            "severity": review.severity,
            "business_usability_tier": review.business_usability_tier,
            "business_usability_reason": review.business_usability_reason,
            "issues": [issue.code for issue in review.issues],
            "scores": {
                "product_appearance_naturalness": review.product_appearance_naturalness,
                "decision_chain_fit": review.decision_chain_fit,
                "product_value_strength": review.product_value_strength,
                "human_realness": review.human_realness,
            },
        }
        item.quality_json = quality

    def _mark_product_experience_llm_review_failure(self, item: ContentBatchItem, error_message: str) -> None:
        quality = dict(item.quality_json or {})
        failures = list(quality.get("product_experience_llm_quality_failures") or [])
        failures.append({"error_message": error_message})
        quality["product_experience_llm_quality_failures"] = failures
        if _is_current_wangyue_article_plan(item.plan_json):
            quality["product_experience_llm_quality_review_unavailable_mark_only"] = True
            if quality.get("product_experience_llm_quality_rewrites"):
                quality["product_experience_llm_quality_review"] = {
                    "pass": False,
                    "rewrite_required": False,
                    "mark_rewrite_required": False,
                    "severity": "unavailable",
                    "business_usability_tier": "watch",
                    "business_usability_reason": "改写后 LLM 审核不可用，保留最终正文并进入 watch。",
                    "issues": [],
                    "scores": {},
                }
                review_report = dict(quality.get("review_report") or {})
                if str(review_report.get("rewrite_reason") or "").startswith("LLM 判断产品出现"):
                    review_report["rewrite_required"] = False
                    review_report.pop("rewrite_reason", None)
                review_report["product_experience_llm_review_unavailable_after_rewrite"] = {
                    "error_message": error_message,
                    "watch": True,
                }
                quality["review_report"] = review_report
        item.quality_json = quality

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

    @staticmethod
    def _repair_article_length_if_needed(
        item: ContentBatchItem,
    ) -> dict[str, Any] | None:
        min_chars = 30
        max_chars = 600
        body = item.body or ""
        body_chars = _compact_len(body)
        full_text = f"{item.title or ''}\n{body}"
        reasoning_leak = "<think" in full_text.lower()
        if not reasoning_leak and min_chars <= body_chars <= max_chars:
            return None

        if reasoning_leak:
            status = "reasoning_leak"
            reason = "正文包含模型推理泄露，疑似生成异常"
        elif body_chars < min_chars:
            status = "extreme_short"
            reason = "正文过短，疑似生成异常"
        else:
            status = "extreme_long"
            reason = "正文过长，疑似生成异常"

        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        review_report.update(
            {
                "rewrite_required": True,
                "rewrite_reason": reason,
            }
        )
        quality["review_report"] = review_report
        quality["hard_pass"] = False
        quality["postprocess_blocked"] = {
            "source": "article_length_guard",
            "reasons": [status],
            "hits": [],
        }
        item.quality_json = quality
        return {
            "pass": False,
            "status": status,
            "body_chars": body_chars,
            "min_chars": min_chars,
            "max_chars": max_chars,
            "rewrite_required": False,
            "manual_review_required": True,
            "reason": reason,
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
                if _is_postprocess_blocked(item):
                    continue
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
            metadata_changed = False
            for item in items:
                if _is_postprocess_blocked(item):
                    continue
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
                    watch_reasons = _title_guard_watch_reasons(item.title or "")
                    if watch_reasons:
                        quality = dict(item.quality_json or {})
                        watches = list(quality.get("title_guard_watch") or [])
                        watches.append({"title": item.title or "", "reasons": watch_reasons})
                        quality["title_guard_watch"] = watches
                        quality["title_guard"] = {
                            "pass": True,
                            "repair_count": len(quality.get("title_guard_repairs") or []),
                            "history_title_count": len(history_titles),
                            "watch_count": len(watches),
                        }
                        item.quality_json = quality
                        metadata_changed = True
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
            if repair_count or metadata_changed:
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
        async def worker(item_id: int) -> int:
            async with self.session_factory() as db:
                item = await self._require_item(db, item_id)
                if item.status != "generated" or not should_review_product_experience(item.plan_json):
                    return 0
                if _is_postprocess_blocked(item):
                    return 0
                review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                if _has_no_rewrite_product_experience_phrase_review(review):
                    self._mark_product_experience_blocking_failure(
                        item,
                        review,
                        source="product_experience_phrase_guard",
                        rewrite_attempted=False,
                    )
                    await db.commit()
                    return 0
                if _should_mark_only_product_experience_phrase_review(item.plan_json, review):
                    self._mark_product_experience_phrase_review(item, review, mark_rewrite_required=False)
                    await db.commit()
                    return 0
                rewrite_count = 0
                cleanup_applied = False
                if "formula_dry_powder_ingestion" in review.reasons:
                    review = self._apply_product_experience_text_cleanup(
                        item,
                        review,
                        cleanup_key="product_experience_formula_dry_powder_cleanups",
                        title=sanitize_formula_dry_powder_ingestion(item.title or ""),
                        body=sanitize_formula_dry_powder_ingestion(item.body or ""),
                    )
                    cleanup_applied = True
                if "formula_usage_form_error" in review.reasons:
                    review = self._apply_product_experience_text_cleanup(
                        item,
                        review,
                        cleanup_key="product_experience_formula_usage_form_cleanups",
                        title=sanitize_wangyue_formula_usage_form(item.title or ""),
                        body=sanitize_wangyue_formula_usage_form(item.body or ""),
                    )
                    cleanup_applied = True
                if "wangyue_time_event_context" in review.reasons:
                    review = self._apply_product_experience_text_cleanup(
                        item,
                        review,
                        cleanup_key="product_experience_wangyue_time_event_cleanups",
                        title=sanitize_wangyue_time_event_context(item.title or ""),
                        body=sanitize_wangyue_time_event_context(item.body or ""),
                    )
                    cleanup_applied = True
                if "wangyue_digestive_effect_context" in review.reasons:
                    review = self._apply_product_experience_text_cleanup(
                        item,
                        review,
                        cleanup_key="product_experience_wangyue_digestive_effect_cleanups",
                        title=sanitize_wangyue_context_phrases(item.title or ""),
                        body=sanitize_wangyue_context_phrases(item.body or ""),
                    )
                    cleanup_applied = True
                review_for_llm = (
                    _append_product_experience_review_reason(review, POST_DELETE_CLEANUP_FLUENCY_REASON)
                    if cleanup_applied
                    else review
                )
                if review_for_llm.rewrite_required:
                    rewritten = await self._rewrite_item_for_product_experience_phrase(db, item, review_for_llm)
                    if rewritten:
                        rewrite_count += 1
                        review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
                        if (
                            "child_self_brewing_formula" in review.reasons
                            or "child_formula_bottle_context" in review.reasons
                        ):
                            review = self._apply_product_experience_text_cleanup(
                                item,
                                review,
                                cleanup_key="product_experience_child_self_brewing_cleanups",
                                title=sanitize_baby_milk_action_phrases(item.title or ""),
                                body=sanitize_baby_milk_action_phrases(item.body or ""),
                            )
                        if (
                            "wangyue_growth_nutrition_drift_context" in review.reasons
                            and self._fallback_clean_wangyue_growth_nutrition_drift(item, review)
                        ):
                            review = review_product_experience_phrase(
                                title=item.title,
                                body=item.body,
                                plan=item.plan_json,
                            )
                    else:
                        review = review_for_llm
                if _has_blocking_product_experience_phrase_review(review):
                    self._mark_product_experience_blocking_failure(
                        item,
                        review,
                        source="product_experience_phrase_guard",
                    )
                    await db.commit()
                    return rewrite_count
                self._mark_product_experience_phrase_review(item, review)
                await db.commit()
                return rewrite_count

        return await self._run_generated_item_workers(batch_id, worker)

    async def _refresh_product_experience_phrase_reviews(self, batch_id: int, job: ContentBatchJob) -> int:
        async def worker(item_id: int) -> int:
            async with self.session_factory() as db:
                item = await self._require_item(db, item_id)
                if item.status != "generated" or not should_review_product_experience(item.plan_json):
                    return 0
                review = review_product_experience_phrase(
                    title=item.title,
                    body=item.body,
                    plan=item.plan_json,
                )
                self._mark_product_experience_phrase_review(item, review)
                await db.commit()
                return 1

        return await self._run_generated_item_workers(batch_id, worker)

    async def _rewrite_mouth_phrase_budget_items(self, batch_id: int, job: ContentBatchJob) -> int:
        async def worker(item_id: int) -> int:
            async with self.session_factory() as db:
                item = await self._require_item(db, item_id)
                if item.status != "generated":
                    return 0
                if _is_postprocess_blocked(item):
                    return 0
                rewrite_count = 0
                initial_hits = _mouth_phrase_budget_hits(item)
                if not initial_hits:
                    self._mark_mouth_phrase_budget_guard(item, initial_hits=[], final_hits=[])
                    await db.commit()
                    return 0
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
                await db.commit()
                return rewrite_count

        return await self._run_generated_item_workers(batch_id, worker)

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
            body = _preserve_rewrite_paragraphs(before["body"], body, item.plan_json)
            forbidden_audit = await ForbiddenTermReviewService(db).audit_text(
                asset_key=item.plan_json.get("asset_key"),
                title=title,
                body=body,
            )
            if forbidden_audit.hits:
                quality = dict(item.quality_json or {})
                failures = list(quality.get("mouth_phrase_budget_rewrite_failures") or [])
                failures.append(
                    {
                        "initial_hits": hits,
                        "error_message": "rewrite_introduced_forbidden_terms",
                        "forbidden_hits": forbidden_audit.hits,
                        "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                    }
                )
                quality["mouth_phrase_budget_rewrite_failures"] = failures
                quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + len(result.stage_calls)
                quality["run_status"] = result.run.status
                item.quality_json = quality
                await db.flush()
                return False
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
            before = {"title": item.title or "", "body": item.body or ""}
            validator_feedback = ""
            stage_call_count = 0
            for attempt in range(1, 3):
                input_payload = self._product_experience_phrase_rewrite_input(item, review)
                if validator_feedback:
                    input_payload["rewrite_instructions"] = [
                        *list(input_payload.get("rewrite_instructions") or []),
                        f"上一个候选未通过改写验收：{validator_feedback}。本轮只修正这个问题，不要扩写。",
                    ]
                result = await orchestrator.run_content_rewrite_stage(
                    run_id=item.run_id,
                    executor_code=self.executor_code,
                    input_payload=input_payload,
                )
                stage_call_count += len(result.stage_calls)
                final = result.output or {}
                final_content = final.get("final") if isinstance(final.get("final"), dict) else {}
                title = str(final.get("title") or final_content.get("title") or "").strip()
                body = str(final.get("body") or final_content.get("body") or "").strip()
                if not title or not body:
                    raise ValueError("content.rewrite returned empty article")
                body = _preserve_rewrite_paragraphs(before["body"], body, item.plan_json)
                after = {"title": title, "body": body}
                post_review = review_product_experience_phrase(title=title, body=body, plan=item.plan_json)
                if _has_blocking_product_experience_phrase_review(post_review):
                    quality = dict(item.quality_json or {})
                    rewrites = list(quality.get("product_experience_phrase_rewrites") or [])
                    rewrites.append(
                        {
                            "rewrite_round": self._product_experience_phrase_rewrite_rounds(item) + 1,
                            "before": before,
                            "after": after,
                            "pre_review": review.model_dump(),
                            "post_review": post_review.model_dump(),
                            "passed": False,
                            "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
                        }
                    )
                    quality["product_experience_phrase_rewrites"] = rewrites
                    quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + stage_call_count
                    quality["run_status"] = result.run.status
                    item.quality_json = quality
                    await db.flush()
                    return False
                validation = await self._validate_cleanup_rewrite_candidate(
                    item=item,
                    orchestrator=orchestrator,
                    before=before,
                    after=after,
                    review=review,
                )
                self._record_rewrite_quality_validation(
                    item,
                    validation=validation,
                    before=before,
                    after=after,
                    attempt=attempt,
                    stage_call_ids=[stage.stage_call_id for stage in result.stage_calls],
                )
                if validation is not None and validation.label == "reject":
                    self._mark_rewrite_quality_validation_failure(
                        item,
                        reason="改写候选引入流畅性、语义连续或事实保留问题，需要人工复核",
                    )
                    await db.flush()
                    return False
                if validation is not None and validation.label == "retry":
                    validator_feedback = validation.evidence or validation.issue_code
                    continue

                item.title = title
                item.body = body
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
                quality["stage_call_count"] = int(quality.get("stage_call_count") or 0) + stage_call_count
                quality["run_status"] = result.run.status
                item.quality_json = quality
                self._mark_product_experience_phrase_review(item, post_review)
                item.error_message = None
                await db.flush()
                return True

            self._mark_rewrite_quality_validation_failure(
                item,
                reason="改写候选连续两次未通过流畅性与语义验收，需要人工复核",
            )
            await db.flush()
            return False
        except Exception as exc:  # pragma: no cover - defensive path for flaky external workers
            quality = dict(item.quality_json or {})
            failures = list(quality.get("product_experience_phrase_rewrite_failures") or [])
            failures.append({"review": review.model_dump(), "error_message": str(exc)})
            quality["product_experience_phrase_rewrite_failures"] = failures
            item.quality_json = quality
            if POST_DELETE_CLEANUP_FLUENCY_REASON in review.reasons:
                self._mark_rewrite_quality_validation_failure(
                    item,
                    reason="改写后验收不可用，禁止自动放行",
                )
            await db.flush()
            return False

    async def _validate_cleanup_rewrite_candidate(
        self,
        *,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator,
        before: dict[str, str],
        after: dict[str, str],
        review: ProductExperiencePhraseReview,
    ) -> RewriteQualityJudgment | None:
        if POST_DELETE_CLEANUP_FLUENCY_REASON not in review.reasons or before == after:
            return None
        review_plan = await self._rewrite_quality_plan_with_provider_config(
            orchestrator=orchestrator,
        )
        return await self.rewrite_quality_validator.review(
            before=before,
            after=after,
            rewrite_source="product_experience_phrase_guard",
            target_issue="、".join(review.reasons),
            plan=review_plan,
        )

    @staticmethod
    def _record_rewrite_quality_validation(
        item: ContentBatchItem,
        *,
        validation: RewriteQualityJudgment | None,
        before: dict[str, str],
        after: dict[str, str],
        attempt: int,
        stage_call_ids: list[str],
    ) -> None:
        if validation is None:
            return
        quality = dict(item.quality_json or {})
        validations = list(quality.get("rewrite_quality_validations") or [])
        validations.append(
            {
                "attempt": attempt,
                "before": before,
                "after": after,
                "judgment": validation.model_dump(),
                "stage_call_ids": stage_call_ids,
            }
        )
        quality["rewrite_quality_validations"] = validations
        item.quality_json = quality

    @staticmethod
    def _mark_rewrite_quality_validation_failure(item: ContentBatchItem, *, reason: str) -> None:
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        review_report.update(
            {
                "rewrite_required": True,
                "rewrite_reason": reason,
                "rewrite_quality_validation_failed": True,
            }
        )
        quality["review_report"] = review_report
        quality["hard_pass"] = False
        quality["rewrite_quality_validation_watch"] = True
        item.quality_json = quality

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
                + review.hard_risk_hits
                + review.wangyue_article_logic_drift_hits
                + review.wangyue_portable_form_hits
                + review.wangyue_supplement_replacement_hits
                + review.wangyue_growth_nutrition_drift_hits
                + review.wangyue_child_product_promo_hits
                + review.wangyue_time_event_context_hits
                + review.wangyue_hidden_negative_comparison_hits
                + review.physical_action_carrier_mismatch_hits
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
        if "complete_selection_price_acceptance_closure_skeleton" in review.reasons:
            phrase_instruction = (
                f"本轮有链路密度信号：{hit_summary or '选择/价格/孩子接受/妈妈收口'}；"
                "这不是单篇硬伤。只有同时命中事实错误、隐性负面、广告收口或强因果风险时，才处理对应问题句；"
                "不要因为节点多就机械删掉正向产品价值或效果证明。"
            )
        elif hit_summary:
            phrase_instruction = (
                f"本轮有链路密度信号：{hit_summary}；它只用于提醒批量同质化。"
                "本轮改写只处理其它明确命中的硬问题，不要为了降链路密度削弱种草表达。"
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
        common_closure_instruction = (
            "本轮命中通用 AI 收口句式；优先删除含“继续观察、先这样、希望一直这样、松了口气、欢迎留言”等模板收口的半句。"
            "不要机械替换成另一个固定总结，也不要补新的妈妈安心式收口。"
            if "common_ai_closure_phrase" in review.reasons
            else "不要新增继续观察、先这样、希望一直这样、松了口气、欢迎留言这类通用 AI 收口。"
        )
        temporal_context_instruction = (
            "本轮命中明确时间语境："
            f"{'/'.join(review.temporal_context_hits)}。"
            "用模型改顺上下文，不要硬替换；核心是删掉会和发布时间冲突的季节、天气、疾病大环境或季节性活动时点。"
            "可以保留最近、现在、今天、昨天、上周、前两天、刚才、刚补、刚到、班里请假这类真人随手记录口吻，只要不和换季/流感/季节语境绑定。"
            "删除后如果上下文不顺，只补主语、标点或极短连接；不要新增新的活动、天气、疾病或季节性场景。"
            if review.temporal_context_hits
            else "不要新增会和发布时间冲突的季节、天气、疾病大环境或季节性活动时点；最近、昨天、刚补货、刚拆快递等真人时间口吻可以保留。"
        )
        wangyue_age_stage_instruction = (
            "本轮命中旺玥年龄/阶段不匹配："
            f"{'/'.join(review.wangyue_explicit_age_hits)}。"
            "产品年龄边界：旺玥只放在孩子3岁以后的儿童奶粉阶段；正文不要完整复述成“3岁以上4段儿童奶粉”。"
            "用模型把命中句和相邻上下文整句改顺，不要机械删年龄词，不要把“一岁多/两岁/半岁”替换成“孩子/这个阶段”造成残句。"
            "把旺玥相关使用/购买/备货关系改到3岁以后；不要新增固定喝法、补货链路或阶段定义句。"
            "不能写低龄、婴配、断奶、辅食、1-2岁开始喝旺玥。"
            if review.wangyue_explicit_age_hits
            else "旺玥年龄事实必须正确：只放在孩子3岁以后的儿童奶粉阶段；正文不要完整复述成“3岁以上4段儿童奶粉”；不要新增低龄、婴配、断奶、辅食或1-2岁开始喝旺玥。"
        )
        odd_phrase_instruction = (
            "本轮命中历史硬替换问题词："
            f"{'/'.join(review.odd_phrase_hits)}。"
            "不要照着固定替换表机械改词；优先删掉问题短句，或用模型把相邻上下文改顺，保持真人口气。"
            if review.odd_phrase_hits
            else "不要新增历史硬替换问题词；如果只是机械清理，保持原文逻辑和真人口气。"
        )
        adult_self_drinking_instruction = (
            f"本轮出现成人自己喝儿童奶粉的错误场景：{'/'.join(review.adult_self_drinking_hits)}；直接删除或改成给孩子冲/孩子喝，不要扩写成新情节。"
            if review.adult_self_drinking_hits
            else "不要写妈妈自己喝、给自己冲或成人试喝旺玥；旺玥只作为给孩子喝的儿童奶粉出现。"
        )
        formula_usage_form_instruction = (
            "本轮命中旺玥产品物理使用/存放形态错误："
            f"{'/'.join(review.formula_usage_form_hits)}。"
            "优先删除命中短句或相邻产品动作，把句子改顺；保留原有正向产品价值。"
            "不要改成新的固定喝法、分装存放、冲泡过程、孩子操作或完整喝奶流程。"
            if review.formula_usage_form_hits
            else "生活细节可以自由，但不要扩写旺玥的物理使用事实；不新增分装存放、固定喝法、孩子操作或完整喝奶流程。"
        )
        physical_action_carrier_instruction = (
            "本轮命中生活物理动作/信息载体错配："
            f"{'/'.join(review.physical_action_carrier_mismatch_hits)}。"
            "问题不是不能写配方，而是把罐装奶粉和“翻配方表”硬接在一起时，读起来像动作和信息载体错配。"
            "只局部处理命中句：优先删除不合理动作词，保留原本的配方/成分关注，不补新的拿罐、翻看、冲泡或喝奶动作。"
            "不要新增冲泡、喝奶、下单、对比清单或新的效果证明。"
            if review.physical_action_carrier_mismatch_hits
            else "写配方/成分时要让信息载体符合现实：罐装奶粉适合写看罐身、扫一眼营养成分；不要把奶粉罐动作硬写成翻配方表。"
        )
        ingredient_benefit_instruction = (
            "本轮命中旺玥成分和正向效果承接："
            f"{'/'.join(review.ingredient_benefit_mismatch_hits)}。"
            "这类表达不作为硬性错误；如需改写，只按当前业务规则控制卖点侧重和语气强度。"
            "不要把强效果洗成“还在观察/不一定/每家不同”，也不要新增第二套成分清单或医疗事实。"
            if review.ingredient_benefit_mismatch_hits
            else "旺玥成分可以承接保护力、精神头、状态稳和正向成长观察；具体卖点侧重服从本篇业务规则，不因成分和积极结果相连而硬改写。"
        )
        supplement_replacement_instruction = (
            "本轮命中旺玥营养替代暗示："
            f"{'/'.join(review.wangyue_supplement_replacement_hits)}。"
            "问题不是不能写营养好处，而是不能把旺玥写成替代营养片、维生素、补剂或钙片。"
            "请局部删掉补剂替代关系，保留原有正向产品价值；可以承接为基础营养、关键营养或日常营养安排更清楚。"
            "不要新增新的补剂对比、固定喝法、安心模板或合规不确定句。"
            if review.wangyue_supplement_replacement_hits
            else "旺玥可以正面写营养配置和日常营养价值，但不要写成替代营养片、维生素、补剂或钙片。"
        )
        post_delete_cleanup_instruction = (
            "本轮已经先按规则删除了高幻觉风险或产品使用形态错误动作。"
            "你的任务是检查删除后的标题和正文是否出现残句、断句、指代不清或前后不接；"
            "如果已经通顺，尽量保持原文不动；如果不顺，只删多余标点或补极短连接。"
            "不要新增冲泡、喝奶、试喝、孩子接受度、新效果证明或新生活情节。"
            if POST_DELETE_CLEANUP_FLUENCY_REASON in review.reasons
            else "如果正文已经做过删除式清理，保持删后文本顺畅即可；不要补新喝奶动作或新事实。"
        )
        hard_risk_instruction = (
            "本轮命中高风险或逻辑错误表达："
            f"{'/'.join(review.hard_risk_hits)}。"
            "如果是孩子已经哈啾、打喷嚏、流鼻涕、咳嗽、不舒服之后才换上/安排上/补上/喝旺玥，"
            "请删除这种事后补救因果；改成旺玥本来就是日常儿童奶粉选择，或只保留妈妈担心接触多、关注保护力的想法。"
            "不要固定替换成安全套话，不要新增生病、治疗、立刻见效、少跑医院或确定归因。"
            if review.hard_risk_hits
            else "不要写孩子已经出现不舒服后才临时喝旺玥；旺玥只作为日常儿童奶粉选择出现，不写治疗、补救或立刻见效。"
        )
        public_disease_context_instruction = (
            "本轮命中公共疾病环境对照："
            f"{'/'.join(review.wangyue_public_disease_context_hits)}。"
            "只删除班里、周围或其他孩子请假、咳嗽、中招、生病等对照分句；保留自家孩子普通状态观察和正确产品依据。"
            "删除后如果句子不通，只补最短连接，不新增另一种疾病、天气、季节、出勤或医疗事实。"
            if review.wangyue_public_disease_context_hits
            else "不要新增班里、周围或其他孩子请假、咳嗽、中招、生病等公共疾病环境对照；自家普通状态观察可以保留。"
        )
        semantic_odd_instruction = (
            "本轮命中会牵动上下文逻辑的敏感表达："
            f"{'/'.join(_semantic_odd_product_experience_phrase_hits(review))}。"
            "不要把它们固定替换成“班里请假/小状况”，要用模型改顺标题和正文："
            "优先删掉疾病或停课所在的半句，或改成妈妈对集体生活接触多的普通担心。"
            "改写后不能出现手足口、流感、停课，也不能出现“班里班里”“班里请假停课”这类拼接句。"
            if _semantic_odd_product_experience_phrase_hits(review)
            else "不要把具体疾病或停课情节写进旺玥帖子；如需表达担心，用集体生活接触多、容易中招这类普通语境。"
        )
        child_self_brewing_instruction = (
            "本轮出现孩子自己冲/泡/舀奶粉的不合理动作："
            f"{'/'.join(review.child_self_brewing_hits)}。"
            "请局部删除孩子操作奶粉的动作；删除后如果不顺，只补主语、标点或极短连接。"
            "不要硬塞固定替换短语，不要保留“自己冲/自己泡/自己舀/自己挖/自己催我泡奶粉”等动作，也不要新增奶粉盒、书包、随身带奶粉或成人试喝情节。"
            if review.child_self_brewing_hits
            else "不要写孩子自己冲奶粉、泡奶粉、舀粉、挖粉或自己操作奶粉罐；冲泡动作由妈妈完成，孩子只负责等、接、喝或喝完后的自然动作。"
        )
        row2_drinking_action_instruction = (
            "本轮命中旺玥 row2 的喝奶动作/补给路径残留："
            f"{'/'.join(review.wangyue_row2_drinking_action_hits)}。"
            "这条规则重点是孩子活动量大时，妈妈为什么选择旺玥儿童奶粉；"
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
            "请保留核心：给孩子选择旺玥儿童奶粉，是为了补充营养、支持成长。"
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
            "如果命中的是单点时间搭配累计效果，例如今天/昨天/刚开/这次换后接少请假、没中招、状态稳、长高长肉，"
            "不要削弱正向效果本身，改成有时间跨度的表达，或删除单点时间锚点。"
            "直接删除对应半句；删除后只做通顺度修复，不补新的卖点白话、购买渠道、喝奶动作或效果证明。"
            if review.wangyue_article_logic_drift_hits
            else "旺玥正文不要写成购买渠道、囤货、冲泡口感或效果证明；产品只作为儿童奶粉选择出现。"
        )
        wangyue_context_instruction = (
            "本轮命中旺玥场景路径错误："
            f"{'/'.join(review.wangyue_portable_form_hits + review.wangyue_supplement_replacement_hits + review.wangyue_article_logic_drift_hits)}。"
            "用模型改顺上下文，优先删除塞书包、路上喝、随身带、翻包看到产品、营养片/维生素/补剂替代、奶粉盒、购物车、下单、囤货、家里备着、奶粉罐这些剧情半句；"
            "不要硬替换成固定短语，也不要改成新的喝奶动作、冲泡动作或导购过程。"
            if _semantic_wangyue_context_reasons(review)
            else "旺玥正文不要写成便携外带、购买渠道、囤货、冲泡口感或奶粉罐剧情。"
        )
        child_product_promo_instruction = (
            "本轮命中孩子主动介绍/推荐/邀请别人喝旺玥的不合理产品台词："
            f"{'/'.join(review.wangyue_child_product_promo_hits)}。"
            "用模型改顺上下文：删掉这段孩子对外推荐产品的对话，改回妈妈随机记录孩子活动量、日常状态，或妈妈为什么选旺玥儿童奶粉。"
            "不要改成新的孩子安利、社交推荐、喝奶邀请、冲泡动作或导购过程。"
            if review.wangyue_child_product_promo_hits
            else "不要写孩子主动介绍、推荐、安利旺玥，或邀请别的小朋友来一杯；产品判断只能由妈妈叙述。"
        )
        wangyue_time_event_instruction = (
            "本轮命中不适合通用投放的明确时间/活动节点："
            f"{'/'.join(review.wangyue_time_event_context_hits)}。"
            "用模型改顺上下文，不要硬替换：删掉命中的季节、天气、疾病大环境或季节性活动时点；承接时写成具体生活画面，不要换成抽象入口词或运营概括。"
            "改写后不要再出现本轮命中词；但可以保留普通地点、周末、昨天、前两天、刚到、刚补、刚拆快递、班里请假这类真人记录口吻。"
            if review.wangyue_time_event_context_hits
            else "旺玥文章不要新增会和发布时间冲突的季节、天气、疾病大环境或季节性活动时点；可以写普通地点、刚拆快递、刚补货、昨天、最近、班里请假等生活记录。"
        )
        wangyue_hidden_negative_instruction = (
            "本轮命中旺玥隐性负面/降级比较："
            f"{'/'.join(review.wangyue_hidden_negative_comparison_hits)}。"
            "用模型改顺整个价格或比较句，不要硬替换词；核心是保留旺玥的正向产品价值，删掉价格、预算、贵不贵、值不值和低配参照物框架。"
            "不要保留价格取舍，也不要换成另一句价格评价；需要承接时，只保留原文或业务规则里已有的非价格产品依据，并用妈妈自然口气写出来。"
            "不要照抄本提示里的抽象词当正文，也不要输出类似“更看重配方/营养配置”的模板句。"
            if review.wangyue_hidden_negative_comparison_hits
            else "旺玥文章不要新增价格、预算、贵不贵、值不值或低配参照物；对比选择只保留非价格产品依据，不要写成价格取舍。"
        )
        wangyue_product_mention_instruction = (
            "本轮旺玥正文缺少产品名；只自然补一次“旺玥”或“旺玥儿童奶粉”，不要因此扩写成导购或卖点清单。"
            if "wangyue_missing_product_mention" in review.reasons
            else "旺玥文章里产品名至少自然出现一次，避免只用“它/这款/里面”承接卖点。"
        )
        scene_motive_bucket = str((item.plan_json or {}).get("scene_motive_bucket") or "")
        scene_motive_instruction = (
            "本轮正文偏离了指定生活入口："
            f"本篇入口是“{scene_motive_bucket}”，但命中了 {'/'.join(review.scene_motive_drift_hits)}。"
            "硬性验收：改写后的 title/body 不能再出现这些命中词，也不要换成同类的整理柜子、翻柜子、快见底、购物清单。"
            "请回到指定入口的第一现场，只修当前句子的入口偏移，不新增产品动作或另一套生活事件；"
            "产品只作为其中一个物件轻带，不要再写库存归位。"
            if review.scene_motive_drift_hits
            else "正文要跟随 scene_motive_bucket 的生活入口，不要默认回到整理柜子、快见底、购物清单这一套。"
        )
        product_action_surface = str((item.plan_json or {}).get("product_action_surface") or "")
        product_action_surface_instruction = (
            "本轮产品动作露出强度过高："
            f"本篇要求“{product_action_surface}”，但命中了 {'/'.join(review.product_action_surface_hits)}。"
            "改写时降低产品动作：物件在场就只写杯子/罐子在桌上、餐边柜旁、早餐角；"
            "妈妈顺手挪放就只写挪到一边、放到桌角、摆回原处；"
            "不要再写孩子端起来喝、喝两口、喝完、妈妈专门冲一杯。"
            if review.product_action_surface_hits
            else "使用记录里的产品动作要服从 product_action_surface，不要每篇都写成冲一杯、端起来、喝两口。"
        )
        product_fact_number_instruction = (
            "本轮命中旺玥产品事实数字口径漂移："
            f"{'/'.join(review.product_fact_number_drift_hits)}。"
            "改写时保留正向营养价值，但删掉或改顺错误数字口径；"
            "关键营养只能按业务规则已有口径写成多种关键营养或30多种关键营养，不要新增十几种、十多种、20多种、几十种。"
            "不要因为修数字而削弱种草，也不要新增另一套成分清单。"
            if review.product_fact_number_drift_hits
            else "旺玥产品事实数字口径要稳定：可以写多种关键营养或30多种关键营养；不要新增十几种、十多种、20多种、几十种关键营养。"
        )
        effect_scope_instruction = (
            "旺玥正向效果与本篇卖点的对应关系由当前业务规则控制；"
            "本轮不要因为睡眠、精力、身高等积极反馈单独删除、降调或改写。"
        )
        product_effect_proof_instruction = (
            "本轮有产品动作和效果证明链路密度信号："
            + "；".join(
                f"{part}:{'/'.join(hits)}"
                for part, hits in review.product_effect_proof_chain_hits.items()
                if hits
            )
            + "。这主要是批量分布信号，不是单篇硬删理由；"
            "如果本轮还有事实错误、产品形态错误、隐性负面、强因果或广告收口，只改那些问题句。"
            "合理的正向效果证明可以保留，不要改成合规声明式不确定。"
            if review.product_effect_proof_chain_hits
            else "不要为了完整而主动补齐产品证明链；正向产品节点多少按帖子类型和业务规则自然决定。"
        )
        decision_chain_instruction = (
            "本轮有候选决策链信号："
            + "；".join(
                f"{part}:{'/'.join(hits)}" for part, hits in review.decision_chain_hits.items() if hits
            )
            + "。这些只是给后续 LLM 质检的提示，不是禁词。"
            "本轮如果还有其他硬问题，只处理硬问题所在句；不要仅因为这些信号删除正向产品价值。"
            if review.decision_chain_hits
            else "不要主动把正文补成完整决策链；每篇保留必要的正向产品节点即可。"
        )
        ugc_post_type_instruction = (
            "本轮 UGC 类型跑偏："
            f"本篇要求“{(item.plan_json or {}).get('ugc_post_type') or ''}”，但命中了 {'/'.join(review.ugc_post_type_drift_hits)}。"
            "如果是轻复盘型，不要再用想问大家、求经验、怎么判断、要不要继续这类求问收尾；"
            "改成“我这段时间回看后的正向依据/现实细节”，不要把动机变成征集答案，也不要用不确定感替代产品价值。"
            if review.ugc_post_type_drift_hits
            else "UGC 类型要稳定：轻复盘写自己的阶段性回看，求建议才可以以问题和征集经验为主。"
        )
        retry_instruction = (
            "这是同一条内容的再次改写：上一轮仍残留 row4 偏题表达。不要同义替换命中词，直接删掉偏题半句；"
            "正文只保留“选择旺玥儿童奶粉来补充成长阶段营养、支持成长”的自然表达。"
            if has_growth_nutrition_drift and self._product_experience_phrase_rewrite_rounds(item) > 0
            else (
                "这是同一条内容的再次改写：上一轮仍残留高风险或事后补救表达。直接删掉孩子出状况后才选/换/喝旺玥的因果链；保留日常接触多、妈妈关注保护力、旺玥作为日常儿童奶粉选择即可。"
                if review.hard_risk_hits and self._product_experience_phrase_rewrite_rounds(item) > 0
                else (
                    "这是同一条内容的再次改写：上一轮仍残留 row2 喝奶动作/补给路径。不要同义替换命中词，直接删掉命中词所在的后半句，保留生活观察和选择旺玥儿童奶粉的理由。"
                    if review.wangyue_row2_drinking_action_hits
                    and self._product_experience_phrase_rewrite_rounds(item) > 0
                    else (
                        "这是同一条内容的再次改写：上一轮仍残留产品动作或效果证明相关硬问题。只处理明确命中的问题句，不要机械删掉全部效果证明。"
                        if review.product_effect_proof_chain_hits
                        and self._product_experience_phrase_rewrite_rounds(item) > 0
                        else "如果本轮是首次改写，优先改顺，不要过度扩写。"
                    )
                )
            )
        )
        skeleton_redirect_instruction = (
            "如果正文已有购买过程或孩子接受度，本轮不要把它们当成硬禁词处理；价格相关表达按旺玥隐性负面处理。"
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
                length_instruction or "正文长度和段落服从业务规则。",
                title_instruction,
                phrase_instruction,
                ai_phrase_instruction,
                common_closure_instruction,
                temporal_context_instruction,
                wangyue_age_stage_instruction,
                odd_phrase_instruction,
                hard_risk_instruction,
                public_disease_context_instruction,
                adult_self_drinking_instruction,
                formula_usage_form_instruction,
                physical_action_carrier_instruction,
                ingredient_benefit_instruction,
                supplement_replacement_instruction,
                post_delete_cleanup_instruction,
                semantic_odd_instruction,
                child_self_brewing_instruction,
                row2_drinking_action_instruction,
                run_on_instruction,
                malformed_fragment_instruction,
                growth_nutrition_drift_instruction,
                wangyue_logic_drift_instruction,
                wangyue_context_instruction,
                child_product_promo_instruction,
                wangyue_time_event_instruction,
                wangyue_hidden_negative_instruction,
                wangyue_product_mention_instruction,
                scene_motive_instruction,
                product_action_surface_instruction,
                product_fact_number_instruction,
                effect_scope_instruction,
                decision_chain_instruction,
                product_effect_proof_instruction,
                ugc_post_type_instruction,
                retry_instruction,
                "rewrite 优先删除问题内容或压缩问题句；不要为了多样化整段重写。只有删除后语义断裂时，才补极短连接。",
                skeleton_redirect_instruction,
                "不要用“省心、踏实、固定下来、心里有数、先这样”作为统一收口。",
                "长个、少请假、不生病、保护力、坐不住这类真人强表达可以保留为观察或别人问，不能写成确定因果。",
                "正文段落服从业务规则；原文已有自然换行时尽量保留，不要为了改写压成单段，也不要为了换行硬拆句。",
                "不要写成导购或品牌介绍。",
                "只输出 JSON：title, body。",
            ],
        }

    def _mark_product_experience_phrase_review(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
        *,
        mark_rewrite_required: bool | None = None,
    ) -> None:
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        review_report["product_experience_phrase_review"] = review.model_dump()
        if mark_rewrite_required is None and _should_mark_only_product_experience_phrase_review(item.plan_json, review):
            should_mark_rewrite = False
        else:
            should_mark_rewrite = review.rewrite_required if mark_rewrite_required is None else mark_rewrite_required
        if should_mark_rewrite:
            existing_reason = str(review_report.get("rewrite_reason") or "")
            if not review_report.get("rewrite_required") or not existing_reason or existing_reason == "业务规则口癖骨架或长度仍需人工处理":
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
            "mark_rewrite_required": should_mark_rewrite,
            "reasons": review.reasons,
        }
        item.quality_json = quality

    def _mark_product_experience_blocking_failure(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
        *,
        source: str,
        rewrite_attempted: bool = True,
    ) -> None:
        self._mark_product_experience_phrase_review(item, review)
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        blocking_hits = _blocking_product_experience_phrase_hits(review)
        review_report.update(
            {
                "rewrite_required": True,
                "rewrite_reason": (
                    "硬性规则改写失败，需要人工复核"
                    if rewrite_attempted
                    else "命中生成后硬拦截，禁止自动改写"
                ),
                "blocking_failure": {
                    "source": source,
                    "reasons": review.reasons,
                    "hits": blocking_hits,
                    "rewrite_allowed": rewrite_attempted,
                },
            }
        )
        quality["review_report"] = review_report
        quality["hard_pass"] = False
        quality["postprocess_blocked"] = {
            "source": source,
            "reasons": review.reasons,
            "hits": blocking_hits,
        }
        item.quality_json = quality
        item.status = "failed"
        prefix = "硬性规则改写后仍命中：" if rewrite_attempted else "生成后硬拦截命中："
        item.error_message = prefix + "、".join(blocking_hits or review.reasons)

    def _mark_royal_friso_structure_review(
        self,
        item: ContentBatchItem,
        review: RoyalFrisoUGCStructureReview,
    ) -> None:
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        payload = review.model_dump()
        review_report["royal_friso_ugc_structure_guard"] = payload
        if review.rewrite_required:
            review_report.update(
                {
                    "rewrite_required": True,
                    "rewrite_reason": "皇家UGC结构风险命中，需要人工复核",
                }
            )
        elif review_report.get("rewrite_reason") == "皇家UGC结构风险命中，需要人工复核":
            review_report["rewrite_required"] = False
            review_report.pop("rewrite_reason", None)
        quality["review_report"] = review_report
        quality["royal_friso_ugc_structure_guard"] = payload
        item.quality_json = quality

    def _mark_royal_friso_structure_blocking_failure(
        self,
        item: ContentBatchItem,
        review: RoyalFrisoUGCStructureReview,
    ) -> None:
        self._mark_royal_friso_structure_review(item, review)
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        payload = review.model_dump()
        review_report.update(
            {
                "rewrite_required": True,
                "rewrite_reason": "皇家UGC结构风险命中，需要人工复核",
                "blocking_failure": {
                    "source": "royal_friso_ugc_structure_guard",
                    "reasons": payload["reasons"],
                    "hits": payload["hits"],
                },
            }
        )
        quality["review_report"] = review_report
        quality["hard_pass"] = False
        quality["postprocess_blocked"] = {
            "source": "royal_friso_ugc_structure_guard",
            "reasons": payload["reasons"],
            "hits": payload["hits"],
        }
        item.quality_json = quality
        item.status = "failed"
        item.error_message = "皇家UGC结构风险命中：" + "、".join(payload["hits"] or payload["reasons"])

    def _mark_forbidden_term_blocking_failure(self, item: ContentBatchItem, hits: list[str]) -> None:
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        review_report.update(
            {
                "rewrite_required": True,
                "rewrite_reason": "违禁词自动改写失败，需要人工复核",
                "blocking_failure": {
                    "source": "forbidden_terms_guard",
                    "hits": hits,
                },
            }
        )
        quality["review_report"] = review_report
        quality["hard_pass"] = False
        quality["postprocess_blocked"] = {
            "source": "forbidden_terms_guard",
            "reasons": ["forbidden_terms_guard"],
            "hits": hits,
        }
        item.quality_json = quality
        item.status = "failed"
        item.error_message = "违禁词自动改写后仍命中：" + "、".join(hits)

    def _mark_ai_flavor_review(self, item: ContentBatchItem, review: AIFlavorReview) -> None:
        quality = dict(item.quality_json or {})
        review_report = dict(quality.get("review_report") or {})
        review_report["ai_flavor_review"] = review.model_dump()
        if review.rewrite_required:
            review_report.update(
                {
                    "rewrite_required": True,
                    "rewrite_reason": "AI 味 / 解释腔 / 标题卖点前置仍需处理",
                }
            )
        elif str(review_report.get("rewrite_reason") or "").startswith("AI 味 / 解释腔"):
            review_report["rewrite_required"] = False
            review_report.pop("rewrite_reason", None)
        quality["review_report"] = review_report
        quality["ai_flavor_humanizer"] = {
            "pass": review.pass_,
            "rewrite_required": review.rewrite_required,
            "reasons": review.reasons,
            "title_hits": review.title_hits,
            "body_hits": review.body_hits,
            "rewrite_operations": review.rewrite_operations,
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

    def _apply_product_experience_phrase_cleanups_once(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> ProductExperiencePhraseReview:
        if review.temporal_context_hits:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_temporal_context_cleanups",
                title=sanitize_temporal_context(item.title or ""),
                body=sanitize_temporal_context(item.body or ""),
            )
        if "common_ai_closure_phrase" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_common_ai_closure_cleanups",
                title=sanitize_common_ai_closure(item.title or ""),
                body=sanitize_common_ai_closure(item.body or ""),
            )
        if "odd_product_experience_phrase" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_odd_phrase_cleanups",
                title=sanitize_odd_product_experience_phrases(item.title or ""),
                body=sanitize_odd_product_experience_phrases(item.body or ""),
            )
        if "adult_self_drinking_child_formula" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_adult_self_drinking_cleanups",
                title=sanitize_adult_self_drinking_phrases(item.title or ""),
                body=sanitize_adult_self_drinking_phrases(item.body or ""),
            )
        if "formula_dry_powder_ingestion" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_formula_dry_powder_cleanups",
                title=sanitize_formula_dry_powder_ingestion(item.title or ""),
                body=sanitize_formula_dry_powder_ingestion(item.body or ""),
            )
        if "formula_usage_form_error" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_formula_usage_form_cleanups",
                title=sanitize_wangyue_formula_usage_form(item.title or ""),
                body=sanitize_wangyue_formula_usage_form(item.body or ""),
            )
        if "child_self_brewing_formula" in review.reasons or "child_formula_bottle_context" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_child_self_brewing_cleanups",
                title=sanitize_baby_milk_action_phrases(item.title or ""),
                body=sanitize_baby_milk_action_phrases(item.body or ""),
            )
        if "wangyue_growth_nutrition_drift_context" in review.reasons and self._fallback_clean_wangyue_growth_nutrition_drift(item, review):
            review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
        if "scene_motive_drift" in review.reasons:
            review = self._apply_scene_motive_drift_cleanup(item, review)
        if "ugc_post_type_drift" in review.reasons:
            review = self._apply_ugc_post_type_drift_cleanup(item, review)
        if "wangyue_missing_product_mention" in review.reasons:
            review = self._apply_product_permission_missing_product_cleanup(item, review)
        if "product_action_surface_drift" in review.reasons:
            review = self._apply_product_action_surface_cleanup(item, review)
        if "wangyue_portable_form_context" in review.reasons:
            review = self._apply_usage_record_portable_cleanup(item, review)
        if (
            "wangyue_wrong_brand" in review.reasons
            or "wangyue_portable_form_context" in review.reasons
            or "wangyue_supplement_replacement_context" in review.reasons
            or "wangyue_digestive_effect_context" in review.reasons
            or "wangyue_article_logic_drift_context" in review.reasons
            or _semantic_wangyue_context_reasons(review)
        ):
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_wangyue_context_cleanups",
                title=sanitize_wangyue_context_phrases(item.title or ""),
                body=sanitize_wangyue_context_phrases(item.body or ""),
            )
        if "wangyue_article_logic_drift_context" in review.reasons:
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_wangyue_context_cleanups",
                title=item.title or "",
                body=_restore_wangyue_selling_context_surface(item.body or "", item.plan_json),
            )
        formatted_title = sanitize_product_experience_format(item.title)
        formatted_body = sanitize_product_experience_format(item.body)
        if formatted_title != (item.title or "") or formatted_body != (item.body or ""):
            review = self._apply_product_experience_text_cleanup(
                item,
                review,
                cleanup_key="product_experience_format_cleanups",
                title=formatted_title,
                body=formatted_body,
            )
        return review

    def _apply_product_experience_text_cleanup(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
        *,
        cleanup_key: str,
        title: str | None,
        body: str | None,
    ) -> ProductExperiencePhraseReview:
        before = {"title": item.title or "", "body": item.body or ""}
        after = {"title": title or "", "body": body or ""}
        if after == before:
            return review
        item.title = after["title"]
        item.body = after["body"]
        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
        quality = dict(item.quality_json or {})
        cleanups = list(quality.get(cleanup_key) or [])
        cleanups.append(
            {
                "before": before,
                "after": after,
                "pre_review": review.model_dump(),
                "post_review": post_review.model_dump(),
            }
        )
        quality[cleanup_key] = cleanups
        item.quality_json = quality
        return post_review

    def _apply_scene_motive_drift_cleanup(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> ProductExperiencePhraseReview:
        plan = item.plan_json or {}
        bucket = str(plan.get("scene_motive_bucket") or "")
        post_type = str(plan.get("post_type") or "")
        if not bucket or not ("补货" in post_type or "清单" in post_type):
            return review

        before = {"title": item.title or "", "body": item.body or ""}
        item.title = _sanitize_scene_motive_drift_text(item.title or "", bucket, review.scene_motive_drift_hits)
        item.body = _sanitize_scene_motive_drift_text(item.body or "", bucket, review.scene_motive_drift_hits)
        after = {"title": item.title or "", "body": item.body or ""}
        if after == before:
            return review

        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
        quality = dict(item.quality_json or {})
        cleanups = list(quality.get("product_experience_scene_motive_cleanups") or [])
        cleanups.append(
            {
                "before": before,
                "after": after,
                "pre_review": review.model_dump(),
                "post_review": post_review.model_dump(),
            }
        )
        quality["product_experience_scene_motive_cleanups"] = cleanups
        item.quality_json = quality
        return post_review

    def _apply_product_permission_missing_product_cleanup(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> ProductExperiencePhraseReview:
        plan = item.plan_json or {}
        post_type = str(plan.get("post_type") or "")
        product_mode = str(plan.get("product_appearance_mode") or "")
        if not post_type and not product_mode:
            return review
        before = {"title": item.title or "", "body": item.body or ""}
        item.title = _restore_product_permission_wangyue_surface(item.title or "", post_type=post_type)
        item.body = _restore_product_permission_wangyue_surface(item.body or "", post_type=post_type)
        after = {"title": item.title or "", "body": item.body or ""}
        if after == before:
            return review
        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
        quality = dict(item.quality_json or {})
        cleanups = list(quality.get("product_experience_missing_product_surface_cleanups") or [])
        cleanups.append(
            {
                "before": before,
                "after": after,
                "pre_review": review.model_dump(),
                "post_review": post_review.model_dump(),
            }
        )
        quality["product_experience_missing_product_surface_cleanups"] = cleanups
        item.quality_json = quality
        return post_review

    def _apply_product_action_surface_cleanup(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> ProductExperiencePhraseReview:
        plan = item.plan_json or {}
        surface = str(plan.get("product_action_surface") or "")
        if not surface:
            return review
        before = {"title": item.title or "", "body": item.body or ""}
        item.title = _sanitize_product_action_surface_text(item.title or "", surface)
        item.body = _sanitize_product_action_surface_text(item.body or "", surface)
        after = {"title": item.title or "", "body": item.body or ""}
        if after == before:
            return review
        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
        quality = dict(item.quality_json or {})
        cleanups = list(quality.get("product_experience_action_surface_cleanups") or [])
        cleanups.append(
            {
                "before": before,
                "after": after,
                "pre_review": review.model_dump(),
                "post_review": post_review.model_dump(),
            }
        )
        quality["product_experience_action_surface_cleanups"] = cleanups
        item.quality_json = quality
        return post_review

    def _apply_usage_record_portable_cleanup(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> ProductExperiencePhraseReview:
        plan = item.plan_json or {}
        post_type = str(plan.get("post_type") or "")
        product_mode = str(plan.get("product_appearance_mode") or "")
        if "使用记录" not in post_type and "日常动作" not in product_mode:
            return review
        before = {"title": item.title or "", "body": item.body or ""}
        item.title = _sanitize_usage_record_portable_text(item.title or "")
        item.body = _sanitize_usage_record_portable_text(item.body or "")
        after = {"title": item.title or "", "body": item.body or ""}
        if after == before:
            return review
        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
        quality = dict(item.quality_json or {})
        cleanups = list(quality.get("product_experience_usage_portable_cleanups") or [])
        cleanups.append(
            {
                "before": before,
                "after": after,
                "pre_review": review.model_dump(),
                "post_review": post_review.model_dump(),
            }
        )
        quality["product_experience_usage_portable_cleanups"] = cleanups
        item.quality_json = quality
        return post_review

    def _apply_ugc_post_type_drift_cleanup(
        self,
        item: ContentBatchItem,
        review: ProductExperiencePhraseReview,
    ) -> ProductExperiencePhraseReview:
        before = {"title": item.title or "", "body": item.body or ""}
        item.title = _sanitize_ugc_post_type_drift_text(item.title or "")
        item.body = _sanitize_ugc_post_type_drift_text(item.body or "")
        post_review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)
        quality = dict(item.quality_json or {})
        cleanups = list(quality.get("product_experience_ugc_post_type_cleanups") or [])
        cleanups.append(
            {
                "before": before,
                "after": {"title": item.title or "", "body": item.body or ""},
                "pre_review": review.model_dump(),
                "post_review": post_review.model_dump(),
            }
        )
        quality["product_experience_ugc_post_type_cleanups"] = cleanups
        item.quality_json = quality
        return post_review

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
            if not item.run_id or not item.body or _is_postprocess_blocked(item):
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


def _max_product_experience_phrase_rewrite_rounds(
    plan: dict[str, Any] | None,
    review: ProductExperiencePhraseReview,
) -> int:
    return MAX_PRODUCT_EXPERIENCE_PHRASE_REWRITE_ROUNDS


def _append_product_experience_review_reason(
    review: ProductExperiencePhraseReview,
    reason: str,
) -> ProductExperiencePhraseReview:
    if reason in review.reasons:
        return replace(review, pass_=False, rewrite_required=True)
    return replace(
        review,
        pass_=False,
        rewrite_required=True,
        reasons=[*review.reasons, reason],
    )


def _persona_style_rewrite_enabled(plan: dict[str, Any] | None) -> bool:
    plan = plan or {}
    if str(plan.get("asset_key") or "").strip() in PERSONA_STYLE_REWRITE_DISABLED_ASSET_KEYS:
        return False
    if should_review_product_experience(plan):
        return False
    value = plan.get("persona_style_rewrite_enabled")
    return value is not False


def _semantic_odd_product_experience_phrase_hits(review: ProductExperiencePhraseReview) -> list[str]:
    semantic_phrases = set(SEMANTIC_ODD_PRODUCT_EXPERIENCE_PHRASES)
    return [hit for hit in review.odd_phrase_hits if hit in semantic_phrases]


def _blocking_product_experience_phrase_hits(review: ProductExperiencePhraseReview) -> list[str]:
    return list(
        dict.fromkeys(
            review.wangyue_time_event_context_hits
            + review.wangyue_no_rewrite_block_hits
            + review.wangyue_public_disease_context_hits
            + review.wangyue_child_product_promo_hits
            + review.temporal_context_hits
            + review.wangyue_wrong_brand_hits
            + review.wangyue_explicit_age_hits
            + review.wangyue_portable_form_hits
            + review.formula_dry_powder_ingestion_hits
            + review.formula_usage_form_hits
            + review.child_self_brewing_hits
            + review.child_formula_bottle_hits
            + review.physical_action_carrier_mismatch_hits
            + review.product_fact_number_drift_hits
            + review.effect_scope_drift_hits
            + review.malformed_fragment_hits
            + [hit for hit in review.hard_risk_hits if hit.startswith("症状效果证明：")]
        )
    )


def _has_no_rewrite_product_experience_phrase_review(review: ProductExperiencePhraseReview) -> bool:
    return bool(review.wangyue_no_rewrite_block_hits)


def _has_blocking_product_experience_phrase_review(review: ProductExperiencePhraseReview) -> bool:
    return bool(_blocking_product_experience_phrase_hits(review))


def _is_ai_flavor_title_only_review(review: AIFlavorReview) -> bool:
    return bool(review.rewrite_required and review.title_hits and not review.body_hits)


def _should_review_product_experience_llm_quality(plan: dict[str, Any] | None) -> bool:
    plan = plan or {}
    if not should_review_product_experience(plan):
        return False
    if plan.get("product_experience_llm_review_enabled") is True:
        return True
    asset_key = str(plan.get("asset_key") or "")
    return "wangyue_painpoint_selling_posttype_matrix" in asset_key or asset_key.startswith("wangyue_")


def _should_rewrite_product_experience_llm_quality(
    plan: dict[str, Any] | None,
    review: ProductExperienceLLMReview,
) -> bool:
    plan = plan or {}
    if _is_current_wangyue_article_plan(plan):
        return review.rewrite_required and _product_experience_rewrite_mode(review) is not None
    if _is_wangyue_mark_only_llm_quality_review(plan, review):
        return False
    if _is_overcomplete_decision_chain_only_llm_review(review):
        return False
    if _is_soft_wangyue_strong_seeding_llm_review(review):
        return False
    if plan.get("product_experience_llm_rewrite_enabled") is True:
        return review.rewrite_required
    return review.rewrite_required


def _should_repair_product_experience_llm_quality(
    plan: dict[str, Any] | None,
    review: ProductExperienceLLMReview,
) -> bool:
    if _is_current_wangyue_article_plan(plan):
        return _should_rewrite_product_experience_llm_quality(plan, review)
    if _is_wangyue_mark_only_llm_quality_review(plan or {}, review):
        return False
    if _should_rewrite_product_experience_llm_quality(plan, review):
        return True
    if review.business_usability_tier != "light_fix_usable":
        return False
    if _is_overcomplete_decision_chain_only_llm_review(review):
        return False
    if _is_soft_wangyue_strong_seeding_llm_review(review):
        return False
    return True


def _is_current_wangyue_article_plan(plan: dict[str, Any] | None) -> bool:
    return str((plan or {}).get("asset_key") or "") == CURRENT_WANGYUE_ARTICLE_ASSET_KEY


def _product_experience_rewrite_mode(review: ProductExperienceLLMReview) -> str | None:
    codes = {issue.code for issue in review.issues}
    if codes.intersection(PRODUCT_EXPERIENCE_COMPLIANCE_ISSUE_CODES):
        return "compliance_cleanup"
    if codes and codes.issubset(PRODUCT_EXPERIENCE_FLUENCY_ISSUE_CODES):
        return "fluency_humanize"
    return None


def _focused_issues_as_rewrite_review(
    issues: list[dict[str, Any]],
    *,
    rewrite_mode: str,
) -> ProductExperienceLLMReview:
    mapped_issues = []
    for issue in issues:
        dimension = str(issue.get("dimension") or "")
        issue_code = str(issue.get("issue_code") or "quality_issue")
        if rewrite_mode == "compliance_cleanup":
            mapped_code = "claim_risk"
        elif dimension == "content_fit" and issue_code == "unnatural_product_appearance":
            mapped_code = "unnatural_product_appearance"
        else:
            mapped_code = "brief_translation_tone"
        mapped_issues.append(
            ProductExperienceLLMIssue(
                code=mapped_code,
                evidence=str(issue.get("evidence") or "")[:200],
                reason=f"{dimension}/{issue_code}",
                rewrite_direction="只局部删除或修正命中表达",
            )
        )
    return ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="rewrite",
        issues=mapped_issues,
        business_usability_tier="light_fix_usable",
        business_usability_reason="Focused Pipeline block routed to local rewrite rehearsal",
        overall_reason="；".join(
            f"{issue.get('dimension')}/{issue.get('issue_code')}: {issue.get('evidence') or ''}"
            for issue in issues
        )[:500],
    )


def _focused_rewrite_candidate_code_hard_review(
    *,
    item: ContentBatchItem,
    after: dict[str, str],
) -> dict[str, Any]:
    title = str(after.get("title") or "")
    body = str(after.get("body") or "")
    forbidden_hits = find_forbidden_hits(
        f"{title}\n{body}",
        WANGYUE_STATIC_FORBIDDEN_TERMS,
    )
    phrase_review = review_product_experience_phrase(
        title=title,
        body=body,
        plan=item.plan_json,
    )
    phrase_hits = _blocking_product_experience_phrase_hits(phrase_review)
    return {
        "pass": not forbidden_hits and not phrase_hits,
        "forbidden_hits": forbidden_hits,
        "phrase_guard_hits": phrase_hits,
        "phrase_guard_reasons": list(phrase_review.reasons),
    }


def _max_product_experience_llm_rewrite_rounds(plan: dict[str, Any] | None) -> int:
    return 2 if _is_current_wangyue_article_plan(plan) else MAX_PRODUCT_EXPERIENCE_LLM_REWRITE_ROUNDS


def _rewrite_removed_required_wangyue_product(
    before: dict[str, str],
    after: dict[str, str],
    plan: dict[str, Any] | None,
) -> bool:
    if not should_review_product_experience(plan):
        return False
    before_body = str(before.get("body") or "")
    after_body = str(after.get("body") or "")
    before_had_wangyue = any(term in before_body for term in ("旺玥", "皇家美素佳儿"))
    after_has_wangyue = any(term in after_body for term in ("旺玥", "皇家美素佳儿"))
    return before_had_wangyue and not after_has_wangyue


def _is_overcomplete_decision_chain_only_llm_review(review: ProductExperienceLLMReview) -> bool:
    codes = {issue.code for issue in review.issues}
    return bool(codes) and codes == {"overcomplete_decision_chain"}


def _is_wangyue_mark_only_llm_quality_review(
    plan: dict[str, Any],
    review: ProductExperienceLLMReview,
) -> bool:
    asset_key = str(plan.get("asset_key") or "")
    if not asset_key.startswith("wangyue_"):
        return False
    codes = {issue.code for issue in review.issues}
    mark_only_codes = {"claim_risk", "unnatural_product_appearance"}
    return bool(codes) and codes.issubset(mark_only_codes)


def _is_soft_wangyue_strong_seeding_llm_review(review: ProductExperienceLLMReview) -> bool:
    """Treat dense but useful Wangyue seeding as a distribution signal, not a rewrite trigger."""
    if review.severity == "hard":
        return False
    codes = {issue.code for issue in review.issues}
    if not codes or not codes.issubset({"overcomplete_decision_chain", "brief_translation_tone"}):
        return False
    if "overcomplete_decision_chain" not in codes:
        return False
    return (
        review.product_value_strength >= 4
        and review.product_appearance_naturalness >= 3
        and review.human_realness >= 3
    )


def _should_mark_only_product_experience_phrase_review(
    plan: dict[str, Any] | None,
    review: ProductExperiencePhraseReview,
) -> bool:
    if not review.rewrite_required:
        return False
    asset_key = str((plan or {}).get("asset_key") or "")
    if (
        asset_key.startswith("wangyue_")
        and set(review.reasons).issubset(
            {
                "product_effect_proof_chain",
                "wangyue_article_logic_drift_context",
            }
        )
    ):
        return True
    if (
        asset_key == CURRENT_WANGYUE_ARTICLE_ASSET_KEY
        and set(review.reasons).issubset(
            {
                "common_ai_closure_phrase",
                "hard_ai_closure_phrase",
                "product_effect_proof_chain",
                "state_template_phrase",
                "wangyue_article_logic_drift_context",
            }
        )
    ):
        return True
    return False


def _postprocess_mode(job: ContentBatchJob) -> str:
    strategy = job.strategy_json if isinstance(job.strategy_json, dict) else {}
    return str(strategy.get("postprocess_mode") or "").strip()


def _generate_only_postprocess_enabled(job: ContentBatchJob) -> bool:
    return _postprocess_mode(job) == "generate_only"


def _generate_only_postprocess_enabled_for_context(job_context: dict[str, Any]) -> bool:
    return str(job_context.get("postprocess_mode") or "").strip() == "generate_only"


def _audit_only_postprocess_enabled(job: ContentBatchJob) -> bool:
    return _postprocess_mode(job) == "audit_only"


def _audit_only_postprocess_enabled_for_context(job_context: dict[str, Any]) -> bool:
    return str(job_context.get("postprocess_mode") or "").strip() == "audit_only"


def _semantic_wangyue_context_reasons(review: ProductExperiencePhraseReview) -> list[str]:
    reasons: list[str] = []
    if "wangyue_portable_form_context" in review.reasons:
        reasons.append("wangyue_portable_form_context")
    if "wangyue_supplement_replacement_context" in review.reasons:
        reasons.append("wangyue_supplement_replacement_context")
    if "wangyue_article_logic_drift_context" in review.reasons:
        reasons.append("wangyue_article_logic_drift_context")
    if "wangyue_explicit_age_context" in review.reasons:
        reasons.append("wangyue_explicit_age_context")
    if "wangyue_child_product_promo_context" in review.reasons:
        reasons.append("wangyue_child_product_promo_context")
    if "wangyue_time_event_context" in review.reasons:
        reasons.append("wangyue_time_event_context")
    if "wangyue_hidden_negative_comparison_context" in review.reasons:
        reasons.append("wangyue_hidden_negative_comparison_context")
    return reasons


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
    title = str(item.title or "")
    body = str(item.body or "")
    for allowed_term in _mouth_phrase_budget_allowed_terms(item):
        if allowed_term:
            title = title.replace(allowed_term, "")
            body = body.replace(allowed_term, "")
    hits: list[str] = []
    for term in avoid_terms:
        if not term:
            continue
        if term in body:
            hits.append(term)
            continue
        if term in title and term not in TITLE_GUARD_WATCH_ONLY_CLOSURE_TERMS:
            hits.append(term)
    return hits


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


def _preserve_rewrite_paragraphs(before_body: str, after_body: str, plan: dict[str, Any] | None) -> str:
    before_paragraphs = [part.strip() for part in re.split(r"\n+", before_body or "") if part.strip()]
    if len(before_paragraphs) < 2 or "\n" in after_body or _business_rule_requires_single_paragraph(plan):
        return after_body

    sentences = [
        match.group(0).strip()
        for match in re.finditer(r".+?(?:[。！？!?]+[”’」』]?|$)", after_body)
        if match.group(0).strip()
    ]
    target_paragraphs = min(len(before_paragraphs), 3, len(sentences))
    if target_paragraphs < 2:
        return after_body

    total_chars = sum(len(sentence) for sentence in sentences)
    paragraphs: list[str] = []
    current: list[str] = []
    consumed_chars = 0
    for index, sentence in enumerate(sentences):
        current.append(sentence)
        consumed_chars += len(sentence)
        remaining_sentences = len(sentences) - index - 1
        remaining_paragraphs = target_paragraphs - len(paragraphs) - 1
        next_cut = total_chars * (len(paragraphs) + 1) / target_paragraphs
        if (
            remaining_paragraphs > 0
            and consumed_chars >= next_cut
            and remaining_sentences >= remaining_paragraphs
        ):
            paragraphs.append("".join(current))
            current = []
    if current:
        paragraphs.append("".join(current))
    return "\n\n".join(paragraphs) if len(paragraphs) >= 2 else after_body


def _business_rule_requires_single_paragraph(plan: dict[str, Any] | None) -> bool:
    rule_text = str(rewrite_business_rule_context(plan))
    return any(
        phrase in rule_text
        for phrase in (
            "正文单段不换行",
            "正文一段不换行",
            "正文不换行",
            "正文不要换行",
            "正文不分段",
        )
    )


def _compact_len(value: str | None) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def _title_weighted_len(title: str | None) -> int:
    total = 0
    for char in re.sub(r"\s+", "", str(title or "").strip()):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if EMOJI_PATTERN.fullmatch(char) else 1
    return total


def _should_apply_title_guard(job: ContentBatchJob, items: list[ContentBatchItem]) -> bool:
    if "wangyue" in (job.asset_key or "").lower() or "旺玥" in (job.product_topic or ""):
        return True
    return any("0705旺玥活动" in str((item.plan_json or {}).get("corpus") or "") for item in items)


def _has_dangling_title_punctuation(title: str) -> bool:
    text = str(title or "").strip()
    return bool(text) and text[-1] in "，、：；,;:"


def _title_guard_reasons(title: str, used_titles: set[str], item: ContentBatchItem | None = None) -> list[str]:
    reasons: list[str] = []
    normalized = _normalize_title(title)
    if normalized and normalized in used_titles:
        reasons.append("duplicate_title")
    reference_titles = _title_reference_norms(item)
    if normalized and normalized in reference_titles:
        reasons.append("copied_reference_title")
    if _title_weighted_len(title) > 20:
        reasons.append("title_too_long")
    if _sanitize_generated_title_format(title) != title:
        reasons.append("generated_title_format")
    for phrase in TITLE_GUARD_FORBIDDEN_SUBSTRINGS:
        if phrase in title:
            reasons.append(f"forbidden_title_phrase:{phrase}")
    for pattern in TITLE_GUARD_BAD_PATTERNS:
        if pattern.search(title):
            reasons.append("ambiguous_age_or_duration")
            break
    if _has_dangling_title_punctuation(title):
        reasons.append("dangling_title_punctuation")
    if _is_marketing_claim_title(title):
        reasons.append("marketing_claim_title_pattern")
    if _is_awkward_title(title):
        reasons.append("awkward_title_pattern")
    if _is_low_natural_title_score(title):
        reasons.append("low_natural_title_score")
    return reasons


def _title_guard_watch_reasons(title: str) -> list[str]:
    reasons: list[str] = []
    for phrase in TITLE_GUARD_WATCH_ONLY_SUBSTRINGS:
        if phrase in title:
            reasons.append(f"watch_title_phrase:{phrase}")
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
    "咳嗽",
    "流鼻涕",
    "中招",
    "请假",
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
    text = _sanitize_title_emojis(text).strip()
    text = re.sub(r"[\u200d\ufe0f]", "", text).strip()
    text = re.sub(r"^\s*(?:标题|title)[:：]\s*", "", text, flags=re.IGNORECASE).strip()
    text = text.strip(" *_`~#")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sanitize_title_emojis(title: str) -> str:
    kept_allowed = False
    parts: list[str] = []
    for char in str(title or ""):
        if not EMOJI_PATTERN.fullmatch(char):
            parts.append(char)
            continue
        if char in TITLE_SURFACE_ALLOWED_EMOJIS and not kept_allowed:
            parts.append(char)
            kept_allowed = True
    return "".join(parts)


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
        "这罐旺玥先留意",
        "我家那罐旺玥",
        "旺玥这罐还在喝",
        "又开一罐旺玥",
        "这罐奶粉有点意外",
        "又开一罐儿童奶粉",
        "这次先不换了",
        "奶粉这钱真省不了",
        "有点肉疼但还行",
    ])
    if any(phrase in body for phrase in ["少请假", "中招", "保护力", "小病小痛", "流鼻涕", "咳嗽"]):
        candidates.extend(["接触多了才认真看奶粉", "这罐奶粉先不乱换"])
    if any(phrase in body for phrase in ["户外", "出去玩", "疯跑", "活动量", "跑跳"]):
        candidates.extend(["出去玩多了以后", "活动量大以后才懂", "疯跑回来也有劲"])
    if any(phrase in body for phrase in ["写写画画", "绘本", "眼脑", "DHA", "看书"]):
        candidates.extend(["写写画画多了以后", "眼脑营养这块我开始看了", "看成分看到眼晕"])
    if any(phrase in body for phrase in ["挑食", "吃饭", "绿叶菜", "追着喂", "营养不够"]):
        candidates.extend(["挑食这事真会反复", "吃饭这事真会反复", "营养补充这块我认了"])
    if "幼儿园" in scene or "集体" in scene:
        candidates.extend(["上幼儿园后才认真看奶粉", "集体生活以后才懂"])
    if "户外" in scene:
        candidates.extend(["出去玩多了以后", "户外回来照样吃喝"])
    if "挑食" in scene or "饭" in scene or "营养不足" in topic:
        candidates.extend(["挑食这事真会反复", "吃饭这事真会反复"])
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
        "给孩子选旺玥儿童奶粉，想法挺简单，日常营养这块认真一点，先这样记着。",
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


def _sanitize_scene_motive_drift_text(text: str, bucket: str, hits: list[str]) -> str:
    if not text or not hits:
        return text
    cleaned = text
    if any("柜子" in hit or hit in {"收纳柜"} for hit in hits):
        action = _scene_motive_replacement_action(bucket)
        surface = _scene_motive_replacement_surface(bucket)
        for phrase in (
            "归置到柜子里",
            "放进厨房柜子里",
            "放进厨房柜子",
            "放进柜子里",
            "放进柜子",
            "放回柜子里",
            "放回柜子",
            "丢进柜子里",
            "丢进柜子",
            "塞进柜子里",
            "塞进柜子",
            "放柜子",
            "往柜子里一塞",
        ):
            cleaned = cleaned.replace(phrase, action)
        cleaned = cleaned.replace(f"{action}里", action)
        cleaned = cleaned.replace("整理柜子", surface)
        cleaned = cleaned.replace("翻柜子", surface)
        cleaned = cleaned.replace("收纳柜", "手边")
        cleaned = cleaned.replace("厨房柜子", "台面边")
        cleaned = cleaned.replace("柜子里", "手边")
        cleaned = cleaned.replace("柜子", "手边")
    if "购物清单" in hits:
        cleaned = cleaned.replace("购物清单", "手机备忘录")
    if any(hit in {"快见底", "只剩半罐", "剩半罐", "小半罐", "快没了", "快空了", "见底", "半罐"} for hit in hits):
        cleaned = cleaned.replace("快见底的旺玥", "旺玥")
        cleaned = cleaned.replace("快见底的皇家美素佳儿旺玥", "皇家美素佳儿旺玥")
        cleaned = cleaned.replace("旺玥快见底了", "旺玥也在里面")
        cleaned = cleaned.replace("皇家美素佳儿旺玥快见底了", "皇家美素佳儿旺玥也在里面")
        cleaned = cleaned.replace("旺玥那罐也快空了", "旺玥也在旁边")
        cleaned = cleaned.replace("旺玥也快空了", "旺玥也在旁边")
        cleaned = cleaned.replace("皇家美素佳儿旺玥也快空了", "皇家美素佳儿旺玥也在旁边")
        cleaned = cleaned.replace("这罐也快见底了", "旺玥也在旁边")
        cleaned = cleaned.replace("这罐快见底了", "旺玥也在旁边")
        cleaned = cleaned.replace("旺玥见底好几天了", "旺玥也顺手带了")
        cleaned = cleaned.replace("皇家美素佳儿旺玥见底好几天了", "皇家美素佳儿旺玥也顺手带了")
        cleaned = cleaned.replace("旺玥见底了", "旺玥也在里面")
        cleaned = cleaned.replace("皇家美素佳儿旺玥见底了", "皇家美素佳儿旺玥也在里面")
        cleaned = re.sub(r"还有半罐(?:皇家美素佳儿)?旺玥", "还有旺玥", cleaned)
        cleaned = re.sub(r"半罐(?:皇家美素佳儿)?旺玥", "旺玥", cleaned)
        cleaned = re.sub(r"(旺玥|皇家美素佳儿旺玥)还?只剩半罐", r"\1也在里面", cleaned)
        cleaned = re.sub(r"(旺玥|皇家美素佳儿旺玥)还?剩半罐", r"\1也在里面", cleaned)
        cleaned = re.sub(r"(旺玥|皇家美素佳儿旺玥)还?剩小半罐", r"\1也在里面", cleaned)
        cleaned = re.sub(r"旁边还有半罐没喝完的", "顺手一起收好", cleaned)
        cleaned = re.sub(r"还有半罐没喝完的", "也顺手收好", cleaned)
        cleaned = cleaned.replace("家里库存清一清发现不少东西都见底了", "回家把几样东西先放好")
        cleaned = cleaned.replace("库存清一清发现不少东西都见底了", "回家把几样东西先放好")
        cleaned = cleaned.replace("不少东西都见底了", "几样东西都顺手补上了")
        cleaned = cleaned.replace("都见底了", "都顺手补上了")
        cleaned = cleaned.replace("见底了", "顺手补上了")
        cleaned = cleaned.replace("快没了", "该补了")
        cleaned = cleaned.replace("快空了", "也在旁边")
    cleaned = cleaned.replace("台面边边上", "台面边上")
    return cleaned


def _scene_motive_replacement_action(bucket: str) -> str:
    replacements = {
        "快递到货拆箱": "先放在门口一起收",
        "月底清单/购物车清理": "记在清单旁",
        "超市顺手补刚需": "拎回家",
        "家人提醒快没了": "记在手机备忘录里",
        "早餐区/厨房台面整理": "留在台面边",
        "常用位置顺手放好": "放到顺手位置",
        "临出门发现某样东西没了": "记在备忘录里",
    }
    return replacements.get(bucket, "先放在手边")


def _scene_motive_replacement_surface(bucket: str) -> str:
    replacements = {
        "快递到货拆箱": "拆快递",
        "月底清单/购物车清理": "翻清单",
        "超市顺手补刚需": "逛货架",
        "家人提醒快没了": "记备忘录",
        "早餐区/厨房台面整理": "收拾台面",
        "常用位置顺手放好": "理顺手位置",
        "临出门发现某样东西没了": "翻玄关抽屉",
    }
    return replacements.get(bucket, "收拾手边东西")


def _restore_product_permission_wangyue_surface(text: str, *, post_type: str) -> str:
    return text


def _restore_wangyue_selling_context_surface(text: str, plan: dict[str, Any] | None) -> str:
    return text


def _sanitize_product_action_surface_text(text: str, surface: str) -> str:
    if not text:
        return text
    cleaned = text
    cleaned = cleaned.replace("皇家美素佳儿旺玥的杯子", "那杯皇家美素佳儿旺玥")
    cleaned = cleaned.replace("皇家美素佳儿旺玥杯子", "那杯皇家美素佳儿旺玥")
    cleaned = cleaned.replace("旺玥的杯子", "那杯旺玥")
    cleaned = cleaned.replace("旺玥杯子", "那杯旺玥")
    if surface in {"物件在场", "妈妈顺手挪放"}:
        for phrase in (
            "顺手端起来抿了一口",
            "端起来抿了一口",
            "端过去抿了一口",
            "端着杯子喝了两口",
            "端着杯子喝两口",
            "端过去喝了一口",
            "端起来喝了一口",
            "端过去喝",
            "他自己端过去喝了几口",
            "他自己端起来喝了几口",
            "自己端过去喝了几口",
            "自己端起来喝了几口",
            "端过去喝了几口",
            "端起来喝了几口",
            "抿了一口",
            "咕咚几口",
            "看了一眼了两口",
            "看了一眼了几口",
            "喝了几口",
            "喝几口",
            "喝两口",
            "喝完",
        ):
            cleaned = cleaned.replace(phrase, "看了一眼")
        for phrase in ("顺手冲了杯", "顺手冲一杯", "冲了杯旺玥", "冲一杯旺玥", "给他冲了杯"):
            cleaned = cleaned.replace(phrase, "顺手放好")
        for old, new in (
            ("怕他路上想起来要喝又找不到", "怕出门前又找不到"),
            ("路上想起来要喝又找不到", "出门前又找不到"),
            ("想起来要喝又找不到", "要用的时候又找不到"),
            ("路上想起来要喝", "出门前又找"),
            ("想起来要喝", "想起来要找"),
            ("喊他喝", "喊他快点"),
            ("叫他喝", "叫他快点"),
            ("让他喝", "让他快点"),
            ("提醒他喝", "提醒他收好"),
            ("明天早上冲好拿", "明天早上再说"),
            ("明早冲好拿", "明早再说"),
            ("冲好拿", "放好"),
            ("冲好带", "放好"),
        ):
            cleaned = cleaned.replace(old, new)
    elif surface == "孩子轻微使用":
        for phrase in (
            "他自己端过去喝了几口",
            "他自己端起来喝了几口",
            "自己端过去喝了几口",
            "自己端起来喝了几口",
            "端着杯子喝了两口",
            "端着杯子喝两口",
            "端过去喝了一口",
            "端起来喝了一口",
            "端过去喝了几口",
            "端起来喝了几口",
            "咕咚几口",
            "看了一眼了两口",
            "看了一眼了几口",
            "喝了几口",
            "喝几口",
            "喝两口",
        ):
            cleaned = cleaned.replace(phrase, "抿了一口")
        for phrase in ("顺手冲了杯", "顺手冲一杯", "冲了杯旺玥", "冲一杯旺玥", "给他冲了杯"):
            cleaned = cleaned.replace(phrase, "顺手放好")
    cleaned = cleaned.replace("看了一眼又看了一眼", "看了一眼")
    cleaned = cleaned.replace("喊他再看了一眼", "喊他快点")
    cleaned = cleaned.replace("不知道喝没看了一眼", "不知道动没动")
    cleaned = cleaned.replace("昨天没看了一眼的", "昨天没收的")
    cleaned = cleaned.replace("没看了一眼的", "没收的")
    cleaned = cleaned.replace("没看了一眼", "没动")
    cleaned = cleaned.replace("抿了一口又抿了一口", "抿了一口")
    return cleaned


def _sanitize_ugc_post_type_drift_text(text: str) -> str:
    if not text:
        return text
    cleaned = text
    replacements = (
        ("喝了一阵轻复盘", "喝了一阵"),
        ("一段轻复盘", "最近这段"),
        ("轻复盘", "这段时间"),
        ("想问问大家", "先按现在节奏"),
        ("想问下大家", "先按现在节奏"),
        ("想听听大家", "先按现在节奏"),
        ("问问大家", "先按现在节奏"),
        ("听听大家", "先按现在节奏"),
        ("大家一般怎么判断", "先按现在节奏"),
        ("大家怎么判断", "先按现在节奏"),
        ("怎么判断继续还是停", "先按现在这样"),
        ("怎么安排的", "怎么调"),
        ("怎么安排", "怎么调"),
        ("要不要继续", "先按现在这样"),
        ("要不要留", "先按现在这样"),
        ("该继续囤", "先按现在节奏"),
        ("继续囤", "按现在节奏"),
        ("再看别的", "后面再调整"),
        ("有同样情况的妈妈吗", "按我家情况看"),
        ("有同样情况", "按我家情况"),
        ("求经验", "先按现在节奏"),
        ("来聊聊", "先按现在节奏"),
    )
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)
    cleaned = cleaned.replace("，。", "。").replace("，，", "，").replace("。。", "。")
    return cleaned


def _sanitize_usage_record_portable_text(text: str) -> str:
    if not text:
        return text
    cleaned = text
    replacements = (
        ("直接塞进他书包侧兜里了", "就留在桌角了"),
        ("塞进他书包侧兜里了", "留在桌角了"),
        ("塞进书包侧兜里了", "留在桌角了"),
        ("塞进他书包侧兜", "留在桌角"),
        ("塞进书包侧兜", "留在桌角"),
        ("放进书包侧兜", "放在桌角"),
        ("装进书包侧兜", "放在桌角"),
    )
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)
    return cleaned


def _is_bad_body_title_candidate(text: str) -> bool:
    if not text:
        return True
    if text.endswith(("的话", "就看它", "就选它")):
        return True
    if text.startswith(("可以", "建议", "推荐", "我会先")):
        return True
    if any(phrase in text for phrase in ("罐身", "粉质", "不结块", "冲起来", "装备", "泡奶")):
        return True
    if "停课" in text or re.search(r"(?:他们班|班里).{0,6}班里", text):
        return True
    if any(phrase in text for phrase in ("HMO", "DHA", "OPO", "PS", "磷脂酰丝氨酸", "乳铁蛋白", "免疫球蛋白", "胆碱", "叶黄素", "钙铁锌")):
        return True
    return False


def _is_postprocess_blocked(item: ContentBatchItem) -> bool:
    return bool((item.quality_json or {}).get("postprocess_blocked"))


def _generated_article_items(final_output: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = final_output.get("items") if isinstance(final_output, dict) else None
    if not isinstance(raw_items, list):
        title = str((final_output or {}).get("title") or (final_output or {}).get("标题") or "").strip()
        body = str((final_output or {}).get("body") or (final_output or {}).get("正文") or "").strip()
        return [{"title": title, "body": body}] if body else []
    items: list[dict[str, str]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        title = str(raw_item.get("title") or raw_item.get("标题") or "").strip()
        body = str(raw_item.get("body") or raw_item.get("正文") or "").strip()
        if body:
            items.append({"title": title, "body": body})
    return items


def _multi_output_parse_failure_quality(
    *,
    executor: str | None,
    stage_call_count: int,
    run_status: str,
    selected_keywords: list[Any],
    expert_config_code: str | None,
    returned_items: list[dict[str, str]],
    selected_index: int,
) -> dict[str, Any]:
    review_report = _default_unified_review_report()
    review_report.update(
        {
            "hard_results": [
                {
                    "ae_code": "multi_output_parse_guard",
                    "pass": False,
                    "risk_level": "high",
                    "feedback": "多篇输出数量不足，未生成该位置对应的文章",
                    "evidence": {
                        "returned_count": len(returned_items),
                        "selected_index": selected_index,
                    },
                }
            ],
            "rewrite_required": False,
        }
    )
    return {
        "executor": executor,
        "stage_call_count": stage_call_count,
        "run_status": run_status,
        "review_report": review_report,
        "hard_pass": False,
        "soft_score_avg": None,
        "selected_keywords": selected_keywords,
        "expert_config_code": expert_config_code,
        "multi_output": {
            "mode": "items_json",
            "returned_count": len(returned_items),
            "selected_index": selected_index,
            "items": returned_items,
            "materialized_to_batch_items": False,
            "parse_error": "insufficient_multi_output_items",
        },
    }


def _multi_output_execution_groups(items: list[ContentBatchItem]) -> list[list[int]]:
    groups: list[list[int]] = []
    grouped: dict[str, list[int]] = {}
    for item in sorted(items, key=lambda value: int(value.item_no or 0)):
        group = (item.plan_json or {}).get("multi_output_group") or {}
        group_id = str(group.get("group_id") or "").strip() if isinstance(group, dict) else ""
        if not group_id:
            groups.append([int(item.id)])
            continue
        if group_id not in grouped:
            grouped[group_id] = []
            groups.append(grouped[group_id])
        grouped[group_id].append(int(item.id))
    return groups


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
