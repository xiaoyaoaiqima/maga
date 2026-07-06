"""Plan and execute comment batches from uploaded comment business rules."""
from __future__ import annotations

import asyncio
import os
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
from app.services.business_rule_asset_types import COMMENT_BUSINESS_RULE_ASSET_TYPES
from app.services.comment_business_rule_service import (
    COMMENT_BUSINESS_RULE_ASSET_TYPE,
    DEFAULT_COMMENT_BUSINESS_RULE_ASSET_KEY,
    DEFAULT_COMMENT_BATCH_LIMIT,
    DEFAULT_COMMENT_BATCH_TOPIC,
    _clean_corpus_for_prompt,
    _split_examples_from_corpus,
)
from app.services.comment_delivery_ledger_service import CommentDeliveryLedgerService, ledger_entry_to_dict
from app.services.activity_quality_guard_service import (
    A2_NEGATIVE_POST_ARRIVAL_MARKERS,
    A2_NEGATIVE_POST_COMMENT_PROFILE_KEY,
    A2_NEGATIVE_POST_TRANSFER_MARKERS,
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
COMMENT_BATCH_MAX_COUNT = 100
COMMENT_RULE_EXAMPLE_SAMPLE_COUNT = 3
COMMENT_GENERATION_MODEL_TIMEOUT_SECONDS = 18
COMMENT_GENERATION_MODEL_MAX_RETRIES = 2
COMMENT_GENERATION_MAX_TOKENS = 256
COMMENT_THREAD_SHORT_REPLY_FORMAT_CODE = "comment_thread_short_reply"
COMMENT_THREAD_SHORT_REPLY_STYLE_CODES = [
    "reply_to_sister_comment",
    "short_agree",
    "half_sentence_reply",
    "comment_thread_followup",
    "relieved_reaction",
]
COMMENT_THREAD_SHORT_REPLY_SUPPLY_MARKERS = ("有货", "到货", "到了", "能拍", "发货", "买到", "下单")
COMMENT_THREAD_SHORT_REPLY_TRANSFER_MARKERS = ("转奶", "换奶", "不转", "不换")
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
COMMENT_MICRO_REPLY_EMPTY_FALLBACKS = [
    "附近店有货",
    "我去门店拿",
    "店里说到了",
    "刚问还有货",
    "导购说到了",
    "下班门店拿",
    "已经拿到了",
    "门店刚到货",
    "店里还有货",
    "可算上架了",
    "明天去门店",
    "附近店到了",
]
COMMENT_MICRO_BATCH_CHECK_EMPTY_FALLBACKS = [
    "先拿一罐扫了下报告能出来",
    "准备转回来先看罐底报告",
    "先试这罐报告能点开",
    "母婴店说罐底码有报告我拿一罐",
    "刚拿一罐报告能点开",
    "先试前扫了报告能看",
    "拿一罐先看未检出",
    "转回来前先扫罐底码",
    "门店有货报告能出来",
    "快喝完先扫报告再拿",
]
COMMENT_THREAD_SHORT_REPLY_EMPTY_FALLBACKS = [
    "终于到了",
    "我的也快到了",
    "先不转了",
    "有底了",
    "等发货中",
    "能不换就不换",
    "转奶先放放",
    "不折腾了",
    "我的发货了",
    "我也买到了",
]
COMMENT_THREAD_SHORT_REPLY_REQUIRED_MARKERS = (
    "到了",
    "到货",
    "有货",
    "能拍",
    "发货",
    "买到",
    "不转",
    "不换",
    "有底",
    "等发货",
    "不折腾",
    "转奶",
    "换奶",
)
COMMENT_MICRO_REPLY_OVERUSED_TERMS = ("踏实", "续上", "补上")
COMMENT_MICRO_REPLY_AWKWARD_STOCK_PHRASES = ("店里新到", "门店新到", "新到", "奶瓶快空", "刚转奶瓶")
COMMENT_MICRO_REPLY_EMOTIVE_OPENER_LIMIT = 3
COMMENT_MICRO_REPLY_OPENER_LIMIT = 2
COMMENT_MICRO_REPLY_EMOTIVE_OPENERS = ("妈呀", "我天", "救命", "可算", "还好", "吓我")
COMMENT_MICRO_REPLY_OPENERS = (
    "妈呀",
    "我天",
    "救命",
    "可算",
    "还好",
    "吓我",
    "快喊",
    "赶紧",
    "马上",
    "导购",
    "刚到",
    "店里",
    "有货",
    "门店",
)
COMMENT_MICRO_BATCH_CHECK_REPLY_MARKERS = (
    "批批检",
    "每批",
    "每批检测",
    "报告",
    "这批",
    "检过",
    "检测",
    "扫",
    "扫码",
    "扫罐底",
    "罐底码",
    "罐底有",
    "二维码",
    "未检出",
    "Not Detected",
)
COMMENT_MICRO_BATCH_CHECK_FORBIDDEN_CERTAINTY_TERMS = ("保证没问题", "绝对安全", "无风险")
COMMENT_MICRO_BATCH_CHECK_PROFESSIONAL_TERMS = ("60多项", "0.03", "三方数据")
COMMENT_MICRO_BATCH_CHECK_AWKWARD_PHRASES = ("刚转门店", "转门店")
COMMENT_MICRO_BATCH_CHECK_REPEAT_LIMITED_PHRASES = ("店员说这批也检过", "报告能点开")
COMMENT_MICRO_BATCH_CHECK_DANGLING_SUFFIXES = ("批", "批批", "报告能", "每批", "这批")
COMMENT_MICRO_BATCH_CHECK_CONTEXT_MARKERS = A2_NEGATIVE_POST_ARRIVAL_MARKERS + A2_NEGATIVE_POST_TRANSFER_MARKERS
COMMENT_MICRO_BATCH_CHECK_DETAIL_GROUPS = (
    ("扫码", "扫罐底", "扫了", "一扫", "二维码", "码"),
    ("报告",),
    ("每批", "批批检", "检测"),
    ("未检出", "Not Detected"),
    ("有底", "放心", "保障"),
)
LOW_INFORMATION_COMMENT_REWRITE_INSTRUCTIONS = [
    "上一轮评论只有空泛开头，信息量太低",
    "只输出一条35字以内的评论正文",
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

    async def create_and_execute_batch(
        self,
        *,
        asset_key: str,
        keyword_asset_key: str | None = None,
        quality_guard_profile_key: str | None = None,
        business_rule: str | None = None,
        rule_id: str | None = None,
        source_row_no: int | None = None,
        draft_corpus: str | None = None,
        draft_rule_id: str | None = None,
        draft_source_row_no: int | None = None,
        count: int | None = None,
        created_by: str | None = None,
    ) -> CommentBatchExecutionResult:
        asset = await self._require_rule_asset(asset_key)
        all_rules = self._rule_items(asset)
        focus_business_rule = _normalize_business_rule(business_rule)
        rules = self._rules_for_business_rule(all_rules, focus_business_rule) if focus_business_rule else all_rules
        focus_rule_id = str(rule_id or "").strip() or None
        focus_source_row_no = _int_or_none(source_row_no)
        if focus_rule_id or focus_source_row_no is not None:
            rules = self._rules_for_single_item(
                rules,
                rule_id=focus_rule_id,
                source_row_no=focus_source_row_no,
            )
        draft_override = _normalize_draft_rule_override(
            draft_corpus=draft_corpus,
            draft_rule_id=draft_rule_id or focus_rule_id,
            draft_source_row_no=draft_source_row_no if draft_source_row_no is not None else focus_source_row_no,
        )
        if draft_override:
            rules = self._rules_with_draft_override(rules, draft_override)
        focus_single_rule = bool(focus_rule_id) or focus_source_row_no is not None
        limit = self._generation_limit(
            asset,
            rules,
            requested_count=count,
            allow_repeat=bool(focus_business_rule) or focus_single_rule,
        )
        resolved_keyword_asset_key = _resolve_keyword_asset_key(keyword_asset_key, asset)
        resolved_quality_guard_profile_key = quality_guard_profile_key or quality_guard_profile_key_from_asset(asset)
        quality_guard_profile = resolve_quality_guard_profile(resolved_quality_guard_profile_key)
        if resolved_quality_guard_profile_key and not quality_guard_profile:
            raise ValueError(f"unknown quality_guard_profile_key: {resolved_quality_guard_profile_key}")
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
                "business_rule_filter": focus_business_rule,
                "rule_id_filter": focus_rule_id,
                "source_row_no_filter": focus_source_row_no,
                "draft_rule_override": _draft_override_summary(draft_override),
                "executor": self.executor_code,
            },
            diversity_plan_json={
                "source": COMMENT_BUSINESS_RULE_ASSET_TYPE,
                "rule_count": len(all_rules),
                "filtered_rule_count": len(rules),
                "selected_count": len(selected_rules),
                "selection_mode": selection_mode,
                "business_rule_filter": focus_business_rule,
                "rule_id_filter": focus_rule_id,
                "source_row_no_filter": focus_source_row_no,
                "draft_rule_override": _draft_override_summary(draft_override),
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
                    plan_json=self._plan_from_rule(
                        rule,
                        asset=asset,
                        item_no=item_no,
                        keyword_asset_key=resolved_keyword_asset_key,
                        quality_guard_profile_key=resolved_quality_guard_profile_key,
                    ),
                )
            )
        await self.db.flush()
        job_id = job.id
        item_ids = [item.id for item in await self._planned_items(job_id)]
        await self.db.commit()

        semaphore = asyncio.Semaphore(COMMENT_BATCH_EXECUTION_CONCURRENCY)

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
            await self._rebalance_micro_reply_batch_variation(job_id)
        self.db.expire_all()
        job = await self._require_job(job_id)
        items = await self._planned_items(job_id)
        ActivityQualityGuardService().review_batch(job, items)
        CommentBatchVariationReviewService().review_batch(items)
        await self.db.flush()
        await self.db.commit()
        generated_items = [item for item in items if item.status == "generated"]
        return CommentBatchExecutionResult(
            batch_id=job_id,
            requested_limit=requested_output_count,
            generated_count=len(generated_items),
            failed_count=failed,
            item_ids=[item.id for item in items],
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

    async def _planned_items(self, batch_id: int) -> list[ContentBatchItem]:
        result = await self.db.execute(
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

    def _plan_from_rule(
        self,
        rule: dict[str, Any],
        *,
        asset: AssetRegistry,
        item_no: int,
        keyword_asset_key: str = DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
        quality_guard_profile_key: str | None = None,
    ) -> dict[str, Any]:
        selected_examples, example_meta = self._selected_prompt_examples(rule)
        keyword_selection, keyword_selection_meta = _keyword_selection_with_rule_overrides(
            _keyword_selection_from_asset(asset),
            rule,
            item_no=item_no,
        )
        plan = {
            "rule_type": "business_rule",
            "render_reference_examples": True,
            "item_no": item_no,
            "asset_key": asset.asset_key,
            "keyword_asset_key": keyword_asset_key,
            "keyword_selection": keyword_selection,
            "generation_requirements": _generation_requirements_from_asset(asset),
            "batch_variation_review": _batch_variation_review_from_asset(asset),
            "quality_guard_profile_key": quality_guard_profile_key,
            "rule_asset_id": asset.id,
            "rule_asset_version": asset.version_no,
            "rule_id": rule.get("rule_id"),
            "business_rule": _business_rule_name(rule),
            "corpus": rule.get("corpus"),
            "examples": selected_examples,
            "supplements": [],
            "draft_rule_override": rule.get("draft_rule_override"),
            **example_meta,
            **keyword_selection_meta,
            "source_row_no": rule.get("source_row_no"),
            "output_fields": ["comment"],
        }
        output_config = _comment_generation_output_config(rule, asset)
        if output_config:
            plan["output_format"] = output_config
            plan["output_format_mode"] = output_config["mode"]
            plan["expansion_count"] = output_config["count"]
        for key in ("prompt_slots", "comment_prompt_slots"):
            if rule.get(key):
                plan[key] = rule.get(key)
        return plan

    def _selected_prompt_examples(self, rule: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        examples = [str(item).strip() for item in rule.get("examples") or [] if str(item).strip()]
        supplements = [str(item).strip() for item in rule.get("supplements") or [] if str(item).strip()]
        pool = examples or supplements
        selected_indices = _sample_indices(len(pool), COMMENT_RULE_EXAMPLE_SAMPLE_COUNT)
        # 重要逻辑：评论也只把少量抽样示例放进 prompt，保留真人语气颗粒，
        # 避免旧式全量示例池把模型拉回模板复刻。
        selected = [pool[index] for index in selected_indices]
        return selected, {
            "example_pool_count": len(examples),
            "supplement_pool_count": len(supplements),
            "example_sample_count": len(selected),
            "selected_example_source": "examples" if examples else ("supplements" if supplements else "none"),
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
                used_empty_fallback = False
                if not comments:
                    fallback_comment = (
                        self._fallback_empty_micro_reply(item)
                        or self._fallback_empty_thread_short_reply(item)
                        or self._fallback_empty_micro_batch_check_reply(item)
                    )
                    comments = [fallback_comment] if fallback_comment else []
                    used_empty_fallback = bool(fallback_comment)
                if not comments:
                    raise ValueError("content.generate returned empty comment")
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
            items = await self._planned_items(batch_id)
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
            items = await self._planned_items(batch_id)
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

    async def _rebalance_micro_reply_batch_variation(self, batch_id: int) -> None:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == batch_id)
                .order_by(ContentBatchItem.item_no)
            )
            items = list(result.scalars().all())
            generated_items = [item for item in items if item.status == "generated" and item.body]
            if not generated_items or not any(
                _uses_comment_micro_reply_format(item.plan_json or {})
                or _uses_comment_micro_batch_check_reply_format(item.plan_json or {})
                or _uses_comment_thread_short_reply_format(item.plan_json or {})
                for item in generated_items
            ):
                return

            used_bodies: set[str] = set()
            opener_counts: dict[str, int] = {}
            batch_check_phrase_counts: dict[str, int] = {}
            emotive_opener_count = 0
            for item in generated_items:
                if _uses_comment_micro_batch_check_reply_format(item.plan_json or {}):
                    previous_body = (item.body or "").strip()
                    body = self._normalize_comment_length(item, item.body or "")
                    reason = self._micro_batch_check_reply_variation_reason(
                        body,
                        used_bodies,
                        item.plan_json or {},
                    )
                    if not reason:
                        phrase = self._micro_batch_check_repeat_limited_phrase(body)
                    else:
                        phrase = ""
                    if phrase and batch_check_phrase_counts.get(phrase, 0) >= 1:
                        reason = "batch_check_phrase_overused"
                    if reason:
                        quality = dict(item.quality_json or {})
                        quality["micro_batch_check_variation_guard"] = {
                            "reason": reason,
                            "previous_body": previous_body,
                            "final_body": body,
                            "action": "flag_only",
                        }
                        item.quality_json = quality

                    item.body = body
                    used_bodies.add(body)
                    phrase = self._micro_batch_check_repeat_limited_phrase(body)
                    if phrase:
                        batch_check_phrase_counts[phrase] = batch_check_phrase_counts.get(phrase, 0) + 1
                    ActivityQualityGuardService().review_item(item)
                    continue

                if _uses_comment_thread_short_reply_format(item.plan_json or {}):
                    previous_body = (item.body or "").strip()
                    body = self._normalize_comment_length(item, item.body or "")
                    reason = self._thread_short_reply_variation_reason(body, used_bodies)
                    if reason:
                        replacement = self._thread_short_reply_variation_fallback(item=item, used_bodies=used_bodies)
                        if replacement:
                            body = replacement
                            quality = dict(item.quality_json or {})
                            quality["thread_short_reply_variation_guard"] = {
                                "reason": reason,
                                "previous_body": previous_body,
                                "final_body": body,
                            }
                            item.quality_json = quality
                    item.body = body
                    used_bodies.add(body)
                    ActivityQualityGuardService().review_item(item)
                    continue

                if not _uses_comment_micro_reply_format(item.plan_json or {}):
                    body = (item.body or "").strip()
                    if body:
                        used_bodies.add(body)
                    continue

                body = self._normalize_comment_length(item, item.body or "")
                reason = self._micro_reply_variation_reason(
                    body,
                    used_bodies,
                    opener_counts,
                    emotive_opener_count,
                )
                if reason:
                    replacement = self._micro_reply_variation_fallback(
                        item=item,
                        used_bodies=used_bodies,
                        opener_counts=opener_counts,
                        emotive_opener_count=emotive_opener_count,
                    )
                    if replacement:
                        previous_body = body
                        body = replacement
                        quality = dict(item.quality_json or {})
                        quality["micro_reply_variation_guard"] = {
                            "reason": reason,
                            "previous_body": previous_body,
                            "final_body": body,
                        }
                        item.quality_json = quality

                item.body = body
                used_bodies.add(body)
                opener = self._micro_reply_opener(body)
                if opener:
                    opener_counts[opener] = opener_counts.get(opener, 0) + 1
                if self._micro_reply_has_emotive_opener(body):
                    emotive_opener_count += 1
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
            "rewrite_instructions": LOW_INFORMATION_COMMENT_REWRITE_INSTRUCTIONS,
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
                "只输出一条35字以内的评论正文",
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
                "只输出一条35字以内的评论正文",
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
        if _uses_comment_micro_batch_check_reply_format(plan):
            return 32
        if str(plan.get("quality_guard_profile_key") or "").strip() == A2_PLOT_DISCUSSION_COMMENT_PROFILE_KEY:
            return 50
        if str(plan.get("quality_guard_profile_key") or "").strip() == A2_NEGATIVE_POST_COMMENT_PROFILE_KEY:
            return 45
        if str(plan.get("quality_guard_profile_key") or "").strip() == A2_SENTIMENT_COMMENT_PROFILE_KEY:
            return 45
        if str(plan.get("quality_guard_profile_key") or "").strip() == A2_SENTIMENT_POST_PROFILE_KEY:
            return 100
        return 35

    def _normalize_comment_length(self, item: ContentBatchItem, comment: str) -> str:
        normalized = comment.strip()
        if self._preserve_overlong_comment_for_guard(item):
            return normalized
        if _uses_comment_micro_reply_format(item.plan_json or {}) and len(normalized) < 5:
            normalized = self._fallback_empty_micro_reply(item) or normalized
        if _uses_comment_thread_short_reply_format(item.plan_json or {}):
            if len(normalized) < 3:
                return self._fallback_empty_thread_short_reply(item) or normalized
            fitted = self._fit_comment_length(normalized, max_chars=self._comment_max_chars(item))
            if self._thread_short_reply_guard_reason(fitted):
                return self._fallback_empty_thread_short_reply(item) or fitted
            return fitted
        if _uses_comment_micro_batch_check_reply_format(item.plan_json or {}):
            fitted = self._fit_comment_length(normalized, max_chars=self._comment_max_chars(item))
            return fitted
        return self._fit_comment_length(normalized, max_chars=self._comment_max_chars(item))

    def _micro_reply_variation_reason(
        self,
        comment: str,
        used_bodies: set[str],
        opener_counts: dict[str, int],
        emotive_opener_count: int = 0,
    ) -> str:
        if comment in used_bodies:
            return "duplicate_body"
        if self._micro_reply_has_awkward_stock_phrase(comment):
            return "awkward_stock_phrase"
        if any(term in comment for term in COMMENT_MICRO_REPLY_OVERUSED_TERMS):
            return "overused_summary_term"
        if self._micro_reply_has_emotive_opener(comment) and emotive_opener_count >= COMMENT_MICRO_REPLY_EMOTIVE_OPENER_LIMIT:
            return "emotive_opener_overused"
        opener = self._micro_reply_opener(comment)
        if opener and opener_counts.get(opener, 0) >= COMMENT_MICRO_REPLY_OPENER_LIMIT:
            return "opener_overused"
        return ""

    def _micro_reply_variation_fallback(
        self,
        *,
        item: ContentBatchItem,
        used_bodies: set[str],
        opener_counts: dict[str, int],
        emotive_opener_count: int = 0,
    ) -> str:
        if not _uses_comment_micro_reply_format(item.plan_json or {}):
            return ""
        start = max(int(getattr(item, "item_no", 1) or 1) - 1, 0)
        for offset in range(len(COMMENT_MICRO_REPLY_EMPTY_FALLBACKS)):
            candidate = COMMENT_MICRO_REPLY_EMPTY_FALLBACKS[(start + offset) % len(COMMENT_MICRO_REPLY_EMPTY_FALLBACKS)]
            if candidate in used_bodies:
                continue
            if any(term in candidate for term in COMMENT_MICRO_REPLY_OVERUSED_TERMS):
                continue
            if self._micro_reply_has_awkward_stock_phrase(candidate):
                continue
            if self._micro_reply_has_emotive_opener(candidate) and emotive_opener_count >= COMMENT_MICRO_REPLY_EMOTIVE_OPENER_LIMIT:
                continue
            opener = self._micro_reply_opener(candidate)
            if opener and opener_counts.get(opener, 0) >= COMMENT_MICRO_REPLY_OPENER_LIMIT:
                continue
            return candidate
        return ""

    def _thread_short_reply_variation_reason(self, comment: str, used_bodies: set[str]) -> str:
        if comment in used_bodies:
            return "duplicate_body"
        return self._thread_short_reply_guard_reason(comment)

    @staticmethod
    def _thread_short_reply_guard_reason(comment: str) -> str:
        normalized = re.sub(r"[，。！？、,.!?\s]+", "", comment or "")
        if not normalized:
            return "empty"
        if len(normalized) < 3:
            return "too_short"
        if normalized in {"这个挺好", "先喝着", "再等等", "问了几家店", "问了几家", "我也", "这个", "这罐"}:
            return "low_information"
        if not any(marker in normalized for marker in COMMENT_THREAD_SHORT_REPLY_REQUIRED_MARKERS):
            return "missing_context_marker"
        return ""

    @staticmethod
    def _thread_short_reply_variation_fallback(*, item: ContentBatchItem, used_bodies: set[str]) -> str:
        start = max(int(getattr(item, "item_no", 1) or 1) - 1, 0)
        for offset in range(len(COMMENT_THREAD_SHORT_REPLY_EMPTY_FALLBACKS)):
            candidate = COMMENT_THREAD_SHORT_REPLY_EMPTY_FALLBACKS[(start + offset) % len(COMMENT_THREAD_SHORT_REPLY_EMPTY_FALLBACKS)]
            if candidate not in used_bodies:
                return candidate
        return ""

    def _micro_batch_check_reply_variation_reason(
        self,
        comment: str,
        used_bodies: set[str],
        plan: dict[str, Any] | None = None,
    ) -> str:
        if comment in used_bodies:
            return "duplicate_body"
        return self._micro_batch_check_reply_guard_reason(comment, plan)

    @staticmethod
    def _micro_batch_check_repeat_limited_phrase(comment: str) -> str:
        normalized = comment.strip()
        for phrase in COMMENT_MICRO_BATCH_CHECK_REPEAT_LIMITED_PHRASES:
            if phrase in normalized:
                return phrase
        return ""

    @staticmethod
    def _micro_batch_check_detail_group_count(comment: str) -> int:
        normalized = comment.strip()
        return sum(1 for group in COMMENT_MICRO_BATCH_CHECK_DETAIL_GROUPS if any(marker in normalized for marker in group))

    def _micro_batch_check_reply_guard_reason(self, comment: str, plan: dict[str, Any] | None = None) -> str:
        normalized = comment.strip()
        if any(term in normalized for term in COMMENT_MICRO_BATCH_CHECK_FORBIDDEN_CERTAINTY_TERMS):
            return "absolute_guarantee"
        if any(term in normalized for term in COMMENT_MICRO_BATCH_CHECK_PROFESSIONAL_TERMS):
            return "too_professional"
        if any(phrase in normalized for phrase in COMMENT_MICRO_BATCH_CHECK_AWKWARD_PHRASES):
            return "awkward_batch_check_phrase"
        if self._micro_batch_check_detail_group_count(normalized) >= 4:
            return "overstuffed_batch_check_details"
        if re.search(r"\s", normalized):
            return "awkward_whitespace"
        if normalized.endswith(COMMENT_MICRO_BATCH_CHECK_DANGLING_SUFFIXES):
            return "incomplete_batch_check_phrase"
        required_markers = self._micro_batch_check_required_context_markers(plan)
        if not any(marker in normalized for marker in required_markers):
            return "missing_context_marker"
        if not any(marker in normalized for marker in COMMENT_MICRO_BATCH_CHECK_REPLY_MARKERS):
            return "missing_batch_check_marker"
        if len(normalized) < 8:
            return "too_short"
        return ""

    @staticmethod
    def _micro_batch_check_required_context_markers(plan: dict[str, Any] | None) -> tuple[str, ...]:
        if not isinstance(plan, dict):
            return COMMENT_MICRO_BATCH_CHECK_CONTEXT_MARKERS
        profile_key = str(plan.get("quality_guard_profile_key") or "").strip()
        profile = resolve_quality_guard_profile(profile_key)
        if not profile or profile.profile_key != A2_NEGATIVE_POST_COMMENT_PROFILE_KEY:
            return COMMENT_MICRO_BATCH_CHECK_CONTEXT_MARKERS
        source = "\n".join(
            str(value or "")
            for value in (
                plan.get("business_rule"),
                plan.get("corpus"),
                " ".join(str(example) for example in plan.get("examples") or []),
            )
        )
        keyword = derive_profile_keyword_from_text(source, profile)
        if keyword == "转奶安抚":
            return A2_NEGATIVE_POST_TRANSFER_MARKERS
        if keyword == "到货安抚":
            return A2_NEGATIVE_POST_ARRIVAL_MARKERS
        return COMMENT_MICRO_BATCH_CHECK_CONTEXT_MARKERS

    @staticmethod
    def _micro_reply_opener(comment: str) -> str:
        normalized = comment.strip()
        for opener in COMMENT_MICRO_REPLY_OPENERS:
            if normalized.startswith(opener):
                return opener
        return normalized[:2]

    @staticmethod
    def _micro_reply_has_emotive_opener(comment: str) -> bool:
        normalized = comment.strip()
        return any(normalized.startswith(opener) for opener in COMMENT_MICRO_REPLY_EMOTIVE_OPENERS)

    @staticmethod
    def _micro_reply_has_awkward_stock_phrase(comment: str) -> bool:
        normalized = comment.strip()
        return any(phrase in normalized for phrase in COMMENT_MICRO_REPLY_AWKWARD_STOCK_PHRASES) or normalized.endswith("导购说到")

    @staticmethod
    def _fallback_empty_micro_reply(item: ContentBatchItem) -> str:
        plan = item.plan_json or {}
        if not _uses_comment_micro_reply_format(plan):
            return ""
        # 只给运营明确选择的微评论格式兜底，避免短输出解析为空时整批掉量。
        index = max(int(getattr(item, "item_no", 1) or 1) - 1, 0) % len(COMMENT_MICRO_REPLY_EMPTY_FALLBACKS)
        return COMMENT_MICRO_REPLY_EMPTY_FALLBACKS[index]

    @staticmethod
    def _fallback_empty_thread_short_reply(item: ContentBatchItem) -> str:
        plan = item.plan_json or {}
        if not _uses_comment_thread_short_reply_format(plan):
            return ""
        index = max(int(getattr(item, "item_no", 1) or 1) - 1, 0) % len(COMMENT_THREAD_SHORT_REPLY_EMPTY_FALLBACKS)
        return COMMENT_THREAD_SHORT_REPLY_EMPTY_FALLBACKS[index]

    @staticmethod
    def _fallback_empty_micro_batch_check_reply(item: ContentBatchItem) -> str:
        plan = item.plan_json or {}
        if not _uses_comment_micro_batch_check_reply_format(plan):
            return ""
        index = max(int(getattr(item, "item_no", 1) or 1) - 1, 0) % len(COMMENT_MICRO_BATCH_CHECK_EMPTY_FALLBACKS)
        return COMMENT_MICRO_BATCH_CHECK_EMPTY_FALLBACKS[index]

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
    *,
    item_no: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    normalized = _copy_keyword_selection(keyword_selection)
    if not _should_force_thread_short_reply(rule, item_no=item_no):
        return normalized, {}

    if normalized is None:
        normalized = {}

    # 重要逻辑：短接楼比例属于单条业务规则的计划层控制，不能写进全局评论格式池；
    # 否则其它活动会被 5-12 字短句误伤。
    normalized["comment_format_control"] = [COMMENT_THREAD_SHORT_REPLY_FORMAT_CODE]
    normalized["comment_speaking_style"] = list(COMMENT_THREAD_SHORT_REPLY_STYLE_CODES)
    return normalized, {
        "keyword_selection_override": {
            "reason": "supply_transfer_thread_short_reply",
            "comment_format_control": [COMMENT_THREAD_SHORT_REPLY_FORMAT_CODE],
            "comment_speaking_style": list(COMMENT_THREAD_SHORT_REPLY_STYLE_CODES),
        }
    }


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


def _should_force_thread_short_reply(rule: dict[str, Any], *, item_no: int) -> bool:
    if item_no % 2 != 0:
        return False
    source = "\n".join(
        str(value or "")
        for value in (
            _business_rule_name(rule),
            rule.get("corpus"),
            " ".join(str(example) for example in rule.get("examples") or []),
            " ".join(str(supplement) for supplement in rule.get("supplements") or []),
        )
    )
    normalized = re.sub(r"\s+", "", source)
    has_short_reply_marker = any(
        marker in normalized
        for marker in (
            "短接楼",
            "短句可以占一半",
            "短句也要",
            "评论区接一句",
            "接一句",
            "接楼感",
            "顺手报个信",
            "可以很短",
        )
    )
    has_supply_transfer_keyword = "有货+转奶" in source
    has_supply_transfer_semantics = any(marker in source for marker in COMMENT_THREAD_SHORT_REPLY_SUPPLY_MARKERS) and any(
        marker in source for marker in COMMENT_THREAD_SHORT_REPLY_TRANSFER_MARKERS
    )
    return has_short_reply_marker and (has_supply_transfer_keyword or has_supply_transfer_semantics)


def _generation_requirements_from_asset(asset: AssetRegistry | None) -> str | None:
    for source in _asset_json_sources(asset):
        value = source.get("generation_requirements")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _batch_variation_review_from_asset(asset: AssetRegistry | None) -> dict[str, Any] | None:
    for source in _asset_json_sources(asset):
        value = source.get("batch_variation_review")
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


def _business_rule_name(rule: dict[str, Any]) -> str | None:
    value = rule.get("business_rule")
    if value is None:
        value = rule.get("comment_" + "angle")
    return _normalize_business_rule(value)


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
) -> dict[str, Any] | None:
    corpus = str(draft_corpus or "").strip()
    if not corpus:
        return None
    rule_id = str(draft_rule_id or "").strip() or None
    source_row_no = _int_or_none(draft_source_row_no)
    if not rule_id and source_row_no is None:
        raise ValueError("draft_corpus requires draft_rule_id, draft_source_row_no, rule_id, or source_row_no")
    return {"corpus": corpus, "rule_id": rule_id, "source_row_no": source_row_no}


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


def _comment_item_soft_timeout_seconds() -> float:
    raw = os.getenv("MAGA_COMMENT_ITEM_SOFT_TIMEOUT_SECONDS", "35")
    try:
        value = float(raw)
    except ValueError:
        return 35.0
    return max(3.0, value)


def _uses_comment_micro_reply_format(plan: dict[str, Any]) -> bool:
    return _uses_comment_format_control(plan, "comment_micro_reply")


def _uses_comment_micro_batch_check_reply_format(plan: dict[str, Any]) -> bool:
    return _uses_comment_format_control(plan, "comment_micro_batch_check_reply")


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
