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


@pytest.mark.asyncio
async def test_prompt_debug_run_returns_raw_llm_output(monkeypatch):
    async def fake_invoke_llm(**kwargs):
        assert kwargs["model_code"] == "deepseek-v4-flash"
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 80
        assert kwargs["messages"] == [
            {"role": "system", "content": "只输出正文"},
            {"role": "user", "content": "写一条评论"},
        ]
        return {
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
        }

    monkeypatch.setattr(content_agent, "invoke_llm", fake_invoke_llm)

    app = FastAPI()
    app.include_router(content_agent.router, prefix="/api/v1/content-agent")
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
    }


@pytest.mark.asyncio
async def test_prompt_debug_run_returns_readable_model_error(monkeypatch):
    async def fake_invoke_llm(**_kwargs):
        raise RuntimeError("未配置 API Key，无法调用模型")

    monkeypatch.setattr(content_agent, "invoke_llm", fake_invoke_llm)

    app = FastAPI()
    app.include_router(content_agent.router, prefix="/api/v1/content-agent")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/content-agent/prompt-debug/run",
            json={
                "prompt": "写一条评论",
                "model_code": "deepseek-v4-flash",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Prompt 调试失败"
    assert payload["data"]["success"] is False
    assert payload["data"]["model_code"] == "deepseek-v4-flash"
    assert payload["data"]["error_message"] == "未配置 API Key，无法调用模型"


@pytest.mark.asyncio
async def test_prompt_debug_run_rejects_blank_prompt_and_model():
    app = FastAPI()
    app.include_router(content_agent.router, prefix="/api/v1/content-agent")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/content-agent/prompt-debug/run",
            json={"prompt": " ", "model_code": " "},
        )

    assert response.status_code == 422
