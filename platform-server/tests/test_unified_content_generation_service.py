import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.expert_config import ExpertConfig
from app.models.maga_assets import AssetRegistry
from app.services.unified_content_generation_service import (
    DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
    SYSTEM_KEYWORD_ASSET_TYPE,
    UnifiedContentGenerationService,
)


@pytest_asyncio.fixture
async def unified_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, ExpertConfig.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_unified_generation_selects_one_sub_keyword_per_category(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="默认关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        _category("persona", "人设", ["经验妈妈", "观察妈妈"]),
                        _category("writing_instruction", "生文指令", ["自然表达", "具体问题"]),
                        _category("perturbation_rule", "扰动规则", ["开头扰动", "长短扰动"]),
                        _category("writing_method", "写作手法", ["场景法", "提问法"]),
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "rule_type": "comment_angle",
                "comment_angle": "整体适应",
                "corpus": "像妈妈在评论区聊刚开始喝源悦的观察。",
                "examples": ["我家刚开始也在看源悦，想蹲蹲真实反馈"],
            },
            item_no=2,
            output_fields=["comment"],
        )

    selected = snapshot.input_snapshot["selected_keywords"]
    assert [item["category_code"] for item in selected] == [
        "persona",
        "writing_instruction",
        "perturbation_rule",
        "writing_method",
    ]
    assert len(selected) == 4
    assert all(len(item["corpus"]) == 1 for item in selected)
    assert snapshot.input_snapshot["content_type"] == "comment"
    assert "整体适应" in snapshot.input_snapshot["rendered_prompt"]
    assert "观察妈妈" in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_unified_generation_handles_extensible_keyword_categories(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="扩展关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        _category("persona", "人设", ["经验妈妈"]),
                        _category("rhythm", "句式节奏", ["短句"]),
                        {
                            **_category("article_only", "文章专用", ["长文结构"]),
                            "applicable_content_types": ["article"],
                        },
                        {
                            **_category("disabled_category", "停用类别", ["不应出现"]),
                            "enabled": False,
                        },
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={"rule_type": "comment_angle", "comment_angle": "互动提问"},
            item_no=1,
            output_fields=["comment"],
        )

    selected = snapshot.input_snapshot["selected_keywords"]
    assert [item["category_code"] for item in selected] == ["persona", "rhythm"]
    assert "短句语料" in snapshot.input_snapshot["rendered_prompt"]
    assert "长文结构语料" not in snapshot.input_snapshot["rendered_prompt"]
    assert "不应出现语料" not in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_unified_generation_uses_expert_template_and_model_config(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            ExpertConfig(
                id=1,
                expert_config_code="comment_generator_v1",
                expert_config_name="评论生成 Expert",
                expert_type="GENERATION",
                expert_app="maga-worker",
                expert_service="content.Generate",
                expert_func="Generate",
                model_code="deepseek-test",
                model_config={"provider_code": "aihubmix", "temperature": 0.6, "max_tokens": 128},
                prompt_template="业务={{ business_rule }}\n关键词={{ keyword_corpus }}",
                enabled=1,
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={"rule_type": "comment_angle", "comment_angle": "互动提问", "corpus": "问问大家"},
            item_no=1,
            output_fields=["comment"],
        )

    expert = snapshot.input_snapshot["expert"]
    assert expert["source"] == "expert_config"
    assert expert["model_config"] == {
        "provider_code": "aihubmix",
        "model_code": "deepseek-test",
        "temperature": 0.6,
        "max_tokens": 128,
    }
    assert snapshot.input_snapshot["rendered_prompt"].startswith("业务=")


def _category(category_code: str, category_name: str, keyword_names: list[str]) -> dict:
    return {
        "category_code": category_code,
        "category_name": category_name,
        "sub_keywords": [
            {
                "keyword_code": f"{category_code}_{index}",
                "keyword_name": keyword_name,
                "corpus": [f"{keyword_name}语料"],
            }
            for index, keyword_name in enumerate(keyword_names, start=1)
        ],
    }
