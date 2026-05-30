"""Operator-facing batch report schemas."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.core.content_agent_defaults import (
    DEFAULT_EXECUTOR_CODE,
    MAGA_WORKER_DEFAULT_AE_MODEL,
    MAGA_WORKER_DEFAULT_GE_MODEL,
)
from app.schemas.base import BaseSchema, TimestampSchema


class ContentBatchRejectReason(BaseSchema):
    source: str
    code: str | None = None
    message: str
    risk_level: str | None = None
    evidence: list[str] = Field(default_factory=list)


class ContentBatchStageTrace(BaseSchema):
    stage_call_id: str
    sequence_no: int
    capability: str
    status: str
    duration_ms: int | None = None
    error_message: str | None = None
    stats: dict[str, Any] | None = None


class ContentBatchSimilarityWarning(BaseSchema):
    item_no: int
    score: float
    reason: str
    batch_id: int | None = None
    batch_code: str | None = None
    scope: str = "current_batch"


class ContentBatchReportSummary(BaseSchema):
    total_count: int = 0
    generated_count: int = 0
    failed_count: int = 0
    hard_pass_count: int = 0
    rewrite_item_count: int = 0
    remaining_rewrite_required_count: int = 0
    forbidden_hit_count: int = 0
    feedback_count: int = 0
    avg_body_chars: float | None = None
    max_pairwise_jaccard_2gram: float = 0.0
    similarity_warning_count: int = 0


class ContentBatchReportItem(BaseSchema):
    item_id: int
    item_no: int
    status: str
    task_id: int | None = None
    run_id: int | None = None
    title: str | None = None
    body: str | None = None
    body_preview: str | None = None
    body_chars: int = 0
    hard_pass: bool | None = None
    rewrite_required: bool | None = None
    rewrite_reason: str | None = None
    rewrite_rounds: int | None = None
    suggestion_count: int = 0
    replacement_count: int = 0
    forbidden_hits: list[str] = Field(default_factory=list)
    final_path: str | None = None
    debug_dir: str | None = None
    review_status: str | None = None
    latest_version_no: int | None = None
    human_feedback_text: str | None = None
    feedback_count: int = 0
    reject_reasons: list[ContentBatchRejectReason] = Field(default_factory=list)
    similarity_warnings: list[ContentBatchSimilarityWarning] = Field(default_factory=list)
    runtime_mode: str | None = None
    generation_duration_ms: int | None = None
    total_duration_ms: int | None = None
    trace_run_id: int | None = None
    trace_stage_calls: list[ContentBatchStageTrace] = Field(default_factory=list)
    opening_type: str | None = None
    structure_type: str | None = None
    content_angle: str | None = None
    persona_lens: str | None = None
    scene_type: str | None = None
    evidence_type: str | None = None
    asset_combo_key: str | None = None
    asset_reuse_reason: str | None = None
    diversity: dict[str, Any] | None = None
    quality: dict[str, Any] | None = None
    error_message: str | None = None


class ContentBatchReportResponse(BaseSchema):
    batch_id: int
    batch_code: str | None = None
    asset_key: str
    product_topic: str
    target_audience: str | None = None
    persona_target: str | None = None
    style: str | None = None
    status: str
    count: int
    summary: ContentBatchReportSummary
    items: list[ContentBatchReportItem]


class ContentBatchModelConfig(BaseSchema):
    ge_model: str | None = Field(default=MAGA_WORKER_DEFAULT_GE_MODEL, max_length=128)
    ae_model: str | None = Field(default=MAGA_WORKER_DEFAULT_AE_MODEL, max_length=128)


class ContentBatchStartRequest(BaseSchema):
    asset_key: str = Field(default="yuanyue", max_length=128)
    product_topic: str = Field(..., max_length=255)
    target_audience: str | None = Field(default=None, max_length=255)
    persona_target: str | None = Field(default=None, max_length=255)
    style: str | None = Field(default=None, max_length=255)
    count: int = Field(default=5, ge=1, le=20)
    executor_code: str = Field(default=DEFAULT_EXECUTOR_CODE, max_length=64)
    generation_model_config: ContentBatchModelConfig = Field(
        default_factory=ContentBatchModelConfig,
        alias="model_config",
    )
    created_by: str | None = Field(default=None, max_length=100)


class ContentCommentBatchStartRequest(BaseSchema):
    asset_key: str = Field(default="yuanyue_comment_activity", max_length=128)
    executor_code: str = Field(default=DEFAULT_EXECUTOR_CODE, max_length=64)
    created_by: str | None = Field(default=None, max_length=100)


class ContentBatchExecutionSummary(BaseSchema):
    requested_limit: int
    generated_count: int
    failed_count: int
    item_ids: list[int] = Field(default_factory=list)


class ContentBatchStartResponse(BaseSchema):
    batch_id: int
    batch_code: str | None = None
    execution: ContentBatchExecutionSummary
    report: ContentBatchReportResponse


class ContentBatchListItem(TimestampSchema):
    batch_id: int
    batch_code: str | None = None
    asset_key: str
    product_topic: str
    target_audience: str | None = None
    persona_target: str | None = None
    style: str | None = None
    status: str
    count: int
    summary: ContentBatchReportSummary


class ContentBatchListResponse(BaseSchema):
    total: int
    items: list[ContentBatchListItem]


class ContentTrainingFeedbackSample(BaseSchema):
    feedback_id: int
    batch_id: int | None = None
    batch_code: str | None = None
    item_id: int
    item_no: int
    version_id: int | None = None
    action: str
    review_status: str
    comment: str | None = None
    submitter: str | None = None
    title: str | None = None
    body_preview: str | None = None
    product_topic: str | None = None
    target_audience: str | None = None
    style: str | None = None
    asset_key: str | None = None
    metadata: dict[str, Any] | None = None
    create_time: str | None = None


class ContentTrainingFeedbackSampleListResponse(BaseSchema):
    total: int
    items: list[ContentTrainingFeedbackSample]


class ContentBatchItemFeedbackRequest(BaseSchema):
    action: Literal["approve", "request_revision", "manual_edit"]
    feedback_text: str | None = Field(default=None, max_length=4000)
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=20000)
    created_by: str | None = Field(default=None, max_length=100)


class ContentBatchItemFeedbackResponse(BaseSchema):
    item_id: int
    version_id: int
    version_no: int
    review_status: str
    item: ContentBatchReportItem
