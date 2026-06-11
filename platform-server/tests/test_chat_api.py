"""API tests for realtime Chat."""

import json
import sys
from pathlib import Path
import os

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

SERVER_ROOT = Path(__file__).resolve().parents[1]
os.chdir(SERVER_ROOT)
sys.path.insert(0, str(SERVER_ROOT))

from app.api.v1.endpoints.chat import router
from app.core.database import get_db
from app.models.agent import Agent
from app.models.base import Base
from app.models.llm_model_route import LLMModelRoute
from app.models.llm_provider_config import LLMProviderConfig
from app.services.llm_factory import LLMFactory


@pytest_asyncio.fixture
async def chat_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Agent.__table__, LLMModelRoute.__table__, LLMProviderConfig.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def fake_call_llm(config, system_prompt, user_prompt, **kwargs):
        assert config["model"] == "deepseek-v4-flash"
        assert system_prompt == "你是测试聊天 Agent"
        assert "用户: 上一轮问题" in user_prompt
        assert "用户: 继续说" in user_prompt
        return "测试回复"

    monkeypatch.setattr(LLMFactory, "call_llm", fake_call_llm)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_send_chat_message_uses_enabled_realtime_agent(chat_client):
    client, session_factory = chat_client
    async with session_factory() as session:
        session.add_all(
            [
                Agent(
                    id=1,
                    agent_code="batch-agent",
                    agent_name="批量 Agent",
                    agent_type="BATCH_GENERATION",
                    expert_config_code_list=[],
                    default_model_code="ignored-model",
                    enabled=1,
                    is_deleted=0,
                ),
                Agent(
                    id=2,
                    agent_code="chat-agent",
                    agent_name="实时聊天 Agent",
                    agent_type="REALTIME_CHAT",
                    expert_config_code_list=[],
                    default_model_code="deepseek-v4-flash",
                    default_config={"system_prompt": "你是测试聊天 Agent"},
                    enabled=1,
                    is_deleted=0,
                ),
            ]
        )
        await session.commit()

    response = await client.post(
        "/api/v1/chat/messages",
        json={
            "message": "继续说",
            "history": [{"role": "user", "content": "上一轮问题"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"] == {
        "agent_code": "chat-agent",
        "agent_name": "实时聊天 Agent",
        "reply": "测试回复",
        "actions": [],
    }


@pytest.mark.asyncio
async def test_send_chat_message_without_agent_returns_business_error(chat_client):
    client, _session_factory = chat_client

    response = await client.post(
        "/api/v1/chat/messages",
        json={"message": "你好", "history": []},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "未配置实时聊天 Agent"


@pytest.mark.asyncio
async def test_send_chat_message_model_error_returns_bad_gateway(chat_client, monkeypatch):
    client, session_factory = chat_client

    async def fail_call_llm(*_args, **_kwargs):
        raise RuntimeError("未配置 API Key，无法调用模型")

    monkeypatch.setattr(LLMFactory, "call_llm", fail_call_llm)
    async with session_factory() as session:
        session.add(
            Agent(
                id=1,
                agent_code="chat-agent",
                agent_name="实时聊天 Agent",
                agent_type="REALTIME_CHAT",
                expert_config_code_list=[],
                default_model_code="deepseek-v4-flash",
                enabled=1,
                is_deleted=0,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/chat/messages",
        json={"message": "你好", "history": []},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "未配置 API Key，无法调用模型"


@pytest.mark.asyncio
async def test_send_chat_message_rejects_invalid_history_role(chat_client):
    client, _session_factory = chat_client

    response = await client.post(
        "/api/v1/chat/messages",
        json={
            "message": "你好",
            "history": [{"role": "system", "content": "不可接受"}],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_chat_message_rejects_blank_message(chat_client):
    client, _session_factory = chat_client

    response = await client.post(
        "/api/v1/chat/messages",
        json={"message": "   ", "history": []},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_comment_angle_context_injects_by_case_prompt_and_allows_fill_action(chat_client, monkeypatch):
    client, session_factory = chat_client
    captured = {}

    async def fake_call_llm(config, system_prompt, user_prompt, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        actions = {
            "actions": [
                {
                    "type": "fill_comment_angle_draft",
                    "label": "填入草稿",
                    "payload": {
                        "draft_corpus": "子方向标题：\n\n像真实评论。\n\n示例：\n- 有同款吗\n\n注意：示例只作为语义素材，不是正文原句。"
                    },
                },
                {"type": "publish_rule", "payload": {"draft_id": 1}},
            ],
        }
        return f"这条规则偏硬，我给你一版更松的草稿。\n```json\n{json.dumps(actions, ensure_ascii=False)}\n```"

    monkeypatch.setattr(LLMFactory, "call_llm", fake_call_llm)
    async with session_factory() as session:
        session.add(
            Agent(
                id=1,
                agent_code="chat-agent",
                agent_name="实时聊天 Agent",
                agent_type="REALTIME_CHAT",
                expert_config_code_list=[],
                default_model_code="deepseek-v4-flash",
                default_config={"system_prompt": "你是测试聊天 Agent"},
                enabled=1,
                is_deleted=0,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/chat/messages",
        json={
            "message": "这条太硬了，帮我改真人一点",
            "history": [],
            "context": {
                "page": "business_rules",
                "asset_key": "a2_sentiment_comment_activity",
                "asset_type": "comment_angle_rule_set",
                "asset_version": 3,
                "rule_id": "comment_angle_001",
                "source_row_no": 16,
                "comment_angle": "剧情讨论",
                "corpus": "正式语料",
                "draft_corpus": "草稿语料",
                "examples": ["旧示例"],
                "supplements": ["旧补充"],
                "test_report_summary": {
                    "batch_id": 12,
                    "generated_count": 8,
                    "failed_count": 2,
                    "risk_count": 1,
                    "samples": [{"item_no": 1, "body": "生成正文", "risks": ["疑似趋同"]}],
                },
            },
        },
    )

    assert response.status_code == 200
    assert "评论切角 by-case 语料副驾" in captured["system_prompt"]
    assert "用户正在要求放松或修正 AI 味/同质化" in captured["system_prompt"]
    assert "asset_key: a2_sentiment_comment_activity" in captured["user_prompt"]
    assert "rule_id: comment_angle_001" in captured["user_prompt"]
    assert "source_row_no: 16" in captured["user_prompt"]
    assert "正式语料" in captured["user_prompt"]
    assert "旧示例" in captured["user_prompt"]
    assert "生成正文" in captured["user_prompt"]
    payload = response.json()["data"]
    assert payload["reply"] == "这条规则偏硬，我给你一版更松的草稿。"
    assert payload["actions"] == [
        {
            "type": "fill_comment_angle_draft",
            "label": "填入草稿",
            "payload": {
                "draft_corpus": "子方向标题：\n\n像真实评论。\n\n示例：\n- 有同款吗\n\n注意：示例只作为语义素材，不是正文原句。",
                "rule_id": "comment_angle_001",
                "source_row_no": 16,
            },
        }
    ]


@pytest.mark.asyncio
async def test_non_business_rule_context_drops_fill_action(chat_client, monkeypatch):
    client, session_factory = chat_client

    async def fake_call_llm(*_args, **_kwargs):
        return json.dumps({
            "reply": "普通回答",
            "actions": [
                {
                    "type": "fill_comment_angle_draft",
                    "payload": {"draft_corpus": "不应该返回"},
                }
            ],
        }, ensure_ascii=False)

    monkeypatch.setattr(LLMFactory, "call_llm", fake_call_llm)
    async with session_factory() as session:
        session.add(
            Agent(
                id=1,
                agent_code="chat-agent",
                agent_name="实时聊天 Agent",
                agent_type="REALTIME_CHAT",
                expert_config_code_list=[],
                default_model_code="deepseek-v4-flash",
                enabled=1,
                is_deleted=0,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/chat/messages",
        json={
            "message": "你好",
            "history": [],
            "context": {"page": "dashboard", "asset_type": "comment_angle_rule_set"},
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["reply"] == "普通回答"
    assert payload["actions"] == []
