"""Build operator-facing reports for MAGA content batch jobs."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import ContentAgentRun, ContentAgentStageCall, ContentBatchItem, ContentBatchItemVersion, ContentBatchJob
from app.schemas.content_batch_report import (
    ContentBatchListItem,
    ContentBatchRejectReason,
    ContentBatchListResponse,
    ContentBatchReportItem,
    ContentBatchReportResponse,
    ContentBatchReportSummary,
    ContentBatchStageTrace,
)

FORBIDDEN_TERMS = ["治疗便秘", "治好便秘", "改善便秘", "解决便秘", "根治", "疗效"]


class ContentBatchReportService:
    """Return a compact batch result view suitable for operator review screens."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_batch_reports(self, *, limit: int = 20, offset: int = 0) -> ContentBatchListResponse:
        total_result = await self.db.execute(select(func.count()).select_from(ContentBatchJob))
        total = int(total_result.scalar_one() or 0)
        result = await self.db.execute(
            select(ContentBatchJob).order_by(ContentBatchJob.create_time.desc(), ContentBatchJob.id.desc()).offset(offset).limit(limit)
        )
        jobs = list(result.scalars().all())
        list_items: list[ContentBatchListItem] = []
        for job in jobs:
            items = await self._batch_items(job.id)
            versions_by_item = await self._latest_versions_for_items(items)
            report_items = [self._report_item(item, [], versions_by_item.get(item.id), None) for item in items]
            list_items.append(
                ContentBatchListItem(
                    batch_id=job.id,
                    batch_code=job.batch_code,
                    asset_key=job.asset_key,
                    product_topic=job.product_topic,
                    target_audience=job.target_audience,
                    style=job.style,
                    status=job.status,
                    count=job.count,
                    summary=self._summary(report_items),
                    create_time=job.create_time,
                    update_time=job.update_time,
                )
            )
        return ContentBatchListResponse(total=total, items=list_items)

    async def get_batch_report(self, batch_id: int) -> ContentBatchReportResponse:
        job = await self._require_job(batch_id)
        items = await self._batch_items(batch_id)
        stage_calls = await self._stage_calls_for_items(items)
        stages_by_run = self._group_stages_by_run(stage_calls)
        runs_by_id = await self._runs_for_items(items)
        versions_by_item = await self._latest_versions_for_items(items)
        report_items = [
            self._report_item(
                item,
                stages_by_run.get(item.run_id or -1, []),
                versions_by_item.get(item.id),
                runs_by_id.get(item.run_id or -1),
            )
            for item in items
        ]
        return ContentBatchReportResponse(
            batch_id=job.id,
            batch_code=job.batch_code,
            asset_key=job.asset_key,
            product_topic=job.product_topic,
            target_audience=job.target_audience,
            style=job.style,
            status=job.status,
            count=job.count,
            summary=self._summary(report_items),
            items=report_items,
        )

    async def build_item_report(self, item: ContentBatchItem) -> ContentBatchReportItem:
        stage_calls = await self._stage_calls_for_items([item])
        latest_version = (await self._latest_versions_for_items([item])).get(item.id)
        run = (await self._runs_for_items([item])).get(item.run_id or -1)
        return self._report_item(item, stage_calls, latest_version, run)

    async def _require_job(self, batch_id: int) -> ContentBatchJob:
        result = await self.db.execute(select(ContentBatchJob).where(ContentBatchJob.id == batch_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError("batch job not found")
        return job

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
        run: ContentAgentRun | None = None,
    ) -> ContentBatchReportItem:
        quality = item.quality_json or {}
        review = quality.get("review_report") or {}
        diversity = item.diversity_json or {}
        runtime_result = self._runtime_result(stage_calls)
        generation_stage = self._generation_stage(stage_calls)
        text = f"{item.title or ''}\n{item.body or ''}"
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
            forbidden_hits=self._forbidden_hits(text),
            final_path=runtime_result.get("final_path"),
            debug_dir=runtime_result.get("debug_dir"),
            review_status=latest_version.review_status if latest_version else (quality.get("human_review") or {}).get("review_status"),
            latest_version_no=latest_version.version_no if latest_version else None,
            human_feedback_text=latest_version.feedback_text if latest_version else (quality.get("human_review") or {}).get("feedback_text"),
            reject_reasons=self._reject_reasons(item, review, text),
            runtime_mode=runtime_result.get("mode") or quality.get("executor"),
            generation_duration_ms=self._stage_duration_ms(generation_stage) if generation_stage else None,
            total_duration_ms=self._total_duration_ms(run, stage_calls),
            trace_run_id=item.run_id,
            trace_stage_calls=[self._stage_trace(stage) for stage in stage_calls],
            opening_type=diversity.get("opening_type"),
            structure_type=diversity.get("structure_type"),
            diversity=diversity or None,
            quality=quality or None,
            error_message=item.error_message,
        )

    def _runtime_result(self, stage_calls: list[ContentAgentStageCall]) -> dict[str, Any]:
        for stage in stage_calls:
            if stage.capability != "xhs.generate_draft":
                continue
            output = stage.output_snapshot or {}
            runtime_result = output.get("runtime_result")
            if isinstance(runtime_result, dict):
                return runtime_result
        return {}

    def _generation_stage(self, stage_calls: list[ContentAgentStageCall]) -> ContentAgentStageCall | None:
        return next((stage for stage in stage_calls if stage.capability == "xhs.generate_draft"), None)

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

    def _reject_reasons(self, item: ContentBatchItem, review: dict[str, Any], text: str) -> list[ContentBatchRejectReason]:
        reasons: list[ContentBatchRejectReason] = []
        # 把 xhs-writer 的结构化审核结果转成运营能直接看到的驳回原因。
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
        for term in self._forbidden_hits(text):
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
            avg_body_chars=round(sum(body_lengths) / len(body_lengths), 2) if body_lengths else None,
            max_pairwise_jaccard_2gram=self._max_pairwise_jaccard([item.body or "" for item in generated]),
        )

    def _forbidden_hits(self, text: str) -> list[str]:
        return [term for term in FORBIDDEN_TERMS if term in text]

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
