"""Tests for delivered comment ledger exact duplicate prevention."""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import content_generation_experts
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import CommentDeliveryLedger, ContentBatchItem
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.services.comment_delivery_ledger_service import (
    DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY,
    CommentDeliveryLedgerService,
)
from app.services.content_comment_batch_service import ContentCommentBatchService


@pytest_asyncio.fixture
async def ledger_session_factory():
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
async def test_comment_delivery_ledger_normalizes_by_strip_only(ledger_session_factory):
    async with ledger_session_factory() as session:
        service = CommentDeliveryLedgerService(session)
        result = await service.upsert_many(
            asset_key=DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY,
            entries=[
                {"category": "有货", "comment_text": " a2至初有货了 "},
                {"category": "有货", "comment_text": "a2至初有货了"},
                {"category": "有货", "comment_text": "a2至初有货啦"},
            ],
            source_type="csv_import",
            source_uri="seed.csv",
            delivered_by="ops",
        )
        await session.commit()

        existing = await service.exists_many(
            asset_key=DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY,
            comments=["a2至初有货了", "a2至初有货啦"],
        )

    assert result.imported_rows == 2
    assert result.skipped_input_duplicate_rows == 1
    assert set(existing) == {"a2至初有货了", "a2至初有货啦"}


@pytest.mark.asyncio
async def test_comment_delivery_ledger_is_asset_scoped(ledger_session_factory):
    async with ledger_session_factory() as session:
        service = CommentDeliveryLedgerService(session)
        await service.upsert_many(
            asset_key="a2_sentiment_comment_activity",
            entries=[{"comment_text": "同一句评论"}],
            source_type="csv_import",
        )
        await service.upsert_many(
            asset_key="other_comment_activity",
            entries=[{"comment_text": "同一句评论"}],
            source_type="csv_import",
        )
        await session.commit()
        result = await session.execute(select(CommentDeliveryLedger))
        rows = list(result.scalars().all())

    assert len(rows) == 2
    assert {row.asset_key for row in rows} == {"a2_sentiment_comment_activity", "other_comment_activity"}


@pytest.mark.asyncio
async def test_comment_delivery_ledger_api_imports_and_checks(ledger_session_factory):
    app = FastAPI()
    app.include_router(content_generation_experts.router, prefix="/api/v1/content-generation")

    async def override_get_db():
        async with ledger_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        import_response = await client.post(
            "/api/v1/content-generation/comment-delivery-ledger/import",
            json={
                "asset_key": DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY,
                "source_type": "csv_import",
                "source_uri": "seed.csv",
                "delivered_by": "ops",
                "entries": [{"category": "有货", "comment_text": "a2到货了"}],
            },
        )
        check_response = await client.post(
            "/api/v1/content-generation/comment-delivery-ledger/check",
            json={
                "asset_key": DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY,
                "comments": ["a2到货了", "a2还没问到"],
            },
        )

    assert import_response.status_code == 200
    assert import_response.json()["data"]["imported_rows"] == 1
    assert check_response.status_code == 200
    data = check_response.json()["data"]
    assert data["duplicate_count"] == 1
    assert data["hits"][0]["index"] == 0
    assert data["hits"][0]["ledger_entry"]["source_uri"] == "seed.csv"


@pytest.mark.asyncio
async def test_comment_batch_marks_delivery_duplicate_as_not_exportable(ledger_session_factory):
    async with ledger_session_factory() as session:
        await CommentDeliveryLedgerService(session).upsert_many(
            asset_key=DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY,
            entries=[{"comment_text": "a2至初有货了"}],
            source_type="csv_import",
            source_uri="seed.csv",
        )
        item = ContentBatchItem(
            batch_id=1,
            item_no=1,
            status="generated",
            body="a2至初有货了",
            plan_json={"asset_key": DEFAULT_COMMENT_DELIVERY_LEDGER_ASSET_KEY},
            quality_json={"hard_pass": True},
        )

        service = ContentCommentBatchService.__new__(ContentCommentBatchService)
        service.executor_code = "maga_direct_llm_executor"
        await service._review_and_rewrite_delivery_duplicate(
            db=session,
            item=item,
            orchestrator=SimpleNamespace(),
        )

    assert item.quality_json["hard_pass"] is False
    assert item.quality_json["delivery_duplicate_guard"]["duplicate"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is True
