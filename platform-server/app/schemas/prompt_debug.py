"""Schemas for the MAGA prompt debug workbench."""
from typing import Optional

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


class PromptDebugRequest(BaseSchema):
    """One raw prompt invocation from the operator debug workbench."""

    prompt: str = Field(..., min_length=1, description="用户提示词")
    model_code: str = Field(..., min_length=1, description="统一模型编码")
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=20000)
    system_prompt: Optional[str] = Field(default=None)

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
