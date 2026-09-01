"""Schemas for the MAGA prompt debug workbench."""
from datetime import datetime
from typing import Optional
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


class PromptDebugRequest(BaseSchema):
    """One raw prompt invocation from the operator debug workbench."""

    prompt: str = Field(..., min_length=1, description="用户提示词")
    model_code: str = Field(..., min_length=1, description="统一模型编码")
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=20000)
    thinking_mode: Literal["default", "enabled", "disabled"] = Field(
        default="default",
        description="模型思考模式；default 不发送 thinking 参数",
    )
    system_prompt: Optional[str] = Field(default=None)
    run_group_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    workbench_mode: Literal["single", "compare"] = "single"
    panel_key: Literal["left", "right"] = "left"
    item_index: int = Field(default=0, ge=0, le=19)
    batch_size: int = Field(default=1, ge=1, le=20)

    @field_validator("prompt", "model_code")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("不能为空")
        return text

    @field_validator("system_prompt")
    @classmethod
    def _strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


class PromptDebugTokenUsage(BaseSchema):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class PromptDebugResponse(BaseSchema):
    success: bool
    content: Optional[str] = None
    model_code: Optional[str] = None
    provider_code: Optional[str] = None
    provider_model: Optional[str] = None
    usage: Optional[PromptDebugTokenUsage] = None
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    history_id: Optional[int] = None
    run_group_id: Optional[str] = None


class PromptDebugHistoryItem(BaseSchema):
    id: int
    run_group_id: str
    workbench_mode: Literal["single", "compare"]
    panel_key: Literal["left", "right"]
    item_index: int
    batch_size: int
    prompt: str
    system_prompt: Optional[str] = None
    requested_model_code: str
    temperature: float
    max_tokens: int
    thinking_mode: Literal["default", "enabled", "disabled"] = "default"
    success: bool
    content: Optional[str] = None
    model_code: Optional[str] = None
    provider_code: Optional[str] = None
    provider_model: Optional[str] = None
    token_usage: Optional[dict] = None
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    create_time: Optional[datetime] = None


class PromptDebugHistoryGroupSummary(BaseSchema):
    run_group_id: str
    workbench_mode: Literal["single", "compare"]
    create_time: Optional[datetime] = None
    total_count: int
    success_count: int
    failed_count: int
    panel_keys: list[Literal["left", "right"]] = Field(default_factory=list)
    model_codes: list[str] = Field(default_factory=list)
    prompt_preview: str = ""


class PromptDebugHistoryListResponse(BaseSchema):
    items: list[PromptDebugHistoryGroupSummary] = Field(default_factory=list)


class PromptDebugHistoryGroupDetail(BaseSchema):
    run_group_id: str
    workbench_mode: Literal["single", "compare"]
    create_time: Optional[datetime] = None
    records: list[PromptDebugHistoryItem] = Field(default_factory=list)
