"""Minimal MAGA-side orchestrator for protocol v0.1 content-agent runs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import normalize_executor_code
from app.models.content_agent import ContentAgentRun, ContentAgentStageCall, ExecutorRegistry
from app.models.llm_model_route import LLMModelRoute
from app.models.llm_provider_config import LLMProviderConfig
from app.schemas.content_agent import (
    ContentAgentRunCompleteRequest,
    ContentAgentRunFailRequest,
    ContentAgentStageCallCompleteRequest,
    ContentAgentStageCallCreate,
    ContentAgentStageCallFailRequest,
    ContentAgentTaskCreate,
)
from app.services.content_agent_service import ContentAgentService
from app.services.executor_invocation_service import ExecutorInvocationClient, InvokeResult, build_invoke_envelope

CONTENT_AGENT_SCHEMA_VERSION = "1"
CONTENT_REWRITE_CAPABILITY = "content.rewrite"


class ContentAgentInvokeError(ValueError):
    """Raised when a live executor call fails before returning a protocol result."""

    def __init__(self, message: str, *, run_id: int, stage_call_id: str):
        super().__init__(message)
        self.run_id = run_id
        self.stage_call_id = stage_call_id


@dataclass(frozen=True)
class SingleCapabilityResult:
    run: ContentAgentRun
    output: dict[str, Any]
    stage_calls: list[ContentAgentStageCall]


def _model_code_from_config(model_config: dict[str, Any]) -> str | None:
    for key in ("model_code", "ge_model", "ae_model"):
        value = str(model_config.get(key) or "").strip()
        if value:
            return value
    return None


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

    async def run_single_capability(
        self,
        request: ContentAgentTaskCreate,
        *,
        capability: str,
        schema_version: str = CONTENT_AGENT_SCHEMA_VERSION,
    ) -> SingleCapabilityResult:
        task = await self.service.create_task(request)
        executor = await self._require_executor(request.executor_code)
        if not executor.invoke_url:
            raise ValueError("executor invoke_url is required")

        run, stage_call = await self.service.start_run_with_stage(
            task.id,
            executor_code=executor.executor_code,
            executor_type=executor.executor_type,
            stage=ContentAgentStageCallCreate(
                capability=capability,
                schema_version=schema_version,
                invoke_mode="sync",
                input_snapshot=request.input_snapshot,
            ),
        )
        stage_call, invoke_result = await self._invoke_and_record_stage(executor, run, stage_call)
        if invoke_result.status == "failed":
            raise ContentAgentInvokeError(
                invoke_result.error_message or f"stage failed: {capability}",
                run_id=run.id,
                stage_call_id=stage_call.stage_call_id,
            )
        output = stage_call.output_snapshot or {}
        await self.service.complete_run(run.id, ContentAgentRunCompleteRequest(output_summary=output))
        await self.db.refresh(run)
        return SingleCapabilityResult(run=run, output=output, stage_calls=[stage_call])

    async def run_content_rewrite_stage(
        self,
        *,
        run_id: int,
        executor_code: str | None,
        input_payload: dict[str, Any],
    ) -> SingleCapabilityResult:
        executor = await self._require_executor(executor_code)
        if not executor.invoke_url:
            raise ValueError("executor invoke_url is required")
        run = await self.db.get(ContentAgentRun, run_id)
        if not run:
            raise ValueError("content agent run not found")

        # 违禁词审核由 MAGA 控制，模型改写只作为同一 run 下追加的执行痕迹。
        run.status = "running"
        run.status_substate = f"running.{CONTENT_REWRITE_CAPABILITY}"
        run.finished_at = None
        await self.db.flush()

        stage_call = await self.service.create_stage_call(
            run.id,
            ContentAgentStageCallCreate(
                capability=CONTENT_REWRITE_CAPABILITY,
                schema_version=CONTENT_AGENT_SCHEMA_VERSION,
                invoke_mode="sync",
                input_snapshot=input_payload,
            ),
        )
        try:
            stage_call, invoke_result = await self._invoke_and_record_stage(executor, run, stage_call)
        except ContentAgentInvokeError:
            await self.service.complete_run(
                run.id,
                ContentAgentRunCompleteRequest(output_summary=self._rewrite_input_summary(input_payload)),
            )
            await self.db.refresh(run)
            raise
        if invoke_result.status == "failed":
            await self.service.complete_run(
                run.id,
                ContentAgentRunCompleteRequest(output_summary=self._rewrite_input_summary(input_payload)),
            )
            await self.db.refresh(run)
            raise ValueError(invoke_result.error_message or f"stage failed: {CONTENT_REWRITE_CAPABILITY}")

        output = stage_call.output_snapshot or {}
        run.rewrite_round += 1
        await self.service.complete_run(
            run.id,
            ContentAgentRunCompleteRequest(output_summary=self._rewrite_output_summary(output)),
        )
        await self.db.refresh(run)
        return SingleCapabilityResult(run=run, output=output, stage_calls=[stage_call])

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
            input_payload=await self._input_payload_with_provider_config(stage_call.input_snapshot or {}),
            callback_base_url=self.callback_base_url,
            deadline_at=stage_call.deadline_at,
        )
        try:
            invoke_result = await self.invocation_client.invoke(
                invoke_url=executor.invoke_url,
                envelope=envelope,
                executor_token=self._executor_token(executor),
            )
        except Exception as exc:
            message = self._invoke_exception_message(exc, stage_call.capability)
            stage_call = await self.service.fail_stage_call(
                run.id,
                stage_call.stage_call_id,
                ContentAgentStageCallFailRequest(
                    error_code="executor_invoke_error",
                    error_message=message,
                    retryable=True,
                    details={"exception_type": type(exc).__name__},
                ),
                validate_transition=False,
            )
            await self.service.fail_run(run.id, ContentAgentRunFailRequest(error_message=message))
            await self.db.refresh(run)
            raise ContentAgentInvokeError(message, run_id=run.id, stage_call_id=stage_call.stage_call_id) from exc

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
            await self.service.fail_run(
                run.id,
                ContentAgentRunFailRequest(
                    error_message=invoke_result.error_message or "Executor returned failed status",
                ),
            )
            await self.db.refresh(run)
        return stage_call, invoke_result

    async def _input_payload_with_provider_config(self, input_payload: dict[str, Any]) -> dict[str, Any]:
        """Attach provider connection details only to the outbound invoke envelope.

        The stage/task snapshots remain free of API keys; the key stays in
        llm_provider_config and is copied into the transient executor request.
        """
        if not isinstance(input_payload, dict):
            return input_payload
        raw_model_config = input_payload.get("model_config")
        if not isinstance(raw_model_config, dict):
            return input_payload
        model_config = dict(raw_model_config)
        try:
            provider = await self._provider_for_model_config(model_config)
        except SQLAlchemyError:
            return input_payload
        if provider is None:
            return input_payload

        model_config["provider_code"] = provider.provider_code
        model_config["base_url"] = provider.base_url
        if provider.api_key:
            model_config["api_key"] = provider.api_key
        for key, value in (provider.default_params or {}).items():
            if key in {"temperature", "max_tokens", "top_p"} and value is not None and key not in model_config:
                model_config[key] = value

        model_code = _model_code_from_config(model_config) or str(provider.default_model or "").strip()
        route = await self._route_for_model(provider.provider_code, model_code)
        if route is not None:
            model_config["model_code"] = route.provider_model
            model_config["provider_model"] = route.provider_model
            model_config["route_model_code"] = route.model_code
            if route.timeout_seconds and "timeout" not in model_config:
                model_config["timeout"] = route.timeout_seconds
        elif model_code and "model_code" not in model_config:
            model_config["model_code"] = model_code

        return {**input_payload, "model_config": model_config}

    async def _provider_for_model_config(self, model_config: dict[str, Any]) -> LLMProviderConfig | None:
        provider_code = str(model_config.get("provider_code") or "").strip()
        if provider_code:
            provider = await self._provider_by_code(provider_code)
            if provider is not None:
                return provider
            # 老专家配置里可能残留已删除 provider_code；继续走模型路由，避免绕过系统 LLM provider。

        model_code = _model_code_from_config(model_config)
        if model_code:
            route = await self._best_route_for_model(model_code)
            if route is not None:
                return await self._provider_by_code(route.provider_code)

        result = await self.db.execute(
            select(LLMProviderConfig)
            .where(
                LLMProviderConfig.enabled == 1,
                LLMProviderConfig.is_deleted == 0,
            )
            .order_by(LLMProviderConfig.priority.desc(), LLMProviderConfig.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _provider_by_code(self, provider_code: str) -> LLMProviderConfig | None:
        result = await self.db.execute(
            select(LLMProviderConfig)
            .where(
                LLMProviderConfig.provider_code == provider_code,
                LLMProviderConfig.enabled == 1,
                LLMProviderConfig.is_deleted == 0,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _best_route_for_model(self, model_code: str) -> LLMModelRoute | None:
        result = await self.db.execute(
            select(LLMModelRoute)
            .where(
                LLMModelRoute.model_code == model_code,
                LLMModelRoute.enabled == 1,
                LLMModelRoute.is_deleted == 0,
            )
            .order_by(LLMModelRoute.priority.desc(), LLMModelRoute.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _route_for_model(self, provider_code: str, model_code: str | None) -> LLMModelRoute | None:
        if not model_code:
            return None
        result = await self.db.execute(
            select(LLMModelRoute)
            .where(
                LLMModelRoute.provider_code == provider_code,
                LLMModelRoute.model_code == model_code,
                LLMModelRoute.enabled == 1,
                LLMModelRoute.is_deleted == 0,
            )
            .order_by(LLMModelRoute.priority.desc(), LLMModelRoute.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _invoke_exception_message(self, exc: Exception, capability: str) -> str:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return (
                "MAGA Worker 未启动或不可访问，请先在项目根目录执行 make worker-start，"
                f"再重试生文。当前失败阶段：{capability}"
            )
        if isinstance(exc, httpx.ReadTimeout):
            return (
                "MAGA Worker 响应超时，请确认 worker 仍在运行，或稍后重试。"
                f"当前失败阶段：{capability}"
            )
        if isinstance(exc, httpx.HTTPError):
            return f"MAGA Worker 调用失败：{exc}。当前失败阶段：{capability}"
        text = str(exc).strip()
        if text:
            return text
        return f"Executor invoke failed during {capability}: {type(exc).__name__}"

    def _rewrite_output_summary(self, output: dict[str, Any]) -> dict[str, str]:
        if output.get("comment"):
            return {"comment": str(output["comment"])}
        final = output.get("final") if isinstance(output.get("final"), dict) else {}
        title = output.get("title") or final.get("title")
        body = output.get("body") or final.get("body")
        if title or body:
            return {"title": str(title or ""), "body": str(body or "")}
        return {}

    def _rewrite_input_summary(self, input_payload: dict[str, Any]) -> dict[str, str]:
        previous = input_payload.get("previous_content") or input_payload.get("previous_draft") or {}
        if not isinstance(previous, dict):
            return {}
        if previous.get("comment"):
            return {"comment": str(previous["comment"])}
        return {
            "title": str(previous.get("title") or ""),
            "body": str(previous.get("body") or ""),
        }

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
