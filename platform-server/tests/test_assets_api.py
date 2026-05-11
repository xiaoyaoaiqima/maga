"""API tests for MAGA Asset Steward surfaces."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.assets import router
from app.core.database import get_db
from app.models.base import Base
from app.models.maga_assets import AssetChangeProposal, AssetChangeRequest, AssetRegistry


@pytest_asyncio.fixture
async def asset_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, AssetChangeRequest.__table__, AssetChangeProposal.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="compliance_rules",
                asset_key="yuanyue",
                display_name="源悦审核规则",
                version_no=1,
                status="active",
                content_json={"items": [{"dimension": "不得宣称治疗便秘"}]},
                created_by="test",
            )
        )
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/assets")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_assets_and_get_latest_asset(asset_client):
    list_response = await asset_client.get("/api/v1/assets", params={"asset_key": "yuanyue"})
    assert list_response.status_code == 200
    listed = list_response.json()["data"]
    assert listed[0]["asset_type"] == "compliance_rules"
    assert listed[0]["asset_key"] == "yuanyue"

    get_response = await asset_client.get("/api/v1/assets/compliance_rules/yuanyue")
    assert get_response.status_code == 200
    asset = get_response.json()["data"]
    assert asset["version_no"] == 1
    assert asset["content_json"]["items"][0]["dimension"] == "不得宣称治疗便秘"


@pytest.mark.asyncio
async def test_asset_steward_creates_request_proposal_and_applies_new_asset_version(asset_client):
    request_response = await asset_client.post(
        "/api/v1/assets/change-requests",
        json={
            "source_text": "新增宝宝便便不规律方向，避免治疗便秘",
            "requester": "运营A",
            "context_json": {"asset_key": "yuanyue"},
        },
    )
    assert request_response.status_code == 200
    request_data = request_response.json()["data"]
    assert request_data["status"] == "pending"

    proposal_response = await asset_client.post(
        "/api/v1/assets/change-proposals",
        json={
            "request_id": request_data["id"],
            "risk_level": "high",
            "summary": "补充便便不规律表达规则",
            "affected_assets_json": [{"asset_type": "compliance_rules", "asset_key": "yuanyue"}],
            "proposed_changes_json": {
                "assets": [
                    {
                        "asset_type": "compliance_rules",
                        "asset_key": "yuanyue",
                        "display_name": "源悦审核规则",
                        "content_json": {"items": [{"dimension": "禁止治疗便秘、改善便秘等医疗化表述"}]},
                    }
                ]
            },
            "risk_notes_json": ["母婴消化相关默认高风险，需要人工确认"],
            "smoke_test_json": {
                "product_topic": "宝宝便便不规律",
                "target_audience": "新手妈妈",
                "style": "经验老道型",
            },
        },
    )
    assert proposal_response.status_code == 200
    proposal_data = proposal_response.json()["data"]
    assert proposal_data["status"] == "proposed"

    apply_response = await asset_client.post(f"/api/v1/assets/change-proposals/{proposal_data['id']}/apply")
    assert apply_response.status_code == 200
    applied = apply_response.json()["data"]
    assert applied["status"] == "applied"
    assert applied["created_asset_ids"]

    latest_response = await asset_client.get("/api/v1/assets/compliance_rules/yuanyue")
    latest = latest_response.json()["data"]
    assert latest["version_no"] == 2
    assert latest["content_json"]["items"][0]["dimension"] == "禁止治疗便秘、改善便秘等医疗化表述"
