"""Build operator-facing reports for MAGA content batch jobs."""
from __future__ import annotations

import json
import re
from io import BytesIO
from collections import Counter
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import (
    ContentAgentRun,
    ContentAgentStageCall,
    ContentBatchItem,
    ContentBatchItemVersion,
    ContentBatchJob,
    ContentFeedback,
)
from app.schemas.content_batch_report import (
    ContentBatchListItem,
    ContentBatchFeedbackInsightResponse,
    ContentBatchFeedbackOptimizationSuggestion,
    ContentBatchFeedbackSample,
    ContentBatchFeedbackStat,
    ContentBatchRejectReason,
    ContentBatchListResponse,
    ContentBatchReportItem,
    ContentBatchReportResponse,
    ContentBatchSimilarityWarning,
    ContentBatchReportSummary,
    ContentBatchStageTrace,
    ContentBatchVersionCompare,
    ContentBatchVersionSnapshot,
    ContentFeedbackSample,
    ContentFeedbackSampleListResponse,
)
from app.services.forbidden_term_review_service import ForbiddenTermReviewService, find_forbidden_hits
from app.services.activity_quality_guard_service import build_article_pool_context_list
from app.services.comment_delivery_ledger_service import CommentDeliveryLedgerService

SIMILARITY_WARNING_THRESHOLD = 0.42

_FEEDBACK_CATEGORY_LABELS = {
    "unnatural": "不自然/生硬",
    "too_long": "太长/啰嗦",
    "too_ad_like": "广告感太强",
    "fact_issue": "信息不准确",
    "tone_mismatch": "语气不对",
    "forbidden_term": "有违禁词",
    "rule_mismatch": "不符合业务规则",
}
_FEEDBACK_ACTION_LABELS = {
    "approve": "通过",
    "request_revision": "要求修改",
    "manual_edit": "人工编辑",
    "accept_rewrite": "采纳改写",
    "reject_rewrite": "不采纳改写",
}
_FEEDBACK_REVIEW_STATUS_LABELS = {
    "approved": "已通过",
    "needs_revision": "待修改",
    "manual_edited": "人工编辑",
}
_REWRITE_DECISION_LABELS = {
    "auto_rewrite_requested": "触发系统改写",
    "accept_rewrite": "采纳改写",
    "reject_rewrite": "不采纳改写",
}


class ContentBatchReportService:
    """Return a compact batch result view suitable for operator review screens."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_batch_reports(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        asset_key: str | None = None,
        rule_id: str | None = None,
        source_row_no: int | None = None,
    ) -> ContentBatchListResponse:
        conditions = []
        normalized_asset_key = str(asset_key or "").strip()
        if normalized_asset_key:
            conditions.append(ContentBatchJob.asset_key == normalized_asset_key)

        rule_filter_enabled = (
            bool(str(rule_id or "").strip()) or source_row_no is not None
        )
        base_query = select(ContentBatchJob).order_by(
            ContentBatchJob.create_time.desc(),
            ContentBatchJob.id.desc(),
        )
        if conditions:
            base_query = base_query.where(*conditions)

        item_cache: dict[int, list[ContentBatchItem]] = {}
        if rule_filter_enabled:
            # 重要逻辑：批次与单条规则的关系目前只存在 item.plan_json，
            # 首版不新增表和迁移，所以列表按 job 拉取后用计划快照过滤。
            result = await self.db.execute(base_query)
            filtered_jobs: list[ContentBatchJob] = []
            for job in result.scalars().all():
                items = await self._batch_items(job.id)
                if self._items_match_rule_filter(items, rule_id=rule_id, source_row_no=source_row_no):
                    item_cache[job.id] = items
                    filtered_jobs.append(job)
            total = len(filtered_jobs)
            jobs = filtered_jobs[offset : offset + limit]
        else:
            total_query = select(func.count()).select_from(ContentBatchJob)
            if conditions:
                total_query = total_query.where(*conditions)
            total_result = await self.db.execute(total_query)
            total = int(total_result.scalar_one() or 0)
            result = await self.db.execute(base_query.offset(offset).limit(limit))
            jobs = list(result.scalars().all())

        list_items: list[ContentBatchListItem] = []
        for job in jobs:
            items = item_cache.get(job.id) or await self._batch_items(job.id)
            versions_by_item = await self._versions_for_items(items)
            feedback_counts = await self._feedback_counts_for_items(items)
            forbidden_terms = await self._forbidden_terms_for_job(job)
            report_items = [
                self._report_item(
                    item,
                    [],
                    versions=versions_by_item.get(item.id, []),
                    run=None,
                    feedback_count=feedback_counts.get(item.id, 0),
                    forbidden_terms=forbidden_terms,
                )
                for item in items
            ]
            self._attach_similarity_warnings(report_items)
            list_items.append(
                ContentBatchListItem(
                    batch_id=job.id,
                    batch_code=job.batch_code,
                    asset_key=job.asset_key,
                    product_topic=job.product_topic,
                    target_audience=job.target_audience,
                    persona_target=self._job_persona_target(job),
                    style=job.style,
                    status=job.status,
                    count=job.count,
                    summary=self._summary(report_items),
                    create_time=job.create_time,
                    update_time=job.update_time,
                )
            )
        return ContentBatchListResponse(total=total, items=list_items)

    def _items_match_rule_filter(
        self,
        items: list[ContentBatchItem],
        *,
        rule_id: str | None,
        source_row_no: int | None,
    ) -> bool:
        normalized_rule_id = str(rule_id or "").strip()
        for item in items:
            plan = item.plan_json or {}
            plan_rule_id = str(plan.get("rule_id") or "").strip()
            plan_source_row_no = _int_or_none(plan.get("source_row_no"))
            if normalized_rule_id and plan_rule_id != normalized_rule_id:
                continue
            if source_row_no is not None and plan_source_row_no != source_row_no:
                continue
            return True
        return False

    async def get_batch_report(self, batch_id: int) -> ContentBatchReportResponse:
        job = await self._require_job(batch_id)
        items = await self._batch_items(batch_id)
        stage_calls = await self._stage_calls_for_items(items)
        stages_by_run = self._group_stages_by_run(stage_calls)
        runs_by_id = await self._runs_for_items(items)
        versions_by_item = await self._versions_for_items(items)
        feedback_counts = await self._feedback_counts_for_items(items)
        forbidden_terms = await self._forbidden_terms_for_job(job)
        report_items = [
            self._report_item(
                item,
                stages_by_run.get(item.run_id or -1, []),
                versions=versions_by_item.get(item.id, []),
                run=runs_by_id.get(item.run_id or -1),
                feedback_count=feedback_counts.get(item.id, 0),
                forbidden_terms=forbidden_terms,
            )
            for item in items
        ]
        self._attach_similarity_warnings(report_items)
        return ContentBatchReportResponse(
            batch_id=job.id,
            batch_code=job.batch_code,
            asset_key=job.asset_key,
            product_topic=job.product_topic,
            target_audience=job.target_audience,
            persona_target=self._job_persona_target(job),
            style=job.style,
            status=job.status,
            count=job.count,
            summary=self._summary(report_items),
            items=report_items,
        )

    async def export_batch_report_excel(self, batch_id: int) -> tuple[str, bytes]:
        report = await self.get_batch_report(batch_id)
        workbook = Workbook()
        result_sheet = workbook.active
        result_sheet.title = "生文结果"

        _write_result_sheet(result_sheet, report)

        output = BytesIO()
        workbook.save(output)
        filename = _excel_filename(report)
        return filename, output.getvalue()

    async def export_article_pool_excel(self, batch_id: int) -> tuple[str, bytes]:
        report = await self.get_batch_report(batch_id)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "文章池数据"
        _write_article_pool_sheet(sheet, report)

        output = BytesIO()
        workbook.save(output)
        filename = _article_pool_excel_filename(report)
        await self._record_article_pool_delivery(report, filename)
        return filename, output.getvalue()

    async def _record_article_pool_delivery(self, report: ContentBatchReportResponse, filename: str) -> None:
        items = _article_pool_export_items(report.items)
        if not items:
            return
        entries = [
            {
                "category": item.content_angle or item.asset_combo_key or "",
                "comment_text": item.body or "",
                "batch_id": report.batch_id,
                "item_id": item.item_id,
                "metadata_json": {
                    "batch_code": report.batch_code,
                    "product_topic": report.product_topic,
                    "item_no": item.item_no,
                },
            }
            for item in items
            if str(item.body or "").strip()
        ]
        await CommentDeliveryLedgerService(self.db).upsert_many(
            asset_key=report.asset_key,
            entries=entries,
            source_type="maga_batch",
            source_uri=f"batch:{report.batch_id}/{filename}",
            delivered_by="content_batch_export",
        )

    async def list_feedback_samples(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        review_status: str | None = None,
    ) -> ContentFeedbackSampleListResponse:
        conditions = []
        if review_status:
            conditions.append(ContentFeedback.review_status == review_status)
        total_query = (
            select(func.count())
            .select_from(ContentFeedback)
            .join(ContentBatchItem, ContentBatchItem.id == ContentFeedback.item_id)
            .join(ContentBatchJob, ContentBatchJob.id == ContentBatchItem.batch_id, isouter=True)
        )
        query = (
            select(ContentFeedback, ContentBatchItem, ContentBatchJob)
            .join(ContentBatchItem, ContentBatchItem.id == ContentFeedback.item_id)
            .join(ContentBatchJob, ContentBatchJob.id == ContentBatchItem.batch_id, isouter=True)
            .order_by(ContentFeedback.create_time.desc(), ContentFeedback.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if conditions:
            total_query = total_query.where(*conditions)
            query = query.where(*conditions)
        total_result = await self.db.execute(total_query)
        result = await self.db.execute(query)
        return ContentFeedbackSampleListResponse(
            total=int(total_result.scalar_one() or 0),
            items=[
                self._feedback_sample(feedback, item, job)
                for feedback, item, job in result.all()
            ],
        )

    async def build_feedback_insights(self, batch_id: int) -> ContentBatchFeedbackInsightResponse:
        job = await self._require_job(batch_id)
        items = await self._batch_items(batch_id)
        item_by_id = {item.id: item for item in items}
        feedbacks = await self._feedbacks_for_items(items)
        category_counter: Counter[str] = Counter()
        action_counter: Counter[str] = Counter()
        review_status_counter: Counter[str] = Counter()
        rewrite_decision_counter: Counter[str] = Counter()
        evidence_by_category: dict[str, list[str]] = {}
        samples: list[ContentBatchFeedbackSample] = []

        for feedback in feedbacks:
            metadata = feedback.metadata_json if isinstance(feedback.metadata_json, dict) else {}
            categories = _feedback_categories(metadata)
            category_counter.update(categories)
            action_counter.update([feedback.action])
            review_status_counter.update([feedback.review_status])
            if metadata.get("auto_rewrite") is True:
                rewrite_decision_counter.update(["auto_rewrite_requested"])
            if feedback.action in {"accept_rewrite", "reject_rewrite"}:
                rewrite_decision_counter.update([feedback.action])

            item = item_by_id.get(feedback.item_id)
            evidence = _feedback_evidence(feedback, item)
            if evidence:
                for category in categories:
                    evidence_by_category.setdefault(category, []).append(evidence)
            if len(samples) < 8 and (feedback.comment or feedback.quoted_text or categories):
                samples.append(
                    ContentBatchFeedbackSample(
                        feedback_id=feedback.id,
                        item_id=feedback.item_id,
                        item_no=item.item_no if item else 0,
                        action=feedback.action,
                        review_status=feedback.review_status,
                        comment=feedback.comment,
                        quoted_text=feedback.quoted_text,
                        feedback_categories=categories,
                        create_time=self._format_time(feedback.create_time),
                    )
                )

        # 这里仅生成只读建议单，不写回规则资产，也不触发自动学习。
        return ContentBatchFeedbackInsightResponse(
            batch_id=job.id,
            batch_code=job.batch_code,
            asset_key=job.asset_key,
            product_topic=job.product_topic,
            total_feedback_count=len(feedbacks),
            category_stats=_counter_stats(category_counter, _FEEDBACK_CATEGORY_LABELS),
            action_stats=_counter_stats(action_counter, _FEEDBACK_ACTION_LABELS),
            review_status_stats=_counter_stats(review_status_counter, _FEEDBACK_REVIEW_STATUS_LABELS),
            rewrite_decision_stats=_counter_stats(rewrite_decision_counter, _REWRITE_DECISION_LABELS),
            samples=samples,
            suggestions=self._feedback_optimization_suggestions(
                category_counter=category_counter,
                rewrite_decision_counter=rewrite_decision_counter,
                evidence_by_category=evidence_by_category,
                content_type=_batch_content_type(items),
                total_feedback_count=len(feedbacks),
            ),
        )

    async def build_item_report(self, item: ContentBatchItem) -> ContentBatchReportItem:
        stage_calls = await self._stage_calls_for_items([item])
        versions = (await self._versions_for_items([item])).get(item.id, [])
        run = (await self._runs_for_items([item])).get(item.run_id or -1)
        feedback_count = (await self._feedback_counts_for_items([item])).get(item.id, 0)
        job = await self._job_for_item(item)
        forbidden_terms = await self._forbidden_terms_for_job(job)
        return self._report_item(
            item,
            stage_calls,
            versions=versions,
            run=run,
            feedback_count=feedback_count,
            forbidden_terms=forbidden_terms,
        )

    def _feedback_sample(
        self,
        feedback: ContentFeedback,
        item: ContentBatchItem,
        job: ContentBatchJob | None,
    ) -> ContentFeedbackSample:
        return ContentFeedbackSample(
            feedback_id=feedback.id,
            batch_id=feedback.batch_id,
            batch_code=job.batch_code if job else None,
            item_id=feedback.item_id,
            item_no=item.item_no,
            version_id=feedback.version_id,
            action=feedback.action,
            review_status=feedback.review_status,
            comment=feedback.comment,
            submitter=feedback.submitter,
            title=item.title,
            body_preview=(item.body or "")[:180] if item.body else None,
            product_topic=job.product_topic if job else None,
            target_audience=job.target_audience if job else None,
            persona_target=self._job_persona_target(job) if job else None,
            style=job.style if job else None,
            asset_key=job.asset_key if job else None,
            metadata=feedback.metadata_json,
            create_time=feedback.create_time.strftime("%Y-%m-%d %H:%M:%S") if feedback.create_time else None,
        )

    async def _require_job(self, batch_id: int) -> ContentBatchJob:
        result = await self.db.execute(select(ContentBatchJob).where(ContentBatchJob.id == batch_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError("batch job not found")
        return job

    async def _job_for_item(self, item: ContentBatchItem) -> ContentBatchJob | None:
        if not item.batch_id:
            return None
        result = await self.db.execute(select(ContentBatchJob).where(ContentBatchJob.id == item.batch_id))
        return result.scalar_one_or_none()

    async def _forbidden_terms_for_job(self, job: ContentBatchJob | None) -> list[str]:
        return await ForbiddenTermReviewService(self.db).list_terms(asset_key=job.asset_key if job else None)

    @staticmethod
    def _job_persona_target(job: ContentBatchJob | None) -> str | None:
        if job is None:
            return None
        strategy = job.strategy_json or {}
        value = strategy.get("persona_target") if isinstance(strategy, dict) else None
        return value if isinstance(value, str) and value.strip() else None

    async def _batch_items(self, batch_id: int) -> list[ContentBatchItem]:
        result = await self.db.execute(
            select(ContentBatchItem).where(ContentBatchItem.batch_id == batch_id).order_by(ContentBatchItem.item_no)
        )
        return list(result.scalars().all())

    async def _stage_calls_for_items(self, items: list[ContentBatchItem]) -> list[ContentAgentStageCall]:
        run_ids = [item.run_id for item in items if item.run_id]
        if not run_ids:
            return []
        result = await self.db.execute(
            select(ContentAgentStageCall)
            .where(ContentAgentStageCall.run_id.in_(run_ids))
            .order_by(ContentAgentStageCall.run_id, ContentAgentStageCall.sequence_no)
        )
        return list(result.scalars().all())

    async def _runs_for_items(self, items: list[ContentBatchItem]) -> dict[int, ContentAgentRun]:
        run_ids = [item.run_id for item in items if item.run_id]
        if not run_ids:
            return {}
        result = await self.db.execute(select(ContentAgentRun).where(ContentAgentRun.id.in_(run_ids)))
        return {run.id: run for run in result.scalars().all()}

    async def _latest_versions_for_items(self, items: list[ContentBatchItem]) -> dict[int, ContentBatchItemVersion]:
        item_ids = [item.id for item in items if item.id]
        if not item_ids:
            return {}
        result = await self.db.execute(
            select(ContentBatchItemVersion)
            .where(ContentBatchItemVersion.item_id.in_(item_ids))
            .order_by(ContentBatchItemVersion.item_id, ContentBatchItemVersion.version_no.desc())
        )
        latest: dict[int, ContentBatchItemVersion] = {}
        for version in result.scalars().all():
            latest.setdefault(version.item_id, version)
        return latest

    async def _versions_for_items(self, items: list[ContentBatchItem]) -> dict[int, list[ContentBatchItemVersion]]:
        item_ids = [item.id for item in items if item.id]
        if not item_ids:
            return {}
        result = await self.db.execute(
            select(ContentBatchItemVersion)
            .where(ContentBatchItemVersion.item_id.in_(item_ids))
            .order_by(ContentBatchItemVersion.item_id, ContentBatchItemVersion.version_no)
        )
        versions: dict[int, list[ContentBatchItemVersion]] = {}
        for version in result.scalars().all():
            versions.setdefault(version.item_id, []).append(version)
        return versions

    async def _feedback_counts_for_items(self, items: list[ContentBatchItem]) -> dict[int, int]:
        item_ids = [item.id for item in items if item.id]
        if not item_ids:
            return {}
        result = await self.db.execute(
            select(ContentFeedback.item_id, func.count(ContentFeedback.id))
            .where(ContentFeedback.item_id.in_(item_ids))
            .group_by(ContentFeedback.item_id)
        )
        return {int(item_id): int(count or 0) for item_id, count in result.all()}

    async def _feedbacks_for_items(self, items: list[ContentBatchItem]) -> list[ContentFeedback]:
        item_ids = [item.id for item in items if item.id]
        if not item_ids:
            return []
        result = await self.db.execute(
            select(ContentFeedback)
            .where(ContentFeedback.item_id.in_(item_ids))
            .order_by(ContentFeedback.create_time.desc(), ContentFeedback.id.desc())
        )
        return list(result.scalars().all())

    def _feedback_optimization_suggestions(
        self,
        *,
        category_counter: Counter[str],
        rewrite_decision_counter: Counter[str],
        evidence_by_category: dict[str, list[str]],
        content_type: str,
        total_feedback_count: int,
    ) -> list[ContentBatchFeedbackOptimizationSuggestion]:
        suggestions: list[ContentBatchFeedbackOptimizationSuggestion] = []
        if total_feedback_count <= 0:
            return suggestions

        if category_counter.get("forbidden_term", 0):
            suggestions.append(
                ContentBatchFeedbackOptimizationSuggestion(
                    suggestion_type="business_forbidden_term",
                    target="业务违禁词",
                    title="把运营明确不希望出现的表达收敛到业务违禁词",
                    reason="本批次存在违禁词类反馈，适合走确定性审核闸口，不建议塞回生文提示词。",
                    evidence=_evidence_for_categories(evidence_by_category, ["forbidden_term"]),
                    priority=_suggestion_priority(category_counter["forbidden_term"], total_feedback_count),
                )
            )

        fact_rule_count = category_counter.get("fact_issue", 0) + category_counter.get("rule_mismatch", 0)
        if fact_rule_count:
            suggestions.append(
                ContentBatchFeedbackOptimizationSuggestion(
                    suggestion_type="business_rule",
                    target="业务规则包",
                    title="补充事实边界或业务规则约束",
                    reason="反馈指向信息准确性或业务规则不匹配，应由业务规则包承载，保持生成链路可追溯。",
                    evidence=_evidence_for_categories(evidence_by_category, ["fact_issue", "rule_mismatch"]),
                    priority=_suggestion_priority(fact_rule_count, total_feedback_count),
                )
            )

        expression_categories = ["unnatural", "too_ad_like", "too_long", "tone_mismatch"]
        expression_count = sum(category_counter.get(category, 0) for category in expression_categories)
        if expression_count:
            suggestions.append(
                ContentBatchFeedbackOptimizationSuggestion(
                    suggestion_type="system_keyword",
                    target=_system_keyword_target(category_counter, content_type),
                    title="补强表达类系统关键词语料",
                    reason="反馈集中在自然度、广告感、篇幅或语气，适合补系统关键词的语料示例，不应增加很硬的业务规则。",
                    evidence=_evidence_for_categories(evidence_by_category, expression_categories),
                    priority=_suggestion_priority(expression_count, total_feedback_count),
                )
            )

        if rewrite_decision_counter.get("reject_rewrite", 0):
            suggestions.append(
                ContentBatchFeedbackOptimizationSuggestion(
                    suggestion_type="expert_prompt",
                    target="审核改写 Expert",
                    title="复盘被拒绝的系统改写",
                    reason="存在不采纳系统改写，说明改写 Expert 可能仍在做机械替换，需要用被拒样例调整改写指令。",
                    evidence=[],
                    priority=_suggestion_priority(rewrite_decision_counter["reject_rewrite"], total_feedback_count),
                )
            )

        return suggestions

    def _group_stages_by_run(self, stage_calls: list[ContentAgentStageCall]) -> dict[int, list[ContentAgentStageCall]]:
        grouped: dict[int, list[ContentAgentStageCall]] = {}
        for stage in stage_calls:
            grouped.setdefault(stage.run_id, []).append(stage)
        return grouped

    def _report_item(
        self,
        item: ContentBatchItem,
        stage_calls: list[ContentAgentStageCall],
        latest_version: ContentBatchItemVersion | None = None,
        *,
        versions: list[ContentBatchItemVersion] | None = None,
        run: ContentAgentRun | None = None,
        feedback_count: int = 0,
        forbidden_terms: list[str] | None = None,
    ) -> ContentBatchReportItem:
        ordered_versions = versions or []
        latest_version = latest_version or (ordered_versions[-1] if ordered_versions else None)
        quality = item.quality_json or {}
        review = quality.get("review_report") or {}
        diversity = item.diversity_json or {}
        runtime_result = self._runtime_result(stage_calls)
        generation_stage = self._generation_stage(stage_calls)
        text = f"{item.title or ''}\n{item.body or ''}"
        forbidden_hits = self._forbidden_hits(text, forbidden_terms)
        return ContentBatchReportItem(
            item_id=item.id,
            item_no=item.item_no,
            status=item.status,
            task_id=item.task_id,
            run_id=item.run_id,
            title=item.title,
            body=item.body,
            body_preview=(item.body or "")[:160] if item.body else None,
            body_chars=len(item.body or ""),
            hard_pass=quality.get("hard_pass"),
            rewrite_required=review.get("rewrite_required"),
            rewrite_reason=review.get("rewrite_reason"),
            rewrite_rounds=review.get("rewrite_rounds"),
            suggestion_count=len(review.get("suggestions") or []),
            replacement_count=len(review.get("replacement_needed") or []),
            forbidden_hits=forbidden_hits,
            final_path=runtime_result.get("final_path"),
            debug_dir=runtime_result.get("debug_dir"),
            review_status=latest_version.review_status if latest_version else (quality.get("human_review") or {}).get("review_status"),
            latest_version_no=latest_version.version_no if latest_version else None,
            human_feedback_text=latest_version.feedback_text if latest_version else (quality.get("human_review") or {}).get("feedback_text"),
            feedback_count=feedback_count,
            reject_reasons=self._reject_reasons(item, review, forbidden_hits),
            similarity_warnings=[],
            version_compare=self._version_compare(latest_version, ordered_versions),
            runtime_mode=runtime_result.get("mode") or quality.get("executor"),
            generation_duration_ms=self._stage_duration_ms(generation_stage) if generation_stage else None,
            total_duration_ms=self._total_duration_ms(run, stage_calls),
            trace_run_id=item.run_id,
            trace_stage_calls=[self._stage_trace(stage) for stage in stage_calls],
            opening_type=diversity.get("opening_type"),
            structure_type=diversity.get("structure_type"),
            content_angle=diversity.get("content_angle"),
            persona_lens=diversity.get("persona_lens"),
            scene_type=diversity.get("scene_type"),
            evidence_type=diversity.get("evidence_type"),
            asset_combo_key=(item.plan_json or {}).get("asset_combo_key"),
            asset_reuse_reason=(item.plan_json or {}).get("asset_reuse_reason"),
            generation_snapshot=self._generation_snapshot(item, stage_calls, run, quality),
            diversity=diversity or None,
            quality=quality or None,
            error_message=item.error_message,
        )

    def _version_compare(
        self,
        latest_version: ContentBatchItemVersion | None,
        versions: list[ContentBatchItemVersion],
    ) -> ContentBatchVersionCompare | None:
        # “通过”等反馈也会生成版本；报告里应展示最近一次真正改变文本的版本差异。
        candidate_versions = list(reversed(versions))
        if latest_version is not None and latest_version not in versions:
            candidate_versions.insert(0, latest_version)
        if not candidate_versions:
            return None
        for version in candidate_versions:
            if version.source_action not in {"accept_rewrite", "auto_rewrite", "manual_edit", "reject_rewrite"}:
                continue
            before = self._compare_before_snapshot(version, versions)
            if before is None:
                continue
            after = self._version_snapshot(version)
            title_changed = (before.title or "") != (after.title or "")
            body_changed = (before.body or "") != (after.body or "")
            if not title_changed and not body_changed and version.source_action != "auto_rewrite":
                continue
            return ContentBatchVersionCompare(
                compare_type=version.source_action,
                before=before,
                after=after,
                title_changed=title_changed,
                body_changed=body_changed,
                body_before_chars=len(before.body or ""),
                body_after_chars=len(after.body or ""),
            )
        return None

    def _compare_before_snapshot(
        self,
        latest_version: ContentBatchItemVersion,
        versions: list[ContentBatchItemVersion],
    ) -> ContentBatchVersionSnapshot | None:
        metadata = latest_version.metadata_json if isinstance(latest_version.metadata_json, dict) else {}
        decision_version_id = metadata.get("decision_for_version_id")
        if decision_version_id is not None:
            for version in versions:
                if version.id == decision_version_id:
                    if latest_version.source_action == "accept_rewrite":
                        return self._compare_before_snapshot(version, versions)
                    return self._version_snapshot(version)

        source_version_id = metadata.get("source_version_id")
        if source_version_id is not None:
            for version in versions:
                if version.id == source_version_id:
                    return self._version_snapshot(version)

        if latest_version.source_action == "manual_edit":
            previous_content = metadata.get("previous_content") if isinstance(metadata.get("previous_content"), dict) else {}
            if previous_content:
                return ContentBatchVersionSnapshot(
                    version_id=None,
                    version_no=max((latest_version.version_no or 1) - 1, 0),
                    source_action="before_manual_edit",
                    review_status=None,
                    title=previous_content.get("title"),
                    body=previous_content.get("body"),
                    feedback_text=latest_version.feedback_text,
                    created_by=latest_version.created_by,
                    create_time=self._format_time(latest_version.create_time),
                )

        if latest_version.source_action not in {"accept_rewrite", "auto_rewrite", "manual_edit", "reject_rewrite"}:
            return None
        previous_versions = [version for version in versions if version.version_no < latest_version.version_no]
        if not previous_versions:
            return None
        return self._version_snapshot(previous_versions[-1])

    @staticmethod
    def _version_snapshot(version: ContentBatchItemVersion) -> ContentBatchVersionSnapshot:
        return ContentBatchVersionSnapshot(
            version_id=version.id,
            version_no=version.version_no,
            source_action=version.source_action,
            review_status=version.review_status,
            title=version.title,
            body=version.body,
            feedback_text=version.feedback_text,
            created_by=version.created_by,
            create_time=ContentBatchReportService._format_time(version.create_time),
        )

    @staticmethod
    def _format_time(value: Any) -> str | None:
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else None

    def _runtime_result(self, stage_calls: list[ContentAgentStageCall]) -> dict[str, Any]:
        for stage in stage_calls:
            if stage.capability != "content.generate":
                continue
            output = stage.output_snapshot or {}
            runtime_result = output.get("runtime_result")
            if isinstance(runtime_result, dict):
                return runtime_result
        return {}

    def _generation_stage(self, stage_calls: list[ContentAgentStageCall]) -> ContentAgentStageCall | None:
        return next((stage for stage in stage_calls if stage.capability == "content.generate"), None)

    def _generation_snapshot(
        self,
        item: ContentBatchItem,
        stage_calls: list[ContentAgentStageCall],
        run: ContentAgentRun | None,
        quality: dict[str, Any],
    ) -> dict[str, Any] | None:
        plan = item.plan_json or {}
        if not isinstance(plan, dict):
            plan = {}
        unified = plan.get("unified_generation") if isinstance(plan.get("unified_generation"), dict) else {}
        generation_stage = self._generation_stage(stage_calls)
        generation_input = self._stage_input(generation_stage)
        source = self._generation_source(generation_input, unified)
        business_rule = self._business_rule_snapshot(source, plan)
        selected_keywords = self._selected_keywords_snapshot(source, unified, quality)
        expert = self._dict_value(source.get("expert")) or self._dict_value(unified.get("expert")) or {}
        model_config = (
            self._dict_value(source.get("model_config"))
            or self._dict_value(expert.get("model_config"))
            or self._dict_value(plan.get("model_config"))
            or {}
        )
        rendered_prompt = self._string_or_none(source.get("rendered_prompt") or unified.get("rendered_prompt"))
        forbidden_review = self._forbidden_review(quality)
        realness_review = self._comment_realness_review(quality)
        activity_quality_guard = self._activity_quality_guard(quality)
        rewrite_records = self._rewrite_records(stage_calls)
        if not any([business_rule, selected_keywords, expert, rendered_prompt, forbidden_review, realness_review, activity_quality_guard, rewrite_records, generation_stage]):
            return None
        capability = (
            self._string_or_none(source.get("capability"))
            or self._string_or_none(unified.get("capability"))
            or (generation_stage.capability if generation_stage else None)
        )
        output_fields = source.get("output_fields") or business_rule.get("output_fields") or plan.get("output_fields") or []
        return {
            "schema_version": "1",
            "rule_type": business_rule.get("rule_type"),
            "content_type": source.get("content_type") or ("comment" if output_fields == ["comment"] else "article"),
            "capability": capability,
            "output_fields": output_fields,
            "business_rule": business_rule,
            "selected_keywords": selected_keywords,
            "keyword_asset": self._dict_value(source.get("keyword_asset")) or self._dict_value(unified.get("keyword_asset")) or {},
            "expert": expert,
            "model_config": model_config,
            "model_route": self._model_route(
                run=run,
                capability=capability,
                runtime_mode=self._runtime_result(stage_calls).get("mode") or quality.get("executor"),
                model_config=model_config,
            ),
            "rendered_prompt": rendered_prompt,
            "forbidden_terms_review": forbidden_review,
            "comment_realness_review": realness_review,
            "activity_quality_guard": activity_quality_guard,
            "rewrite_records": rewrite_records,
            "execution_stages": [self._stage_trace(stage).model_dump(mode="json") for stage in stage_calls],
        }

    def _generation_source(self, generation_input: dict[str, Any], unified: dict[str, Any]) -> dict[str, Any]:
        nested_snapshot = generation_input.get("generation_snapshot")
        if isinstance(nested_snapshot, dict):
            return nested_snapshot
        if any(key in generation_input for key in ("business_rule", "selected_keywords", "expert", "rendered_prompt")):
            return generation_input
        return unified

    def _business_rule_snapshot(self, source: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        business_rule = self._dict_value(source.get("business_rule")) or plan
        return {
            key: value
            for key, value in dict(business_rule).items()
            if key not in {"unified_generation", "batch_context", "model_config"}
        }

    def _selected_keywords_snapshot(
        self,
        source: dict[str, Any],
        unified: dict[str, Any],
        quality: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates = source.get("selected_keywords") or unified.get("selected_keywords") or quality.get("selected_keywords")
        return [item for item in candidates or [] if isinstance(item, dict)]

    def _forbidden_review(self, quality: dict[str, Any]) -> dict[str, Any] | None:
        review_report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
        review = quality.get("forbidden_terms_review") or review_report.get("forbidden_terms_review")
        return review if isinstance(review, dict) else None

    def _comment_realness_review(self, quality: dict[str, Any]) -> dict[str, Any] | None:
        review_report = quality.get("review_report") if isinstance(quality.get("review_report"), dict) else {}
        review = quality.get("comment_realness_review") or review_report.get("comment_realness_review")
        return review if isinstance(review, dict) else None

    def _activity_quality_guard(self, quality: dict[str, Any]) -> dict[str, Any] | None:
        review = quality.get("activity_quality_guard")
        return review if isinstance(review, dict) else None

    def _rewrite_records(self, stage_calls: list[ContentAgentStageCall]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for stage in stage_calls:
            if stage.capability != "content.rewrite":
                continue
            input_payload = stage.input_snapshot or {}
            output_payload = stage.output_snapshot or {}
            records.append(
                {
                    "stage_call_id": stage.stage_call_id,
                    "sequence_no": stage.sequence_no,
                    "capability": stage.capability,
                    "status": stage.status,
                    "duration_ms": self._stage_duration_ms(stage),
                    "before": self._rewrite_before(input_payload),
                    "after": self._rewrite_after(output_payload),
                    "forbidden_hits": self._list_of_strings(input_payload.get("forbidden_hits")),
                    "style_hits": self._list_of_strings(input_payload.get("style_hits")),
                    "rewrite_source": self._string_or_none(input_payload.get("rewrite_source")),
                    "rewrite_instructions": self._list_of_strings(input_payload.get("rewrite_instructions")),
                    "expert": self._dict_value(input_payload.get("expert")) or {},
                    "model_config": self._dict_value(input_payload.get("model_config")) or {},
                    "rendered_prompt": self._string_or_none(input_payload.get("rendered_prompt")),
                    "error_message": stage.error_message,
                }
            )
        return records

    def _rewrite_before(self, input_payload: dict[str, Any]) -> dict[str, str]:
        previous = input_payload.get("previous_content") or input_payload.get("previous_draft") or {}
        return self._content_summary(previous if isinstance(previous, dict) else {})

    def _rewrite_after(self, output_payload: dict[str, Any]) -> dict[str, str]:
        return self._content_summary(output_payload)

    def _content_summary(self, payload: dict[str, Any]) -> dict[str, str]:
        final = payload.get("final") if isinstance(payload.get("final"), dict) else {}
        comment = payload.get("comment") or final.get("comment")
        if comment:
            return {"comment": str(comment)}
        title = payload.get("title") or final.get("title")
        body = payload.get("body") or final.get("body")
        result: dict[str, str] = {}
        if title:
            result["title"] = str(title)
        if body:
            result["body"] = str(body)
        return result

    def _model_route(
        self,
        *,
        run: ContentAgentRun | None,
        capability: str | None,
        runtime_mode: str | None,
        model_config: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "executor_code": run.executor_code if run else None,
            "executor_type": run.executor_type if run else None,
            "capability": capability,
            "runtime_mode": runtime_mode,
            "provider_code": model_config.get("provider_code") or model_config.get("provider"),
            "model_code": model_config.get("model_code") or model_config.get("ge_model"),
            "temperature": model_config.get("temperature"),
            "max_tokens": model_config.get("max_tokens"),
        }

    def _stage_input(self, stage: ContentAgentStageCall | None) -> dict[str, Any]:
        if stage is None or not isinstance(stage.input_snapshot, dict):
            return {}
        return stage.input_snapshot

    def _stage_trace(self, stage: ContentAgentStageCall) -> ContentBatchStageTrace:
        return ContentBatchStageTrace(
            stage_call_id=stage.stage_call_id,
            sequence_no=stage.sequence_no,
            capability=stage.capability,
            status=stage.status,
            duration_ms=self._stage_duration_ms(stage),
            error_message=stage.error_message,
            stats=stage.stats_json,
        )

    def _reject_reasons(
        self,
        item: ContentBatchItem,
        review: dict[str, Any],
        forbidden_hits: list[str],
    ) -> list[ContentBatchRejectReason]:
        reasons: list[ContentBatchRejectReason] = []
        # 把结构化审核结果转成运营能直接看到的驳回原因。
        for hard_result in review.get("hard_results") or []:
            if not isinstance(hard_result, dict) or hard_result.get("pass") is not False:
                continue
            evidence = hard_result.get("evidence") or []
            reasons.append(
                ContentBatchRejectReason(
                    source="hard_review",
                    code=self._string_or_none(hard_result.get("ae_code")),
                    message=self._reject_message(
                        hard_result.get("feedback") or hard_result.get("reason"),
                        evidence=evidence,
                        fallback="硬性审核未通过",
                    ),
                    risk_level=self._string_or_none(hard_result.get("risk_level")),
                    evidence=[str(item) for item in evidence if item is not None],
                )
            )
        for failed in review.get("failed_aes") or []:
            if isinstance(failed, dict):
                reasons.append(
                    ContentBatchRejectReason(
                        source="failed_ae",
                        code=self._string_or_none(failed.get("ae_code") or failed.get("code")),
                        message=str(failed.get("feedback") or failed.get("reason") or failed.get("message") or "AE 审核失败"),
                        risk_level=self._string_or_none(failed.get("risk_level")),
                    )
                )
            elif failed:
                reasons.append(ContentBatchRejectReason(source="failed_ae", code=str(failed), message=str(failed)))
        for term in forbidden_hits:
            reasons.append(ContentBatchRejectReason(source="forbidden_term", code=term, message=f"命中禁用词：{term}"))
        if item.status == "failed" and item.error_message:
            reasons.append(ContentBatchRejectReason(source="executor_error", message=item.error_message))
        return reasons

    def _total_duration_ms(self, run: ContentAgentRun | None, stage_calls: list[ContentAgentStageCall]) -> int | None:
        # Run 时间可能被数据库取整，阶段 stats 通常更精确；总耗时不能小于阶段耗时。
        durations = [value for value in (self._run_duration_ms(run), self._stage_calls_duration_ms(stage_calls)) if value is not None]
        return max(durations) if durations else None

    def _reject_message(self, value: Any, *, evidence: list[Any], fallback: str) -> str:
        message = self._string_or_none(value)
        if message and message.lower() not in {"fail", "failed", "false"}:
            return message
        evidence_text = "、".join(str(item) for item in evidence if item is not None)
        return f"命中硬性审核红线：{evidence_text}" if evidence_text else fallback

    def _stage_duration_ms(self, stage: ContentAgentStageCall | None) -> int | None:
        if not stage:
            return None
        stats_duration = self._duration_from_stats(stage.stats_json or {})
        if stats_duration is not None:
            return stats_duration
        if stage.started_at and stage.finished_at:
            return max(0, int((stage.finished_at - stage.started_at).total_seconds() * 1000))
        return None

    def _run_duration_ms(self, run: ContentAgentRun | None) -> int | None:
        if not run or not run.started_at or not run.finished_at:
            return None
        return max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))

    def _stage_calls_duration_ms(self, stage_calls: list[ContentAgentStageCall]) -> int | None:
        durations = [duration for stage in stage_calls if (duration := self._stage_duration_ms(stage)) is not None]
        return sum(durations) if durations else None

    def _duration_from_stats(self, stats: dict[str, Any]) -> int | None:
        for key in ("total_latency_ms", "latency_ms", "duration_ms", "elapsed_ms"):
            value = stats.get(key)
            if isinstance(value, (int, float)):
                return max(0, int(value))
        return None

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _dict_value(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list_of_strings(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _summary(self, items: list[ContentBatchReportItem]) -> ContentBatchReportSummary:
        generated_statuses = {"generated", "approved", "manual_edited", "needs_revision"}
        generated = [item for item in items if item.status in generated_statuses]
        body_lengths = [item.body_chars for item in generated if item.body_chars]
        forbidden_hit_count = sum(len(item.forbidden_hits) for item in items)
        return ContentBatchReportSummary(
            total_count=len(items),
            generated_count=len(generated),
            failed_count=sum(1 for item in items if item.status == "failed"),
            hard_pass_count=sum(1 for item in items if item.hard_pass is True),
            rewrite_item_count=sum(1 for item in items if item.rewrite_reason or item.rewrite_rounds),
            remaining_rewrite_required_count=sum(1 for item in items if item.rewrite_required is True),
            forbidden_hit_count=forbidden_hit_count,
            feedback_count=sum(item.feedback_count for item in items),
            avg_body_chars=round(sum(body_lengths) / len(body_lengths), 2) if body_lengths else None,
            max_pairwise_jaccard_2gram=self._max_pairwise_jaccard([item.body or "" for item in generated]),
            similarity_warning_count=sum(1 for item in items if item.similarity_warnings),
        )

    def _forbidden_hits(self, text: str, business_terms: list[str] | None = None) -> list[str]:
        return find_forbidden_hits(text, business_terms)

    def _max_pairwise_jaccard(self, bodies: list[str]) -> float:
        max_score = 0.0
        for i, left in enumerate(bodies):
            for right in bodies[i + 1 :]:
                max_score = max(max_score, self._jaccard_2gram(left, right))
        return round(max_score, 4)

    def _jaccard_2gram(self, left: str, right: str) -> float:
        left_tokens = self._text_2grams(left)
        right_tokens = self._text_2grams(right)
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    def _text_2grams(self, text: str) -> set[str]:
        clean = re.sub(r"\s+", "", text or "")
        return {clean[i : i + 2] for i in range(max(len(clean) - 1, 0)) if clean[i : i + 2].strip()}

    def _attach_similarity_warnings(self, items: list[ContentBatchReportItem]) -> None:
        comparable = [item for item in items if item.body]
        for index, left in enumerate(comparable):
            for right in comparable[index + 1 :]:
                score = round(self._jaccard_2gram(left.body or "", right.body or ""), 4)
                if score < SIMILARITY_WARNING_THRESHOLD:
                    continue
                warning_for_left = ContentBatchSimilarityWarning(
                    item_no=right.item_no,
                    score=score,
                    reason="正文 2-gram 相似度偏高",
                    scope="current_batch",
                )
                warning_for_right = ContentBatchSimilarityWarning(
                    item_no=left.item_no,
                    score=score,
                    reason="正文 2-gram 相似度偏高",
                    scope="current_batch",
                )
                left.similarity_warnings.append(warning_for_left)
                right.similarity_warnings.append(warning_for_right)
        self._attach_rewrite_similarity_warnings(items)

    def _attach_rewrite_similarity_warnings(self, items: list[ContentBatchReportItem]) -> None:
        for item in items:
            quality = item.quality or {}
            rewrites = quality.get("similarity_rewrites") or []
            if not isinstance(rewrites, list):
                continue
            for rewrite in rewrites:
                if not isinstance(rewrite, dict):
                    continue
                scope = rewrite.get("scope") or "current_batch"
                if scope != "history":
                    continue
                similar_item_no = rewrite.get("similar_item_no")
                score = rewrite.get("post_rewrite_similarity_score") or rewrite.get("similarity_score")
                if not isinstance(similar_item_no, int) or not isinstance(score, (int, float)):
                    continue
                if rewrite.get("similarity_rewrite_passed") is True and float(score) < SIMILARITY_WARNING_THRESHOLD:
                    continue
                item.similarity_warnings.append(
                    ContentBatchSimilarityWarning(
                        item_no=similar_item_no,
                        score=round(float(score), 4),
                        reason="与历史批次正文 2-gram 相似度偏高",
                        batch_id=rewrite.get("similar_batch_id"),
                        batch_code=rewrite.get("similar_batch_code"),
                        scope="history",
                    )
                )


def _feedback_categories(metadata: dict[str, Any]) -> list[str]:
    values = metadata.get("feedback_categories")
    if not isinstance(values, list):
        return []
    categories: list[str] = []
    for value in values:
        code = str(value or "").strip()
        if code in _FEEDBACK_CATEGORY_LABELS and code not in categories:
            categories.append(code)
    return categories


def _feedback_evidence(feedback: ContentFeedback, item: ContentBatchItem | None) -> str | None:
    parts: list[str] = []
    if item is not None:
        parts.append(f"第 {item.item_no} 条")
    if feedback.quoted_text:
        parts.append(f"片段：{_truncate(feedback.quoted_text, 80)}")
    if feedback.comment:
        parts.append(f"反馈：{_truncate(feedback.comment, 100)}")
    return "；".join(parts) if parts else None


def _counter_stats(counter: Counter[str], labels: dict[str, str]) -> list[ContentBatchFeedbackStat]:
    label_order = {code: index for index, code in enumerate(labels)}
    return [
        ContentBatchFeedbackStat(code=code, label=labels.get(code, code), count=count)
        for code, count in sorted(
            counter.items(),
            key=lambda item: (-item[1], label_order.get(item[0], len(label_order)), labels.get(item[0], item[0])),
        )
        if count > 0
    ]


def _evidence_for_categories(evidence_by_category: dict[str, list[str]], categories: list[str]) -> list[str]:
    evidence: list[str] = []
    for category in categories:
        for item in evidence_by_category.get(category, []):
            if item not in evidence:
                evidence.append(item)
            if len(evidence) >= 4:
                return evidence
    return evidence


def _batch_content_type(items: list[ContentBatchItem]) -> str:
    for item in items:
        plan = item.plan_json or {}
        output_fields = plan.get("output_fields") or []
        if output_fields == ["comment"]:
            return "comment"
        if "body" in output_fields:
            return "article"
        if plan.get("rule_type") == "business_rule":
            return "comment"
    return "article"


def _system_keyword_target(category_counter: Counter[str], content_type: str) -> str:
    if category_counter.get("too_long", 0):
        return "系统关键词 / 评论格式控制" if content_type == "comment" else "系统关键词 / 帖子格式控制"
    if content_type == "comment":
        return "系统关键词 / 生评论指令"
    return "系统关键词 / 写作手法"


def _suggestion_priority(count: int, total: int) -> str:
    ratio = count / max(total, 1)
    if count >= 3 or ratio >= 0.5:
        return "high"
    if count >= 2 or ratio >= 0.25:
        return "medium"
    return "low"


def _truncate(value: str, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[:limit]}..."


def _write_overview_sheet(sheet: Any, report: ContentBatchReportResponse) -> None:
    summary = report.summary
    rows = [
        ("批次ID", report.batch_id),
        ("批次Code", report.batch_code or ""),
        ("资产Key", report.asset_key),
        ("主题", report.product_topic),
        ("人群", report.target_audience or "-"),
        ("人设/对象", report.persona_target or "-"),
        ("风格", report.style or "-"),
        ("状态", report.status),
        ("总数", summary.total_count),
        ("已生成", summary.generated_count),
        ("失败", summary.failed_count),
        ("红线通过", summary.hard_pass_count),
        ("自动改写", summary.rewrite_item_count),
        ("仍需处理", summary.remaining_rewrite_required_count),
        ("禁用词命中", summary.forbidden_hit_count),
        ("相似提醒", summary.similarity_warning_count),
        ("平均字数", summary.avg_body_chars if summary.avg_body_chars is not None else "-"),
    ]
    sheet.append(["字段", "值"])
    for row in rows:
        sheet.append(list(row))
    _style_table_header(sheet, header_row=1, column_count=2)
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 48
    sheet.freeze_panes = "A2"


def _write_result_sheet(sheet: Any, report: ContentBatchReportResponse) -> None:
    headers = [
        "标题",
        "正文",
        "业务规则",
        "序号",
        "状态",
        "字数",
        "红线通过",
        "审核状态",
        "改写轮次",
        "改写原因",
        "禁用词",
        "相似提醒",
        "运行模式",
        "生文耗时ms",
        "总耗时ms",
        "Run ID",
        "Task ID",
        "系统语料包",
        "Expert",
        "模型",
        "错误信息",
    ]
    sheet.append(headers)
    for item in report.items:
        snapshot = item.generation_snapshot or {}
        sheet.append(
            [
                item.title or "",
                item.body or "",
                _business_rule_label(snapshot.get("business_rule")),
                item.item_no,
                item.status,
                item.body_chars,
                _bool_label(item.hard_pass),
                item.review_status or "",
                item.rewrite_rounds or 0,
                item.rewrite_reason or "",
                "、".join(item.forbidden_hits or []),
                _similarity_text(item.similarity_warnings),
                item.runtime_mode or "",
                item.generation_duration_ms if item.generation_duration_ms is not None else "",
                item.total_duration_ms if item.total_duration_ms is not None else "",
                item.trace_run_id or item.run_id or "",
                item.task_id or "",
                _keyword_asset_label(snapshot.get("keyword_asset")),
                _expert_label(snapshot.get("expert")),
                _model_label(snapshot),
                item.error_message or "",
            ]
        )
    _style_table_header(sheet, header_row=1, column_count=len(headers))
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    widths = {
        "A": 24,
        "B": 58,
        "C": 32,
        "D": 8,
        "E": 12,
        "F": 8,
        "G": 12,
        "H": 12,
        "I": 10,
        "J": 36,
        "K": 18,
        "L": 28,
        "M": 12,
        "N": 12,
        "O": 12,
        "P": 12,
        "Q": 12,
        "R": 28,
        "S": 26,
        "T": 24,
        "U": 36,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for row_index in range(2, sheet.max_row + 1):
        sheet.row_dimensions[row_index].height = 42


def _write_article_pool_sheet(sheet: Any, report: ContentBatchReportResponse) -> None:
    headers = ["ID", "Content ID", "标题", "正文", "上下文变量(context_list)"]
    sheet.append(headers)
    for item in _article_pool_export_items(report.items):
        context_list = _article_pool_context_list(item)
        sheet.append(
            [
                "",
                "",
                item.title or "",
                item.body or "",
                json.dumps(context_list, ensure_ascii=False),
            ]
        )
    _style_table_header(sheet, header_row=1, column_count=len(headers))
    sheet.freeze_panes = "A2"
    sheet.column_dimensions["A"].width = 12
    sheet.column_dimensions["B"].width = 16
    sheet.column_dimensions["C"].width = 18
    sheet.column_dimensions["D"].width = 56
    sheet.column_dimensions["E"].width = 72
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def _article_pool_export_items(items: list[ContentBatchReportItem]) -> list[ContentBatchReportItem]:
    # 文章池导出只保留可直接入库的正文，审核失败或仍需重写的行留在批次报告里看。
    return [item for item in items if _article_pool_item_exportable(item)]


def _article_pool_item_exportable(item: ContentBatchReportItem) -> bool:
    if str(item.status or "") != "generated":
        return False
    if not str(item.body or "").strip():
        return False
    if item.hard_pass is False:
        return False
    if item.rewrite_required is True:
        return False
    return True


def _article_pool_context_list(item: ContentBatchReportItem) -> dict[str, str]:
    quality = item.quality or {}
    guard = quality.get("activity_quality_guard") if isinstance(quality, dict) else {}
    if isinstance(guard, dict) and isinstance(guard.get("context_list"), dict):
        return {
            str(key): str(value or "")
            for key, value in guard["context_list"].items()
        }

    snapshot = item.generation_snapshot or {}
    business_rule = snapshot.get("business_rule") if isinstance(snapshot.get("business_rule"), dict) else {}
    plan = dict(business_rule or {})
    plan["unified_generation"] = {"selected_keywords": snapshot.get("selected_keywords") or []}
    pseudo_item = SimpleNamespace(
        plan_json=plan,
        quality_json=quality,
        title=item.title,
        body=item.body,
    )
    return build_article_pool_context_list(pseudo_item)


def _style_table_header(sheet: Any, *, header_row: int, column_count: int) -> None:
    fill = PatternFill("solid", fgColor="1F2937")
    font = Font(color="FFFFFF", bold=True)
    side = Side(style="thin", color="D9D9D9")
    border = Border(left=side, right=side, top=side, bottom=side)
    for row in sheet.iter_rows(min_row=header_row, max_row=sheet.max_row, max_col=column_count):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for cell in sheet[header_row]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center")


def _bool_label(value: bool | None) -> str:
    if value is True:
        return "通过"
    if value is False:
        return "未通过"
    return "未知"


def _similarity_text(warnings: list[ContentBatchSimilarityWarning]) -> str:
    if not warnings:
        return ""
    return "；".join(
        f"与第{warning.item_no}条 {round(warning.score * 100)}%"
        + (f"（{warning.batch_code}）" if warning.batch_code else "")
        for warning in warnings
    )


def _business_rule_label(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("business_rule", "topic", "rule_id"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return str(value.get("rule_type") or "")


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _keyword_asset_label(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    asset_key = str(value.get("asset_key") or "").strip()
    source = str(value.get("source") or "").strip()
    return f"{asset_key}（{source}）" if source else asset_key


def _expert_label(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    code = str(value.get("expert_config_code") or "").strip()
    source = str(value.get("source") or "").strip()
    return f"{code}（{source}）" if source else code


def _model_label(snapshot: dict[str, Any]) -> str:
    route = snapshot.get("model_route") if isinstance(snapshot.get("model_route"), dict) else {}
    expert = snapshot.get("expert") if isinstance(snapshot.get("expert"), dict) else {}
    model_config = snapshot.get("model_config") if isinstance(snapshot.get("model_config"), dict) else {}
    for source in (route, model_config, expert.get("model_config") if isinstance(expert.get("model_config"), dict) else {}):
        for key in ("model_code", "ge_model", "model"):
            text = str(source.get(key) or "").strip()
            if text:
                return text
    return ""


def _excel_filename(report: ContentBatchReportResponse) -> str:
    batch_code = re.sub(r"[^0-9A-Za-z_-]+", "_", report.batch_code or f"batch_{report.batch_id}").strip("_")
    return f"生文结果_{batch_code or report.batch_id}.xlsx"


def _article_pool_excel_filename(report: ContentBatchReportResponse) -> str:
    topic = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5_-]+", "_", report.product_topic or "评论").strip("_")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"生成{topic or '评论'}-{timestamp}.xlsx"
