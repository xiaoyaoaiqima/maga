"""Service for MAGA content-agent execution-layer APIs."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import (
    ContentAgentArtifact,
    ContentAgentEvent,
    ContentAgentRun,
    ContentAgentTask,
)
from app.schemas.content_agent import (
    ContentAgentArtifactCreate,
    ContentAgentClaimRequest,
    ContentAgentClaimResponse,
    ContentAgentEventCreate,
    ContentAgentRunCompleteRequest,
    ContentAgentRunFailRequest,
    ContentAgentSnapshotResponse,
    ContentAgentTaskCreate,
)


class ContentAgentService:
    """Business service for content-specific executor tasks and run writeback."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(self, request: ContentAgentTaskCreate) -> ContentAgentTask:
        task = ContentAgentTask(
            task_code=request.task_code or f"cat-{uuid4().hex[:12]}",
            task_type=request.task_type,
            status="pending",
            priority=request.priority,
            executor_code=request.executor_code,
            brand_id=request.brand_id,
            product_id=request.product_id,
            campaign_id=request.campaign_id,
            brief_id=request.brief_id,
            input_snapshot=request.input_snapshot,
            asset_refs=request.asset_refs,
            retry_count=0,
            created_by=request.created_by,
        )
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def claim_task(self, request: ContentAgentClaimRequest) -> Optional[ContentAgentClaimResponse]:
        query = (
            select(ContentAgentTask)
            .where(ContentAgentTask.status == "pending")
            .where(ContentAgentTask.executor_code == request.executor_code)
            .order_by(ContentAgentTask.priority.desc(), ContentAgentTask.create_time.asc(), ContentAgentTask.id.asc())
            .limit(1)
        )
        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        task = next((item for item in candidates if self._capability_matches(item.task_type, request.capabilities)), None)
        if task is None:
            return None

        task.status = "running"
        task.update_time = datetime.utcnow()

        run = ContentAgentRun(
            task_id=task.id,
            run_code=f"car-{uuid4().hex[:12]}",
            executor_code=request.executor_code,
            executor_type=request.executor_type,
            external_run_id=request.external_run_id,
            status="running",
            config_snapshot=request.config_snapshot,
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        await self.db.refresh(task)

        return ContentAgentClaimResponse(
            task_id=task.id,
            run_id=run.id,
            task_type=task.task_type,
            input=task.input_snapshot or {},
            asset_refs=task.asset_refs or {},
        )

    async def get_task_snapshot(self, task_id: int, run_id: Optional[int] = None) -> Optional[ContentAgentSnapshotResponse]:
        task = await self.db.get(ContentAgentTask, task_id)
        if not task:
            return None
        return ContentAgentSnapshotResponse(
            task_id=task.id,
            run_id=run_id,
            task_type=task.task_type,
            input=task.input_snapshot or {},
            asset_refs=task.asset_refs or {},
        )

    async def create_event(self, run_id: int, request: ContentAgentEventCreate) -> ContentAgentEvent:
        await self._require_run(run_id)
        event = ContentAgentEvent(
            run_id=run_id,
            step=request.step,
            event_type=request.event_type,
            expert_code=request.expert_code,
            model_code=request.model_code,
            input_snapshot=request.input_snapshot,
            output_snapshot=request.output_snapshot,
            message=request.message,
            latency_ms=request.latency_ms,
            token_usage=request.token_usage,
            metadata_json=request.metadata,
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def create_artifact(self, run_id: int, request: ContentAgentArtifactCreate) -> ContentAgentArtifact:
        await self._require_run(run_id)
        artifact = ContentAgentArtifact(
            run_id=run_id,
            artifact_type=request.artifact_type,
            name=request.name,
            content_text=request.content_text,
            content_json=request.content_json,
            file_url=request.file_url,
            version_no=request.version_no,
            metadata_json=request.metadata,
        )
        self.db.add(artifact)
        await self.db.flush()
        await self.db.refresh(artifact)
        return artifact

    async def complete_run(self, run_id: int, request: ContentAgentRunCompleteRequest) -> ContentAgentRun:
        run = await self._require_run(run_id)
        task = await self._require_task(run.task_id)
        now = datetime.utcnow()

        run.status = "succeeded"
        run.finished_at = now
        run.model_summary = request.model_summary
        run.update_time = now
        task.status = "succeeded"
        task.output_summary = request.output_summary
        task.update_time = now
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def fail_run(self, run_id: int, request: ContentAgentRunFailRequest) -> ContentAgentRun:
        run = await self._require_run(run_id)
        task = await self._require_task(run.task_id)
        now = datetime.utcnow()

        run.status = "failed"
        run.error_message = request.error_message
        run.finished_at = now
        run.update_time = now
        task.status = "failed"
        task.error_message = request.error_message
        if request.output_summary is not None:
            task.output_summary = request.output_summary
        task.update_time = now
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def _require_run(self, run_id: int) -> ContentAgentRun:
        run = await self.db.get(ContentAgentRun, run_id)
        if not run:
            raise ValueError("content agent run not found")
        return run

    async def _require_task(self, task_id: int) -> ContentAgentTask:
        task = await self.db.get(ContentAgentTask, task_id)
        if not task:
            raise ValueError("content agent task not found")
        return task

    @staticmethod
    def _capability_matches(task_type: str, capabilities: list[str]) -> bool:
        return not capabilities or task_type in capabilities
