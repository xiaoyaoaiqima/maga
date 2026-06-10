"""Content-agent execution layer schemas."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.schemas.base import BaseSchema, TimestampSchema


ContentAgentTaskType = Literal["asset_import", "content_generate", "content_rewrite"]
ContentAgentStatus = Literal["pending", "running", "succeeded", "failed", "needs_review", "cancelled"]


class ContentAgentTaskCreate(BaseSchema):
    task_code: Optional[str] = Field(default=None, max_length=64)
    task_type: ContentAgentTaskType = "content_generate"
    priority: int = 0
    executor_code: Optional[str] = Field(default=DEFAULT_EXECUTOR_CODE, max_length=64)
    brand_id: Optional[int] = None
    product_id: Optional[int] = None
    campaign_id: Optional[int] = None
    brief_id: Optional[int] = None
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    asset_refs: dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = Field(default=None, max_length=100)


class ContentAgentTaskResponse(TimestampSchema):
    id: int
    task_code: Optional[str] = None
    task_type: str
    status: str
    priority: int
    executor_code: Optional[str] = None
    brand_id: Optional[int] = None
    product_id: Optional[int] = None
    campaign_id: Optional[int] = None
    brief_id: Optional[int] = None
    input_snapshot: Optional[dict[str, Any]] = None
    asset_refs: Optional[dict[str, Any]] = None
    output_summary: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int
    created_by: Optional[str] = None


class ContentAgentClaimRequest(BaseSchema):
    executor_code: str = Field(..., max_length=64)
    capabilities: list[str] = Field(default_factory=list)
    external_run_id: Optional[str] = Field(default=None, max_length=128)
    executor_type: Optional[str] = Field(default="direct_llm", max_length=64)
    config_snapshot: Optional[dict[str, Any]] = None


class ContentAgentClaimResponse(BaseSchema):
    task_id: int
    run_id: int
    task_type: str
    input: dict[str, Any] = Field(default_factory=dict)
    asset_refs: dict[str, Any] = Field(default_factory=dict)


class ContentAgentSnapshotResponse(BaseSchema):
    task_id: int
    run_id: Optional[int] = None
    task_type: str
    input: dict[str, Any] = Field(default_factory=dict)
    asset_refs: dict[str, Any] = Field(default_factory=dict)


class ContentAgentRunResponse(TimestampSchema):
    id: int
    task_id: int
    run_code: Optional[str] = None
    run_token: Optional[str] = None
    executor_code: str
    executor_type: Optional[str] = None
    external_run_id: Optional[str] = None
    status: str
    status_substate: Optional[str] = None
    current_stage_call_id: Optional[str] = None
    rewrite_round: int = 0
    weighted_score_summary_json: Optional[dict[str, Any]] = None
    model_summary: Optional[dict[str, Any]] = None
    config_snapshot: Optional[dict[str, Any]] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None


class ContentAgentStageCallCreate(BaseSchema):
    stage_call_id: Optional[str] = Field(default=None, max_length=64)
    capability: str = Field(..., max_length=128)
    schema_version: str = Field(default="1", max_length=16)
    invoke_mode: str = Field(default="sync", max_length=16)
    input_snapshot: Optional[dict[str, Any]] = None
    retry_of_stage_call_id: Optional[str] = Field(default=None, max_length=64)
    deadline_at: Optional[datetime] = None


class ContentAgentStageCallCompleteRequest(BaseSchema):
    output: dict[str, Any] = Field(default_factory=dict)
    stats: Optional[dict[str, Any]] = None


class ContentAgentStageCallFailRequest(BaseSchema):
    error_code: str = Field(..., max_length=64)
    error_message: str
    retryable: bool = False
    details: Optional[dict[str, Any]] = None


class ContentAgentStageCallResponse(BaseSchema):
    id: int
    stage_call_id: str
    run_id: int
    sequence_no: int
    capability: str
    schema_version: str
    invoke_mode: str
    status: str
    input_snapshot: Optional[dict[str, Any]] = None
    output_snapshot: Optional[dict[str, Any]] = None
    stats_json: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: Optional[int] = None
    retry_of_stage_call_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None


class ContentAgentHeartbeatRequest(BaseSchema):
    run_token: str = Field(..., max_length=64)
    stage_call_id: str = Field(..., max_length=64)
    progress_hint: Optional[str] = Field(default=None, max_length=128)
    occurred_at: Optional[datetime] = None


class ContentAgentHumanReviewRequest(BaseSchema):
    stage_call_id: Optional[str] = Field(default=None, max_length=64)
    reason: str = Field(..., max_length=64)
    payload: Optional[dict[str, Any]] = None


class ContentAgentHumanReviewResponse(BaseSchema):
    id: int
    run_id: int
    stage_call_id: Optional[str] = None
    reason: str
    payload_json: Optional[dict[str, Any]] = None
    response_schema_json: Optional[dict[str, Any]] = None
    ui_hint: Optional[str] = None
    status: str
    responder_user_id: Optional[int] = None
    response_json: Optional[dict[str, Any]] = None
    requested_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None


class ContentAgentEventCreate(BaseSchema):
    stage_call_id: Optional[str] = Field(default=None, max_length=64)
    step: str = Field(..., max_length=64)
    event_type: str = Field(..., max_length=64)
    expert_code: Optional[str] = Field(default=None, max_length=128)
    model_code: Optional[str] = Field(default=None, max_length=128)
    input_snapshot: Optional[dict[str, Any]] = None
    output_snapshot: Optional[dict[str, Any]] = None
    message: Optional[str] = None
    latency_ms: Optional[int] = None
    token_usage: Optional[dict[str, Any]] = None
    otel_attributes: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=128)
    occurred_at: Optional[datetime] = None


class ContentAgentEventResponse(BaseSchema):
    id: int
    run_id: int
    stage_call_id: Optional[str] = None
    step: str
    event_type: str
    expert_code: Optional[str] = None
    model_code: Optional[str] = None
    input_snapshot: Optional[dict[str, Any]] = None
    output_snapshot: Optional[dict[str, Any]] = None
    message: Optional[str] = None
    latency_ms: Optional[int] = None
    token_usage: Optional[dict[str, Any]] = None
    otel_attributes_json: Optional[dict[str, Any]] = None
    metadata_json: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = None
    occurred_at: Optional[datetime] = None
    create_time: Optional[datetime] = None


class ContentAgentArtifactCreate(BaseSchema):
    stage_call_id: Optional[str] = Field(default=None, max_length=64)
    artifact_code: Optional[str] = Field(default=None, max_length=64)
    artifact_type: str = Field(..., max_length=64)
    name: Optional[str] = Field(default=None, max_length=255)
    content_text: Optional[str] = None
    content_json: Optional[dict[str, Any]] = None
    file_url: Optional[str] = Field(default=None, max_length=1024)
    version_no: int = 1
    metadata: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class ContentAgentArtifactResponse(BaseSchema):
    id: int
    run_id: int
    stage_call_id: Optional[str] = None
    artifact_code: Optional[str] = None
    artifact_type: str
    name: Optional[str] = None
    content_text: Optional[str] = None
    content_json: Optional[dict[str, Any]] = None
    file_url: Optional[str] = None
    version_no: int
    metadata_json: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = None
    create_time: Optional[datetime] = None


class ContentAgentRunCompleteRequest(BaseSchema):
    output_summary: dict[str, Any] = Field(default_factory=dict)
    model_summary: Optional[dict[str, Any]] = None


class ContentAgentRunFailRequest(BaseSchema):
    error_message: str
    output_summary: Optional[dict[str, Any]] = None
