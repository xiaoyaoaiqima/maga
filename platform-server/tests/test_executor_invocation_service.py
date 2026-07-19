"""MVP-aligned protocol tests for MAGA -> Executor sync invocation."""

import pytest

from app.services.executor_invocation_service import (
    DirectLLMCallResult,
    ExecutorInvocationClient,
    InvokeResult,
    MockExecutorInvocationClient,
    build_invoke_envelope,
    _normalize_unified_content_output,
)
from app.utils.model_config import ensure_chat_completions_endpoint


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


def test_openai_compatible_v1_base_url_appends_chat_completions_once():
    assert ensure_chat_completions_endpoint("https://aihubmix.com/v1") == "https://aihubmix.com/v1/chat/completions"


def test_normalize_article_output_accepts_items_json_and_strips_topic_tags():
    output = _normalize_unified_content_output(
        """
        {
          "items": [
            {"title": "肚子响少了#儿童奶粉[话题]#", "body": "旺玥喝了一周，肚子响少了。#旺玥#"},
            {"title": "精神好些", "body": "娃晚上还在客厅玩。 #儿童成长"}
          ]
        }
        """,
        {"content_type": "article", "output_fields": ["title", "body"]},
    )

    assert output["title"] == "肚子响少了"
    assert output["body"] == "旺玥喝了一周，肚子响少了。"
    assert output["items"] == [
        {"title": "肚子响少了", "body": "旺玥喝了一周，肚子响少了。"},
        {"title": "精神好些", "body": "娃晚上还在客厅玩。"},
    ]


def test_normalize_article_output_accepts_top_level_array():
    output = _normalize_unified_content_output(
        """
        [
          {"title": "第一篇#旺玥#", "body": "孩子喝着还顺，饭量也稳。"},
          {"title": "第二篇", "body": "放学回来精神头还挺足。"}
        ]
        """,
        {"content_type": "article", "output_fields": ["title", "body"]},
    )

    assert output["items"] == [
        {"title": "第一篇", "body": "孩子喝着还顺，饭量也稳。"},
        {"title": "第二篇", "body": "放学回来精神头还挺足。"},
    ]


def test_normalize_article_output_accepts_stringified_items():
    output = _normalize_unified_content_output(
        '{"items":"[{\\"title\\":\\"第一篇\\",\\"body\\":\\"正文一\\"},{\\"title\\":\\"第二篇\\",\\"body\\":\\"正文二\\"}]"}',
        {"content_type": "article", "output_fields": ["title", "body"]},
    )

    assert output["items"] == [
        {"title": "第一篇", "body": "正文一"},
        {"title": "第二篇", "body": "正文二"},
    ]


def test_normalize_article_output_accepts_items_json_nested_in_body():
    output = _normalize_unified_content_output(
        '{"title":"今天这点变化","body":"{\\"items\\":[{\\"title\\":\\"喝旺玥一个月\\",\\"body\\":\\"饭量稳了。\\"},{\\"title\\":\\"又开一罐\\",\\"body\\":\\"这次继续喝。\\"}]}"}',
        {"content_type": "article", "output_fields": ["title", "body"]},
    )

    assert output["items"] == [
        {"title": "喝旺玥一个月", "body": "饭量稳了。"},
        {"title": "又开一罐", "body": "这次继续喝。"},
    ]


def test_normalize_article_output_repairs_nested_body_items_missing_outer_brace():
    output = _normalize_unified_content_output(
        '{"title":"今天这点变化","body":"{\\"items\\":[{\\"title\\":\\"挑了一圈\\",\\"body\\":\\"最后选了旺玥。\\"},{\\"title\\":\\"每天一杯\\",\\"body\\":\\"冲杯奶粉就好。\\"}]"}',
        {"content_type": "article", "output_fields": ["title", "body"]},
    )

    assert output["items"] == [
        {"title": "挑了一圈", "body": "最后选了旺玥。"},
        {"title": "每天一杯", "body": "冲杯奶粉就好。"},
    ]


def test_normalize_article_output_keeps_single_article_contract():
    output = _normalize_unified_content_output(
        '{"title":"标题#话题#","body":"正文内容 #收尾话题"}',
        {"content_type": "article", "output_fields": ["title", "body"]},
    )

    assert output == {"title": "标题", "body": "正文内容"}


def test_normalize_article_output_rejects_truncated_json_with_replacement_character():
    with pytest.raises(ValueError, match="malformed JSON"):
        _normalize_unified_content_output(
            '{"title":"妈妈群分享","body":"今天看到一条信息，说�',
            {"content_type": "article", "output_fields": ["title", "body"]},
        )


def test_normalize_comment_output_accepts_json_string_array_mode():
    output = _normalize_unified_content_output(
        '["a2终于到货了", "我也买到了新货"]',
        {
            "content_type": "comment",
            "output_fields": ["comment"],
            "output_format_mode": "json_string_array",
        },
    )

    assert output["comment"] == "a2终于到货了"
    assert output["comments"] == ["a2终于到货了", "我也买到了新货"]
    assert output["items"] == [{"comment": "a2终于到货了"}, {"comment": "我也买到了新货"}]


def test_normalize_comment_output_accepts_json_object_array_mode():
    output = _normalize_unified_content_output(
        '[{"内容":"报告能扫出来"}, {"comment":"礼盒里的东西挺实在"}]',
        {
            "content_type": "comment",
            "output_fields": ["comment"],
            "output_format": {"mode": "json_object_array", "count": 2},
        },
    )

    assert output["comment"] == "报告能扫出来"
    assert output["comments"] == ["报告能扫出来", "礼盒里的东西挺实在"]


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


@pytest.mark.asyncio
async def test_direct_llm_invoke_generates_comment_without_http_worker(monkeypatch):
    calls = []

    async def fake_call(**kwargs):
        calls.append(kwargs)
        return "```text\n1. 评论：最近娃精神头好多了。\n```"

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    http_client = FakeAsyncClient(FakeResponse(500, {"unexpected": "http worker should not be called"}))
    client = ExecutorInvocationClient(http_client=http_client)

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-comment",
            "capability": "content.generate",
            "input": {
                "content_type": "comment",
                "output_fields": ["comment"],
                "rendered_prompt": "生成一条评论",
                "model_config": {"model_code": "deepseek-v4-flash", "temperature": 0.8},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["comment"] == "最近娃精神头好多了。"
    assert result.output["runtime_result"]["mode"] == "direct_llm_content_runtime"
    assert result.output["runtime_result"]["model_attempts"] == 1
    assert result.stats["adapter"] == "platform_server.direct_llm"
    assert calls[0]["model"] == "deepseek-v4-flash"
    assert http_client.calls == []


@pytest.mark.asyncio
async def test_direct_llm_generate_parses_article_json(monkeypatch):
    async def fake_call(**kwargs):
        return '{"title":"真实体验标题","body":"这是正文。"}'

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient(http_client=FakeAsyncClient(FakeResponse(500, {})))

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-json",
            "capability": "content.generate",
            "input": {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "rendered_prompt": "生成一篇文章",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["title"] == "真实体验标题"
    assert result.output["body"] == "这是正文。"


@pytest.mark.asyncio
async def test_direct_llm_generate_records_finish_reason_and_usage(monkeypatch):
    async def fake_call(**kwargs):
        return DirectLLMCallResult(
            content='{"title":"真实标题","body":"真实正文。"}',
            model_code="deepseek-v4-flash",
            provider_code="aihubmix",
            provider_model="deepseek-v4-flash",
            usage={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
            latency_ms=100,
            finish_reason="stop",
        )

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-metadata",
            "capability": "content.generate",
            "input": {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "rendered_prompt": "生成一篇文章",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.output["runtime_result"]["finish_reason"] == "stop"
    assert result.output["runtime_result"]["usage"] == {
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 150,
    }


@pytest.mark.asyncio
async def test_direct_llm_generate_flattens_nested_article_json_body(monkeypatch):
    async def fake_call(**kwargs):
        return '{"title":"外层标题","body":"{\\"title\\":\\"内层标题\\",\\"body\\":\\"内层正文。\\"}"}'

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-nested-json-body",
            "capability": "content.generate",
            "input": {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "rendered_prompt": "生成一篇文章",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["title"] == "内层标题"
    assert result.output["body"] == "内层正文。"


@pytest.mark.asyncio
async def test_direct_llm_generate_repairs_loose_article_json(monkeypatch):
    async def fake_call(**kwargs):
        return '{\n"title": "有姐妹一起转a2吗？刚补了一罐试试🧐",\n"body": "家里奶粉快见底了。\\n\\n到货后扫了罐底码，报告能看到。"\n'

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-loose-json",
            "capability": "content.generate",
            "input": {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "rendered_prompt": "生成一篇文章",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["title"] == "有姐妹一起转a2吗？刚补了一罐试试🧐"
    assert result.output["body"] == "家里奶粉快见底了。\n\n到货后扫了罐底码，报告能看到。"


@pytest.mark.asyncio
async def test_direct_llm_generate_parses_article_plain_text(monkeypatch):
    async def fake_call(**kwargs):
        return "自然标题\n正文第一段\n正文第二段"

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-plain",
            "capability": "content.generate",
            "input": {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "rendered_prompt": "生成一篇文章",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["title"] == "自然标题"
    assert result.output["body"] == "正文第一段\n正文第二段"


@pytest.mark.asyncio
async def test_direct_llm_generate_retries_empty_normalized_output(monkeypatch):
    calls = []

    async def fake_call(**kwargs):
        calls.append(kwargs)
        return "" if len(calls) == 1 else "评论：第二次有内容"

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-empty-retry",
            "capability": "content.generate",
            "input": {
                "content_type": "comment",
                "output_fields": ["comment"],
                "rendered_prompt": "生成一条评论",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["comment"] == "第二次有内容"
    assert result.output["runtime_result"]["model_attempts"] == 2
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_direct_llm_generate_retries_malformed_article_json(monkeypatch):
    calls = []

    async def fake_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return '{"title":"半截标题","body":"半截正文�'
        return '{"title":"完整标题","body":"完整正文。"}'

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-malformed-retry",
            "capability": "content.generate",
            "input": {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "rendered_prompt": "生成一篇文章",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["title"] == "完整标题"
    assert result.output["body"] == "完整正文。"
    assert result.output["runtime_result"]["model_attempts"] == 2
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_direct_llm_generate_keeps_explicit_empty_result_after_retries(monkeypatch):
    async def fake_call(**kwargs):
        return ""

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-empty-final",
            "capability": "content.generate",
            "input": {
                "content_type": "comment",
                "output_fields": ["comment"],
                "rendered_prompt": "生成一条评论",
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["comment"] == ""
    assert result.output["runtime_result"]["empty_output"] is True
    assert result.output["runtime_result"]["empty_reason"] == "content.generate produced empty comment"
    assert result.output["runtime_result"]["model_attempts"] == 2


@pytest.mark.asyncio
async def test_direct_llm_rewrite_cleans_comment_output(monkeypatch):
    async def fake_call(**kwargs):
        return '{"comment":"改好后的评论"}'

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-rewrite",
            "capability": "content.rewrite",
            "input": {
                "content_type": "comment",
                "output_fields": ["comment"],
                "previous_content": {"comment": "原评论"},
                "forbidden_hits": ["绝对"],
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["comment"] == "改好后的评论"
    assert result.output["runtime_result"]["mode"] == "direct_llm_content_rewrite_runtime"
    assert result.output["runtime_result"]["forbidden_hits"] == ["绝对"]


@pytest.mark.asyncio
async def test_direct_llm_rewrite_retries_empty_output(monkeypatch):
    calls = []

    async def fake_call(**kwargs):
        calls.append(kwargs)
        return "" if len(calls) == 1 else '{"title":"新标题","body":"新正文"}'

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-rewrite-retry",
            "capability": "content.rewrite",
            "input": {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "previous_content": {"title": "旧标题", "body": "旧正文"},
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["title"] == "新标题"
    assert result.output["body"] == "新正文"
    assert result.output["runtime_result"]["model_attempts"] == 2


@pytest.mark.asyncio
async def test_direct_llm_rewrite_flattens_nested_article_json_body(monkeypatch):
    async def fake_call(**kwargs):
        return '{"title":"外层标题","body":"{\\"title\\":\\"改后标题\\",\\"body\\":\\"改后正文。\\"}"}'

    monkeypatch.setattr("app.services.executor_invocation_service._call_openai_compatible_model", fake_call)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-rewrite-nested-json-body",
            "capability": "content.rewrite",
            "input": {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "previous_content": {"title": "旧标题", "body": "旧正文"},
                "model_config": {"model_code": "deepseek-v4-flash"},
            },
        },
    )

    assert result.status == "succeeded"
    assert result.output["title"] == "改后标题"
    assert result.output["body"] == "改后正文。"


@pytest.mark.asyncio
async def test_direct_llm_returns_clear_error_when_api_key_missing(monkeypatch):
    for key in ["MAGA_DIRECT_MODEL_API_KEY", "DEEPSEEK_API_KEY", "AIHUBMIX_API_KEY", "OPENAI_API_KEY", "ARK_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    client = ExecutorInvocationClient()

    result = await client.invoke(
        invoke_url="llm://direct/content",
        envelope={
            "stage_call_id": "stage-direct-missing-key",
            "capability": "content.generate",
            "input": {
                "content_type": "comment",
                "output_fields": ["comment"],
                "rendered_prompt": "生成一条评论",
                "model_config": {"model_code": "deepseek-v4-flash", "base_url": "https://provider.example/v1"},
            },
        },
    )

    assert result.status == "failed"
    assert result.error_code == "direct_llm_error"
    assert "缺少 API Key" in result.error_message
