"""MAGA -> Executor protocol v0.1 invocation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

PROTOCOL_VERSION = "0.1"


@dataclass(frozen=True)
class InvokeResult:
    """Normalized result of calling an executor /invoke endpoint."""

    mode: str
    stage_call_id: str
    output: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None
    ack_at: str | None = None


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_invoke_envelope(
    *,
    run_id: int,
    task_id: int,
    stage_call_id: str,
    capability: str,
    schema_version: str,
    run_token: str,
    input_payload: dict[str, Any],
    callback_base_url: str,
    deadline_at: datetime | None,
) -> dict[str, Any]:
    """Build the protocol v0.1 invocation envelope sent from MAGA to Executor."""
    callback_base = callback_base_url.rstrip("/")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "task_id": task_id,
        "stage_call_id": stage_call_id,
        "capability": capability,
        "schema_version": schema_version,
        "run_token": run_token,
        "deadline_at": _iso_or_none(deadline_at),
        "input": input_payload or {},
        "callback": {
            "events_url": f"{callback_base}/runs/{run_id}/events",
            "artifacts_url": f"{callback_base}/runs/{run_id}/artifacts",
            "heartbeat_url": f"{callback_base}/runs/{run_id}/heartbeat",
            "human_review_url": f"{callback_base}/runs/{run_id}/human-review",
            "complete_url": f"{callback_base}/runs/{run_id}/stage-calls/{stage_call_id}/complete",
            "fail_url": f"{callback_base}/runs/{run_id}/stage-calls/{stage_call_id}/fail",
        },
    }


class MockExecutorInvocationClient:
    """Local deterministic mock for early API smoke before Hermes /invoke exists."""

    async def invoke(self, *, invoke_url: str, envelope: dict[str, Any]) -> InvokeResult:
        input_payload = envelope.get("input") or {}
        return InvokeResult(
            mode="sync",
            stage_call_id=envelope["stage_call_id"],
            output={
                "structured_brief": {
                    "brief_type": input_payload.get("brief_type"),
                    "product_topic": input_payload.get("product_topic"),
                    "target_audience": input_payload.get("target_audience"),
                    "style": input_payload.get("style"),
                }
            },
            stats={"mock": True},
        )


class ExecutorInvocationClient:
    """HTTP client for MAGA push invocation of an executor capability."""

    def __init__(self, http_client: Any | None = None, timeout_seconds: float = 30.0):
        self.http_client = http_client or httpx.AsyncClient()
        self.timeout_seconds = timeout_seconds

    async def invoke(self, *, invoke_url: str, envelope: dict[str, Any]) -> InvokeResult:
        response = await self.http_client.post(
            invoke_url,
            json=envelope,
            headers={
                "X-Maga-Protocol-Version": PROTOCOL_VERSION,
                "Idempotency-Key": envelope.get("stage_call_id", ""),
            },
            timeout=self.timeout_seconds,
        )
        payload = response.json()

        if response.status_code == 200:
            return InvokeResult(
                mode="sync",
                stage_call_id=payload.get("stage_call_id") or envelope["stage_call_id"],
                output=payload.get("output") or {},
                stats=payload.get("stats"),
                ack_at=None,
            )

        if response.status_code == 202:
            return InvokeResult(
                mode="async",
                stage_call_id=payload.get("stage_call_id") or envelope["stage_call_id"],
                output=None,
                stats=None,
                ack_at=payload.get("ack_at"),
            )

        raise RuntimeError(f"Executor invoke failed: status={response.status_code} body={response.text}")
