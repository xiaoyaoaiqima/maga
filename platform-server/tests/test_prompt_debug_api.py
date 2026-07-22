"""API tests for the raw prompt debug workbench."""

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

SERVER_ROOT = Path(__file__).resolve().parents[1]
os.chdir(SERVER_ROOT)
sys.path.insert(0, str(SERVER_ROOT))

from app.api.v1.endpoints import content_agent
from app.core.database import get_db
from app.services.executor_invocation_service import DirectLLMCallResult


class _FakePromptDebugDb:
    def __init__(self):
        self.records = []

    def add(self, record):
        record.id = len(self.records) + 1
        self.records.append(record)

    async def flush(self):
        return None


def _prompt_debug_app(db=None) -> FastAPI:
    app = FastAPI()
    app.include_router(content_agent.router, prefix="/api/v1/content-agent")
    fake_db = db or _FakePromptDebugDb()

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.state.prompt_debug_db = fake_db
    return app


@pytest.mark.asyncio
async def test_prompt_debug_run_returns_raw_llm_output(monkeypatch):
    async def fake_model_config(_db, *, model_code):
        assert model_code == "deepseek-v4-flash"
        return {
            "model_code": "deepseek-v4-flash",
            "provider_code": "deepseek",
        }

    async def fake_call_direct_llm(**kwargs):
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 80
        assert kwargs["system_prompt"] == "只输出正文"
        assert kwargs["user_prompt"] == "写一条评论"
        assert kwargs["model_config"]["provider_code"] == "deepseek"
        return DirectLLMCallResult(
            content="我也刷到有货了，先拍两罐",
            model_code="deepseek-v4-flash",
            provider_code="deepseek",
            provider_model="deepseek-v4-flash",
            usage={
                "input_tokens": 12,
                "output_tokens": 16,
                "total_tokens": 28,
            },
            latency_ms=321,
        )

    monkeypatch.setattr(content_agent, "_prompt_debug_model_config", fake_model_config)
    monkeypatch.setattr(content_agent, "call_direct_llm", fake_call_direct_llm)

    app = _prompt_debug_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/content-agent/prompt-debug/run",
            json={
                "prompt": " 写一条评论 ",
                "system_prompt": " 只输出正文 ",
                "model_code": "deepseek-v4-flash",
                "temperature": 0.3,
                "max_tokens": 80,
                "run_group_id": "group-success",
                "workbench_mode": "compare",
                "panel_key": "right",
                "item_index": 2,
                "batch_size": 3,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"] == {
        "success": True,
        "content": "我也刷到有货了，先拍两罐",
        "model_code": "deepseek-v4-flash",
        "provider_code": "deepseek",
        "provider_model": "deepseek-v4-flash",
        "usage": {
            "input_tokens": 12,
            "output_tokens": 16,
            "total_tokens": 28,
        },
        "latency_ms": 321,
        "error_message": None,
        "history_id": 1,
        "run_group_id": "group-success",
    }
    history = app.state.prompt_debug_db.records[0]
    assert history.run_group_id == "group-success"
    assert history.workbench_mode == "compare"
    assert history.panel_key == "right"
    assert history.item_index == 2
    assert history.batch_size == 3
    assert history.prompt == "写一条评论"
    assert history.system_prompt == "只输出正文"
    assert history.success is True
    assert history.content == "我也刷到有货了，先拍两罐"
    assert history.token_usage["total_tokens"] == 28


@pytest.mark.asyncio
async def test_prompt_debug_run_returns_readable_model_error(monkeypatch):
    async def fake_model_config(_db, *, model_code):
        return {"model_code": model_code}

    async def fake_call_direct_llm(**kwargs):
        assert kwargs["temperature"] == 0.9
        assert kwargs["max_tokens"] == 1500
        raise RuntimeError("未配置 API Key，无法调用模型")

    monkeypatch.setattr(content_agent, "_prompt_debug_model_config", fake_model_config)
    monkeypatch.setattr(content_agent, "call_direct_llm", fake_call_direct_llm)

    app = _prompt_debug_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/content-agent/prompt-debug/run",
            json={
                "prompt": "写一条评论",
                "model_code": "deepseek-v4-flash",
                "run_group_id": "group-failed",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Prompt 调试失败"
    assert payload["data"]["success"] is False
    assert payload["data"]["model_code"] == "deepseek-v4-flash"
    assert payload["data"]["error_message"] == "未配置 API Key，无法调用模型"
    assert payload["data"]["history_id"] == 1
    assert payload["data"]["run_group_id"] == "group-failed"
    history = app.state.prompt_debug_db.records[0]
    assert history.success is False
    assert history.temperature == 0.9
    assert history.error_message == "未配置 API Key，无法调用模型"


@pytest.mark.asyncio
async def test_prompt_debug_run_rejects_blank_prompt_and_model():
    app = _prompt_debug_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/content-agent/prompt-debug/run",
            json={"prompt": " ", "model_code": " "},
        )

    assert response.status_code == 422
