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


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
REVIEW_ITEMS = {
    873: {4, 5, 9, 14, 16, 19, 21, 27, 29, 30, 33, 34, 37, 43, 45, 52, 71, 72, 75, 80, 90, 94},
    874: {2, 3, 9, 10, 11, 14, 17, 29, 42, 45, 46, 48, 56, 59, 60, 62, 78, 83, 89, 93, 94, 100},
}


def apply_manual_fix(item: ContentBatchItem) -> None:
    key = (item.batch_id, item.item_no)
    if key == (873, 19):
        item.body = (item.body or "").replace(
            "a2至初清淡不腥，淡淡奶香，冲泡时完全不挂壁不结块，粉质细腻，宝宝一口气咕咚咕咚喝光，转奶也很顺利。",
            "a2至初粉质细腻，冲泡不挂壁，淡淡奶香，宝宝一口气咕咚咕咚喝光。",
        )
    elif key == (874, 9):
        item.body = (item.body or "").replace(
            "我家娃一直喝这个，刚囤了一箱，想想还挺划算的～",
            "我家娃一直喝这个，正好也要补货，想想还挺划算的～",
        )
    elif key == (874, 10):
        item.body = (item.body or "").replace("每一罐都查", "每批都有检测")
    elif key == (874, 100):
        item.body = (item.body or "").replace("🙋‍♀️", "🙋")


def clear_review_state(item: ContentBatchItem) -> None:
    quality = dict(item.quality_json or {})
    for key in (
        "hard_pass",
        "final_postprocess_state",
        "product_experience_llm_quality_review",
        "product_experience_llm_review",
        "product_experience_llm_quality_failures",
        "a2_reiyu_text_guard",
        "a2_reiyu_batch_detection_guard",
        "a2_reiyu_old_can_guard",
        "a2_reiyu_forbidden_terms_guard",
        "business_usability_tier",
        "business_usability_reason",
    ):
        quality.pop(key, None)
    quality["review_report"] = {}
    item.quality_json = quality


async def rewrite_one(batch_id: int, item_no: int, semaphore: asyncio.Semaphore) -> dict[str, object]:
    async with semaphore:
        async with async_session_factory() as db:
            item = (
                await db.execute(
                    select(ContentBatchItem).where(
                        ContentBatchItem.batch_id == batch_id,
                        ContentBatchItem.item_no == item_no,
                    )
                )
            ).scalar_one()
            before = {"title": item.title or "", "body": item.body or ""}
            apply_manual_fix(item)
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
            clear_review_state(item)
            await db.commit()
            return {
                "batch_id": batch_id,
                "item_no": item_no,
                "changed": before != {"title": item.title or "", "body": item.body or ""},
                "rewrite_method": review.get("rewrite_method"),
                "final_hits": review.get("final_hits") or [],
                "last_error": review.get("last_error"),
            }


async def main() -> None:
    semaphore = asyncio.Semaphore(10)
    rewrites = await asyncio.gather(
        *(
            rewrite_one(batch_id, item_no, semaphore)
            for batch_id, item_nos in REVIEW_ITEMS.items()
            for item_no in sorted(item_nos)
        )
    )
    print(json.dumps({"stage": "rewritten", "items": rewrites}, ensure_ascii=False), flush=True)

    audit_results = []
    for batch_id in sorted(REVIEW_ITEMS):
        async with async_session_factory() as db:
            result = await ContentBatchExecutionService(
                db,
                callback_base_url="/api/v1/content-agent",
            ).review_a2_reiyu_items(batch_id, concurrency=10)
            await db.commit()
            audit_results.append(
                {
                    "batch_id": batch_id,
                    "guard_issue_count": result.guard_issue_count,
                    "reviewed_count": result.business_review.reviewed_count,
                    "skipped_count": result.business_review.skipped_count,
                    "failed_count": result.business_review.failed_count,
                    "tier_counts": result.business_review.tier_counts,
                }
            )
    print(json.dumps({"stage": "reaudited", "results": audit_results}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
