"""Minimal MAGA-side orchestrator for protocol v0.1 content-agent runs."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import ContentAgentRun, ContentAgentStageCall, ExecutorRegistry
from app.schemas.content_agent import (
    ContentAgentStageCallCompleteRequest,
    ContentAgentStageCallCreate,
    ContentAgentTaskCreate,
)
from app.services.content_agent_service import ContentAgentService
from app.services.executor_invocation_service import ExecutorInvocationClient, InvokeResult, build_invoke_envelope

FIRST_XHS_CAPABILITY = "xhs.interpret_brief"
FIRST_XHS_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class OrchestratorStartResult:
    run: ContentAgentRun
    stage_call: ContentAgentStageCall
    invoke_result: InvokeResult


class ContentAgentOrchestrator:
    """Creates a task/run/stage and pushes the first capability to an executor."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        invocation_client: ExecutorInvocationClient | None = None,
        callback_base_url: str,
    ):
        self.db = db
        self.service = ContentAgentService(db)
        self.invocation_client = invocation_client or ExecutorInvocationClient()
        self.callback_base_url = callback_base_url

    async def start_generation_run(self, request: ContentAgentTaskCreate) -> OrchestratorStartResult:
        task = await self.service.create_task(request)
        executor = await self._require_executor(request.executor_code or "hermes_xhs_writer")
        if not executor.invoke_url:
            raise ValueError("executor invoke_url is required")

        run, stage_call = await self.service.start_run_with_stage(
            task.id,
            executor_code=executor.executor_code,
            executor_type=executor.executor_type,
            stage=ContentAgentStageCallCreate(
                capability=FIRST_XHS_CAPABILITY,
                schema_version=FIRST_XHS_SCHEMA_VERSION,
                invoke_mode="sync",
                input_snapshot=request.input_snapshot,
            ),
        )

        envelope = build_invoke_envelope(
            run_id=run.id,
            task_id=task.id,
            stage_call_id=stage_call.stage_call_id,
            capability=stage_call.capability,
            schema_version=stage_call.schema_version,
            run_token=run.run_token,
            input_payload=stage_call.input_snapshot or {},
            callback_base_url=self.callback_base_url,
            deadline_at=stage_call.deadline_at,
        )
        invoke_result = await self.invocation_client.invoke(invoke_url=executor.invoke_url, envelope=envelope)

        if invoke_result.mode == "sync":
            stage_call = await self.service.complete_stage_call(
                run.id,
                stage_call.stage_call_id,
                ContentAgentStageCallCompleteRequest(
                    run_token=run.run_token,
                    output=invoke_result.output or {},
                    stats=invoke_result.stats,
                ),
            )
            await self.db.refresh(run)

        return OrchestratorStartResult(run=run, stage_call=stage_call, invoke_result=invoke_result)

    async def _require_executor(self, executor_code: str) -> ExecutorRegistry:
        result = await self.db.execute(select(ExecutorRegistry).where(ExecutorRegistry.executor_code == executor_code))
        executor = result.scalar_one_or_none()
        if not executor:
            raise ValueError("executor not found")
        return executor
