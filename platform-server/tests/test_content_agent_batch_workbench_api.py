"""API tests for the operator-facing content-agent workbench batch flow."""

from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.content_agent import router
from app.core.database import get_db
from app.models.base import Base
from app.models.content_agent import (
    ContentAgentStageCall,
    ContentBatchItem,
    ContentBatchItemVersion,
    ContentFeedback,
    ExecutorRegistry,
)
from app.models.llm_provider_config import LLMProviderConfig
from app.models.maga_assets import AssetChangeRequest, AssetRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.services.content_comment_batch_service import ContentCommentBatchService


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
                    {"capability": "asset.import", "schema_version": "1"},
                    {"capability": "content.generate", "schema_version": "1"},
                    {"capability": "content.rewrite", "schema_version": "1"},
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


def test_comment_rule_selection_balances_angles_when_rule_pool_is_large():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rules = [
        {
            "comment_angle": angle,
            "corpus": f"{angle} corpus {index}",
            "source_row_no": index,
        }
        for angle, start in [("便便问题", 1), ("奶量补充", 11), ("生长发育", 21)]
        for index in range(start, start + 10)
    ]

    selected = service._select_rules(rules, 6)

    assert len(selected) == 6
    assert {rule["comment_angle"] for rule in selected} == {"便便问题", "奶量补充", "生长发育"}
    assert [rule["source_row_no"] for rule in selected] != list(range(1, 7))


def test_comment_plan_injects_one_reference_example_from_pool():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    rule = {
        "rule_id": "comment_angle_001",
        "comment_angle": "便便问题",
        "corpus": "像评论区宝妈接话，聊便便频率和软硬。",
        "examples": ["同款，崽崽都是香蕉软便便", "加一，现在固定一天一次"],
        "supplements": ["我家拉得挺轻松的，没有那么费劲"],
        "source_row_no": 1,
    }
    asset = SimpleNamespace(asset_key="yuanyue", id=7, version_no=3)

    plan = service._plan_from_rule(rule, asset=asset, item_no=1)

    assert len(plan["examples"]) == 1
    assert plan["examples"][0] in rule["examples"]
    assert plan["supplements"] == []
    assert plan["example_pool_count"] == 2
    assert plan["supplement_pool_count"] == 1
    assert plan["selected_example_source"] == "examples"


def test_comment_length_fallback_keeps_short_natural_clause():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)

    comment = service._fit_comment_length("从旧奶转源悦，我家娃皮肤敏感，先少量掺着喝。")

    assert comment == "从旧奶转源悦，我家娃皮肤敏感"
    assert len(comment) <= 20


def test_comment_length_fallback_leaves_short_comment_unchanged():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)

    assert service._fit_comment_length("纸尿裤里不吓人") == "纸尿裤里不吓人"


@pytest.mark.asyncio
async def test_comment_similarity_rewrite_updates_quality_metadata():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    service.executor_code = "hermes_maga_worker"
    item = ContentBatchItem(
        batch_id=1,
        item_no=2,
        status="generated",
        run_id=11,
        body="你们都在哪买的，多少钱一罐",
        quality_json={"hard_pass": True, "stage_call_count": 1, "run_status": "succeeded"},
        plan_json={"unified_generation": {"selected_keywords": []}},
    )
    similar_item = {
        "batch_id": 1,
        "item_no": 1,
        "body": "姐妹们都在哪买的，多少钱一罐呀",
        "score": 0.72,
        "scope": "current_batch",
    }
    orchestrator = _CommentRewriteOrchestrator("先问正品渠道，别急着囤。")

    await service._rewrite_item_for_similarity(item=item, similar_item=similar_item, orchestrator=orchestrator)

    assert item.body == "先问正品渠道，别急着囤。"
    rewrite = item.quality_json["similarity_rewrites"][0]
    assert rewrite["similar_item_no"] == 1
    assert rewrite["pre_rewrite_similarity_score"] == 0.72
    assert rewrite["similarity_rewrite_passed"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert orchestrator.input_payload["content_type"] == "comment"
    assert "避开相似评论" in " ".join(orchestrator.input_payload["rewrite_instructions"])


@pytest.mark.asyncio
async def test_comment_similarity_rewrite_rechecks_candidates_after_rewrite():
    service = ContentCommentBatchService.__new__(ContentCommentBatchService)
    service.executor_code = "hermes_maga_worker"
    item = ContentBatchItem(
        batch_id=1,
        item_no=3,
        status="generated",
        run_id=11,
        body="一直喝这款，家里省心少折腾。",
        quality_json={"hard_pass": True, "stage_call_count": 1, "run_status": "succeeded"},
        plan_json={"unified_generation": {"selected_keywords": []}},
    )
    previous_items = [
        ContentBatchItem(batch_id=1, item_no=1, status="generated", body="一直喝这款，没折腾换奶。"),
        ContentBatchItem(batch_id=1, item_no=2, status="generated", body="半夜冲奶就拿这罐，不用想"),
    ]

    async def fake_previous_items(db, current_item):  # noqa: ANN001
        return previous_items

    async def fake_history_items(db, current_item):  # noqa: ANN001
        return []

    service._previous_generated_items = fake_previous_items
    service._history_items_for_similarity = fake_history_items
    orchestrator = _CommentRewriteSequenceOrchestrator(
        [
            "半夜冲奶还拿这罐",
            "临睡那顿肯喝，我就放心。",
        ]
    )

    await service._review_and_rewrite_similarity(db=None, item=item, orchestrator=orchestrator)

    assert item.body == "临睡那顿肯喝，我就放心。"
    assert len(item.quality_json["similarity_rewrites"]) == 2
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert item.quality_json["hard_pass"] is True


class _CommentRewriteOrchestrator:
    def __init__(self, comment: str):
        self.comment = comment
        self.input_payload = None

    async def run_content_rewrite_stage(self, *, run_id, executor_code, input_payload):  # noqa: ANN001
        self.input_payload = input_payload
        return SimpleNamespace(
            output={"comment": self.comment},
            stage_calls=[object()],
            run=SimpleNamespace(status="succeeded"),
        )


class _CommentRewriteSequenceOrchestrator:
    def __init__(self, comments: list[str]):
        self.comments = list(comments)
        self.input_payloads = []

    async def run_content_rewrite_stage(self, *, run_id, executor_code, input_payload):  # noqa: ANN001
        self.input_payloads.append(input_payload)
        return SimpleNamespace(
            output={"comment": self.comments.pop(0)},
            stage_calls=[object()],
            run=SimpleNamespace(status="succeeded"),
        )


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
    assert report["items"][0]["generation_snapshot"]["rule_type"] == "comment_angle"
    assert report["items"][0]["generation_snapshot"]["business_rule"]["comment_angle"] == "整体适应"
    assert report["items"][0]["generation_snapshot"]["expert"]["expert_config_code"] == "comment_generator_v1"
    assert "整体适应" in report["items"][0]["generation_snapshot"]["rendered_prompt"]

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
        "comment_format_control",
    ]


@pytest.mark.asyncio
async def test_comment_batch_can_use_dedicated_keyword_package(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="content_generation_keywords",
                asset_key="a2_plot_discussion_comment_keywords",
                display_name="A2剧情讨论评论语料包",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        {
                            "category_code": "persona",
                            "category_name": "人设",
                            "sub_keywords": [
                                {
                                    "keyword_code": "plot_mom",
                                    "keyword_name": "剧情接话妈妈",
                                    "corpus": ["像妈妈在评论区接剧情，不从全局活动池里乱抽格式。"],
                                }
                            ],
                        }
                    ]
                },
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={
            "asset_key": "yuanyue_comment_activity",
            "keyword_asset_key": "a2_plot_discussion_comment_keywords",
            "created_by": "ops",
        },
    )

    assert response.status_code == 200
    first = response.json()["data"]["report"]["items"][0]
    assert first["generation_snapshot"]["keyword_asset"]["asset_key"] == "a2_plot_discussion_comment_keywords"
    assert first["generation_snapshot"]["selected_keywords"][0]["keyword_name"] == "剧情接话妈妈"

    async with session_factory() as session:
        item = (
            await session.execute(select(ContentBatchItem).order_by(ContentBatchItem.item_no))
        ).scalars().first()

    assert item.plan_json["keyword_asset_key"] == "a2_plot_discussion_comment_keywords"
    assert item.plan_json["unified_generation"]["keyword_asset"]["asset_key"] == "a2_plot_discussion_comment_keywords"


@pytest.mark.asyncio
async def test_batch_report_can_export_generated_results_excel(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )
    assert start_response.status_code == 200
    batch_id = start_response.json()["data"]["batch_id"]

    response = await client.get(f"/api/v1/content-agent/batches/{batch_id}/export.xlsx")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    workbook = load_workbook(BytesIO(response.content))
    assert workbook.sheetnames == ["批次概览", "生文结果"]
    overview = workbook["批次概览"]
    result = workbook["生文结果"]
    assert overview["A1"].value == "字段"
    assert overview["B5"].value == "美素佳儿源悦活动评论"
    assert result["A1"].value == "序号"
    assert result["D1"].value == "正文"
    assert result["D2"].value == "我家刚开始也在看源悦，想蹲蹲真实反馈"
    assert result["R1"].value == "系统语料包"


@pytest.mark.asyncio
async def test_article_batch_can_start_from_product_experience_rule_asset_key_only(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    response = await client.post(
        "/api/v1/content-agent/batches/start",
        json={"asset_key": "yuanyue_product_experience", "created_by": "ops"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["execution"]["requested_limit"] == 2
    assert data["execution"]["generated_count"] == 2
    report = data["report"]
    assert report["asset_key"] == "yuanyue_product_experience"
    assert report["product_topic"] == "美素佳儿源悦活动生文"
    assert report["items"][0]["title"]
    assert report["items"][0]["body"]

    async with session_factory() as session:
        item = (
            await session.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == data["batch_id"])
                .order_by(ContentBatchItem.item_no)
            )
        ).scalars().first()

    assert item.plan_json["rule_type"] == "product_experience"
    assert item.plan_json["product_experience"] == "0-6个月，3个月内，奶量补充"
    assert item.plan_json["unified_generation"]["capability"] == "content.generate"
    assert [kw["category_code"] for kw in item.plan_json["unified_generation"]["selected_keywords"]] == [
        "persona",
        "writing_instruction",
        "perturbation_rule",
        "writing_method",
        "article_format_control",
    ]


@pytest.mark.asyncio
async def test_comment_batch_runs_forbidden_term_review_and_rewrite(content_agent_workbench_client):
    client, session_factory = content_agent_workbench_client
    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="business_forbidden_terms",
                asset_key="yuanyue_comment_activity",
                display_name="源悦评论业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "schema_version": "1",
                    "terms": [{"term": "源悦", "enabled": True}],
                },
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )

    assert response.status_code == 200
    report = response.json()["data"]["report"]
    first = report["items"][0]
    assert "源悦" not in first["body"]
    assert first["forbidden_hits"] == []
    assert first["quality"]["forbidden_terms_review"]["initial_hits"] == ["源悦"]
    assert first["quality"]["forbidden_terms_review"]["final_hits"] == []
    assert first["quality"]["review_report"]["hard_results"][-1]["ae_code"] == "forbidden_terms_guard"
    assert first["generation_snapshot"]["forbidden_terms_review"]["initial_hits"] == ["源悦"]
    assert first["generation_snapshot"]["rewrite_records"][0]["capability"] == "content.rewrite"
    assert "源悦" in first["generation_snapshot"]["rewrite_records"][0]["before"]["comment"]
    assert "源悦" not in first["generation_snapshot"]["rewrite_records"][0]["after"]["comment"]
    assert report["summary"]["rewrite_item_count"] >= 1

    async with session_factory() as session:
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert any(stage.capability == "content.rewrite" for stage in stage_calls)


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
    assert manual_data["item"]["version_compare"]["compare_type"] == "manual_edit"
    assert manual_data["item"]["version_compare"]["before"]["body"] == item["body"]
    assert manual_data["item"]["version_compare"]["after"]["body"] == "这是运营人工改后的正文，保留真实经历，也避免医疗化表达。"
    assert manual_data["item"]["version_compare"]["body_changed"] is True

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
    assert report_item["version_compare"]["compare_type"] == "manual_edit"
    assert report_item["version_compare"]["after"]["body"] == "这是运营人工改后的正文，保留真实经历，也避免医疗化表达。"


@pytest.mark.asyncio
async def test_batch_feedback_can_auto_rewrite_from_operator_revision(content_agent_workbench_client):
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
    original_body = item["body"]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头再具体一点，少一点总结腔。",
            "quoted_text": "原正文比较总结。",
            "feedback_categories": ["unnatural", "too_ad_like", "unknown"],
            "auto_rewrite": True,
            "created_by": "reviewer-a",
        },
    )

    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["review_status"] == "needs_revision"
    assert feedback_data["version_no"] == 2
    rewritten = feedback_data["item"]
    assert rewritten["status"] == "needs_revision"
    assert rewritten["body"] != original_body
    assert "按运营反馈调整：开头再具体一点" in rewritten["body"]
    assert rewritten["quality"]["human_review"]["auto_rewrite"]["source"] == "operator_feedback"
    assert rewritten["quality"]["review_report"]["rewrite_reason"] == "operator_feedback"
    assert rewritten["generation_snapshot"]["rewrite_records"][-1]["capability"] == "content.rewrite"
    assert rewritten["version_compare"]["compare_type"] == "auto_rewrite"
    assert rewritten["version_compare"]["before"]["body"] == original_body
    assert rewritten["version_compare"]["after"]["body"] == rewritten["body"]
    assert rewritten["version_compare"]["body_changed"] is True

    async with session_factory() as session:
        versions = (
            await session.execute(
                select(ContentBatchItemVersion)
                .where(ContentBatchItemVersion.item_id == item["item_id"])
                .order_by(ContentBatchItemVersion.version_no)
            )
        ).scalars().all()
        feedback = (await session.execute(select(ContentFeedback))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert [version.source_action for version in versions] == ["request_revision", "auto_rewrite"]
    assert feedback.metadata_json["auto_rewrite"] is True
    assert feedback.metadata_json["auto_rewrite_version_id"] == versions[-1].id
    assert any(stage.capability == "content.rewrite" for stage in stage_calls)
    rewrite_stage = next(stage for stage in stage_calls if stage.capability == "content.rewrite")
    rewrite_input = rewrite_stage.input_snapshot or {}
    rewrite_instructions = "\n".join(rewrite_input.get("rewrite_instructions") or [])
    assert rewrite_input["rewrite_source"] == "operator_feedback"
    assert rewrite_input["quoted_text"] == "原正文比较总结。"
    assert rewrite_input["feedback_categories"] == ["unnatural", "too_ad_like"]
    assert rewrite_input["model_config"]["temperature"] >= 0.55
    assert "不是违禁词替换" in rewrite_instructions
    assert "不要只做同义替换" in rewrite_instructions
    assert "运营圈选的原文片段：原正文比较总结。" in rewrite_instructions
    assert "不自然/生硬" in rewrite_instructions
    assert feedback.quoted_text == "原正文比较总结。"
    assert feedback.metadata_json["feedback_categories"] == ["unnatural", "too_ad_like"]


@pytest.mark.asyncio
async def test_batch_feedback_insights_summarize_operator_feedback(content_agent_workbench_client):
    client, _session_factory = content_agent_workbench_client
    start_response = await client.post(
        "/api/v1/content-agent/comment-batches/start",
        json={"asset_key": "yuanyue_comment_activity", "created_by": "ops"},
    )
    item = start_response.json()["data"]["report"]["items"][0]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "这句有点像广告口吻，不够像真实评论。",
            "quoted_text": "想蹲蹲真实反馈",
            "feedback_categories": ["too_ad_like", "unnatural", "unknown"],
            "created_by": "reviewer-a",
        },
    )
    assert feedback_response.status_code == 200

    insight_response = await client.get(
        f"/api/v1/content-agent/batches/{start_response.json()['data']['batch_id']}/feedback-insights"
    )

    assert insight_response.status_code == 200
    insights = insight_response.json()["data"]
    assert insights["total_feedback_count"] == 1
    assert insights["category_stats"] == [
        {"code": "unnatural", "label": "不自然/生硬", "count": 1},
        {"code": "too_ad_like", "label": "广告感太强", "count": 1},
    ]
    assert insights["action_stats"] == [{"code": "request_revision", "label": "要求修改", "count": 1}]
    assert insights["samples"][0]["quoted_text"] == "想蹲蹲真实反馈"
    assert insights["samples"][0]["feedback_categories"] == ["too_ad_like", "unnatural"]
    assert insights["suggestions"][0]["suggestion_type"] == "system_keyword"
    assert insights["suggestions"][0]["target"] == "系统关键词 / 生评论指令"
    assert "广告口吻" in insights["suggestions"][0]["evidence"][0]


@pytest.mark.asyncio
async def test_batch_feedback_can_accept_auto_rewrite(content_agent_workbench_client):
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

    rewrite_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头再具体一点，少一点总结腔。",
            "auto_rewrite": True,
            "created_by": "reviewer-a",
        },
    )
    rewritten = rewrite_response.json()["data"]["item"]

    accept_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={"action": "accept_rewrite", "created_by": "reviewer-a"},
    )

    assert accept_response.status_code == 200
    accepted = accept_response.json()["data"]["item"]
    assert accepted["status"] == "approved"
    assert accepted["review_status"] == "approved"
    assert accepted["body"] == rewritten["body"]
    assert accepted["version_compare"]["compare_type"] == "accept_rewrite"
    assert accepted["version_compare"]["after"]["body"] == rewritten["body"]


@pytest.mark.asyncio
async def test_batch_feedback_can_reject_auto_rewrite_and_restore_source(content_agent_workbench_client):
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
    original_body = item["body"]

    rewrite_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": "开头再具体一点，少一点总结腔。",
            "auto_rewrite": True,
            "created_by": "reviewer-a",
        },
    )
    rewritten_body = rewrite_response.json()["data"]["item"]["body"]

    reject_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={"action": "reject_rewrite", "created_by": "reviewer-a"},
    )

    assert reject_response.status_code == 200
    rejected = reject_response.json()["data"]["item"]
    assert rejected["status"] == "needs_revision"
    assert rejected["review_status"] == "needs_revision"
    assert rejected["body"] == original_body
    assert rejected["version_compare"]["compare_type"] == "reject_rewrite"
    assert rejected["version_compare"]["before"]["body"] == rewritten_body
    assert rejected["version_compare"]["after"]["body"] == original_body


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
async def test_operator_feedback_can_add_business_forbidden_term(content_agent_workbench_client):
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
    term = item["body"][:4]

    feedback_response = await client.post(
        f"/api/v1/content-agent/batch-items/{item['item_id']}/feedback",
        json={
            "action": "request_revision",
            "feedback_text": f"加入业务违禁词：{term}",
            "business_forbidden_terms": [term],
            "created_by": "ops",
        },
    )

    assert feedback_response.status_code == 200
    feedback_data = feedback_response.json()["data"]
    assert feedback_data["item"]["review_status"] == "needs_revision"
    assert term not in feedback_data["item"]["body"]
    assert term not in feedback_data["item"]["forbidden_hits"]
    assert feedback_data["item"]["quality"]["forbidden_terms_review"]["initial_hits"] == [term]
    assert feedback_data["item"]["quality"]["forbidden_terms_review"]["final_hits"] == []

    report_response = await client.get(
        f"/api/v1/content-agent/batches/{start_response.json()['data']['batch_id']}/report"
    )
    report = report_response.json()["data"]
    assert term not in report["items"][0]["body"]
    assert term not in report["items"][0]["forbidden_hits"]
    assert report["summary"]["forbidden_hit_count"] == 0

    async with session_factory() as session:
        asset = (
            await session.execute(
                select(AssetRegistry).where(
                    AssetRegistry.asset_type == "business_forbidden_terms",
                    AssetRegistry.asset_key == "yuanyue",
                    AssetRegistry.status == "active",
                )
            )
        ).scalar_one()
        feedback = (await session.execute(select(ContentFeedback))).scalar_one()
        change_request = (await session.execute(select(AssetChangeRequest))).scalar_one_or_none()

    assert asset.content_json["terms"][-1]["term"] == term
    assert feedback.metadata_json["business_forbidden_terms"] == [term]
    assert feedback.metadata_json["business_forbidden_terms_added"] == [term]
    assert feedback.metadata_json["forbidden_terms_review"]["initial_hits"] == [term]
    assert feedback.metadata_json["forbidden_terms_review"]["final_hits"] == []
    assert change_request is None


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

    response = await client.get("/api/v1/content-agent/feedback-samples")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["items"][0]["review_status"] == "approved"
    assert data["items"][0]["comment"] == "修改后可发布"
    assert data["items"][0]["product_topic"] == "宝宝便便不规律"
    assert data["items"][0]["body_preview"]

    filtered = await client.get(
        "/api/v1/content-agent/feedback-samples",
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
        AssetRegistry(
            asset_type="product_experience_rule_set",
            asset_key="yuanyue_product_experience",
            display_name="源悦产品使用体验规则",
            version_no=1,
            status="active",
            asset_stage="production",
            content_json={
                "rule_type": "product_experience",
                "activity_name": "美素佳儿源悦活动生文",
                "default_generation_count": 10,
                "items": [
                    {
                        "rule_id": "product_experience_001",
                        "product_experience": "0-6个月，3个月内，奶量补充",
                        "baby_stage": "0-6个月",
                        "use_duration": "3个月内",
                        "topic": "奶量补充",
                        "corpus": "围绕0-6个月宝宝的奶量补充体验自然展开。",
                        "examples": ["刚换源悦那阵子，喂奶没之前那么拉扯。"],
                        "source_row_no": 1,
                    },
                    {
                        "rule_id": "product_experience_002",
                        "product_experience": "7-12个月，3-6个月，消化吸收",
                        "baby_stage": "7-12个月",
                        "use_duration": "3-6个月",
                        "topic": "消化吸收",
                        "corpus": "围绕喝完后的肚肚状态和便便节奏自然展开。",
                        "examples": ["主要看喝完后的肚肚状态和便便节奏。"],
                        "source_row_no": 2,
                    },
                ],
            },
            metadata_json={
                "rule_type": "product_experience",
                "default_generation_count": 10,
                "rule_count": 2,
                "example_count": 2,
            },
        ),
    ]
