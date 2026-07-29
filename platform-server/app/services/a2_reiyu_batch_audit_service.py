"""Independent batch-audit task for generated a2 礼遇 articles."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.services.content_batch_execution_service import (
    A2ReiyuBatchAuditResult,
    ContentBatchExecutionService,
)
from app.services.product_experience_llm_review_service import A2_REIYU_ARTICLE_ASSET_KEY


logger = logging.getLogger(__name__)

A2_REIYU_AUDIT_STATE_KEY = "a2_reiyu_audit"
A2_REIYU_AUDIT_CONCURRENCY = 10


class A2ReiyuBatchAuditService:
    """Persist and run the independent audit state for one generated batch."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        execution_service: ContentBatchExecutionService | None = None,
    ) -> None:
        self.db = db
        self.execution_service = execution_service or ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
        )

    async def queue(
        self,
        batch_id: int,
        *,
        concurrency: int = A2_REIYU_AUDIT_CONCURRENCY,
    ) -> bool:
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        job = await self._require_a2_job(batch_id, for_update=True)
        state = _audit_state(job)
        if state.get("status") in {"queued", "running", "completed"}:
            return False
        self._set_state(
            job,
            {
                "status": "queued",
                "concurrency": concurrency,
                "queued_at": _now_iso(),
            },
        )
        await self.db.flush()
        return True

    async def run(self, batch_id: int) -> A2ReiyuBatchAuditResult | None:
        job = await self._require_a2_job(batch_id, for_update=True)
        state = _audit_state(job)
        if state.get("status") != "queued":
            return None
        concurrency = int(state.get("concurrency") or A2_REIYU_AUDIT_CONCURRENCY)
        self._set_state(
            job,
            {
                **state,
                "status": "running",
                "started_at": _now_iso(),
            },
        )
        await self.db.commit()

        try:
            result = await self.execution_service.review_a2_reiyu_items(
                batch_id,
                concurrency=concurrency,
            )
        except Exception as exc:  # noqa: BLE001 - audit failure must become visible watch state
            await self.db.rollback()
            await self._mark_batch_unavailable(batch_id, str(exc))
            job = await self._require_a2_job(batch_id)
            self._set_state(
                job,
                {
                    **_audit_state(job),
                    "status": "failed",
                    "completed_at": _now_iso(),
                    "error": str(exc),
                },
            )
            await self.db.commit()
            return None

        job = await self._require_a2_job(batch_id)
        self._set_state(
            job,
            {
                **_audit_state(job),
                "status": "completed",
                "completed_at": _now_iso(),
                "guard_issue_count": result.guard_issue_count,
                "reviewed_count": result.business_review.reviewed_count,
                "skipped_count": result.business_review.skipped_count,
                "failed_count": result.business_review.failed_count,
                "tier_counts": result.business_review.tier_counts,
            },
        )
        await self.db.commit()
        return result

    async def _require_a2_job(
        self,
        batch_id: int,
        *,
        for_update: bool = False,
    ) -> ContentBatchJob:
        statement = select(ContentBatchJob).where(ContentBatchJob.id == batch_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.db.execute(statement)
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError("batch job not found")
        if str(job.asset_key or "") != A2_REIYU_ARTICLE_ASSET_KEY:
            raise ValueError("batch job is not an a2 reiyu batch")
        return job

    async def _mark_batch_unavailable(self, batch_id: int, error_message: str) -> None:
        result = await self.db.execute(
            select(ContentBatchItem).where(
                ContentBatchItem.batch_id == batch_id,
                ContentBatchItem.status == "generated",
            )
        )
        for item in result.scalars().all():
            quality = dict(item.quality_json or {})
            review_report = dict(quality.get("review_report") or {})
            unavailable = {
                "error_message": error_message,
                "watch": True,
            }
            quality["a2_reiyu_audit_unavailable_watch"] = unavailable
            quality["product_experience_llm_quality_review"] = {
                "pass": False,
                "rewrite_required": False,
                "mark_rewrite_required": False,
                "severity": "unavailable",
                "business_usability_tier": "watch",
                "business_usability_reason": "a2礼遇独立审核不可用，不能进入直接可用池。",
                "issues": [],
                "scores": {},
            }
            quality["hard_pass"] = False
            review_report["a2_reiyu_audit_unavailable"] = unavailable
            quality["review_report"] = review_report
            item.quality_json = quality
            flag_modified(item, "quality_json")
        await self.db.flush()

    @staticmethod
    def _set_state(job: ContentBatchJob, state: dict[str, Any]) -> None:
        strategy = dict(job.strategy_json or {})
        strategy[A2_REIYU_AUDIT_STATE_KEY] = state
        job.strategy_json = strategy
        flag_modified(job, "strategy_json")


class A2ReiyuBatchAuditDispatcher:
    """Run queued audits outside the generation request without duplicate local tasks."""

    _tasks: dict[int, asyncio.Task[None]] = {}

    @classmethod
    def dispatch(
        cls,
        batch_id: int,
        *,
        session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    ) -> bool:
        existing = cls._tasks.get(batch_id)
        if existing is not None and not existing.done():
            return False
        task = asyncio.create_task(
            cls._run(batch_id, session_factory=session_factory),
            name=f"a2-reiyu-audit-{batch_id}",
        )
        cls._tasks[batch_id] = task
        task.add_done_callback(lambda completed: cls._discard(batch_id, completed))
        return True

    @classmethod
    async def resume_pending(
        cls,
        *,
        session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    ) -> int:
        pending_batch_ids: list[int] = []
        async with session_factory() as db:
            result = await db.execute(
                select(ContentBatchJob).where(
                    ContentBatchJob.asset_key == A2_REIYU_ARTICLE_ASSET_KEY,
                    ContentBatchJob.status.in_({"generated", "partially_generated"}),
                )
            )
            for job in result.scalars().all():
                state = _audit_state(job)
                if state.get("status") not in {"queued", "running"}:
                    continue
                A2ReiyuBatchAuditService._set_state(
                    job,
                    {
                        **state,
                        "status": "queued",
                        "resumed_at": _now_iso(),
                    },
                )
                pending_batch_ids.append(job.id)
            if pending_batch_ids:
                await db.commit()
        for batch_id in pending_batch_ids:
            cls.dispatch(batch_id, session_factory=session_factory)
        return len(pending_batch_ids)

    @classmethod
    async def _run(
        cls,
        batch_id: int,
        *,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as db:
            try:
                await A2ReiyuBatchAuditService(db).run(batch_id)
            except Exception:  # noqa: BLE001 - background task must log unexpected lifecycle errors
                logger.exception("a2 reiyu batch audit task crashed", extra={"batch_id": batch_id})

    @classmethod
    def _discard(cls, batch_id: int, completed: asyncio.Task[None]) -> None:
        if cls._tasks.get(batch_id) is completed:
            cls._tasks.pop(batch_id, None)


def _audit_state(job: ContentBatchJob) -> dict[str, Any]:
    strategy = job.strategy_json if isinstance(job.strategy_json, dict) else {}
    state = strategy.get(A2_REIYU_AUDIT_STATE_KEY)
    return dict(state) if isinstance(state, dict) else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
