"""Tests for business forbidden-term ledger entries."""

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
from app.models.content_agent import ContentBatchItem
from app.models.maga_assets import AssetRegistry
from app.models.maga_core import MAGA_CORE_TABLE_NAMES
from app.services.business_forbidden_term_service import (
    A2_REIYU_QWEN_PLUS_MODEL_CONFIG,
    A2_REIYU_UGC_POST_ASSET_KEY,
    A2_SENTIMENT_COMMENT_ASSET_KEY,
    BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
    BusinessForbiddenTermService,
)
from app.services.content_agent_bootstrap_service import (
    seed_a2_reiyu_forbidden_terms,
    seed_a2_sentiment_comment_forbidden_terms,
)
from app.services.forbidden_term_review_service import ForbiddenTermReviewService


@pytest_asyncio.fixture
async def forbidden_term_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


class RecordingRewriteOrchestrator:
    def __init__(self, output: dict):
        self.output = output
        self.calls: list[dict] = []

    async def run_content_rewrite_stage(self, *, run_id, executor_code, input_payload):
        self.calls.append(input_payload)
        return SimpleNamespace(output=self.output)


@pytest.mark.asyncio
async def test_business_forbidden_terms_keep_legacy_string_terms(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                asset_key="legacy_comment_activity",
                display_name="旧格式业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={"schema_version": "1", "terms": ["源悦"]},
            )
        )
        await session.commit()

        service = BusinessForbiddenTermService(session)
        assert await service.list_terms(asset_key="legacy_comment_activity", include_default=False) == ["源悦"]
        entries = await service.list_entries(asset_key="legacy_comment_activity", include_default=False)

    assert entries[0]["term"] == "源悦"
    assert entries[0]["enabled"] is True


@pytest.mark.asyncio
async def test_business_forbidden_term_entries_upsert_reason_and_disable(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        service = BusinessForbiddenTermService(session)
        first = await service.upsert_entries(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            entries=[
                {
                    "term": "小程序",
                    "reason": "小红书不能出现微信生态的词",
                    "replacement": "",
                }
            ],
            created_by="ops",
        )
        second = await service.upsert_entries(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            entries=[
                {
                    "term": "小程序",
                    "reason": "平台侧禁止微信生态露出",
                    "replacement": "平台入口",
                }
            ],
            created_by="ops2",
        )
        entries = await service.list_entries(asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY, include_default=False)
        await service.set_enabled(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            term="小程序",
            enabled=False,
            created_by="ops2",
        )
        disabled_terms = await service.list_terms(asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY, include_default=False)
        disabled_entries = await service.list_entries(asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY, include_default=False)
        disabled_audit = await ForbiddenTermReviewService(session).audit_text(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            title=None,
            body="可以去小程序看一下",
        )

    assert first.added_terms == ["小程序"]
    assert second.added_terms == []
    assert second.updated_terms == ["小程序"]
    assert [entry["term"] for entry in entries] == ["小程序"]
    assert entries[0]["reason"] == "平台侧禁止微信生态露出"
    assert entries[0]["replacement"] == "平台入口"
    assert disabled_terms == []
    assert disabled_entries[0]["enabled"] is False
    assert disabled_audit.hits == []


@pytest.mark.asyncio
async def test_a2_forbidden_term_audit_is_asset_scoped(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            entries=[{"term": "小程序", "reason": "小红书不能出现微信生态的词"}],
            created_by="ops",
        )
        await session.commit()

        review_service = ForbiddenTermReviewService(session)
        other_audit = await review_service.audit_text(
            asset_key="other_comment_activity",
            title=None,
            body="可以去小程序看一下",
        )
        item = ContentBatchItem(body="可以去小程序看一下")
        review = await review_service.review_and_rewrite_item(
            item=item,
            asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
            orchestrator=None,
            executor_code=None,
            content_type="comment",
        )

    assert other_audit.hits == []
    assert review["initial_hits"] == ["小程序"]
    assert review["final_hits"] == []
    assert "小程序" not in item.body


@pytest.mark.asyncio
async def test_layered_replace_is_deterministic_without_model_call(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {
                    "term": "A2至初",
                    "replacement": "a2至初",
                    "enforcement": "replace",
                }
            ],
            created_by="ops",
        )
        item = ContentBatchItem(title="A2至初活动", body="我家一直喝A2至初", run_id=1)
        orchestrator = RecordingRewriteOrchestrator({"title": "不应调用", "body": "不应调用"})
        review = await ForbiddenTermReviewService(session).review_and_rewrite_item(
            item=item,
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            orchestrator=orchestrator,
            executor_code="test",
            content_type="article",
        )

    assert orchestrator.calls == []
    assert item.title == "a2至初活动"
    assert item.body == "我家一直喝a2至初"
    assert review["rewrite_method"] == "deterministic_replace"
    assert review["final_hits"] == []


@pytest.mark.asyncio
async def test_deterministic_title_removal_preserves_body_terminal_punctuation(forbidden_term_session_factory):
    asset_key = "article_title_only_forbidden_term"
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=asset_key,
            entries=[
                {
                    "term": "🍼",
                    "replacement": "",
                    "enforcement": "replace",
                }
            ],
            created_by="ops",
        )
        item = ContentBatchItem(title="🍼最近的小变化", body="孩子今天状态不错。", run_id=1)
        orchestrator = RecordingRewriteOrchestrator({"title": "不应调用", "body": "不应调用"})
        review = await ForbiddenTermReviewService(session).review_and_rewrite_item(
            item=item,
            asset_key=asset_key,
            orchestrator=orchestrator,
            executor_code="test",
            content_type="article",
        )

    assert orchestrator.calls == []
    assert item.title == "最近的小变化"
    assert item.body == "孩子今天状态不错。"
    assert review["rewrite_method"] == "deterministic_replace"
    assert review["final_hits"] == []


@pytest.mark.asyncio
async def test_a2_reiyu_lexical_normalization_is_fully_downstream(forbidden_term_session_factory):
    replacements = {
        "肚子": "肚肚",
        "便便": "💩",
        "粑粑": "💩",
        "眼睛": "👀",
        "QQ": "🌍",
        "朋友圈": "pyq",
    }
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {"term": term, "replacement": replacement, "enforcement": "replace"}
                for term, replacement in replacements.items()
            ],
            created_by="ops",
        )
        item = ContentBatchItem(
            title="眼睛看到的",
            body="宝宝肚子舒服，便便粑粑都正常，QQ上也有人聊，朋友圈也刷到了。",
            run_id=1,
        )
        orchestrator = RecordingRewriteOrchestrator({"title": "不应调用", "body": "不应调用"})
        review = await ForbiddenTermReviewService(session).review_and_rewrite_item(
            item=item,
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            orchestrator=orchestrator,
            executor_code="test",
            content_type="article",
        )

    assert orchestrator.calls == []
    assert item.title == "👀看到的"
    assert item.body == "宝宝肚肚舒服，💩💩都正常，🌍上也有人聊，pyq也刷到了。"
    assert review["rewrite_method"] == "deterministic_replace"
    assert review["final_hits"] == []


@pytest.mark.asyncio
async def test_layered_model_rewrite_uses_qwen_plus_and_preserves_facts(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {
                    "term": "羊毛",
                    "enforcement": "model_rewrite",
                    "rewrite_model_config": A2_REIYU_QWEN_PLUS_MODEL_CONFIG,
                }
            ],
            created_by="ops",
        )
        item = ContentBatchItem(
            title="宝爸发现的活动",
            body="宝爸刷到后说有羊毛，积分、集罐、抽奖都有，而且a2至初现在每批都有检测。",
            run_id=1,
            plan_json={"asset_key": A2_REIYU_UGC_POST_ASSET_KEY},
        )
        orchestrator = RecordingRewriteOrchestrator(
            {
                "title": "宝爸发现的活动",
                "body": "宝爸刷到后说福利挺好，积分、集罐、抽奖都有，而且a2至初现在每批都有检测。",
            }
        )
        review = await ForbiddenTermReviewService(session).review_and_rewrite_item(
            item=item,
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            orchestrator=orchestrator,
            executor_code="test",
            content_type="article",
        )

    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["model_config"]["provider_code"] == "aliyun"
    assert orchestrator.calls[0]["model_config"]["model_code"] == "qwen-plus"
    assert orchestrator.calls[0]["rewrite_source"] == "business_forbidden_term_policy"
    assert "羊毛" not in item.body
    assert "每批都有检测" in item.body
    assert review["final_hits"] == []


@pytest.mark.asyncio
async def test_layered_model_rewrite_rejects_candidate_that_drops_detection(forbidden_term_session_factory):
    original = "宝爸说活动有羊毛，集罐、抽奖都有，而且a2至初现在每批都有检测。"
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {
                    "term": "羊毛",
                    "enforcement": "model_rewrite",
                    "rewrite_model_config": A2_REIYU_QWEN_PLUS_MODEL_CONFIG,
                }
            ],
            created_by="ops",
        )
        item = ContentBatchItem(title="活动分享", body=original, run_id=1)
        orchestrator = RecordingRewriteOrchestrator(
            {"title": "活动分享", "body": "活动福利挺好，集罐、抽奖都有。"}
        )
        review = await ForbiddenTermReviewService(session).review_and_rewrite_item(
            item=item,
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            orchestrator=orchestrator,
            executor_code="test",
            content_type="article",
            max_rounds=1,
        )

    assert item.body == original
    assert review["final_hits"] == ["羊毛"]
    assert review["rewrite_method"] == "content.rewrite_rejected"
    assert "检测" in review["last_error"]
    assert "宝爸来源" in review["last_error"]


@pytest.mark.asyncio
async def test_layered_hard_ban_blocks_without_mutating_or_calling_model(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[{"term": "空罐", "enforcement": "hard_ban", "reason": "旧罐不参与"}],
            created_by="ops",
        )
        item = ContentBatchItem(title="活动分享", body="家里的空罐也能参加", run_id=1)
        orchestrator = RecordingRewriteOrchestrator({"title": "不应调用", "body": "不应调用"})
        review = await ForbiddenTermReviewService(session).review_and_rewrite_item(
            item=item,
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            orchestrator=orchestrator,
            executor_code="test",
            content_type="article",
        )

    assert orchestrator.calls == []
    assert item.body == "家里的空罐也能参加"
    assert review["rewrite_method"] == "hard_ban"
    assert review["blocking_hits"] == ["空罐"]
    assert item.quality_json["hard_pass"] is False


@pytest.mark.asyncio
async def test_contextual_prize_term_only_blocks_in_activity_prize_sentence(forbidden_term_session_factory):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {
                    "term": "积木",
                    "enforcement": "hard_ban",
                    "match_mode": "activity_prize_context",
                }
            ],
            created_by="ops",
        )
        service = ForbiddenTermReviewService(session)
        ordinary = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="娃在客厅玩积木，我在冲奶。",
        )
        wrong_prize = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="集罐还能兑换积木。",
        )
        enumerated_prize = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="积分能换的还挺多！\n什么积木、绘本都有。",
        )
        adjacent_ordinary_scene = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="活动礼品挺丰富。娃在客厅玩积木，我在冲奶。",
        )

    assert ordinary.hits == []
    assert wrong_prize.hits == ["积木"]
    assert enumerated_prize.hits == ["积木"]
    assert adjacent_ordinary_scene.hits == []


@pytest.mark.asyncio
async def test_risk_polarity_term_allows_negated_endorsement_and_rewrites_negative_assertion(
    forbidden_term_session_factory,
):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {
                    "term": "踩雷",
                    "enforcement": "model_rewrite",
                    "match_mode": "risk_polarity_context",
                },
                {
                    "term": "翻车",
                    "enforcement": "model_rewrite",
                    "match_mode": "risk_polarity_context",
                },
            ],
            created_by="ops",
        )
        service = ForbiddenTermReviewService(session)
        endorsement = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="闭眼入不踩雷，选对了也没踩雷。",
        )
        negative_assertion = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="之前选这款真的踩雷了。",
        )
        mixed_context = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="这次没踩雷，但之前确实踩雷了。",
        )
        smooth_transition = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="转奶分享",
            body="转奶那会儿没翻车，适应得挺快。",
        )
        failed_transition = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="转奶分享",
            body="这次转奶真的翻车了。",
        )
        mixed_transition = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="转奶分享",
            body="前半程没翻车，后面还是翻车了。",
        )

    assert endorsement.hits == []
    assert negative_assertion.hits == ["踩雷"]
    assert mixed_context.hits == ["踩雷"]
    assert smooth_transition.hits == []
    assert failed_transition.hits == ["翻车"]
    assert mixed_transition.hits == ["翻车"]


@pytest.mark.asyncio
async def test_detection_page_wording_is_allowed_but_navigation_to_detection_is_rewritten(
    forbidden_term_session_factory,
):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {
                    "term": "往下翻",
                    "enforcement": "model_rewrite",
                    "match_mode": "detection_page_context",
                    "rewrite_model_config": A2_REIYU_QWEN_PLUS_MODEL_CONFIG,
                }
            ],
            created_by="ops",
        )
        service = ForbiddenTermReviewService(session)
        allowed_page_source = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="活动页面上还介绍了a2至初每批都有检测。",
        )
        allowed_navigation = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="我往下翻看了看抽奖奖品，确实挺丰富。",
        )
        wrong_navigation_source = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="我往下翻才看到a2至初现在每批都有检测。",
        )

    assert allowed_page_source.hits == []
    assert allowed_navigation.hits == []
    assert wrong_navigation_source.hits == ["往下翻"]


@pytest.mark.asyncio
async def test_a2_reiyu_seed_excludes_overbroad_operator_terms():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await seed_a2_reiyu_forbidden_terms(conn)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        entries = await BusinessForbiddenTermService(session).list_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            include_default=False,
        )
        medical_audit = await ForbiddenTermReviewService(session).audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="以前总为便秘折腾，现在说治疗便秘也不作为本活动审核项。",
        )
        anxiety_audit = await ForbiddenTermReviewService(session).audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="喝至初后踏实多了",
            body="喝a2至初以后，娃的小脸肉嘟嘟了，老母亲的焦虑一下没了。",
        )
        old_stock_audit = await ForbiddenTermReviewService(session).audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="集罐活动",
            body="正好家里囤了好几罐，集3罐就能换小车车。",
        )
    await engine.dispose()

    by_term = {entry["term"]: entry for entry in entries}
    assert by_term["A2至初"]["enforcement"] == "replace"
    assert by_term["肚子"]["replacement"] == "肚肚"
    assert {"便便", "肠胃"}.isdisjoint(by_term)
    assert by_term["粑粑"]["replacement"] == "💩"
    assert by_term["眼睛"]["replacement"] == "👀"
    assert by_term["QQ"]["replacement"] == "🌍"
    assert by_term["免费"]["replacement"] == "🆓"
    assert by_term["羊毛"]["enforcement"] == "model_rewrite"
    assert by_term["羊毛"]["rewrite_model_config"]["model_code"] == "qwen-plus"
    assert by_term["踩雷"]["match_mode"] == "risk_polarity_context"
    assert by_term["翻车"]["match_mode"] == "risk_polarity_context"
    assert by_term["报名"]["enforcement"] == "model_rewrite"
    assert by_term["报名"]["match_mode"] == "registration_required_context"
    assert {"焦虑", "担心", "不安", "不放心"}.isdisjoint(by_term)
    assert by_term["朋友圈"]["enforcement"] == "replace"
    assert by_term["朋友圈"]["replacement"] == "pyq"
    assert by_term["顺手"]["enforcement"] == "model_rewrite"
    assert {"活动页面", "页面里", "页面上"}.isdisjoint(by_term)
    assert by_term["往下翻"]["match_mode"] == "detection_page_context"
    assert by_term["翻了翻活动页面"]["match_mode"] == "detection_page_context"
    assert by_term["空罐"]["enforcement"] == "hard_ban"
    assert by_term["囤了好几罐"]["enforcement"] == "hard_ban"
    assert by_term["质量问题"]["enforcement"] == "hard_ban"
    assert by_term["问题批次"]["enforcement"] == "hard_ban"
    assert by_term["真伪"]["enforcement"] == "hard_ban"
    assert by_term["踩雷"]["enforcement"] == "model_rewrite"
    assert by_term["积木"]["match_mode"] == "activity_prize_context"
    assert {"生病", "便秘", "抵抗力", "产品", "避免"}.isdisjoint(by_term)
    assert medical_audit.hits == []
    assert anxiety_audit.hits == []
    assert old_stock_audit.hits == ["囤了好几罐"]


@pytest.mark.asyncio
async def test_a2_reiyu_registration_and_digestive_terms_use_contextual_policy(
    forbidden_term_session_factory,
):
    async with forbidden_term_session_factory() as session:
        await BusinessForbiddenTermService(session).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {
                    "term": "报名",
                    "enforcement": "model_rewrite",
                    "match_mode": "registration_required_context",
                }
            ],
            created_by="ops",
        )
        service = ForbiddenTermReviewService(session)
        allowed = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="这活动不用报名，宝宝肠胃挺适应，便便也规律。",
        )
        required = await service.audit_text(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            title="活动分享",
            body="参加前需要先报名，再去了解活动内容。",
        )

    assert allowed.hits == []
    assert required.hits == ["报名"]


@pytest.mark.asyncio
async def test_business_forbidden_term_api_lists_updates_and_disables(forbidden_term_session_factory):
    app = FastAPI()
    app.include_router(content_generation_experts.router, prefix="/api/v1/content-generation")

    async def override_get_db():
        async with forbidden_term_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/content-generation/business-forbidden-terms",
            json={
                "asset_key": A2_SENTIMENT_COMMENT_ASSET_KEY,
                "entries": [
                    {
                        "term": "小程序",
                        "reason": "小红书不能出现微信生态的词",
                    }
                ],
                "created_by": "ops",
            },
        )
        list_response = await client.get(
            "/api/v1/content-generation/business-forbidden-terms",
            params={"asset_key": A2_SENTIMENT_COMMENT_ASSET_KEY},
        )
        disable_response = await client.patch(
            "/api/v1/content-generation/business-forbidden-terms/status",
            json={
                "asset_key": A2_SENTIMENT_COMMENT_ASSET_KEY,
                "term": "小程序",
                "enabled": False,
                "updated_by": "ops",
            },
        )

    async with forbidden_term_session_factory() as session:
        active_asset_count = (
            await session.execute(
                select(AssetRegistry).where(
                    AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                    AssetRegistry.asset_key == A2_SENTIMENT_COMMENT_ASSET_KEY,
                    AssetRegistry.status == "active",
                )
            )
        ).scalars().all()

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert disable_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["reason"] == "小红书不能出现微信生态的词"
    assert disable_response.json()["data"]["items"][0]["enabled"] is False
    assert len(active_asset_count) == 1


@pytest.mark.asyncio
async def test_bootstrap_seed_updates_existing_a2_term_reason():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        tables = [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        await conn.execute(
            AssetRegistry.__table__.insert().values(
                asset_type=BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                asset_key=A2_SENTIMENT_COMMENT_ASSET_KEY,
                display_name="A2业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={"schema_version": "1", "terms": [{"term": "小程序", "enabled": True}]},
            )
        )
        await seed_a2_sentiment_comment_forbidden_terms(conn)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        active_asset = (
            await session.execute(
                select(AssetRegistry).where(
                    AssetRegistry.asset_type == BUSINESS_FORBIDDEN_TERMS_ASSET_TYPE,
                    AssetRegistry.asset_key == A2_SENTIMENT_COMMENT_ASSET_KEY,
                    AssetRegistry.status == "active",
                )
            )
        ).scalar_one()
    await engine.dispose()

    assert active_asset.version_no == 2
    assert active_asset.content_json["terms"][0]["term"] == "小程序"
    assert active_asset.content_json["terms"][0]["reason"] == "小红书不能出现微信生态的词"
    seeded_terms = {entry["term"]: entry["reason"] for entry in active_asset.content_json["terms"]}
    assert seeded_terms["0.03"] == "业务新要求：暂不露出蜡样/蜡毒检测的明确数值"
    assert seeded_terms["60+"] == "业务新要求：暂不露出检测报告/检测项目的明确数量"
    assert seeded_terms["60多项"] == "业务新要求：暂不露出检测报告/检测项目的明确数量"
    assert active_asset.metadata_json["added_term_count"] == 3
    assert active_asset.metadata_json["updated_term_count"] == 1
