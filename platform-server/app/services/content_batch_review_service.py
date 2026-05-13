"""Operator review and versioning service for batch-generated content items."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import ContentBatchItem, ContentBatchItemVersion, ContentBatchJob, ContentFeedback
from app.models.maga_assets import AssetChangeRequest
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
_ASSET_RULE_INTENT_PATTERNS = [
    r"禁止",
    r"不能",
    r"不应",
    r"不对",
    r"错误",
    r"没有关系",
    r"无关",
    r"不要提",
    r"别提",
]
_ASSET_RULE_DOMAIN_PATTERNS = [
    r"卖点",
    r"产品",
    r"品牌",
    r"配方",
    r"蛋白",
    r"公司",
    r"事实",
    r"提及",
    r"宣称",
]


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
        change_request = await self._maybe_create_asset_change_request(
            item=item,
            version=version,
            feedback=feedback,
            request=request,
        )
        if change_request is not None:
            version.metadata_json = {
                **(version.metadata_json or {}),
                "asset_change_request_id": change_request.id,
            }
            feedback.metadata_json = {
                **(feedback.metadata_json or {}),
                "asset_change_request_id": change_request.id,
                "asset_change_intent": "fact_or_compliance_rule",
            }
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

    async def _maybe_create_asset_change_request(
        self,
        *,
        item: ContentBatchItem,
        version: ContentBatchItemVersion,
        feedback: ContentFeedback,
        request: ContentBatchItemFeedbackRequest,
    ) -> AssetChangeRequest | None:
        text = (request.feedback_text or "").strip()
        if request.action == "approve" or not _looks_like_asset_rule_feedback(text):
            return None

        job = await self._job_for_item(item)
        source_text = (
            f"运营反馈：{text}\n"
            "请评估是否需要更新 MAGA 资料资产，避免后续生成再次出现同类事实错误或违规卖点。"
        )
        context = {
            "source": "content_batch_feedback",
            "intent": "fact_or_compliance_rule",
            "affected_asset_types": ["compliance_rules", "brand_profile", "product_selling_points"],
            "suggested_stage": "candidate",
            "feedback_id": feedback.id,
            "version_id": version.id,
            "batch_id": item.batch_id,
            "item_id": item.id,
            "item_no": item.item_no,
            "task_id": item.task_id,
            "run_id": item.run_id,
            "asset_key": job.asset_key if job else None,
            "product_topic": job.product_topic if job else None,
            "target_audience": job.target_audience if job else None,
            "style": job.style if job else None,
            "title": item.title,
            "body_excerpt": _excerpt(item.body),
            "detected_terms": _detected_terms(text),
        }
        change_request = AssetChangeRequest(
            source_text=source_text,
            requester=request.created_by,
            context_json={key: value for key, value in context.items() if value is not None},
            status="pending",
            created_by=request.created_by or "content_batch_workbench",
        )
        self.db.add(change_request)
        await self.db.flush()
        return change_request

    async def _job_for_item(self, item: ContentBatchItem) -> ContentBatchJob | None:
        if not item.batch_id:
            return None
        result = await self.db.execute(select(ContentBatchJob).where(ContentBatchJob.id == item.batch_id))
        return result.scalar_one_or_none()

    async def _next_version_no(self, item_id: int) -> int:
        result = await self.db.execute(
            select(func.max(ContentBatchItemVersion.version_no)).where(ContentBatchItemVersion.item_id == item_id)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1


def _looks_like_asset_rule_feedback(text: str) -> bool:
    if not text:
        return False
    has_intent = any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _ASSET_RULE_INTENT_PATTERNS)
    has_domain = any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _ASSET_RULE_DOMAIN_PATTERNS)
    return has_intent and has_domain


def _detected_terms(text: str) -> list[str]:
    terms = []
    for match in re.finditer(r"[A-Za-z0-9]+(?:\s*[A-Za-z0-9]+)*|[\u4e00-\u9fa5]{2,}", text):
        value = match.group(0).strip()
        if value and value not in terms:
            terms.append(value)
    return terms[:20]


def _excerpt(value: str | None, *, limit: int = 500) -> str | None:
    if not value:
        return None
    text = value.strip()
    return text if len(text) <= limit else f"{text[:limit]}..."
