"""API tests for operator-facing content batch report endpoint."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.content_agent import router
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import (
    ContentAgentRun,
    ContentAgentStageCall,
    ContentBatchItem,
    ContentBatchItemVersion,
    ContentBatchJob,
    ContentFeedback,
)


@pytest_asyncio.fixture
async def batch_report_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ContentBatchJob.__table__,
                ContentBatchItem.__table__,
                ContentBatchItemVersion.__table__,
                ContentFeedback.__table__,
                ContentAgentRun.__table__,
                ContentAgentStageCall.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        job = ContentBatchJob(
            batch_code="batch_api_report",
            asset_key="yuanyue",
            product_topic="源悦小红书小批量",
            target_audience="新手妈妈",
            style="真实口语化",
            count=1,
            status="generated",
        )
        session.add(job)
        await session.flush()
        session.add(
            ContentBatchItem(
                batch_id=job.id,
                item_no=1,
                status="generated",
                plan_json={"rule_id": "business_rule_001", "source_row_no": 5},
                title="换奶前先看这3点",
                body="新手爸妈先别慌，慢慢观察宝宝日常状态。",
                quality_json={
                    "hard_pass": True,
                    "review_report": {"rewrite_required": False, "suggestions": [], "replacement_needed": []},
                },
            )
        )
        await session.commit()
        batch_id = job.id

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/content-agent")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, batch_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_batch_report_endpoint_returns_operator_view(batch_report_client):
    client, batch_id = batch_report_client
    response = await client.get(f"/api/v1/content-agent/batches/{batch_id}/report")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["batch_id"] == batch_id
    assert data["summary"]["generated_count"] == 1
    assert data["summary"]["hard_pass_count"] == 1
    assert data["items"][0]["title"] == "换奶前先看这3点"
    assert data["items"][0]["hard_pass"] is True
    assert data["items"][0]["rewrite_required"] is False
    assert "generation_snapshot" not in data["items"][0]
    assert "diversity" not in data["items"][0]


@pytest.mark.asyncio
async def test_list_batches_endpoint_filters_by_asset_and_rule(batch_report_client):
    client, batch_id = batch_report_client

    asset_response = await client.get(
        "/api/v1/content-agent/batches",
        params={"asset_key": "yuanyue", "limit": 10},
    )
    assert asset_response.status_code == 200
    asset_data = asset_response.json()["data"]
    assert asset_data["total"] == 1
    assert asset_data["items"][0]["batch_id"] == batch_id

    rule_response = await client.get(
        "/api/v1/content-agent/batches",
        params={
            "asset_key": "yuanyue",
            "rule_id": "business_rule_001",
            "source_row_no": 5,
            "limit": 10,
        },
    )
    assert rule_response.status_code == 200
    assert rule_response.json()["data"]["total"] == 1

    missing_response = await client.get(
        "/api/v1/content-agent/batches",
        params={"asset_key": "yuanyue", "rule_id": "business_rule_missing"},
    )
    assert missing_response.status_code == 200
    assert missing_response.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_get_batch_report_endpoint_returns_404_when_batch_missing(batch_report_client):
    client, _batch_id = batch_report_client
    response = await client.get("/api/v1/content-agent/batches/999/report")

    assert response.status_code == 404
