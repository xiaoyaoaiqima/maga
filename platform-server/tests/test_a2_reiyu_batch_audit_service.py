from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import ContentBatchItem, ContentBatchJob
from app.models.maga_assets import AssetRegistry
from app.services.a2_reiyu_batch_audit_service import (
    A2ReiyuBatchAuditDispatcher,
    A2ReiyuBatchAuditService,
)
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.product_experience_llm_review_service import ProductExperienceLLMReview


A2_ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"


class PassingGoldReviewer:
    def __init__(self) -> None:
        self.calls = 0

    async def review(self, **_kwargs) -> ProductExperienceLLMReview:
        self.calls += 1
        return ProductExperienceLLMReview(
            pass_=True,
            rewrite_required=False,
            severity="pass",
            business_usability_tier="direct_pool",
            business_usability_reason="通过",
            review_rubric_code="a2_reiyu_business_usability_v1",
        )


class HoldoutGoldReviewer:
    async def review(self, **_kwargs) -> ProductExperienceLLMReview:
        return ProductExperienceLLMReview(
            pass_=False,
            rewrite_required=True,
            severity="hard",
            business_usability_tier="hold_out",
            business_usability_reason="积分礼品事实错误",
            review_rubric_code="a2_reiyu_business_usability_v1",
        )


@pytest.mark.asyncio
async def test_independent_a2_audit_runs_guards_then_gold_and_clears_audit_skipped() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ContentBatchJob.__table__,
                ContentBatchItem.__table__,
                AssetRegistry.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    reviewer = PassingGoldReviewer()

    async with session_factory() as db:
        job = ContentBatchJob(
            batch_code="a2-independent-audit",
            asset_key=A2_ASSET_KEY,
            product_topic="a2礼遇",
            count=5,
            status="generated",
            strategy_json={"postprocess_mode": "generate_only"},
        )
        db.add(job)
        await db.flush()
        db.add(
            AssetRegistry(
                asset_type="business_forbidden_terms",
                asset_key=A2_ASSET_KEY,
                display_name="a2礼遇审核词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "terms": [
                        {
                            "term": "羊毛",
                            "enabled": True,
                            "enforcement": "model_rewrite",
                            "reason": "交给后链路自然改写",
                        },
                        {
                            "term": "空罐",
                            "enabled": True,
                            "enforcement": "hard_ban",
                            "reason": "旧罐不能参加",
                        },
                    ]
                },
            )
        )
        base_quality = {
            "hard_pass": False,
            "audit_skipped": True,
            "review_report": {"audit_skipped": True},
        }
        db.add_all(
            [
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=1,
                    status="generated",
                    title="a2至初活动分享",
                    body="参加完活动才知道，a2至初现在每批都有检测。",
                    plan_json={"asset_key": A2_ASSET_KEY},
                    quality_json=base_quality,
                ),
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=2,
                    status="generated",
                    title="a2至初集罐",
                    body="以前的罐子也能参加集罐，a2至初现在每批都有检测。",
                    plan_json={"asset_key": A2_ASSET_KEY},
                    quality_json=base_quality,
                ),
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=3,
                    status="generated",
                    title="a2至初老客分享",
                    body="我家从出生就喝a2至初，后来转奶也很顺利。",
                    plan_json={"asset_key": A2_ASSET_KEY},
                    quality_json=base_quality,
                ),
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=4,
                    status="generated",
                    title="a2至初活动福利",
                    body="这波羊毛挺实在，a2至初现在每批都有检测。",
                    plan_json={"asset_key": A2_ASSET_KEY},
                    quality_json=base_quality,
                ),
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=5,
                    status="generated",
                    title="a2至初集罐",
                    body="空罐可以参加集罐，a2至初现在每批都有检测。",
                    plan_json={"asset_key": A2_ASSET_KEY},
                    quality_json=base_quality,
                ),
            ]
        )
        await db.commit()

        execution = ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
            session_factory=session_factory,
            product_experience_llm_reviewer=reviewer,
        )
        result = await execution.review_a2_reiyu_items(job.id, concurrency=1)

    assert result.guard_issue_count >= 4
    assert result.business_review.reviewed_count == 3
    assert result.business_review.skipped_count == 2
    assert reviewer.calls == 3

    async with session_factory() as db:
        items = list(
            (
                await db.execute(
                    select(ContentBatchItem)
                    .where(ContentBatchItem.batch_id == job.id)
                    .order_by(ContentBatchItem.item_no)
                )
            ).scalars().all()
        )

    assert items[0].quality_json["hard_pass"] is True, items[0].quality_json
    assert items[0].quality_json["postprocess_mode"] == "independent_audit"
    assert "audit_skipped" not in items[0].quality_json
    assert items[1].quality_json["hard_pass"] is False
    assert items[1].quality_json["a2_reiyu_old_can_guard"]["pass"] is False
    assert items[2].quality_json["hard_pass"] is True
    assert items[2].quality_json["a2_reiyu_text_guard"]["business_usability_tier"] == "light_fix_usable"
    assert items[3].quality_json["hard_pass"] is True
    assert items[3].quality_json["a2_reiyu_forbidden_terms_guard"]["business_usability_tier"] == "light_fix_usable"
    assert items[4].quality_json["hard_pass"] is False
    assert items[4].quality_json["a2_reiyu_forbidden_terms_guard"]["business_usability_tier"] == "hold_out"
    await engine.dispose()


@pytest.mark.asyncio
async def test_independent_a2_audit_keeps_gold_holdout_out_of_hard_pass() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[ContentBatchJob.__table__, ContentBatchItem.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        job = ContentBatchJob(
            batch_code="a2-gold-holdout",
            asset_key=A2_ASSET_KEY,
            product_topic="a2礼遇",
            count=1,
            status="generated",
            strategy_json={"postprocess_mode": "generate_only"},
        )
        db.add(job)
        await db.flush()
        db.add(
            ContentBatchItem(
                batch_id=job.id,
                item_no=1,
                status="generated",
                title="a2至初积分活动",
                body="积分可以兑换素材未提供的奶粉奖品。",
                plan_json={"asset_key": A2_ASSET_KEY},
                quality_json={"hard_pass": False, "audit_skipped": True},
            )
        )
        await db.commit()

        execution = ContentBatchExecutionService(
            db,
            callback_base_url="/api/v1/content-agent",
            session_factory=session_factory,
            product_experience_llm_reviewer=HoldoutGoldReviewer(),
        )
        await execution.review_a2_reiyu_items(job.id, concurrency=1)

    async with session_factory() as db:
        item = (
            await db.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id))
        ).scalar_one()

    assert item.quality_json["product_experience_llm_quality_review"]["pass"] is False
    assert item.quality_json["product_experience_llm_quality_review"]["business_usability_tier"] == "hold_out"
    assert item.quality_json["hard_pass"] is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_a2_audit_task_deduplicates_queue_and_marks_failure_as_watch() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[ContentBatchJob.__table__, ContentBatchItem.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    class FailingExecutionService:
        async def review_a2_reiyu_items(self, batch_id: int, *, concurrency: int):
            assert concurrency == 7
            raise RuntimeError("judge unavailable")

    async with session_factory() as db:
        job = ContentBatchJob(
            batch_code="a2-independent-audit-failure",
            asset_key=A2_ASSET_KEY,
            product_topic="a2礼遇",
            count=1,
            status="generated",
            strategy_json={},
        )
        db.add(job)
        await db.flush()
        db.add(
            ContentBatchItem(
                batch_id=job.id,
                item_no=1,
                status="generated",
                title="a2至初活动",
                body="a2至初现在每批都有检测。",
                plan_json={"asset_key": A2_ASSET_KEY},
                quality_json={"hard_pass": False, "audit_skipped": True},
            )
        )
        await db.commit()

        service = A2ReiyuBatchAuditService(
            db,
            execution_service=FailingExecutionService(),
        )
        assert await service.queue(job.id, concurrency=7) is True
        assert await service.queue(job.id, concurrency=7) is False
        await db.commit()
        assert await service.run(job.id) is None

    async with session_factory() as db:
        persisted_job = await db.get(ContentBatchJob, job.id)
        item = (
            await db.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id))
        ).scalar_one()

    state = persisted_job.strategy_json["a2_reiyu_audit"]
    assert state["status"] == "failed"
    assert state["error"] == "judge unavailable"
    assert item.quality_json["hard_pass"] is False
    assert item.quality_json["product_experience_llm_quality_review"]["business_usability_tier"] == "watch"
    await engine.dispose()


@pytest.mark.asyncio
async def test_pending_a2_audit_is_requeued_after_process_restart(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[ContentBatchJob.__table__])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        job = ContentBatchJob(
            batch_code="a2-audit-recovery",
            asset_key=A2_ASSET_KEY,
            product_topic="a2礼遇",
            count=1,
            status="generated",
            strategy_json={
                "a2_reiyu_audit": {
                    "status": "running",
                    "concurrency": 10,
                }
            },
        )
        db.add(job)
        await db.commit()

    dispatched: list[int] = []

    def fake_dispatch(cls, batch_id: int, *, session_factory) -> bool:
        dispatched.append(batch_id)
        return True

    monkeypatch.setattr(
        A2ReiyuBatchAuditDispatcher,
        "dispatch",
        classmethod(fake_dispatch),
    )
    resumed = await A2ReiyuBatchAuditDispatcher.resume_pending(
        session_factory=session_factory,
    )

    assert resumed == 1
    assert dispatched == [job.id]
    async with session_factory() as db:
        persisted = await db.get(ContentBatchJob, job.id)
    assert persisted.strategy_json["a2_reiyu_audit"]["status"] == "queued"
    assert persisted.strategy_json["a2_reiyu_audit"]["resumed_at"]
    await engine.dispose()
