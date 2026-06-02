"""MVP-aligned protocol tests for MAGA -> Executor sync invocation."""

import pytest

from app.services.executor_invocation_service import (
    ExecutorInvocationClient,
    InvokeResult,
    MockExecutorInvocationClient,
    build_invoke_envelope,
)


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
async def test_mvp_invoke_envelope_excludes_transition_callback_urls_and_run_token():
    envelope = build_invoke_envelope(
        run_id=10,
        task_id=20,
        stage_call_id="stage-001",
        capability="content.generate",
        schema_version="1",
        run_token="rt-001",
        input_payload={"content_type": "article", "rendered_prompt": "生成内容"},
        callback_base_url="https://maga.example.com/api/v1/content-agent",
        deadline_at=None,
    )

    assert envelope["protocol_version"] == "0.1"
    assert envelope["run_id"] == 10
    assert envelope["task_id"] == 20
    assert envelope["stage_call_id"] == "stage-001"
    assert envelope["capability"] == "content.generate"
    assert envelope["input"] == {"content_type": "article", "rendered_prompt": "生成内容"}
    assert set(envelope["callback"]) == {"events_url", "artifacts_url", "human_review_url"}
    assert "complete_url" not in envelope["callback"]
    assert "fail_url" not in envelope["callback"]
    assert "run_token" not in envelope
    assert envelope["executor_hints"]["timeout_seconds"] == 60


@pytest.mark.asyncio
async def test_mvp_invoke_sync_200_returns_succeeded_output_envelope():
    http_client = FakeAsyncClient(
        FakeResponse(
            200,
            {
                "stage_call_id": "stage-001",
                "status": "succeeded",
                "output": {"content": {"topic": "美素佳儿源悦"}},
                "stats": {"total_latency_ms": 10},
            },
        )
    )
    client = ExecutorInvocationClient(http_client=http_client)

    result = await client.invoke(
        invoke_url="https://executor.example.com/invoke",
        envelope={"stage_call_id": "stage-001", "capability": "content.generate"},
        executor_token="test-token",
    )

    assert result == InvokeResult(
        mode="sync",
        stage_call_id="stage-001",
        status="succeeded",
        output={"content": {"topic": "美素佳儿源悦"}},
        stats={"total_latency_ms": 10},
        error_code=None,
        error_message=None,
    )
    assert http_client.calls[0]["headers"] == {
        "X-Maga-Protocol-Version": "0.1",
        "Authorization": "Bearer test-token",
    }
    assert http_client.calls[0]["timeout"] == 180.0


@pytest.mark.asyncio
async def test_executor_invoke_timeout_can_be_configured(monkeypatch):
    monkeypatch.setenv("MAGA_EXECUTOR_INVOKE_TIMEOUT_SECONDS", "240")
    http_client = FakeAsyncClient(
        FakeResponse(
            200,
            {"stage_call_id": "stage-timeout", "status": "succeeded", "output": {}, "stats": {}},
        )
    )
    client = ExecutorInvocationClient(http_client=http_client)

    await client.invoke(
        invoke_url="https://executor.example.com/invoke",
        envelope={"stage_call_id": "stage-timeout", "capability": "content.generate"},
    )

    assert http_client.calls[0]["timeout"] == 240.0


@pytest.mark.asyncio
async def test_mvp_invoke_omits_authorization_header_when_token_is_absent():
    http_client = FakeAsyncClient(
        FakeResponse(
            200,
            {"stage_call_id": "stage-no-token", "status": "succeeded", "output": {}, "stats": {}},
        )
    )
    client = ExecutorInvocationClient(http_client=http_client)

    await client.invoke(
        invoke_url="https://executor.example.com/invoke",
        envelope={"stage_call_id": "stage-no-token", "capability": "content.generate"},
    )

    assert http_client.calls[0]["headers"] == {"X-Maga-Protocol-Version": "0.1"}


@pytest.mark.asyncio
async def test_mvp_invoke_sync_200_can_return_failed_output_envelope():
    http_client = FakeAsyncClient(
        FakeResponse(
            200,
            {
                "stage_call_id": "stage-002",
                "status": "failed",
                "error_code": "model_error",
                "error_message": "provider 5xx",
            },
        )
    )
    client = ExecutorInvocationClient(http_client=http_client)

    result = await client.invoke(
        invoke_url="https://executor.example.com/invoke",
        envelope={"stage_call_id": "stage-002", "capability": "content.generate"},
    )

    assert result.mode == "sync"
    assert result.status == "failed"
    assert result.error_code == "model_error"
    assert result.error_message == "provider 5xx"
    assert result.output is None


@pytest.mark.asyncio
async def test_mvp_invoke_rejects_async_202_ack():
    http_client = FakeAsyncClient(FakeResponse(202, {"stage_call_id": "stage-003", "ack_at": "2026-05-08T12:00:00Z"}))
    client = ExecutorInvocationClient(http_client=http_client)

    with pytest.raises(RuntimeError, match="MVP protocol requires sync"):
        await client.invoke(
            invoke_url="https://executor.example.com/invoke",
            envelope={"stage_call_id": "stage-003", "capability": "content.generate"},
        )


@pytest.mark.asyncio
async def test_invoke_raises_on_unexpected_status():
    http_client = FakeAsyncClient(FakeResponse(500, {"error": "boom"}))
    client = ExecutorInvocationClient(http_client=http_client)

    with pytest.raises(RuntimeError, match="Executor invoke failed"):
        await client.invoke(
            invoke_url="https://executor.example.com/invoke",
            envelope={"stage_call_id": "stage-004"},
        )


@pytest.mark.asyncio
async def test_mock_executor_supports_asset_import_for_local_asset_smoke():
    client = MockExecutorInvocationClient()
    result = await client.invoke(
        invoke_url="mock://maga-worker/invoke",
        envelope={
            "stage_call_id": "asset-import-mock",
            "capability": "asset.import",
            "input": {"asset_key": "yuanyue", "source_hash": "hash-001"},
        },
    )

    assert result.status == "succeeded"
    assert result.output["asset_key"] == "yuanyue"
    assert result.output["source_hash"] == "hash-001"
    assert {asset["asset_type"] for asset in result.output["assets"]} >= {
        "brand_profile",
        "painpoint_model",
        "product_selling_points",
        "ugc_expression_corpus",
    }
