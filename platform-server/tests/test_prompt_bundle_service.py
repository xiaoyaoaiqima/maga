"""Tests for building prompt bundle snapshots."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.maga_assets import AssetRegistry
from app.models.prompt_optimizer import PromptAsset, PromptVersion
from app.services.asset_import_service import WORKER_STATIC_ASSET_SOURCE_NAME
from app.services.prompt_bundle_service import PromptBundleService


@pytest.mark.asyncio
async def test_prompt_bundle_service_builds_current_prompt_and_static_asset_snapshot():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[PromptAsset.__table__, PromptVersion.__table__, AssetRegistry.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        prompt = PromptAsset(name="xhs_writer.ge.soul", prompt_type="generation", tags=["ge"])
        ignored_prompt = PromptAsset(name="other.prompt", prompt_type="generation")
        session.add_all([prompt, ignored_prompt])
        await session.flush()
        version = PromptVersion(prompt_id=prompt.id, version_no=1, content="你是 GE 主写手。")
        ignored_version = PromptVersion(prompt_id=ignored_prompt.id, version_no=1, content="ignore")
        session.add_all([version, ignored_version])
        await session.flush()
        prompt.current_version_id = version.id
        ignored_prompt.current_version_id = ignored_version.id
        session.add(
            AssetRegistry(
                asset_type="expert_corpus",
                asset_key="compliance_redline",
                version_no=1,
                status="active",
                source_name=WORKER_STATIC_ASSET_SOURCE_NAME,
                source_hash="corpus-hash",
                content_json={"content": {"expert": "compliance_redline"}},
            )
        )
        session.add(
            AssetRegistry(
                asset_type="expert_corpus",
                asset_key="ignored",
                version_no=1,
                status="active",
                source_name="other-source",
                content_json={"content": {}},
            )
        )
        await session.commit()

    async with session_factory() as session:
        bundle = await PromptBundleService(session).build_xhs_writer_prompt_bundle_snapshot()

    assert bundle["schema_version"] == "1"
    assert set(bundle["prompts"]) == {"xhs_writer.ge.soul"}
    assert bundle["prompts"]["xhs_writer.ge.soul"]["content"] == "你是 GE 主写手。"
    assert set(bundle["assets"]) == {"expert_corpus:compliance_redline"}
    assert bundle["assets"]["expert_corpus:compliance_redline"]["source_hash"] == "corpus-hash"
    assert bundle["summary"]["prompt_count"] == 1
    assert bundle["summary"]["asset_count"] == 1
    assert len(bundle["summary"]["bundle_hash"]) == 64
