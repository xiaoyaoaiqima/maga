"""Schemas for template-variable corpus management."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_serializer

from app.schemas.base import BaseSchema, PageInfo


CorpusStatus = Literal["active", "draft", "archived"]
PreviewFillMode = Literal["selected_only", "selected_or_first"]
PreviewMissingPolicy = Literal["keep_placeholder", "empty"]


class TemplateVariableItem(BaseSchema):
    name: str
    corpus_count: int = 0
    active_count: int = 0
    draft_count: int = 0


class TemplateVariableListResponse(BaseSchema):
    template_path: str
    variables: list[TemplateVariableItem]


class TemplateVariableCorpusItem(BaseSchema):
    id: int
    tenant_code: str
    variable_name: str
    name: str
    markdown: str
    tags: list[str] = Field(default_factory=list)
    status: CorpusStatus = "active"
    source: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_serializer("id")
    def serialize_id(self, value: int) -> str:
        """Serialize snowflake IDs as strings to avoid JS precision loss."""
        return str(value)


class TemplateVariableCorpusListResponse(BaseSchema):
    items: list[TemplateVariableCorpusItem]
    page_info: PageInfo


class TemplateVariableCorpusCreate(BaseSchema):
    variable_name: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=255)
    markdown: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    status: CorpusStatus = "active"
    source: str | None = None
    tenant_code: str = "default"
    created_by: str | None = "template-variable-corpus"


class TemplateVariableCorpusUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    markdown: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    status: CorpusStatus | None = None
    source: str | None = None
    updated_by: str | None = "template-variable-corpus"


class PromptPreviewRequest(BaseSchema):
    tenant_code: str = "default"
    selected_item_ids: dict[str, str] = Field(default_factory=dict)
    draft_values: dict[str, str] = Field(default_factory=dict)
    fill_mode: PreviewFillMode = "selected_or_first"
    missing_policy: PreviewMissingPolicy = "keep_placeholder"


class PromptPreviewResponse(BaseSchema):
    template_path: str
    rendered_prompt: str
    used_items: dict[str, TemplateVariableCorpusItem]
    missing_variables: list[str]
