from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.executor_invocation_service import DirectLLMInvocationClient
from app.services.forbidden_term_review_service import ForbiddenTermReviewService

from repair_and_reaudit import ASSET_KEY, clear_review_state


async def rewrite_forbidden_term() -> dict[str, object]:
    attempts = []
    for attempt in range(1, 4):
        async with async_session_factory() as db:
            item = (
                await db.execute(
                    select(ContentBatchItem).where(
                        ContentBatchItem.batch_id == 873,
                        ContentBatchItem.item_no == 14,
                    )
                )
            ).scalar_one()
            executor = await ContentAgentService(db).get_executor(DEFAULT_EXECUTOR_CODE)
            if executor is None:
                raise RuntimeError(f"executor not found: {DEFAULT_EXECUTOR_CODE}")
            review = await ForbiddenTermReviewService(db).review_and_rewrite_item(
                item=item,
                asset_key=ASSET_KEY,
                orchestrator=ContentAgentOrchestrator(
                    db,
                    invocation_client=DirectLLMInvocationClient(),
                    callback_base_url="/api/v1/content-agent",
                ),
                executor_code=DEFAULT_EXECUTOR_CODE,
                content_type="article",
            )
            attempts.append(
                {
                    "attempt": attempt,
                    "rewrite_method": review.get("rewrite_method"),
                    "final_hits": review.get("final_hits") or [],
                    "last_error": review.get("last_error"),
                }
            )
            if not review.get("final_hits"):
                clear_review_state(item)
                await db.commit()
                return {"success": True, "attempts": attempts}
            await db.rollback()
    async with async_session_factory() as db:
        item = (
            await db.execute(
                select(ContentBatchItem).where(
                    ContentBatchItem.batch_id == 873,
                    ContentBatchItem.item_no == 14,
                )
            )
        ).scalar_one()
        item.body = (item.body or "").replace(
            "正好家里娃一直喝这个，囤货顺便攒罐，一举两得。",
            "正好家里娃一直喝这个，补货时参加集罐，一举两得。",
        )
        final_audit = await ForbiddenTermReviewService(db).audit_text(
            asset_key=ASSET_KEY,
            title=item.title or "",
            body=item.body or "",
        )
        if final_audit.hits:
            await db.rollback()
            return {"success": False, "attempts": attempts, "final_hits": final_audit.hits}
        clear_review_state(item)
        await db.commit()
    return {"success": True, "attempts": attempts, "fallback": "sentence_level_minimal_rewrite"}


async def fix_batch_detection() -> None:
    async with async_session_factory() as db:
        item = (
            await db.execute(
                select(ContentBatchItem).where(
                    ContentBatchItem.batch_id == 874,
                    ContentBatchItem.item_no == 94,
                )
            )
        ).scalar_one()
        item.body = (item.body or "").replace(
            "至少知道每罐都经过检查，让人放心",
            "知道现在每批都有检测，让人放心",
        )
        clear_review_state(item)
        await db.commit()


async def main() -> None:
    rewrite = await rewrite_forbidden_term()
    if not rewrite["success"]:
        raise RuntimeError(json.dumps(rewrite, ensure_ascii=False))
    await fix_batch_detection()
    results = []
    for batch_id in (873, 874):
        async with async_session_factory() as db:
            result = await ContentBatchExecutionService(
                db,
                callback_base_url="/api/v1/content-agent",
            ).review_a2_reiyu_items(batch_id, concurrency=2)
            await db.commit()
            results.append(
                {
                    "batch_id": batch_id,
                    "guard_issue_count": result.guard_issue_count,
                    "reviewed_count": result.business_review.reviewed_count,
                    "skipped_count": result.business_review.skipped_count,
                    "failed_count": result.business_review.failed_count,
                    "tier_counts": result.business_review.tier_counts,
                }
            )
    print(json.dumps({"rewrite": rewrite, "audit": results}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
