"""Tests for worker-backed MAGA asset imports."""

import base64
import hashlib

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ExecutorRegistry
from app.models.maga_assets import AssetImportRun, AssetRegistry
from app.models.prompt_optimizer import PromptAsset, PromptEvaluation, PromptIssue, PromptOptimizerRun, PromptVersion
from app.services.asset_import_service import import_maga_worker_static_assets, import_yuanyue_training_rules
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


@pytest.mark.asyncio
async def test_import_maga_worker_static_assets_versions_prompts_and_registry_assets(tmp_path):
    workspace = tmp_path / "workspace"
    profile = tmp_path
    (workspace / "ge_writer").mkdir(parents=True)
    (workspace / "experts" / "compliance_redline").mkdir(parents=True)
    (workspace / "experts" / "business_logic").mkdir(parents=True)
    (workspace / "experts" / "painpoint_anchor").mkdir(parents=True)
    (workspace / "outputs" / "runtime_fast_1").mkdir(parents=True)
    (workspace / "tools").mkdir(parents=True)
    (workspace / "system.md").write_text("你是 GE 主写手。", encoding="utf-8")
    (workspace / "ge_writer" / "style_templates.md").write_text("## 风格模板\n自然真实", encoding="utf-8")
    (workspace / "experts" / "_registry.yaml").write_text(
        "experts:\n"
        "  compliance_redline:\n"
        "    type: AE\n"
        "    must: true\n"
        "    score_type: 0/1\n"
        "  business_logic:\n"
        "    type: AE\n"
        "    must: true\n"
        "    score_type: 0-100\n"
        "  painpoint_anchor:\n"
        "    type: AE\n"
        "    must: false\n"
        "    score_type: 0-100\n",
        encoding="utf-8",
    )
    (workspace / "experts" / "_brief_types.yaml").write_text(
        "brief_types:\n  xhs_product_seeding_professional_advisor:\n    required_aes: [compliance_redline, business_logic]\n",
        encoding="utf-8",
    )
    (workspace / "experts" / "compliance_redline" / "system.md").write_text(
        "你是合规红线专家。",
        encoding="utf-8",
    )
    (workspace / "experts" / "compliance_redline" / "score_rubric.md").write_text(
        "score: 1 pass / 0 fail",
        encoding="utf-8",
    )
    (workspace / "experts" / "compliance_redline" / "corpus.yaml").write_text(
        "expert: compliance_redline\noutput_mode: fixed\ngroups:\n  红线:\n    items:\n      - text: 禁止医疗化\n",
        encoding="utf-8",
    )
    (workspace / "experts" / "business_logic" / "system.md").write_text(
        "你是业务逻辑总审。",
        encoding="utf-8",
    )
    (workspace / "experts" / "business_logic" / "score_rubric.md").write_text(
        "score: 100",
        encoding="utf-8",
    )
    (workspace / "experts" / "business_logic" / "corpus.yaml").write_text(
        "expert: business_logic\noutput_mode: fixed\ngroups: {}\n",
        encoding="utf-8",
    )
    (workspace / "experts" / "painpoint_anchor" / "system.md").write_text(
        "旧拆分 AE 不能继续导入",
        encoding="utf-8",
    )
    (workspace / "experts" / "painpoint_anchor" / "corpus.yaml").write_text(
        "expert: painpoint_anchor\noutput_mode: fixed\ngroups: {}\n",
        encoding="utf-8",
    )
    (workspace / "outputs" / "runtime_fast_1" / "ge-runtime_fast.prompt.md").write_text(
        "运行产物不能进提示词资产",
        encoding="utf-8",
    )
    (workspace / "tools" / "xhs_runtime.py").write_text("# code should be ignored", encoding="utf-8")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                PromptAsset.__table__,
                PromptVersion.__table__,
                PromptIssue.__table__,
                PromptOptimizerRun.__table__,
                PromptEvaluation.__table__,
                AssetRegistry.__table__,
                AssetImportRun.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        legacy_ge = PromptAsset(name="xhs_writer.ge.soul", prompt_type="generation", tags=["ge"], is_deleted=0)
        legacy_ae = PromptAsset(
            name="xhs_writer.ae.compliance_redline.persona",
            prompt_type="critic",
            tags=["ae", "persona"],
            is_deleted=0,
        )
        legacy_split_ae = PromptAsset(
            name="xhs_writer.ae.painpoint_anchor.system",
            prompt_type="critic",
            tags=["ae", "painpoint_anchor"],
            is_deleted=0,
        )
        session.add_all([legacy_ge, legacy_ae, legacy_split_ae])
        await session.flush()
        session.add_all(
            [
                PromptVersion(prompt_id=legacy_ge.id, version_no=1, content="old ge"),
                PromptVersion(prompt_id=legacy_ae.id, version_no=1, content="old ae"),
                PromptVersion(prompt_id=legacy_split_ae.id, version_no=1, content="old split ae"),
                AssetRegistry(
                    asset_type="expert_corpus",
                    asset_key="painpoint_anchor",
                    display_name="旧拆分 AE 语料",
                    version_no=1,
                    status="active",
                    source_name="old",
                    source_hash="old",
                    content_json={"content": {"expert": "painpoint_anchor"}},
                ),
            ]
        )
        await session.flush()
        result = await import_maga_worker_static_assets(session, workspace)
        await session.commit()

    assert result.imported_prompts == 6
    assert result.imported_assets == 4
    assert "xhs_writer.ge.system" in result.prompt_names
    assert "xhs_writer.ae.compliance_redline.system" in result.prompt_names
    assert "xhs_writer.ae.business_logic.system" in result.prompt_names
    assert ("expert_corpus", "compliance_redline") in result.asset_keys
    assert ("expert_corpus", "business_logic") in result.asset_keys

    async with session_factory() as session:
        prompts = (await session.execute(PromptAsset.__table__.select())).mappings().all()
        versions = (await session.execute(PromptVersion.__table__.select())).mappings().all()
        assets = (await session.execute(AssetRegistry.__table__.select())).mappings().all()
        runs = (await session.execute(AssetImportRun.__table__.select())).mappings().all()

    prompt_names = {row["name"] for row in prompts}
    assert "xhs_writer.ge.system" in prompt_names
    assert "xhs_writer.ge.style_templates" in prompt_names
    assert "xhs_writer.ae.compliance_redline.system" in prompt_names
    assert "xhs_writer.ae.compliance_redline.score_rubric" in prompt_names
    assert "xhs_writer.ae.business_logic.system" in prompt_names
    assert "xhs_writer.ae.business_logic.score_rubric" in prompt_names
    assert "xhs_writer.ge.soul" not in prompt_names
    assert "xhs_writer.ae.compliance_redline.persona" not in prompt_names
    assert "xhs_writer.ae.painpoint_anchor.system" not in prompt_names
    assert "ge-runtime_fast.prompt.md" not in prompt_names
    assert len(versions) == 6
    by_asset = {(row["asset_type"], row["asset_key"]): row for row in assets}
    assert by_asset[("expert_registry", "xhs_writer")]["content_json"]["content"]["experts"]["compliance_redline"]["score_type"] == "0/1"
    assert by_asset[("brief_type_registry", "xhs_writer")]["content_json"]["content"]["brief_types"]
    assert by_asset[("expert_corpus", "compliance_redline")]["content_json"]["content"]["expert"] == "compliance_redline"
    assert by_asset[("expert_corpus", "business_logic")]["content_json"]["content"]["expert"] == "business_logic"
    assert by_asset[("expert_corpus", "painpoint_anchor")]["status"] == "archived"
    assert runs[0]["summary_json"]["excluded_dirs"] == ["outputs", "tests", "__pycache__", ".pytest_cache"]

    async with session_factory() as session:
        second = await import_maga_worker_static_assets(session, workspace)
        await session.commit()

    assert second.imported_prompts == 0
    assert second.imported_assets == 0

    async with session_factory() as session:
        prompt_count = len((await session.execute(PromptAsset.__table__.select())).mappings().all())
        version_count = len((await session.execute(PromptVersion.__table__.select())).mappings().all())
        asset_count = len((await session.execute(AssetRegistry.__table__.select())).mappings().all())

    assert prompt_count == 6
    assert version_count == 6
    assert asset_count == 5
