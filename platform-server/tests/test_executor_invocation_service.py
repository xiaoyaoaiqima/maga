"""Tests for MAGA -> Executor push invocation client."""

import pytest

from app.services.executor_invocation_service import ExecutorInvocationClient, InvokeResult, build_invoke_envelope


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self.response


@pytest.mark.asyncio
async def test_build_invoke_envelope_contains_protocol_and_callback_urls():
    envelope = build_invoke_envelope(
        run_id=10,
        task_id=20,
        stage_call_id="stage-001",
        capability="xhs.interpret_brief",
        schema_version="1",
        run_token="rt-001",
        input_payload={"brief": {"topic": "A2 奶粉"}},
        callback_base_url="https://maga.example.com/api/v1/content-agent",
        deadline_at=None,
    )

    assert envelope["protocol_version"] == "0.1"
    assert envelope["run_id"] == 10
    assert envelope["task_id"] == 20
    assert envelope["stage_call_id"] == "stage-001"
    assert envelope["capability"] == "xhs.interpret_brief"
    assert envelope["input"] == {"brief": {"topic": "A2 奶粉"}}
    assert envelope["callback"]["events_url"].endswith("/runs/10/events")
    assert envelope["callback"]["complete_url"].endswith("/runs/10/stage-calls/stage-001/complete")
    assert envelope["callback"]["fail_url"].endswith("/runs/10/stage-calls/stage-001/fail")
    assert envelope["run_token"] == "rt-001"


@pytest.mark.asyncio
async def test_invoke_sync_200_returns_output_envelope():
    http_client = FakeAsyncClient(
        FakeResponse(
            200,
            {
                "stage_call_id": "stage-001",
                "status": "succeeded",
                "output": {"structured_brief": {"topic": "A2 奶粉"}},
                "stats": {"duration_ms": 10},
            },
        )
    )
    client = ExecutorInvocationClient(http_client=http_client)

    result = await client.invoke(
        invoke_url="https://executor.example.com/invoke",
        envelope={"stage_call_id": "stage-001", "capability": "xhs.interpret_brief"},
    )

    assert result == InvokeResult(
        mode="sync",
        stage_call_id="stage-001",
        output={"structured_brief": {"topic": "A2 奶粉"}},
        stats={"duration_ms": 10},
        ack_at=None,
    )
    assert http_client.calls[0]["url"] == "https://executor.example.com/invoke"
    assert http_client.calls[0]["headers"]["X-Maga-Protocol-Version"] == "0.1"


@pytest.mark.asyncio
async def test_invoke_async_202_returns_ack():
    http_client = FakeAsyncClient(FakeResponse(202, {"stage_call_id": "stage-002", "ack_at": "2026-05-08T12:00:00Z"}))
    client = ExecutorInvocationClient(http_client=http_client)

    result = await client.invoke(
        invoke_url="https://executor.example.com/invoke",
        envelope={"stage_call_id": "stage-002", "capability": "xhs.generate_draft"},
    )

    assert result.mode == "async"
    assert result.stage_call_id == "stage-002"
    assert result.ack_at == "2026-05-08T12:00:00Z"
    assert result.output is None


@pytest.mark.asyncio
async def test_invoke_raises_on_unexpected_status():
    http_client = FakeAsyncClient(FakeResponse(500, {"error": "boom"}))
    client = ExecutorInvocationClient(http_client=http_client)

    with pytest.raises(RuntimeError, match="Executor invoke failed"):
        await client.invoke(
            invoke_url="https://executor.example.com/invoke",
            envelope={"stage_call_id": "stage-003"},
        )
