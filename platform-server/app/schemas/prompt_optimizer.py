"""
Prompt optimizer schemas.
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema, TimestampSchema


PromptType = Literal["generation", "critic", "other"]
IssueType = Literal["human_opinion", "review_problem", "batch_case"]
OptimizerMode = Literal["local_patch", "global_refactor", "critic_patch", "batch_patch"]
RunStatus = Literal["pending", "running", "succeeded", "failed"]
PatchOperation = Literal["replace", "delete", "insert_after", "insert_before"]
PatchStatus = Literal["pending", "accepted", "rejected", "edited"]


class PromptAssetCreate(BaseSchema):
    name: str = Field(..., max_length=255)
    content: str
    prompt_type: PromptType = "generation"
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    created_by: Optional[str] = Field(default=None, max_length=64)


class PromptAssetUpdate(BaseSchema):
    name: Optional[str] = Field(default=None, max_length=255)
    prompt_type: Optional[PromptType] = None
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class PromptVersionCreate(BaseSchema):
    content: str
    parent_version_id: Optional[int] = None
    source_run_id: Optional[int] = None
    change_summary: Optional[str] = None
    created_by: Optional[str] = Field(default=None, max_length=64)
    set_current: bool = True


class PromptAssetResponse(TimestampSchema):
    id: int
    tenant_code: Optional[str] = None
    name: str
    prompt_type: str
    description: Optional[str] = None
    current_version_id: Optional[int] = None
    tags: Optional[list[str]] = None
    is_deleted: int


class PromptVersionResponse(BaseSchema):
    id: int
    prompt_id: int
    version_no: int
    content: str
    parent_version_id: Optional[int] = None
    source_run_id: Optional[int] = None
    change_summary: Optional[str] = None
    created_by: Optional[str] = None
    create_time: Optional[datetime] = None


class PromptIssueResponse(BaseSchema):
    id: int
    prompt_id: int
    prompt_version_id: int
    issue_type: str
    problem_text: str
    generated_content: Optional[str] = None
    generated_title: Optional[str] = None
    issue_metadata: Optional[dict[str, Any]] = None
    create_time: Optional[datetime] = None


class PromptPatchResponse(TimestampSchema):
    id: int
    run_id: int
    patch_index: int
    operation: str
    old_text: str
    new_text: Optional[str] = None
    reason: Optional[str] = None
    status: str
    edited_new_text: Optional[str] = None
    review_comment: Optional[str] = None


class PromptOptimizerRunCreate(BaseSchema):
    mode: OptimizerMode
    problem_text: str
    prompt_id: Optional[int] = None
    prompt_version_id: Optional[int] = None
    prompt_content: Optional[str] = None
    prompt_name: Optional[str] = Field(default=None, max_length=255)
    prompt_type: PromptType = "generation"
    tenant_code: Optional[str] = Field(default=None, max_length=64)
    issue_type: Optional[IssueType] = None
    generated_content: Optional[str] = None
    generated_title: Optional[str] = None
    issue_metadata: Optional[dict[str, Any]] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 8000
    timeout: int = 90
    json_mode: bool = True
    include_revised_prompt: bool = False


class PromptOptimizerRunResponse(TimestampSchema):
    id: int
    prompt_id: int
    prompt_version_id: int
    issue_id: Optional[int] = None
    mode: str
    model: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[str] = None
    max_tokens: Optional[int] = None
    status: str
    input_snapshot: Optional[dict[str, Any]] = None
    raw_output: Optional[str] = None
    parsed_output: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    patches: list[PromptPatchResponse] = []


class PromptPatchUpdate(BaseSchema):
    status: Optional[PatchStatus] = None
    edited_new_text: Optional[str] = None
    review_comment: Optional[str] = None


class PromptPatchApplyRequest(BaseSchema):
    patch_ids: Optional[list[int]] = None
    change_summary: Optional[str] = None
    created_by: Optional[str] = Field(default=None, max_length=64)
    save_version: bool = True


class PromptPatchApplyConflict(BaseModel):
    patch_id: int
    reason: str


class PromptPatchApplyResponse(BaseSchema):
    applied_patch_ids: list[int]
    conflicts: list[PromptPatchApplyConflict]
    candidate_content: str
    new_version: Optional[PromptVersionResponse] = None
