"""Tests for worker-backed MAGA asset imports."""

import base64
import hashlib

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ExecutorRegistry
from app.models.maga_assets import AssetImportRun, AssetRegistry
from app.services.asset_import_service import import_yuanyue_training_rules
from app.services.executor_invocation_service import InvokeResult


class FakeAssetImportInvocationClient:
    def __init__(self):
        self.calls = []

    async def invoke(self, *, invoke_url, envelope, executor_token=None):
        self.calls.append({"invoke_url": invoke_url, "envelope": envelope, "executor_token": executor_token})
        source_hash = envelope["input"]["source_hash"]
        asset_key = envelope["input"]["asset_key"]
        return InvokeResult(
            mode="sync",
            stage_call_id=envelope["stage_call_id"],
            output={
                "asset_key": asset_key,
                "source_hash": source_hash,
                "warnings": ["跳过空白行 1 条"],
                "assets": [
                    {
                        "asset_type": "brand_profile",
                        "display_name": "源悦品牌资料",
                        "content_json": {"brand_name": "源悦", "content_style": "高质量真实用户ugc"},
                    },
                    {
                        "asset_type": "painpoint_model",
                        "display_name": "源悦主题/痛点模型",
                        "content_json": {
                            "topics": [
                                {
                                    "topic": "便便不规律",
                                    "descriptions": ["羊屎蛋/干硬", "便便又干又硬"],
                                    "selling_points": [
                                        {
                                            "selling_point": "好消化易吸收",
                                            "expressions": ["便便基本一天一次，拉起来也不费劲"],
                                        }
                                    ],
                                }
                            ],
                            "items": [
                                {
                                    "painpoint": "便便不规律",
                                    "description": "羊屎蛋/干硬；便便又干又硬",
                                    "selling_point": "好消化易吸收",
                                }
                            ],
                        },
                    },
                ],
            },
            stats={"fake": True},
        )


@pytest.mark.asyncio
async def test_import_yuanyue_training_rules_invokes_worker_and_persists_assets():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[ExecutorRegistry.__table__, AssetRegistry.__table__, AssetImportRun.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    workbook_content = b"fake-xlsx-content"
    expected_hash = hashlib.sha256(workbook_content).hexdigest()
    fake_client = FakeAssetImportInvocationClient()

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="hermes_maga_worker",
                executor_type="hermes_profile",
                profile_name="maga-worker",
                invoke_url="http://127.0.0.1:8765/invoke",
                supported_capabilities_json=[{"capability": "asset.import", "schema_version": "1"}],
                config_json={"executor_token": "test-token"},
                enabled=1,
            )
        )
        session.add(
            AssetRegistry(
                asset_type="painpoint_model",
                asset_key="yuanyue",
                display_name="源悦旧痛点模型",
                version_no=1,
                status="active",
                content_json={"items": [{"painpoint": "历史错误痛点"}]},
                created_by="old-importer",
            )
        )
        await session.commit()

        result = await import_yuanyue_training_rules(
            session,
            workbook_content,
            source_name="源悦种草活动-ai训练规则.xlsx",
            invocation_client=fake_client,
        )
        await session.commit()

    assert result.imported_assets == 2
    assert result.import_run_id is not None
    assert result.source_hash == expected_hash
    assert ("painpoint_model", "yuanyue") in result.asset_keys
    call = fake_client.calls[0]
    assert call["invoke_url"] == "http://127.0.0.1:8765/invoke"
    assert call["executor_token"] == "test-token"
    assert call["envelope"]["capability"] == "asset.import"
    assert call["envelope"]["input"]["source_hash"] == expected_hash
    assert base64.b64decode(call["envelope"]["input"]["source_content_base64"]) == workbook_content

    async with session_factory() as session:
        assets = (await session.execute(AssetRegistry.__table__.select())).mappings().all()
        runs = (await session.execute(AssetImportRun.__table__.select())).mappings().all()

    by_key = {(row["asset_type"], row["asset_key"], row["status"]): row for row in assets}
    assert by_key[("brand_profile", "yuanyue", "active")]["version_no"] == 1
    assert by_key[("brand_profile", "yuanyue", "active")]["asset_stage"] == "production"
    assert by_key[("painpoint_model", "yuanyue", "archived")]["version_no"] == 1
    assert by_key[("painpoint_model", "yuanyue", "active")]["version_no"] == 2
    assert by_key[("painpoint_model", "yuanyue", "active")]["asset_stage"] == "production"
    assert by_key[("brand_profile", "yuanyue", "active")]["metadata_json"]["importer"] == "worker_asset_import_v1"
    topics = by_key[("painpoint_model", "yuanyue", "active")]["content_json"]["topics"]
    assert topics[0]["topic"] == "便便不规律"
    assert topics[0]["selling_points"][0]["expressions"] == ["便便基本一天一次，拉起来也不费劲"]
    assert runs[0]["summary_json"]["warnings"] == ["跳过空白行 1 条"]


@pytest.mark.asyncio
async def test_import_yuanyue_training_rules_rejects_missing_executor():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[ExecutorRegistry.__table__, AssetRegistry.__table__, AssetImportRun.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        with pytest.raises(ValueError, match="executor not found"):
            await import_yuanyue_training_rules(session, b"fake-xlsx-content")
