"""Operator review and versioning service for batch-generated content items."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import ContentBatchItem, ContentBatchItemVersion, ContentFeedback
from app.schemas.content_batch_report import (
    ContentBatchItemFeedbackRequest,
    ContentBatchItemFeedbackResponse,
)
from app.services.content_batch_report_service import ContentBatchReportService


_ACTION_STATUS = {
    "approve": "approved",
    "request_revision": "needs_revision",
    "manual_edit": "manual_edited",
}


class ContentBatchReviewService:
    """Persist operator feedback while keeping generated/edited versions auditable."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_feedback(
        self,
        item_id: int,
        request: ContentBatchItemFeedbackRequest,
    ) -> ContentBatchItemFeedbackResponse:
        item = await self._require_item(item_id)
        review_status = _ACTION_STATUS[request.action]

        if request.action == "manual_edit":
            if not (request.title and request.title.strip()) or not (request.body and request.body.strip()):
                raise ValueError("manual edit requires title and body")
            item.title = request.title.strip()
            item.body = request.body.strip()
        elif item.status not in {"generated", "approved", "manual_edited", "needs_revision"}:
            raise ValueError("batch item is not ready for operator review")

        item.status = review_status
        quality = dict(item.quality_json or {})
        human_review = dict(quality.get("human_review") or {})
        human_review.update(
            {
                "action": request.action,
                "review_status": review_status,
                "feedback_text": request.feedback_text,
                "created_by": request.created_by,
            }
        )
        quality["human_review"] = human_review
        item.quality_json = quality

        next_version_no = await self._next_version_no(item_id)
        version = ContentBatchItemVersion(
            item_id=item_id,
            version_no=next_version_no,
            source_action=request.action,
            review_status=review_status,
            title=item.title,
            body=item.body,
            feedback_text=request.feedback_text,
            created_by=request.created_by,
            metadata_json={"batch_id": item.batch_id, "item_no": item.item_no},
        )
        self.db.add(version)
        await self.db.flush()
        feedback = ContentFeedback(
            batch_id=item.batch_id,
            item_id=item.id,
            version_id=version.id,
            task_id=item.task_id,
            run_id=item.run_id,
            action=request.action,
            review_status=review_status,
            comment=request.feedback_text,
            submitter=request.created_by,
            metadata_json={
                "item_no": item.item_no,
                "source": "content_batch_workbench",
                "manual_edit": request.action == "manual_edit",
            },
        )
        self.db.add(feedback)
        await self.db.flush()

        report_item = await ContentBatchReportService(self.db).build_item_report(item)
        return ContentBatchItemFeedbackResponse(
            item_id=item.id,
            version_id=version.id,
            version_no=version.version_no,
            review_status=review_status,
            item=report_item,
        )

    async def _require_item(self, item_id: int) -> ContentBatchItem:
        result = await self.db.execute(select(ContentBatchItem).where(ContentBatchItem.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError("batch item not found")
        return item

    async def _next_version_no(self, item_id: int) -> int:
        result = await self.db.execute(
            select(func.max(ContentBatchItemVersion.version_no)).where(ContentBatchItemVersion.item_id == item_id)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1
