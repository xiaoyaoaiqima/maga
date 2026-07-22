"""Service for MAGA content-agent execution-layer APIs."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_CONTENT_GENERATION_SYSTEM_PROMPT
from app.models.content_agent import (
    ContentAgentArtifact,
    ContentAgentEvent,
    ContentAgentHumanReview,
    ContentAgentRun,
    ContentAgentStageCall,
    ContentAgentTask,
    ExecutorRegistry,
)
from app.schemas.content_agent import (
    ContentAgentArtifactCreate,
    ContentAgentClaimRequest,
    ContentAgentClaimResponse,
    ContentAgentEventCreate,
    ContentAgentRunCompleteRequest,
    ContentAgentRunFailRequest,
    ContentAgentSnapshotResponse,
    ContentAgentHeartbeatRequest,
    ContentAgentHumanReviewRequest,
    ContentAgentStageCallCompleteRequest,
    ContentAgentStageCallCreate,
    ContentAgentStageCallFailRequest,
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

    async def get_executor(self, executor_code: str) -> ExecutorRegistry | None:
        result = await self.db.execute(select(ExecutorRegistry).where(ExecutorRegistry.executor_code == executor_code))
        return result.scalar_one_or_none()

    async def claim_task(self, request: ContentAgentClaimRequest) -> Optional[ContentAgentClaimResponse]:
        query = (
            select(ContentAgentTask)
            .where(ContentAgentTask.status == "pending")
            .where(or_(ContentAgentTask.executor_code == request.executor_code, ContentAgentTask.executor_code.is_(None)))
            .order_by(ContentAgentTask.priority.desc(), ContentAgentTask.create_time.asc(), ContentAgentTask.id.asc())
        )
        result = await self.db.execute(query)
        candidates = list(result.scalars().all())

        task = next((item for item in candidates if self._capability_matches(item.task_type, request.capabilities)), None)
        if task is None:
            return None

        now = datetime.utcnow()
        claim_result = await self.db.execute(
            update(ContentAgentTask)
            .where(ContentAgentTask.id == task.id)
            .where(ContentAgentTask.status == "pending")
            .values(status="running", executor_code=request.executor_code, update_time=now)
        )
        if claim_result.rowcount != 1:
            return None

        await self.db.refresh(task)

        run = ContentAgentRun(
            task_id=task.id,
            run_code=f"car-{uuid4().hex[:12]}",
            run_token=f"rt-{uuid4().hex}",
            executor_code=request.executor_code,
            executor_type=request.executor_type,
            external_run_id=request.external_run_id,
            status="running",
            status_substate="running.claimed",
            rewrite_round=0,
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

    async def start_run_with_stage(
        self,
        task_id: int,
        *,
        executor_code: str,
        stage: ContentAgentStageCallCreate,
        executor_type: str = "direct_llm",
        config_snapshot: Optional[dict] = None,
    ) -> tuple[ContentAgentRun, ContentAgentStageCall]:
        """Start a protocol v0.1 run and its first stage call."""
        task = await self._require_task(task_id)
        now = datetime.utcnow()
        run = ContentAgentRun(
            task_id=task.id,
            run_code=f"car-{uuid4().hex[:12]}",
            run_token=f"rt-{uuid4().hex}",
            executor_code=executor_code,
            executor_type=executor_type,
            status="running",
            status_substate=f"running.{stage.capability}",
            current_stage_call_id=stage.stage_call_id or f"stage-{uuid4().hex[:12]}",
            rewrite_round=0,
            config_snapshot=config_snapshot,
            started_at=now,
        )
        task.status = "running"
        task.executor_code = task.executor_code or executor_code
        task.update_time = now
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)

        stage_call = await self.create_stage_call(run.id, stage, force_stage_call_id=run.current_stage_call_id)
        await self.db.refresh(run)
        return run, stage_call

    async def create_stage_call(
        self,
        run_id: int,
        request: ContentAgentStageCallCreate,
        *,
        force_stage_call_id: Optional[str] = None,
    ) -> ContentAgentStageCall:
        run = await self._require_run(run_id)
        max_sequence = await self.db.scalar(
            select(func.max(ContentAgentStageCall.sequence_no)).where(ContentAgentStageCall.run_id == run_id)
        )
        stage_call_id = force_stage_call_id or request.stage_call_id or f"stage-{uuid4().hex[:12]}"
        now = datetime.utcnow()
        stage_call = ContentAgentStageCall(
            stage_call_id=stage_call_id,
            run_id=run.id,
            sequence_no=(max_sequence or 0) + 1,
            capability=request.capability,
            schema_version=request.schema_version,
            invoke_mode=request.invoke_mode,
            status="running",
            input_snapshot=request.input_snapshot,
            retry_of_stage_call_id=request.retry_of_stage_call_id,
            started_at=now,
            deadline_at=request.deadline_at,
        )
        run.current_stage_call_id = stage_call_id
        run.status_substate = f"running.{request.capability}"
        run.update_time = now
        self.db.add(stage_call)
        await self.db.flush()
        await self.db.refresh(stage_call)
        return stage_call

    async def get_task_snapshot(self, task_id: int, run_id: Optional[int] = None) -> Optional[ContentAgentSnapshotResponse]:
        task = await self.db.get(ContentAgentTask, task_id)
        if not task:
            return None
        input_snapshot = task.input_snapshot or {}
        model_config = input_snapshot.get("model_config") if isinstance(input_snapshot, dict) else {}
        if not isinstance(model_config, dict):
            model_config = {}
        system_prompt = None
        if task.task_type == "content_generate":
            system_prompt = str(
                model_config.get("system_prompt")
                or DEFAULT_CONTENT_GENERATION_SYSTEM_PROMPT
            )
        return ContentAgentSnapshotResponse(
            task_id=task.id,
            run_id=run_id,
            task_type=task.task_type,
            system_prompt=system_prompt,
            input=input_snapshot,
            asset_refs=task.asset_refs or {},
        )

    async def create_event(self, run_id: int, request: ContentAgentEventCreate) -> ContentAgentEvent:
        await self._require_run(run_id)
        if request.idempotency_key:
            existing = await self._find_event_by_idempotency_key(run_id, request.idempotency_key)
            if existing:
                return existing
        if request.stage_call_id:
            await self._require_stage_call_for_run(run_id, request.stage_call_id)
        event = ContentAgentEvent(
            run_id=run_id,
            stage_call_id=request.stage_call_id,
            step=request.step,
            event_type=request.event_type,
            expert_code=request.expert_code,
            model_code=request.model_code,
            input_snapshot=request.input_snapshot,
            output_snapshot=request.output_snapshot,
            message=request.message,
            latency_ms=request.latency_ms,
            token_usage=request.token_usage,
            otel_attributes_json=request.otel_attributes,
            metadata_json=request.metadata,
            idempotency_key=request.idempotency_key,
            occurred_at=request.occurred_at,
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def create_artifact(self, run_id: int, request: ContentAgentArtifactCreate) -> ContentAgentArtifact:
        await self._require_run(run_id)
        if request.idempotency_key:
            existing = await self._find_artifact_by_idempotency_key(run_id, request.idempotency_key)
            if existing:
                return existing
        if request.stage_call_id:
            await self._require_stage_call_for_run(run_id, request.stage_call_id)
        artifact = ContentAgentArtifact(
            run_id=run_id,
            stage_call_id=request.stage_call_id,
            artifact_code=request.artifact_code,
            artifact_type=request.artifact_type,
            name=request.name,
            content_text=request.content_text,
            content_json=request.content_json,
            file_url=request.file_url,
            version_no=request.version_no,
            metadata_json=request.metadata,
            idempotency_key=request.idempotency_key,
        )
        self.db.add(artifact)
        await self.db.flush()
        await self.db.refresh(artifact)
        return artifact

    async def complete_stage_call(
        self,
        run_id: int,
        stage_call_id: str,
        request: ContentAgentStageCallCompleteRequest,
        *,
        validate_transition: bool = True,
    ) -> ContentAgentStageCall:
        run = await self._require_run(run_id)
        if validate_transition:
            self._validate_current_stage(run, stage_call_id)
        stage_call = await self._require_stage_call_for_run(run_id, stage_call_id)
        now = datetime.utcnow()
        stage_call.status = "succeeded"
        stage_call.output_snapshot = request.output
        stage_call.stats_json = request.stats
        stage_call.finished_at = now
        stage_call.update_time = now
        run.update_time = now
        await self.db.flush()
        await self.db.refresh(stage_call)
        return stage_call

    async def fail_stage_call(
        self,
        run_id: int,
        stage_call_id: str,
        request: ContentAgentStageCallFailRequest,
        *,
        validate_transition: bool = True,
    ) -> ContentAgentStageCall:
        run = await self._require_run(run_id)
        if validate_transition:
            self._validate_current_stage(run, stage_call_id)
        stage_call = await self._require_stage_call_for_run(run_id, stage_call_id)
        now = datetime.utcnow()
        stage_call.status = "failed"
        stage_call.error_code = request.error_code
        stage_call.error_message = request.error_message
        stage_call.retryable = 1 if request.retryable else 0
        stage_call.stats_json = {"details": request.details} if request.details else stage_call.stats_json
        stage_call.finished_at = now
        stage_call.update_time = now
        run.update_time = now
        await self.db.flush()
        await self.db.refresh(stage_call)
        return stage_call

    async def record_heartbeat(self, run_id: int, request: ContentAgentHeartbeatRequest) -> ContentAgentRun:
        run = await self._require_run(run_id)
        self._validate_run_token(run, request.run_token)
        self._validate_current_stage(run, request.stage_call_id)
        await self._require_stage_call_for_run(run_id, request.stage_call_id)
        now = request.occurred_at or datetime.utcnow()
        run.status_substate = f"running.{request.progress_hint}" if request.progress_hint else "running.heartbeat"
        run.update_time = now
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def request_human_review(
        self,
        run_id: int,
        request: ContentAgentHumanReviewRequest,
        *,
        stage_call_id_header: str | None = None,
        protocol_version_header: str | None = None,
    ) -> ContentAgentHumanReview:
        run = await self._require_run(run_id)
        if protocol_version_header and protocol_version_header != "0.1":
            raise ValueError("unsupported protocol version")
        stage_call_id = request.stage_call_id or stage_call_id_header
        if stage_call_id_header and request.stage_call_id and stage_call_id_header != request.stage_call_id:
            raise ValueError("stage header does not match request stage_call_id")
        if stage_call_id:
            self._validate_current_stage(run, stage_call_id)
            await self._require_stage_call_for_run(run_id, stage_call_id)
        now = datetime.utcnow()
        review = ContentAgentHumanReview(
            run_id=run_id,
            stage_call_id=stage_call_id,
            reason=request.reason,
            payload_json=request.payload,
            response_schema_json=None,
            ui_hint=None,
            status="pending",
            requested_at=now,
        )
        run.status = "needs_review"
        run.status_substate = "needs_review.pending"
        run.update_time = now
        task = await self._require_task(run.task_id)
        task.status = "needs_review"
        task.update_time = now
        self.db.add(review)
        await self.db.flush()
        await self.db.refresh(review)
        return review

    async def complete_run(self, run_id: int, request: ContentAgentRunCompleteRequest) -> ContentAgentRun:
        run = await self._require_run(run_id)
        task = await self._require_task(run.task_id)
        now = datetime.utcnow()

        run.status = "succeeded"
        run.status_substate = None
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
        run.status_substate = None
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

    async def _require_stage_call_for_run(self, run_id: int, stage_call_id: str) -> ContentAgentStageCall:
        result = await self.db.execute(
            select(ContentAgentStageCall).where(
                ContentAgentStageCall.run_id == run_id,
                ContentAgentStageCall.stage_call_id == stage_call_id,
            )
        )
        stage_call = result.scalar_one_or_none()
        if not stage_call:
            raise ValueError("stage call not found for run")
        return stage_call

    async def _find_event_by_idempotency_key(self, run_id: int, idempotency_key: str) -> Optional[ContentAgentEvent]:
        result = await self.db.execute(
            select(ContentAgentEvent).where(
                ContentAgentEvent.run_id == run_id,
                ContentAgentEvent.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def _find_artifact_by_idempotency_key(self, run_id: int, idempotency_key: str) -> Optional[ContentAgentArtifact]:
        result = await self.db.execute(
            select(ContentAgentArtifact).where(
                ContentAgentArtifact.run_id == run_id,
                ContentAgentArtifact.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _validate_run_token(run: ContentAgentRun, run_token: str) -> None:
        if not run.run_token or run.run_token != run_token:
            raise ValueError("invalid run token")

    @staticmethod
    def _validate_current_stage(run: ContentAgentRun, stage_call_id: str) -> None:
        if run.current_stage_call_id != stage_call_id:
            raise ValueError("stage call is not current")

    @staticmethod
    def _capability_matches(task_type: str, capabilities: list[str]) -> bool:
        return not capabilities or task_type in capabilities
