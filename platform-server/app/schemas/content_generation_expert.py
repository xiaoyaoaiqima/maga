"""Schemas for content-generation flow Expert management."""
from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class ContentGenerationExpertResponse(BaseSchema):
    """Operator-facing Expert config used by the unified generation flow."""

    id: int | None = None
    expert_config_code: str
    expert_config_name: str
    expert_type: str
    stage: str
    capability: str
    content_type: str
    description: str | None = None
    model_code: str | None = None
    model_config_data: dict[str, Any] = Field(
        default_factory=dict,
        serialization_alias="model_config",
        validation_alias="model_config",
    )
    prompt_template: str
    enabled: bool = True
    source: str
    variables: list[str] = Field(default_factory=list)
    update_time: str | None = None


class ContentGenerationAuditFlowResponse(BaseSchema):
    """Deterministic audit flow summary shown next to Expert configs."""

    source: str
    max_rewrite_rounds: int
    rewrite_capability: str
    static_forbidden_terms: list[str] = Field(default_factory=list)
    business_forbidden_terms: list[str] = Field(default_factory=list)


class ContentGenerationExpertListResponse(BaseSchema):
    items: list[ContentGenerationExpertResponse]
    audit_flow: ContentGenerationAuditFlowResponse


class ContentGenerationExpertUpsertRequest(BaseSchema):
    expert_config_name: str = Field(..., max_length=255)
    description: str | None = None
    model_code: str | None = Field(default=None, max_length=255)
    model_config_data: dict[str, Any] = Field(
        default_factory=dict,
        serialization_alias="model_config",
        validation_alias="model_config",
    )
    prompt_template: str
    enabled: bool = True
    updated_by: str | None = None


class ContentGenerationExpertPreviewRequest(BaseSchema):
    business_rule: dict[str, Any] = Field(default_factory=dict)
    content_type: str | None = None
    forbidden_hits: list[str] = Field(default_factory=list)
    previous_content: dict[str, Any] = Field(default_factory=dict)
    selected_keywords: list[dict[str, Any]] = Field(default_factory=list)


class ContentGenerationExpertPreviewResponse(BaseSchema):
    expert_config_code: str
    rendered_prompt: str
    model_config_data: dict[str, Any] = Field(
        default_factory=dict,
        serialization_alias="model_config",
        validation_alias="model_config",
    )
