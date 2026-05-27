"""Tests for template-variable corpus APIs."""
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.models.base import Base
from app.models.graph import GraphNode
from app.modules.keyword_corpus.endpoints.template_variable_corpus import router
from app.services.template_variable_corpus_service import TemplateVariableCorpusService


@pytest_asyncio.fixture
async def corpus_client(tmp_path, monkeypatch):
    template_path = tmp_path / "生文提示词模版.md"
    template_path.write_text("{{人设}}\n\n{{痛点}}\n\n{{表达写作规则}}", encoding="utf-8")
    monkeypatch.setattr(
        TemplateVariableCorpusService,
        "__init__",
        lambda self, db, template_path_arg=None: setattr(self, "db", db)
        or setattr(self, "template_path", template_path),
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[GraphNode.__table__])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/keyword-corpus")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await engine.dispose()


@pytest.mark.asyncio
async def test_template_variables_are_parsed_from_prompt_template(corpus_client):
    response = await corpus_client.get("/api/v1/keyword-corpus/template-variable-corpus/variables")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["name"] for item in data["variables"]] == ["人设", "痛点", "表达写作规则"]
    assert data["variables"][0]["corpus_count"] == 0


@pytest.mark.asyncio
async def test_create_list_update_archive_template_variable_corpus(corpus_client):
    create_response = await corpus_client.post(
        "/api/v1/keyword-corpus/template-variable-corpus",
        json={
            "variable_name": "痛点",
            "name": "便便观察",
            "markdown": "- 妈妈每天会观察便便状态",
            "tags": ["转奶"],
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["variable_name"] == "痛点"
    assert created["markdown"] == "- 妈妈每天会观察便便状态"

    list_response = await corpus_client.get(
        "/api/v1/keyword-corpus/template-variable-corpus",
        params={"variable_name": "痛点"},
    )
    assert list_response.status_code == 200
    listed = list_response.json()["data"]
    assert listed["page_info"]["total"] == 1
    assert listed["items"][0]["tags"] == ["转奶"]

    update_response = await corpus_client.put(
        f"/api/v1/keyword-corpus/template-variable-corpus/{created['id']}",
        json={"name": "便便状态观察", "status": "draft", "markdown": "普通 Markdown 文本"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["status"] == "draft"

    delete_response = await corpus_client.delete(
        f"/api/v1/keyword-corpus/template-variable-corpus/{created['id']}"
    )
    assert delete_response.status_code == 200

    archived_list_response = await corpus_client.get(
        "/api/v1/keyword-corpus/template-variable-corpus",
        params={"status": "archived"},
    )
    assert archived_list_response.status_code == 200
    assert archived_list_response.json()["data"]["items"][0]["status"] == "archived"


@pytest.mark.asyncio
async def test_preview_prompt_renders_selected_and_draft_values(corpus_client):
    create_response = await corpus_client.post(
        "/api/v1/keyword-corpus/template-variable-corpus",
        json={
            "variable_name": "痛点",
            "name": "肠胃敏感",
            "markdown": "宝宝转奶期肚肚容易不舒服",
        },
    )
    item_id = create_response.json()["data"]["id"]

    preview_response = await corpus_client.post(
        "/api/v1/keyword-corpus/template-variable-corpus/preview",
        json={
            "selected_item_ids": {"痛点": item_id},
            "draft_values": {"人设": "新手妈妈第一人称"},
            "missing_policy": "keep_placeholder",
        },
    )

    assert preview_response.status_code == 200
    data = preview_response.json()["data"]
    assert "新手妈妈第一人称" in data["rendered_prompt"]
    assert "宝宝转奶期肚肚容易不舒服" in data["rendered_prompt"]
    assert "{{表达写作规则}}" in data["rendered_prompt"]
    assert data["missing_variables"] == ["表达写作规则"]
