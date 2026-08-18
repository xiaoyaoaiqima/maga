import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.assets import router
from app.core.database import get_db
from app.models.base import Base
from app.models.maga_assets import AssetRegistry


@pytest.mark.asyncio
async def test_article_business_rule_node_graph_endpoint():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="article_business_rule_set",
                asset_key="chunyue_api_probe",
                display_name="莼悦 API 探针",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "generation_instruction": "写一篇妈妈 UGC。",
                    "items": [
                        {
                            "rule_id": "rule_001",
                            "business_rule": "有机品质+奶粉选择",
                            "content_direction": "写真实选奶记录。",
                            "selling_painpoint_group": "有机品质+奶粉选择",
                        }
                    ],
                    "selling_painpoint_expressions": [
                        {
                            "source_row_no": 1,
                            "selling_painpoint_group": "有机品质+奶粉选择",
                            "expression": "莼悦是欧盟认证的有机产品。",
                        }
                    ],
                },
            )
        )
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/assets")
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/assets/article-business-rule-sets/chunyue_api_probe/node-graph"
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "maga-node-graph/v1"
    assert data["manifest"]["rule_count"] == 1
    assert data["manifest"]["expression_count"] == 1
    assert data["raap_export"]["strategy_blueprint"]["logical_combination_count"] == 1
    await engine.dispose()
