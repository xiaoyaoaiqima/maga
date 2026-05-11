"""Minimal MAGA-side orchestrator for protocol v0.1 content-agent runs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import normalize_executor_code
from app.models.content_agent import ContentAgentRun, ContentAgentStageCall, ExecutorRegistry
from app.schemas.content_agent import (
    ContentAgentRunCompleteRequest,
    ContentAgentStageCallCompleteRequest,
    ContentAgentStageCallCreate,
    ContentAgentStageCallFailRequest,
    ContentAgentTaskCreate,
)
from app.services.content_agent_service import ContentAgentService
from app.services.executor_invocation_service import ExecutorInvocationClient, InvokeResult, build_invoke_envelope

FIRST_XHS_CAPABILITY = "xhs.interpret_brief"
FIRST_XHS_SCHEMA_VERSION = "1"
MVP_XHS_CAPABILITIES = [
    "xhs.interpret_brief",
    "xhs.run_ae_analysis",
    "xhs.generate_draft",
    "xhs.run_ae_review",
]
REWRITE_XHS_CAPABILITY = "xhs.rewrite_draft"
MAX_MVP_REWRITE_ROUNDS = 1


@dataclass(frozen=True)
class OrchestratorStartResult:
    run: ContentAgentRun
    stage_call: ContentAgentStageCall
    invoke_result: InvokeResult


@dataclass(frozen=True)
class MvpGenerationResult:
    run: ContentAgentRun
    final_content: dict[str, str]
    stage_calls: list[ContentAgentStageCall]


class ContentAgentOrchestrator:
    """Creates MAGA tasks/runs/stages and pushes sync capabilities to an executor."""

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
        executor = await self._require_executor(request.executor_code)
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

        stage_call, invoke_result = await self._invoke_and_record_stage(executor, run, stage_call)
        return OrchestratorStartResult(run=run, stage_call=stage_call, invoke_result=invoke_result)

    async def run_mvp_generation_chain(self, request: ContentAgentTaskCreate) -> MvpGenerationResult:
        task = await self.service.create_task(request)
        executor = await self._require_executor(request.executor_code)
        if not executor.invoke_url:
            raise ValueError("executor invoke_url is required")

        run: ContentAgentRun | None = None
        stage_calls: list[ContentAgentStageCall] = []
        context: dict[str, Any] = dict(request.input_snapshot or {})

        for index, capability in enumerate(MVP_XHS_CAPABILITIES):
            stage_request = ContentAgentStageCallCreate(
                capability=capability,
                schema_version=FIRST_XHS_SCHEMA_VERSION,
                invoke_mode="sync",
                input_snapshot=self._input_for_capability(capability, context),
            )
            if run is None:
                run, stage_call = await self.service.start_run_with_stage(
                    task.id,
                    executor_code=executor.executor_code,
                    executor_type=executor.executor_type,
                    stage=stage_request,
                )
            else:
                stage_call = await self.service.create_stage_call(run.id, stage_request)

            stage_call, invoke_result = await self._invoke_and_record_stage(executor, run, stage_call)
            stage_calls.append(stage_call)
            if invoke_result.status == "failed":
                raise ValueError(invoke_result.error_message or f"stage failed: {capability}")
            context.update(stage_call.output_snapshot or {})

        if run is None:
            raise ValueError("run was not created")
        if self._review_requires_rewrite(context) and run.rewrite_round < MAX_MVP_REWRITE_ROUNDS:
            stage_request = ContentAgentStageCallCreate(
                capability=REWRITE_XHS_CAPABILITY,
                schema_version=FIRST_XHS_SCHEMA_VERSION,
                invoke_mode="sync",
                input_snapshot=self._input_for_capability(REWRITE_XHS_CAPABILITY, context),
            )
            stage_call = await self.service.create_stage_call(run.id, stage_request)
            stage_call, invoke_result = await self._invoke_and_record_stage(executor, run, stage_call)
            stage_calls.append(stage_call)
            if invoke_result.status == "failed":
                raise ValueError(invoke_result.error_message or f"stage failed: {REWRITE_XHS_CAPABILITY}")
            context.update(stage_call.output_snapshot or {})
            run.rewrite_round += 1
            await self.db.flush()
        final_content = self._extract_final_content(context)
        await self.service.complete_run(run.id, ContentAgentRunCompleteRequest(output_summary=final_content))
        await self.db.refresh(run)
        return MvpGenerationResult(run=run, final_content=final_content, stage_calls=stage_calls)

    async def _invoke_and_record_stage(
        self,
        executor: ExecutorRegistry,
        run: ContentAgentRun,
        stage_call: ContentAgentStageCall,
    ) -> tuple[ContentAgentStageCall, InvokeResult]:
        envelope = build_invoke_envelope(
            run_id=run.id,
            task_id=run.task_id,
            stage_call_id=stage_call.stage_call_id,
            capability=stage_call.capability,
            schema_version=stage_call.schema_version,
            run_token=run.run_token,
            input_payload=stage_call.input_snapshot or {},
            callback_base_url=self.callback_base_url,
            deadline_at=stage_call.deadline_at,
        )
        invoke_result = await self.invocation_client.invoke(
            invoke_url=executor.invoke_url,
            envelope=envelope,
            executor_token=self._executor_token(executor),
        )

        if invoke_result.status == "succeeded":
            stage_call = await self.service.complete_stage_call(
                run.id,
                stage_call.stage_call_id,
                ContentAgentStageCallCompleteRequest(
                    output=invoke_result.output or {},
                    stats=invoke_result.stats,
                ),
                validate_transition=False,
            )
            await self.db.refresh(run)
        elif invoke_result.status == "failed":
            stage_call = await self.service.fail_stage_call(
                run.id,
                stage_call.stage_call_id,
                ContentAgentStageCallFailRequest(
                    error_code=invoke_result.error_code or "executor_internal",
                    error_message=invoke_result.error_message or "Executor returned failed status",
                ),
                validate_transition=False,
            )
            await self.db.refresh(run)
        return stage_call, invoke_result

    def _input_for_capability(self, capability: str, context: dict[str, Any]) -> dict[str, Any]:
        if capability == "xhs.interpret_brief":
            payload = {
                "brief_type": context.get("brief_type"),
                "product_topic": context.get("product_topic"),
                "target_audience": context.get("target_audience"),
                "style": context.get("style"),
            }
            if context.get("generation_snapshot"):
                payload["generation_snapshot"] = context.get("generation_snapshot")
            return payload
        if capability == "xhs.run_ae_analysis":
            payload = {"structured_brief": context.get("structured_brief", {})}
            if context.get("generation_snapshot"):
                payload["generation_snapshot"] = context.get("generation_snapshot")
            return payload
        if capability == "xhs.generate_draft":
            payload = {
                "structured_brief": context.get("structured_brief", {}),
                "analyses": context.get("analyses", {}),
            }
            if context.get("generation_snapshot"):
                payload["generation_snapshot"] = context.get("generation_snapshot")
            return payload
        if capability == "xhs.run_ae_review":
            payload = {
                "draft": context.get("draft", {}),
                "structured_brief": context.get("structured_brief", {}),
            }
            if context.get("generation_snapshot"):
                payload["generation_snapshot"] = context.get("generation_snapshot")
            return payload
        if capability == "xhs.rewrite_draft":
            payload = {
                "previous_draft": context.get("draft", {}),
                "structured_brief": context.get("structured_brief", {}),
                "analyses": context.get("analyses", {}),
                "review_report": {
                    "hard_results": context.get("hard_results", []),
                    "soft_scores": context.get("soft_scores", []),
                    "failed_aes": context.get("failed_aes", []),
                },
                "rewrite_round": context.get("rewrite_round", 0) + 1,
            }
            if context.get("generation_snapshot"):
                payload["generation_snapshot"] = context.get("generation_snapshot")
            return payload
        return dict(context)

    def _review_requires_rewrite(self, context: dict[str, Any]) -> bool:
        hard_results = context.get("hard_results") or []
        if any(result.get("pass") is False for result in hard_results if isinstance(result, dict)):
            return True
        return bool(context.get("failed_aes"))

    def _extract_final_content(self, context: dict[str, Any]) -> dict[str, str]:
        draft = context.get("final") or context.get("draft") or {}
        title = draft.get("title") or context.get("title")
        body = draft.get("body") or context.get("body")
        if not title or not body:
            raise ValueError("generation did not produce publishable title/body")
        return {"title": str(title), "body": str(body)}

    def _executor_token(self, executor: ExecutorRegistry) -> str | None:
        config = executor.config_json or {}
        token = config.get("executor_token") if isinstance(config, dict) else None
        if token is not None:
            return str(token)
        return None

    async def _require_executor(self, executor_code: str | None) -> ExecutorRegistry:
        normalized_code = normalize_executor_code(executor_code)
        result = await self.db.execute(select(ExecutorRegistry).where(ExecutorRegistry.executor_code == normalized_code))
        executor = result.scalar_one_or_none()
        if not executor:
            raise ValueError("executor not found")
        return executor
