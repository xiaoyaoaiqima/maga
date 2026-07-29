from __future__ import annotations

import asyncio
import json

from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem
from app.services.business_forbidden_term_service import (
    A2_REIYU_UGC_POST_ASSET_KEY,
    BusinessForbiddenTermService,
)
from app.services.forbidden_term_review_service import ForbiddenTermReviewService


async def main() -> None:
    async with async_session_factory() as db:
        result = await BusinessForbiddenTermService(db).upsert_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            entries=[
                {
                    "term": "😂",
                    "reason": "运营新增禁用emoji，后链路确定性移除",
                    "replacement": "",
                    "enforcement": "replace",
                    "match_mode": "literal",
                    "source": "operator_rule_20260728",
                }
            ],
            created_by="ops",
        )
        item = ContentBatchItem(
            title="a2活动挺实在😂",
            body="老客看到这次活动，确实挺心动😂",
            run_id=1,
        )
        review = await ForbiddenTermReviewService(db).review_and_rewrite_item(
            item=item,
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            orchestrator=None,
            executor_code=None,
            content_type="article",
        )
        await db.commit()
        print(
            json.dumps(
                {
                    "asset_version": result.asset.version_no if result.asset else None,
                    "added_terms": result.added_terms,
                    "updated_terms": result.updated_terms,
                    "title": item.title,
                    "body": item.body,
                    "rewrite_method": review.get("rewrite_method"),
                    "final_hits": review.get("final_hits"),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
