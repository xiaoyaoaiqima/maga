"""
JobCreateDraft schemas
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


# 草稿模式类型
JobCreateDraftMode = Literal["explicit_combinations", "allocation_rules", "variants", "ai", "strategy_v3"]


class VariableShareMappingItem(BaseSchema):
    """变量共享映射项 - 定义某个 Expert 的某个变量使用哪个策略维度"""
    expert_code: str = Field(..., description="Expert 配置编码")
    variable: str = Field(..., description="变量名（如：人设、必带词、安全词）")


class StrategyDimensionMapping(BaseSchema):
    """策略维度映射 - 一个维度可以映射到多个 Expert 的变量"""
    dimension: str = Field(..., description="策略维度名（如：persona, keyword）")
    mappings: List[VariableShareMappingItem] = Field(..., description="变量映射列表")


class DraftValidationIssue(BaseSchema):
    code: str = Field(..., description="错误码/告警码")
    message: str = Field(..., description="提示信息")
    path: Optional[str] = Field(default=None, description="字段路径（JSON Pointer 或简化路径）")
    level: Literal["error", "warning"] = Field(default="error", description="级别")


class DraftValidationResult(BaseSchema):
    is_valid: bool = Field(..., description="是否通过校验")
    errors: List[DraftValidationIssue] = Field(default_factory=list, description="错误列表")
    warnings: List[DraftValidationIssue] = Field(default_factory=list, description="告警列表")
    auto_fixes: List[Dict[str, Any]] = Field(default_factory=list, description="可自动修复项（提示用）")


class JobCreateDraftCreate(BaseSchema):
    tenant_id: Optional[int] = Field(default=None, description="租户ID")
    mode: JobCreateDraftMode = Field(..., description="创建方式")
    draft_json: Optional[Dict[str, Any]] = Field(default=None, description="草稿 JSON（可选，空则后端生成最小骨架）")
    remark: Optional[str] = Field(default=None, description="备注")
    created_by: Optional[str] = Field(default=None, description="创建人（可选）")


class JobCreateDraftPatch(BaseSchema):
    patch: Dict[str, Any] = Field(..., description="局部更新内容（deep merge 到 draft_json）")
    note: Optional[str] = Field(default=None, description="版本备注（可选）")
    updated_by: Optional[str] = Field(default=None, description="更新人（可选）")


class JobCreateDraftInDB(TimestampSchema):
    draft_id: str
    tenant_id: Optional[int] = None
    mode: str
    draft_json: Dict[str, Any]
    compiled_json: Optional[Dict[str, Any]] = None
    validation_json: Optional[Dict[str, Any]] = None
    remark: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_deleted: int = 0


class JobCreateDraftResponse(JobCreateDraftInDB):
    pass


class JobCreateDraftValidateResponse(BaseSchema):
    draft_id: str
    validation: DraftValidationResult


class JobCreateDraftCompileResponse(BaseSchema):
    draft_id: str
    compiled_json: Dict[str, Any]



