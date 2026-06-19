"""Operator-facing batch report schemas."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.core.content_agent_defaults import (
    DEFAULT_EXECUTOR_CODE,
    MAGA_WORKER_DEFAULT_AE_MODEL,
    MAGA_WORKER_DEFAULT_GE_MODEL,
)
from app.services.product_experience_rule_service import DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY
from app.schemas.base import BaseSchema, TimestampSchema


ARTICLE_BATCH_MAX_COUNT = 1000


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


class ContentBatchVersionSnapshot(BaseSchema):
    version_id: int | None = None
    version_no: int | None = None
    source_action: str
    review_status: str | None = None
    title: str | None = None
    body: str | None = None
    feedback_text: str | None = None
    created_by: str | None = None
    create_time: str | None = None


class ContentBatchVersionCompare(BaseSchema):
    compare_type: str
    before: ContentBatchVersionSnapshot
    after: ContentBatchVersionSnapshot
    title_changed: bool = False
    body_changed: bool = False
    body_before_chars: int = 0
    body_after_chars: int = 0


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
    closure_cluster_stats: dict[str, Any] = Field(default_factory=dict)
    content_path_skeleton_stats: dict[str, Any] = Field(default_factory=dict)


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
    version_compare: ContentBatchVersionCompare | None = None
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
    generation_snapshot: dict[str, Any] | None = None
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
    provider_code: str | None = Field(default=None, max_length=64)
    model_code: str | None = Field(default=None, max_length=128)
    ge_model: str | None = Field(default=MAGA_WORKER_DEFAULT_GE_MODEL, max_length=128)
    ae_model: str | None = Field(default=MAGA_WORKER_DEFAULT_AE_MODEL, max_length=128)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=100000)
    system_prompt: str | None = None


class ContentBatchModelConfigRotationItem(BaseSchema):
    provider_code: str | None = Field(default=None, max_length=64)
    model_code: str | None = Field(default=None, max_length=128)
    ge_model: str | None = Field(default=None, max_length=128)
    ae_model: str | None = Field(default=None, max_length=128)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=100000)
    system_prompt: str | None = None


class ContentBatchStartRequest(BaseSchema):
    asset_key: str = Field(default=DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY, max_length=128)
    keyword_asset_key: str | None = Field(default=None, max_length=128)
    rule_id: str | None = Field(default=None, max_length=128)
    source_row_no: int | None = Field(default=None, ge=1)
    product_topic: str | None = Field(default=None, max_length=255)
    target_audience: str | None = Field(default=None, max_length=255)
    persona_target: str | None = Field(default=None, max_length=255)
    style: str | None = Field(default=None, max_length=255)
    count: int = Field(default=10, ge=1, le=ARTICLE_BATCH_MAX_COUNT)
    executor_code: str = Field(default=DEFAULT_EXECUTOR_CODE, max_length=64)
    generation_model_config: ContentBatchModelConfig = Field(
        default_factory=ContentBatchModelConfig,
        alias="model_config",
    )
    model_config_rotation: list[ContentBatchModelConfigRotationItem] = Field(default_factory=list, max_length=20)
    created_by: str | None = Field(default=None, max_length=100)


class ContentCommentBatchStartRequest(BaseSchema):
    asset_key: str = Field(default="yuanyue_comment_activity", max_length=128)
    keyword_asset_key: str | None = Field(default=None, max_length=128)
    quality_guard_profile_key: str | None = Field(default=None, max_length=128)
    business_rule: str | None = Field(default=None, max_length=255)
    rule_id: str | None = Field(default=None, max_length=128)
    source_row_no: int | None = Field(default=None, ge=1)
    draft_corpus: str | None = None
    draft_rule_id: str | None = Field(default=None, max_length=128)
    draft_source_row_no: int | None = Field(default=None, ge=1)
    count: int | None = Field(default=None, ge=1, le=100)
    executor_code: str = Field(default=DEFAULT_EXECUTOR_CODE, max_length=64)
    created_by: str | None = Field(default=None, max_length=100)


class ContentGenerationPreflightRequest(BaseSchema):
    asset_key: str = Field(..., max_length=128)
    asset_type: str | None = Field(default=None, max_length=64)
    executor_code: str = Field(default=DEFAULT_EXECUTOR_CODE, max_length=64)


class ContentGenerationPreflightCheck(BaseSchema):
    code: str
    label: str
    status: Literal["pass", "warning", "fail"]
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ContentGenerationPreflightResponse(BaseSchema):
    passed: bool
    status: Literal["ready", "warning", "blocked"]
    asset_key: str
    asset_type: str | None = None
    content_type: Literal["article", "comment"] | None = None
    executor_code: str
    checks: list[ContentGenerationPreflightCheck] = Field(default_factory=list)
    blocking_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


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


class ContentFeedbackSample(BaseSchema):
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


class ContentFeedbackSampleListResponse(BaseSchema):
    total: int
    items: list[ContentFeedbackSample]


class ContentBatchFeedbackStat(BaseSchema):
    code: str
    label: str
    count: int


class ContentBatchFeedbackSample(BaseSchema):
    feedback_id: int
    item_id: int
    item_no: int
    action: str
    review_status: str
    comment: str | None = None
    quoted_text: str | None = None
    feedback_categories: list[str] = Field(default_factory=list)
    create_time: str | None = None


class ContentBatchFeedbackOptimizationSuggestion(BaseSchema):
    suggestion_type: Literal["business_rule", "system_keyword", "business_forbidden_term", "expert_prompt"]
    target: str
    title: str
    reason: str
    evidence: list[str] = Field(default_factory=list)
    priority: Literal["high", "medium", "low"] = "medium"


class ContentBatchFeedbackInsightResponse(BaseSchema):
    batch_id: int
    batch_code: str | None = None
    asset_key: str
    product_topic: str
    total_feedback_count: int = 0
    category_stats: list[ContentBatchFeedbackStat] = Field(default_factory=list)
    action_stats: list[ContentBatchFeedbackStat] = Field(default_factory=list)
    review_status_stats: list[ContentBatchFeedbackStat] = Field(default_factory=list)
    rewrite_decision_stats: list[ContentBatchFeedbackStat] = Field(default_factory=list)
    samples: list[ContentBatchFeedbackSample] = Field(default_factory=list)
    suggestions: list[ContentBatchFeedbackOptimizationSuggestion] = Field(default_factory=list)


class ContentBatchItemFeedbackRequest(BaseSchema):
    action: Literal["approve", "request_revision", "manual_edit", "accept_rewrite", "reject_rewrite"]
    feedback_text: str | None = Field(default=None, max_length=4000)
    quoted_text: str | None = Field(default=None, max_length=2000)
    feedback_categories: list[str] = Field(default_factory=list)
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=20000)
    created_by: str | None = Field(default=None, max_length=100)
    business_forbidden_terms: list[str] = Field(default_factory=list)
    business_forbidden_term_entries: list[dict] = Field(default_factory=list)
    auto_rewrite: bool = False


class ContentBatchItemFeedbackResponse(BaseSchema):
    item_id: int
    version_id: int
    version_no: int
    review_status: str
    item: ContentBatchReportItem
