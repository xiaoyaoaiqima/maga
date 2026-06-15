"""Tests for business forbidden-term ledger entries."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import content_generation_experts
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import ContentBatchItem
from app.models.maga_assets import AssetRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.services.business_forbidden_term_service import (
    A2_SENTIMENT_COMMENT_ASSET_KEY,
    BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
    BusinessForbiddenTermService,
)
from app.services.content_agent_bootstrap_service import seed_a2_sentiment_comment_forbidden_terms
from app.services.forbidden_term_review_service import ForbiddenTermReviewService


@pytest_asyncio.fixture
async def forbidden_term_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_business_forbidden_terms_keep_legacy_string_terms(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                asset_key="legacy_comment_activity",
                display_name="旧格式业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={"schema_version": "1", "terms": ["源悦"]},
            )
        )
        await session.commit()

        service = BusinessForbiddenTermService(session)
        assert await service.list_terms(asset_key="legacy_comment_activity", include_default=False) == ["源悦"]
        entries = await service.list_entries(asset_key="legacy_comment_activity", include_default=False)

    assert entries[0]["term"] == "源悦"
    assert entries[0]["enabled"] is True


@pytest.mark.asyncio
async def test_business_forbidden_term_entries_upsert_reason_and_disable(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        service = BusinessForbiddenTermService(session)
        first = await service.upsert_entries(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            entries=[
                {
                    "term": "小程序",
                    "reason": "小红书不能出现微信生态的词",
                    "replacement": "",
                }
            ],
            created_by="ops",
        )
        second = await service.upsert_entries(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            entries=[
                {
                    "term": "小程序",
                    "reason": "平台侧禁止微信生态露出",
                    "replacement": "平台入口",
                }
            ],
            created_by="ops2",
        )
        entries = await service.list_entries(asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY, include_default=False)
        await service.set_enabled(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            term="小程序",
            enabled=False,
            created_by="ops2",
        )
        disabled_terms = await service.list_terms(asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY, include_default=False)
        disabled_entries = await service.list_entries(asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY, include_default=False)

    assert first.added_terms == ["小程序"]
    assert second.added_terms == []
    assert second.updated_terms == ["小程序"]
    assert [entry["term"] for entry in entries] == ["小程序"]
    assert entries[0]["reason"] == "平台侧禁止微信生态露出"
    assert entries[0]["replacement"] == "平台入口"
    assert disabled_terms == []
    assert disabled_entries[0]["enabled"] is False


@pytest.mark.asyncio
async def test_a2_forbidden_term_audit_is_asset_scoped(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            entries=[{"term": "小程序", "reason": "小红书不能出现微信生态的词"}],
            created_by="ops",
        )
        await session.commit()

        review_service = ForbiddenTermReviewService(session)
        other_audit = await review_service.audit_text(
            asset_key="other_comment_activity",
            title=None,
            body="可以去小程序看一下",
        )
        item = ContentBatchItem(body="可以去小程序看一下")
        review = await review_service.review_and_rewrite_item(
            item=item,
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            orchestrator=None,
            executor_code=None,
            content_type="comment",
        )

    assert other_audit.hits == []
    assert review["initial_hits"] == ["小程序"]
    assert review["final_hits"] == []
    assert "小程序" not in item.body


@pytest.mark.asyncio
async def test_business_forbidden_term_api_lists_updates_and_disables(forbidden_term_session_factory):
    app = FastAPI()
    app.include_router(content_generation_experts.router, prefix="/api/v1/content-generation")

    async def override_get_db():
        async with forbidden_term_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/content-generation/business-forbidden-terms",
            json={
                "asset_key": A2_SENTIMENT_COMMENT_ASSET_KEY,
                "entries": [
                    {
                        "term": "小程序",
                        "reason": "小红书不能出现微信生态的词",
                    }
                ],
                "created_by": "ops",
            },
        )
        list_response = await client.get(
            "/api/v1/content-generation/business-forbidden-terms",
            params={"asset_key": A2_SENTIMENT_COMMENT_ASSET_KEY},
        )
        disable_response = await client.patch(
            "/api/v1/content-generation/business-forbidden-terms/status",
            json={
                "asset_key": A2_SENTIMENT_COMMENT_ASSET_KEY,
                "term": "小程序",
                "enabled": False,
                "updated_by": "ops",
            },
        )

    async with forbidden_term_session_factory() as session:
        active_asset_count = (
            await session.execute(
                select(AssetRegistry).where(
                    AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                    AssetRegistry.asset_key == A2_SENTIMENT_COMMENT_ASSET_KEY,
                    AssetRegistry.status == "active",
                )
            )
        ).scalars().all()

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert disable_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["reason"] == "小红书不能出现微信生态的词"
    assert disable_response.json()["data"]["items"][0]["enabled"] is False
    assert len(active_asset_count) == 1


@pytest.mark.asyncio
async def test_bootstrap_seed_updates_existing_a2_term_reason():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await conn.execute(
            AssetRegistry.__table__.insert().values(
                asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
                display_name="A2业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={"schema_version": "1", "terms": [{"term": "小程序", "enabled": True}]},
            )
        )
        await seed_a2_sentiment_comment_forbidden_terms(conn)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        active_asset = (
            await session.execute(
                select(AssetRegistry).where(
                    AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                    AssetRegistry.asset_key == A2_SENTIMENT_COMMENT_ASSET_KEY,
                    AssetRegistry.status == "active",
                )
            )
        ).scalar_one()
    await engine.dispose()

    assert active_asset.version_no == 2
    assert active_asset.content_json["terms"][0]["term"] == "小程序"
    assert active_asset.content_json["terms"][0]["reason"] == "小红书不能出现微信生态的词"
    assert active_asset.metadata_json["updated_term_count"] == 1
