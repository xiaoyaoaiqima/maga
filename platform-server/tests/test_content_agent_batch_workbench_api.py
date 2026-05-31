"""API tests for the operator-facing content-agent workbench batch flow."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.content_agent import router
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import ContentBatchItem, ContentFeedback, ExecutorRegistry
from app.models.llm_provider_config import LLMProviderConfig
from app.models.maga_assets import AssetChangeRequest, AssetRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES


@pytest_asyncio.fixture
async def content_agent_workbench_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="hermes_maga_worker",
                executor_type="hermes_profile",
                profile_name="maga-worker",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                supported_capabilities_json=[
                    {"capability": "xhs.interpret_brief", "schema_version": "1"},
                    {"capability": "xhs.run_ae_analysis", "schema_version": "1"},
                    {"capability": "xhs.generate_draft", "schema_version": "1"},
                    {"capability": "xhs.review_and_rewrite", "schema_version": "1"},
                    {"capability": "xhs.run_ae_review", "schema_version": "1"},
                    {"capability": "xhs.rewrite_draft", "schema_version": "1"},
                    {"capability": "comment.generate", "schema_version": "1"},
                    {"capability": "content.generate", "schema_version": "1"},
                ],
                enabled=1,
            )
        )
        session.add_all(_yuanyue_assets())
        await session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/content-agent")

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_workbench_can_start_batch_then_list_and_open_report(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 2,
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["batch_id"]
    assert data["execution"] == {
        "requested_limit": 2,
        "generated_count": 2,
        "failed_count": 0,
        "item_ids": data["execution"]["item_ids"],
    }
    assert len(data["execution"]["item_ids"]) == 2
    assert data["report"]["summary"]["generated_count"] == 2
    assert [item["status"] for item in data["report"]["items"]] == ["generated", "generated"]
    assert data["report"]["items"][0]["title"]
    assert data["report"]["items"][0]["body"]

    list_response = await client.get("/api/v1/content-agent/batches", params={"limit": 10})
    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 1
    assert list_data["items"][0]["batch_id"] == data["batch_id"]
    assert list_data["items"][0]["summary"]["generated_count"] == 2

    report_response = await client.get(
        f"/api/v1/content-agent/batches/{data['batch_id']}/report"
    )
    assert report_response.status_code == 200
    report = report_response.json()["data"]
    assert report["batch_code"] == data["batch_code"]
    assert report["summary"]["hard_pass_count"] == 2


@pytest.mark.asyncio
async def test_batch_workbench_uses_default_executor_when_form_sends_blank_code(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "executor_code": "   ",
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["execution"]["generated_count"] == 1
    assert data["report"]["items"][0]["status"] == "generated"


@pytest.mark.asyncio
async def test_comment_batch_can_start_from_rule_asset_key_only(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["execution"]["requested_limit"] == 3
    assert data["execution"]["generated_count"] == 3
    assert data["execution"]["failed_count"] == 0
    report = data["report"]
    assert report["asset_key"] == "yuanyue_comment_activity"
    assert report["product_topic"] == "美素佳儿源悦活动评论"
    assert report["items"][0]["title"] == "整体适应"
    assert report["items"][0]["body"] == "我家刚开始也在看源悦，想蹲蹲真实反馈"
    assert report["items"][0]["quality"]["rule_type"] == "comment_angle"

    async with session_factory() as session:
        item = (
            await session.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == data["batch_id"])
                .order_by(ContentBatchItem.item_no)
            )
        ).scalars().first()

    assert item.plan_json["rule_type"] == "comment_angle"
    assert item.plan_json["comment_angle"] == "整体适应"
    assert "像妈妈在评论区聊刚开始喝源悦" in item.plan_json["corpus"]
    assert item.plan_json["examples"] == ["我家刚开始也在看源悦，想蹲蹲真实反馈"]
    assert item.plan_json["unified_generation"]["capability"] == "content.generate"
    assert [kw["category_code"] for kw in item.plan_json["unified_generation"]["selected_keywords"]] == [
        "persona",
        "comment_writing_instruction",
        "perturbation_rule",
        "writing_method",
        "format_control",
    ]


@pytest.mark.asyncio
async def test_batch_workbench_uses_maga_default_provider_model(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    async with session_factory() as session:
        session.add(
            LLMProviderConfig(
                id=1,
                provider_code="aihubmix",
                provider_name="AIHubMix",
                provider_type="openai_compatible",
                base_url="https://api.example.test/v1",
                api_key="test-key",
                default_model="deepseek-v4-flash",
                priority=100,
                enabled=1,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalars().first()

    assert item.plan_json["model_config"] == {
        "ge_model": "deepseek-v4-flash",
        "ae_model": "deepseek-v4-flash",
    }


@pytest.mark.asyncio
async def test_batch_workbench_can_record_operator_feedback_and_manual_edit(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    assert start_response.status_code == 200
    item = start_response.json()["data"]["report"]["items"][0]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头再具体一点，少一点总结腔。",
            "created_by": "reviewer-a",
        },
    )
    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["review_status"] == "needs_revision"
    assert feedback_data["version_no"] == 1
    assert feedback_data["item"]["human_feedback_text"] == "开头再具体一点，少一点总结腔。"

    manual_edit_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "manual_edit",
            "title": "我家便便不规律那阵子，转源悦后的真实记录",
            "body": "这是运营人工改后的正文，保留真实经历，也避免医疗化表达。",
            "feedback_text": "运营直接人工改稿。",
            "created_by": "reviewer-a",
        },
    )
    assert manual_edit_response.status_code == 200
    manual_data = manual_edit_response.json()["data"]
    assert manual_data["review_status"] == "manual_edited"
    assert manual_data["version_no"] == 2
    assert manual_data["item"]["title"] == "我家便便不规律那阵子，转源悦后的真实记录"
    assert manual_data["item"]["body"] == "这是运营人工改后的正文，保留真实经历，也避免医疗化表达。"

    approve_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={"action": "approve", "feedback_text": "可发布", "created_by": "reviewer-a"},
    )
    assert approve_response.status_code == 200
    approve_data = approve_response.json()["data"]
    assert approve_data["review_status"] == "approved"
    assert approve_data["version_no"] == 3
    assert approve_data["item"]["feedback_count"] == 3

    report_response = await client.get(
        f"/api/v1/content-agent/batches/{start_response.json()['data']['batch_id']}/report"
    )
    report_item = report_response.json()["data"]["items"][0]
    assert report_response.json()["data"]["summary"]["feedback_count"] == 3
    assert report_item["status"] == "approved"
    assert report_item["review_status"] == "approved"
    assert report_item["latest_version_no"] == 3
    assert report_item["human_feedback_text"] == "可发布"
    assert report_item["feedback_count"] == 3


@pytest.mark.asyncio
async def test_batch_feedback_is_persisted_for_training(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头像真实妈妈一点，少一点口号。",
            "created_by": "reviewer-a",
        },
    )

    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["item"]["feedback_count"] == 1

    async with session_factory() as session:
        feedback = (await session.execute(select(ContentFeedback))).scalar_one()
    assert feedback.item_id == item["item_id"]
    assert feedback.version_id == feedback_data["version_id"]
    assert feedback.action == "request_revision"
    assert feedback.review_status == "needs_revision"
    assert feedback.comment == "开头像真实妈妈一点，少一点口号。"
    assert feedback.submitter == "reviewer-a"
    assert feedback.metadata_json["source"] == "content_batch_workbench"
    assert feedback.metadata_json.get("asset_change_request_id") is None


@pytest.mark.asyncio
async def test_fact_rule_feedback_creates_asset_change_request(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验复盘",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "源悦和 a2 蛋白、a2 公司没有关系，是完全独立的两款奶粉。禁止提及a2 蛋白。",
            "created_by": "ops",
        },
    )

    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["item"]["review_status"] == "needs_revision"

    async with session_factory() as session:
        change_request = (await session.execute(select(AssetChangeRequest))).scalar_one()
        feedback = (await session.execute(select(ContentFeedback))).scalar_one()

    assert "禁止提及a2 蛋白" in change_request.source_text
    assert change_request.status == "pending"
    assert change_request.requester == "ops"
    assert change_request.context_json["asset_key"] == "yuanyue"
    assert change_request.context_json["intent"] == "fact_or_compliance_rule"
    assert "compliance_rules" in change_request.context_json["affected_asset_types"]
    assert feedback.metadata_json["asset_change_request_id"] == change_request.id
    assert feedback.metadata_json["asset_change_intent"] == "fact_or_compliance_rule"


@pytest.mark.asyncio
async def test_training_feedback_samples_list_returns_cross_batch_feedback(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={
            "asset_key": "yuanyue",
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
            "count": 1,
            "created_by": "ops",
        },
    )
    item = start_response.json()["data"]["report"]["items"][0]

    await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头像真实妈妈一点，少一点口号。",
            "created_by": "reviewer-a",
        },
    )
    await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={"action": "approve", "feedback_text": "修改后可发布", "created_by": "reviewer-b"},
    )

    response = await client.get("/api/v1/content-agent/training/feedback-samples")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["items"][0]["review_status"] == "approved"
    assert data["items"][0]["comment"] == "修改后可发布"
    assert data["items"][0]["product_topic"] == "宝宝便便不规律"
    assert data["items"][0]["body_preview"]

    filtered = await client.get(
        "/api/v1/content-agent/training/feedback-samples",
        params={"review_status": "needs_revision"},
    )
    assert filtered.status_code == 200
    filtered_data = filtered.json()["data"]
    assert filtered_data["total"] == 1
    assert filtered_data["items"][0]["review_status"] == "needs_revision"
    assert filtered_data["items"][0]["comment"] == "开头像真实妈妈一点，少一点口号。"


def _yuanyue_assets() -> list[AssetRegistry]:
    return [
        AssetRegistry(
            asset_type="painpoint_model",
            asset_key="yuanyue",
            display_name="源悦痛点模型",
            version_no=1,
            status="active",
            content_json={
                "items": [
                    {"painpoint": "便便不规律", "symptom": "拉臭费劲", "description": "便便状态不稳定", "selling_point": "好消化易吸收"},
                    {"painpoint": "肚肚不舒服", "symptom": "胀气", "description": "喝奶后肚肚闹腾", "selling_point": "温和"},
                ]
            },
        ),
        AssetRegistry(
            asset_type="product_selling_points",
            asset_key="yuanyue",
            display_name="源悦产品卖点",
            version_no=1,
            status="active",
            content_json={
                "items": [
                    {"selling_point": "好消化易吸收", "advantage": "软凝乳"},
                    {"selling_point": "温和", "advantage": "亲和宝宝肚肚"},
                ]
            },
        ),
        AssetRegistry(
            asset_type="reference_examples",
            asset_key="yuanyue",
            display_name="源悦参考例文",
            version_no=1,
            status="active",
            content_json={
                "items": [
                    {"example_id": "ex1", "title": "过来人经验", "body": "先观察宝宝便便状态", "style_tags": ["经验笔记"]},
                    {"example_id": "ex2", "title": "场景共鸣", "body": "新手妈妈别焦虑", "style_tags": ["场景共鸣"]},
                ]
            },
        ),
        AssetRegistry(
            asset_type="compliance_rules",
            asset_key="yuanyue",
            display_name="源悦审核规则",
            version_no=1,
            status="active",
            content_json={"items": [{"dimension": "禁止治疗便秘", "risk_level": "high"}]},
        ),
        AssetRegistry(
            asset_type="comment_angle_rule_set",
            asset_key="yuanyue_comment_activity",
            display_name="源悦活动评论切角规则",
            version_no=1,
            status="active",
            content_json={
                "rule_type": "comment_angle",
                "activity_name": "美素佳儿源悦活动评论",
                "default_generation_count": 10,
                "items": [
                    {
                        "rule_id": "comment_angle_001",
                        "comment_angle": "整体适应",
                        "corpus": "整体适应：\n像妈妈在评论区聊刚开始喝源悦的观察，语气自然一点。",
                        "examples": ["我家刚开始也在看源悦，想蹲蹲真实反馈"],
                        "supplements": [],
                        "source_row_no": 1,
                    },
                    {
                        "rule_id": "comment_angle_002",
                        "comment_angle": "成分讨论",
                        "corpus": "成分讨论：\n像在确认信息，别写成科普长文。",
                        "examples": ["软分子蛋白这个点我也想了解下"],
                        "supplements": [],
                        "source_row_no": 2,
                    },
                    {
                        "rule_id": "comment_angle_003",
                        "comment_angle": "同款求反馈",
                        "corpus": "同款求反馈：\n像同阶段妈妈顺手问一句。",
                        "examples": ["有同月龄宝宝喝过吗，想看看大家怎么说"],
                        "supplements": [],
                        "source_row_no": 3,
                    },
                ],
            },
            metadata_json={
                "rule_type": "comment_angle",
                "default_generation_count": 10,
                "rule_count": 3,
                "example_count": 3,
            },
        ),
    ]
