"""Operator review and versioning service for batch-generated content items."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.models.content_agent import (
    ContentAgentRun,
    ContentBatchItem,
    ContentBatchItemVersion,
    ContentBatchJob,
    ContentFeedback,
    ExecutorRegistry,
)
from app.models.maga_assets import AssetChangeRequest
from app.schemas.content_batch_report import (
    ContentBatchItemFeedbackRequest,
    ContentBatchItemFeedbackResponse,
)
from app.services.business_forbidden_term_service import (
    BusinessForbiddenTermService,
    normalize_business_forbidden_terms,
)
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.content_generation_expert_service import ContentGenerationExpertService
from app.services.executor_invocation_service import ExecutorInvocationClient, MockExecutorInvocationClient
from app.services.forbidden_term_review_service import ForbiddenTermReviewService


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

    def __init__(
        self,
        db: AsyncSession,
        *,
        invocation_client: ExecutorInvocationClient | None = None,
        callback_base_url: str = "/api/v1/content-agent",
    ):
        self.db = db
        self.invocation_client = invocation_client
        self.callback_base_url = callback_base_url

    async def submit_feedback(
        self,
        item_id: int,
        request: ContentBatchItemFeedbackRequest,
    ) -> ContentBatchItemFeedbackResponse:
        item = await self._require_item(item_id)
        previous_title = item.title
        previous_body = item.body
        review_status = _ACTION_STATUS[request.action]
        auto_rewrite_requested = request.auto_rewrite and request.action == "request_revision"
        if request.auto_rewrite and request.action != "request_revision":
            raise ValueError("auto rewrite only supports request_revision feedback")
        if auto_rewrite_requested and not (request.feedback_text or "").strip():
            raise ValueError("auto rewrite requires feedback_text")

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
        version_metadata = {"batch_id": item.batch_id, "item_no": item.item_no}
        if request.action == "manual_edit":
            version_metadata["previous_content"] = {
                "title": previous_title,
                "body": previous_body,
            }
        version = ContentBatchItemVersion(
            item_id=item_id,
            version_no=next_version_no,
            source_action=request.action,
            review_status=review_status,
            title=item.title,
            body=item.body,
            feedback_text=request.feedback_text,
            created_by=request.created_by,
            metadata_json=version_metadata,
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
                "auto_rewrite_requested": auto_rewrite_requested,
            },
        )
        self.db.add(feedback)
        await self.db.flush()
        business_forbidden_terms = normalize_business_forbidden_terms(request.business_forbidden_terms)
        if business_forbidden_terms:
            job = await self._job_for_item(item)
            term_result = await BusinessForbiddenTermService(self.db).add_terms(
                asset_key=job.asset_key if job else None,
                terms=business_forbidden_terms,
                created_by=request.created_by,
                source_context={
                    "batch_id": item.batch_id,
                    "item_id": item.id,
                    "item_no": item.item_no,
                    "feedback_id": feedback.id,
                    "version_id": version.id,
                },
            )
            metadata_patch = {
                "business_forbidden_terms": business_forbidden_terms,
                "business_forbidden_terms_added": term_result.added_terms,
                "business_forbidden_terms_asset_key": term_result.asset_key,
            }
            version.metadata_json = {**(version.metadata_json or {}), **metadata_patch}
            feedback.metadata_json = {**(feedback.metadata_json or {}), **metadata_patch}
            forbidden_review = await ForbiddenTermReviewService(self.db).review_and_rewrite_item(
                item=item,
                asset_key=term_result.asset_key,
                orchestrator=None,
                executor_code=None,
                content_type=_content_type_for_item(item),
            )
            version.title = item.title
            version.body = item.body
            version.metadata_json = {
                **(version.metadata_json or {}),
                "forbidden_terms_review": forbidden_review,
            }
            feedback.metadata_json = {
                **(feedback.metadata_json or {}),
                "forbidden_terms_review": forbidden_review,
            }
            await self.db.flush()

        rewrite_version = None
        if auto_rewrite_requested and not business_forbidden_terms:
            rewrite_version = await self._auto_rewrite_from_feedback(
                item=item,
                feedback=feedback,
                source_version=version,
                request=request,
            )

        change_request = None
        if not business_forbidden_terms:
            feedback_version = rewrite_version or version
            change_request = await self._maybe_create_asset_change_request(
                item=item,
                version=feedback_version,
                feedback=feedback,
                request=request,
            )
        if change_request is not None:
            feedback_version = rewrite_version or version
            feedback_version.metadata_json = {
                **(feedback_version.metadata_json or {}),
                "asset_change_request_id": change_request.id,
            }
            feedback.metadata_json = {
                **(feedback.metadata_json or {}),
                "asset_change_request_id": change_request.id,
                "asset_change_intent": "fact_or_compliance_rule",
            }
            await self.db.flush()

        report_item = await ContentBatchReportService(self.db).build_item_report(item)
        response_version = rewrite_version or version
        return ContentBatchItemFeedbackResponse(
            item_id=item.id,
            version_id=response_version.id,
            version_no=response_version.version_no,
            review_status=review_status,
            item=report_item,
        )

    async def _auto_rewrite_from_feedback(
        self,
        *,
        item: ContentBatchItem,
        feedback: ContentFeedback,
        source_version: ContentBatchItemVersion,
        request: ContentBatchItemFeedbackRequest,
    ) -> ContentBatchItemVersion:
        if not item.run_id:
            raise ValueError("auto rewrite requires a generated run")
        content_type = _content_type_for_item(item)
        previous_content = _previous_content_for_item(item, content_type=content_type)
        output_fields = ["comment"] if content_type == "comment" else ["title", "body"]
        rewrite_instructions = _operator_rewrite_instructions(request.feedback_text)
        input_payload = {
            "rewrite_source": "operator_feedback",
            "previous_content": previous_content,
            "content_type": content_type,
            "output_fields": output_fields,
            "business_rule": dict(item.plan_json or {}),
            "selected_keywords": _selected_keywords_from_item(item),
            "forbidden_hits": [],
            "operator_feedback": request.feedback_text,
            "review_report": {
                "hard_results": [],
                "soft_scores": [],
                "failed_aes": [],
                "rewrite_required": True,
                "rewrite_reason": "operator_feedback",
                "operator_feedback": request.feedback_text,
            },
            "rewrite_round": _current_rewrite_round(item) + 1,
            "rewrite_instructions": rewrite_instructions,
        }
        # 自动改写仍复用内容流的改写 Expert；MAGA 只把运营反馈组装进确定的改写输入。
        rewrite_snapshot = await ContentGenerationExpertService(self.db).build_rewrite_snapshot(
            content_type=content_type,
            previous_content=previous_content,
            business_rule=input_payload["business_rule"],
            selected_keywords=input_payload["selected_keywords"],
            forbidden_hits=[],
            rewrite_instructions=rewrite_instructions,
            output_fields=output_fields,
        )
        rewrite_snapshot["model_config"] = _operator_feedback_model_config(rewrite_snapshot.get("model_config"))
        input_payload.update(rewrite_snapshot)
        executor_code = await self._executor_code_for_item(item)
        orchestrator = ContentAgentOrchestrator(
            self.db,
            invocation_client=await self._invocation_client_for_executor(executor_code),
            callback_base_url=self.callback_base_url,
        )
        result = await orchestrator.run_content_rewrite_stage(
            run_id=item.run_id,
            executor_code=executor_code,
            input_payload=input_payload,
        )
        _apply_rewrite_output(item, result.output or {}, content_type=content_type)
        quality = dict(item.quality_json or {})
        human_review = dict(quality.get("human_review") or {})
        human_review["auto_rewrite"] = {
            "source": "operator_feedback",
            "feedback_text": request.feedback_text,
            "source_version_id": source_version.id,
            "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
        }
        review_report = dict(quality.get("review_report") or {})
        review_report.update(
            {
                "rewrite_required": False,
                "rewrite_reason": "operator_feedback",
                "rewrite_rounds": max(_current_rewrite_round(item), input_payload["rewrite_round"]),
                "operator_feedback": request.feedback_text,
            }
        )
        quality["human_review"] = human_review
        quality["review_report"] = review_report
        item.quality_json = quality
        item.status = "needs_revision"
        next_version_no = await self._next_version_no(item.id)
        rewrite_version = ContentBatchItemVersion(
            item_id=item.id,
            version_no=next_version_no,
            source_action="auto_rewrite",
            review_status="needs_revision",
            title=item.title,
            body=item.body,
            feedback_text=request.feedback_text,
            created_by=request.created_by,
            metadata_json={
                "batch_id": item.batch_id,
                "item_no": item.item_no,
                "source": "operator_feedback_auto_rewrite",
                "source_version_id": source_version.id,
                "feedback_id": feedback.id,
                "stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
            },
        )
        self.db.add(rewrite_version)
        await self.db.flush()
        feedback.metadata_json = {
            **(feedback.metadata_json or {}),
            "auto_rewrite": True,
            "auto_rewrite_version_id": rewrite_version.id,
            "auto_rewrite_stage_call_ids": [stage.stage_call_id for stage in result.stage_calls],
        }
        await self.db.flush()
        return rewrite_version

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

    async def _executor_code_for_item(self, item: ContentBatchItem) -> str:
        if item.run_id:
            run = await self.db.get(ContentAgentRun, item.run_id)
            if run and run.executor_code:
                return run.executor_code
        job = await self._job_for_item(item)
        strategy = job.strategy_json if job and isinstance(job.strategy_json, dict) else {}
        executor = strategy.get("executor") if isinstance(strategy, dict) else None
        return str(executor or DEFAULT_EXECUTOR_CODE)

    async def _invocation_client_for_executor(self, executor_code: str) -> ExecutorInvocationClient:
        if self.invocation_client is not None:
            return self.invocation_client
        result = await self.db.execute(select(ExecutorRegistry).where(ExecutorRegistry.executor_code == executor_code))
        executor = result.scalar_one_or_none()
        if executor and executor.invoke_url and executor.invoke_url.startswith("mock://"):
            return MockExecutorInvocationClient()
        return ExecutorInvocationClient()

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


def _content_type_for_item(item: ContentBatchItem) -> str:
    plan = item.plan_json or {}
    if plan.get("rule_type") == "comment_angle" or plan.get("output_fields") == ["comment"]:
        return "comment"
    return "article"


def _previous_content_for_item(item: ContentBatchItem, *, content_type: str) -> dict[str, str]:
    if content_type == "comment":
        return {"comment": item.body or ""}
    return {"title": item.title or "", "body": item.body or ""}


def _selected_keywords_from_item(item: ContentBatchItem) -> list[Any]:
    plan = item.plan_json or {}
    unified = plan.get("unified_generation") if isinstance(plan, dict) else {}
    if isinstance(unified, dict) and isinstance(unified.get("selected_keywords"), list):
        return unified["selected_keywords"]
    quality = item.quality_json or {}
    if isinstance(quality, dict) and isinstance(quality.get("selected_keywords"), list):
        return quality["selected_keywords"]
    return []


def _operator_rewrite_instructions(feedback_text: str | None) -> list[str]:
    feedback = (feedback_text or "").strip()
    instructions = [
        "这是运营反馈改写，不是违禁词替换；先理解反馈意图，再重写相关短句。",
        f"运营反馈原文：{feedback}",
        "不要只做同义替换、调换语序或把生硬表达换成另一句生硬表达。",
        "这里的“只改必要位置”指被反馈影响的一整句或相邻短句，不是词级替换。",
        "保留原业务规则、内容类型和评论区语气；改完要像真实妈妈顺手说的话。",
    ]
    quoted_terms = _quoted_feedback_terms(feedback)
    if quoted_terms:
        instructions.append(
            "运营点名不满意的表达："
            + "、".join(quoted_terms)
            + "；不要原样保留，也不要换成同样书面或别扭的近义句。"
        )
    if re.search(r"生硬|不自然|太硬|别扭|不像人话|机器味|AI味", feedback):
        instructions.append("反馈指向自然度问题：优先把相关句子改成更口语、更轻、更像评论区的表达。")
    if re.search(r"太长|啰嗦|冗长|字数", feedback):
        instructions.append("反馈指向长度问题：在不丢核心信息的前提下压缩句子，少用解释性铺垫。")
    if re.search(r"广告|营销|口播|种草感|推销", feedback):
        instructions.append("反馈指向营销感问题：降低推荐口吻，改成个人观察或轻交流。")
    instructions.append("不要解释改写过程，只返回改写后的内容。")
    return instructions


def _quoted_feedback_terms(feedback: str) -> list[str]:
    terms = []
    for match in re.finditer(r"[\"'“”‘’「」『』](.{1,80}?)[\"'“”‘’「」『』]", feedback):
        value = match.group(1).strip()
        if value and value not in terms:
            terms.append(value)
    return terms


def _operator_feedback_model_config(model_config: Any) -> dict[str, Any]:
    result = dict(model_config or {}) if isinstance(model_config, dict) else {}
    try:
        temperature = float(result.get("temperature"))
    except (TypeError, ValueError):
        temperature = 0.0
    # 运营反馈常是风格和自然度问题，温度太低会倾向机械保守替换；违禁词改写不走这里。
    if temperature < 0.55:
        result["temperature"] = 0.55
    return result


def _current_rewrite_round(item: ContentBatchItem) -> int:
    quality = item.quality_json or {}
    review_report = quality.get("review_report") if isinstance(quality, dict) else {}
    if not isinstance(review_report, dict):
        return 0
    try:
        return int(review_report.get("rewrite_rounds") or 0)
    except (TypeError, ValueError):
        return 0


def _apply_rewrite_output(item: ContentBatchItem, output: dict[str, Any], *, content_type: str) -> None:
    if content_type == "comment":
        comment = str(output.get("comment") or "").strip()
        if not comment:
            raise ValueError("content.rewrite returned empty comment")
        item.body = comment
        return

    final = output.get("final") if isinstance(output.get("final"), dict) else {}
    title = str(output.get("title") or final.get("title") or "").strip()
    body = str(output.get("body") or final.get("body") or "").strip()
    if not title and not body:
        raise ValueError("content.rewrite returned empty article")
    if title:
        item.title = title
    if body:
        item.body = body
