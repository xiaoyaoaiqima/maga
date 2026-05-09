"""Content-agent execution layer schemas."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


ContentAgentTaskType = Literal["xhs_generate", "xhs_rewrite", "prompt_optimize"]
ContentAgentStatus = Literal["pending", "running", "succeeded", "failed", "needs_review", "cancelled"]


class ContentAgentTaskCreate(BaseSchema):
    task_code: Optional[str] = Field(default=None, max_length=64)
    task_type: ContentAgentTaskType = "xhs_generate"
    priority: int = 0
    executor_code: Optional[str] = Field(default="hermes_xhs_writer", max_length=64)
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
    executor_type: Optional[str] = Field(default="hermes_profile", max_length=64)
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
    executor_code: str
    executor_type: Optional[str] = None
    external_run_id: Optional[str] = None
    status: str
    model_summary: Optional[dict[str, Any]] = None
    config_snapshot: Optional[dict[str, Any]] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None


class ContentAgentEventCreate(BaseSchema):
    step: str = Field(..., max_length=64)
    event_type: str = Field(..., max_length=64)
    expert_code: Optional[str] = Field(default=None, max_length=128)
    model_code: Optional[str] = Field(default=None, max_length=128)
    input_snapshot: Optional[dict[str, Any]] = None
    output_snapshot: Optional[dict[str, Any]] = None
    message: Optional[str] = None
    latency_ms: Optional[int] = None
    token_usage: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None


class ContentAgentEventResponse(BaseSchema):
    id: int
    run_id: int
    step: str
    event_type: str
    expert_code: Optional[str] = None
    model_code: Optional[str] = None
    input_snapshot: Optional[dict[str, Any]] = None
    output_snapshot: Optional[dict[str, Any]] = None
    message: Optional[str] = None
    latency_ms: Optional[int] = None
    token_usage: Optional[dict[str, Any]] = None
    metadata_json: Optional[dict[str, Any]] = None
    create_time: Optional[datetime] = None


class ContentAgentArtifactCreate(BaseSchema):
    artifact_type: str = Field(..., max_length=64)
    name: Optional[str] = Field(default=None, max_length=255)
    content_text: Optional[str] = None
    content_json: Optional[dict[str, Any]] = None
    file_url: Optional[str] = Field(default=None, max_length=1024)
    version_no: int = 1
    metadata: Optional[dict[str, Any]] = None


class ContentAgentArtifactResponse(BaseSchema):
    id: int
    run_id: int
    artifact_type: str
    name: Optional[str] = None
    content_text: Optional[str] = None
    content_json: Optional[dict[str, Any]] = None
    file_url: Optional[str] = None
    version_no: int
    metadata_json: Optional[dict[str, Any]] = None
    create_time: Optional[datetime] = None


class ContentAgentRunCompleteRequest(BaseSchema):
    output_summary: dict[str, Any] = Field(default_factory=dict)
    model_summary: Optional[dict[str, Any]] = None


class ContentAgentRunFailRequest(BaseSchema):
    error_message: str
    output_summary: Optional[dict[str, Any]] = None
