"""
JobVariant schemas
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


class JobVariantBase(BaseSchema):
    tenant_id: Optional[int] = Field(default=None, description="租户ID（NULL 表示全局共享）")
    agent_code: Optional[str] = Field(default=None, description="关联 Agent 编码（可选）")
    variant_name: str = Field(..., min_length=1, max_length=255, description="Variant 名称")
    tags: list[str] = Field(default_factory=list, description="标签")
    expert_config_code_list: list[str] = Field(default_factory=list, description="Expert 编排顺序（快照）")
    expert_param_config: dict[str, Any] = Field(..., description="组合模板参数（expert_code -> plugin_config_snapshot[]）")
    enabled: bool = Field(default=True, description="是否启用")
    remark: Optional[str] = Field(default=None, description="备注")


class JobVariantCreate(JobVariantBase):
    created_by: Optional[str] = Field(default=None, description="创建人（可选）")


class JobVariantUpdate(BaseSchema):
    tenant_id: Optional[int] = None
    agent_code: Optional[str] = None
    variant_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tags: Optional[list[str]] = None
    expert_config_code_list: Optional[list[str]] = None
    expert_param_config: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = None
    updated_by: Optional[str] = Field(default=None, description="更新人（可选）")


class JobVariantInDB(JobVariantBase, TimestampSchema):
    variant_id: str = Field(..., description="Variant ID")
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_deleted: int = 0


class JobVariantResponse(JobVariantInDB):
    pass

