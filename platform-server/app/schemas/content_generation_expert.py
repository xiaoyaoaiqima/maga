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


class BusinessForbiddenTermEntryRequest(BaseSchema):
    term: str = Field(..., min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)
    replacement: str | None = Field(default=None, max_length=100)
    enabled: bool = True


class BusinessForbiddenTermEntryResponse(BaseSchema):
    term: str
    reason: str = ""
    enabled: bool = True
    created_at: str = ""
    created_by: str = ""
    updated_at: str = ""
    updated_by: str = ""
    replacement: str = ""
    source: str = ""
    asset_key: str = ""


class BusinessForbiddenTermListResponse(BaseSchema):
    asset_key: str
    items: list[BusinessForbiddenTermEntryResponse] = Field(default_factory=list)


class BusinessForbiddenTermUpsertRequest(BaseSchema):
    asset_key: str | None = Field(default=None, max_length=128)
    entries: list[BusinessForbiddenTermEntryRequest] = Field(default_factory=list)
    created_by: str | None = Field(default=None, max_length=100)


class BusinessForbiddenTermStatusRequest(BaseSchema):
    asset_key: str | None = Field(default=None, max_length=128)
    term: str = Field(..., min_length=1, max_length=100)
    enabled: bool
    updated_by: str | None = Field(default=None, max_length=100)


class CommentDeliveryLedgerEntry(BaseSchema):
    id: int | None = None
    asset_key: str
    category: str = ""
    comment_text: str
    normalized_comment: str
    comment_hash: str
    source_type: str
    source_uri: str = ""
    batch_id: int | None = None
    item_id: int | None = None
    delivered_by: str = ""
    delivered_at: str = ""


class CommentDeliveryLedgerListResponse(BaseSchema):
    asset_key: str
    total: int = 0
    items: list[CommentDeliveryLedgerEntry] = Field(default_factory=list)


class CommentDeliveryLedgerImportEntry(BaseSchema):
    category: str | None = Field(default=None, max_length=255)
    comment_text: str = Field(..., min_length=1)
    source_uri: str | None = None
    batch_id: int | None = None
    item_id: int | None = None
    metadata_json: dict[str, Any] | None = None


class CommentDeliveryLedgerImportRequest(BaseSchema):
    asset_key: str | None = Field(default=None, max_length=128)
    source_type: str = Field(default="csv_import", max_length=32)
    source_uri: str | None = None
    delivered_by: str | None = Field(default=None, max_length=100)
    entries: list[CommentDeliveryLedgerImportEntry] = Field(default_factory=list)


class CommentDeliveryLedgerImportResponse(BaseSchema):
    asset_key: str
    imported_rows: int = 0
    skipped_existing_rows: int = 0
    skipped_input_duplicate_rows: int = 0
    total_input_rows: int = 0


class CommentDeliveryLedgerCheckRequest(BaseSchema):
    asset_key: str | None = Field(default=None, max_length=128)
    comments: list[str] = Field(default_factory=list)


class CommentDeliveryLedgerDuplicateHit(BaseSchema):
    index: int
    comment_text: str
    normalized_comment: str
    ledger_entry: CommentDeliveryLedgerEntry


class CommentDeliveryLedgerCheckResponse(BaseSchema):
    asset_key: str
    duplicate_count: int = 0
    hits: list[CommentDeliveryLedgerDuplicateHit] = Field(default_factory=list)


class ContentGenerationAuditFlowResponse(BaseSchema):
    """Deterministic audit flow summary shown next to Expert configs."""

    source: str
    max_rewrite_rounds: int
    rewrite_capability: str
    static_forbidden_terms: list[str] = Field(default_factory=list)
    business_forbidden_terms: list[str] = Field(default_factory=list)
    business_forbidden_term_entries: list[BusinessForbiddenTermEntryResponse] = Field(default_factory=list)


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
