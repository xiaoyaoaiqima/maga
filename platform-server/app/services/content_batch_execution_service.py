"""Execute planned MAGA content batch items through the content-agent chain."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.schemas.content_agent import ContentAgentTaskCreate
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_batch_snapshot_adapter import build_xhs_generation_snapshot_from_plan
from app.services.executor_invocation_service import ExecutorInvocationClient


@dataclass(frozen=True)
class BatchExecutionResult:
    batch_id: int
    requested_limit: int
    generated_count: int
    failed_count: int
    item_ids: list[int]


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
    ):
        self.db = db
        self.invocation_client = invocation_client
        self.callback_base_url = callback_base_url
        self.executor_code = executor_code

    async def execute_batch_items(
        self,
        batch_id: int,
        *,
        limit: int,
        created_by: str | None = None,
    ) -> BatchExecutionResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        job = await self._require_job(batch_id)
        items = await self._planned_items(batch_id, limit)
        orchestrator = ContentAgentOrchestrator(
            self.db,
            invocation_client=self.invocation_client,
            callback_base_url=self.callback_base_url,
        )

        generated = 0
        failed = 0
        item_ids: list[int] = []
        for item in items:
            item.status = "running"
            await self.db.flush()
            snapshot = build_xhs_generation_snapshot_from_plan(item.plan_json, batch_id=job.id, batch_code=job.batch_code)
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
                    "forbidden_overlap_group": diversity_slot.get("forbidden_overlap_group"),
                }
                item.error_message = None
                generated += 1
            except Exception as exc:  # pragma: no cover - error path covered by later retry tests
                item.status = "failed"
                item.error_message = str(exc)
                failed += 1
            item_ids.append(item.id)
            await self.db.flush()

        if generated:
            job.status = "partially_generated" if generated < job.count else "generated"
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

    def _review_report_from_stage_calls(self, stage_calls: list[Any]) -> dict[str, Any]:
        runtime_fast_report = self._review_report_for_capability(stage_calls, "xhs.generate_draft", require_runtime_fast=True)
        if runtime_fast_report:
            return runtime_fast_report

        ae_review_report = self._review_report_for_capability(stage_calls, "xhs.run_ae_review")
        if ae_review_report:
            return ae_review_report

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


    def _task_input_from_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        brief = snapshot.get("brief") or {}
        return {
            "brief_type": "xhs_product_seeding",
            "product_topic": self._topic_for_diversity(brief, snapshot),
            "target_audience": brief.get("target_audience"),
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
