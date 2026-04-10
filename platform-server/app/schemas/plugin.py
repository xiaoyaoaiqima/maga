"""
Plugin schemas

v2 重构：
- 新增 strategy_id 字段：绑定的内容策略ID
- 新增 variable_mappings 字段：变量到 label 的映射配置
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema, TimestampSchema


class VariableMapping(BaseSchema):
    """变量映射配置"""
    variable_name: str = Field(..., description="变量名（如：写者、场景、卖点）")
    label: str = Field(..., description="对应的 label（如：人设、场景、卖点）")


class PluginBase(BaseSchema):
    """Plugin base schema"""
    plugin_code: str = Field(..., max_length=255, description="插件的code")
    plugin_name: str = Field(..., max_length=255, description="插件的名称")
    plugin_type: Optional[str] = Field(default=None, max_length=255, description="插件的类型")
    variable_list: Optional[List[str]] = Field(default=None, description="变量列表")
    context_template: Optional[str] = Field(default=None, description="内容模板")
    enabled: bool = Field(default=True, description="是否激活")
    remark: Optional[str] = Field(default=None, description="备注")
    
    # ========== v2 新增字段 ==========
    strategy_id: Optional[int] = Field(default=None, description="绑定的内容策略ID（来自 keyword-corpus 服务）")
    variable_mappings: Optional[List[VariableMapping]] = Field(default=None, description="变量映射配置")
    
    @field_validator('enabled', mode='before')
    @classmethod
    def set_enabled_default(cls, v):
        """如果 enabled 为 None（数据库中的 NULL），则默认为 True"""
        if v is None:
            return True
        return v


class PluginCreate(PluginBase):
    """Plugin create schema"""
    pass


class PluginUpdate(BaseSchema):
    """Plugin update schema"""
    plugin_name: Optional[str] = Field(default=None, max_length=255)
    plugin_type: Optional[str] = Field(default=None, max_length=255)
    variable_list: Optional[List[str]] = None
    context_template: Optional[str] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = None
    # v2 新增
    strategy_id: Optional[int] = Field(default=None, description="绑定的内容策略ID")
    variable_mappings: Optional[List[VariableMapping]] = Field(default=None, description="变量映射配置")


class PluginInDB(PluginBase, TimestampSchema):
    """Plugin in database schema"""
    id: int
    publish_status: str = Field(default="DRAFT", description="上线状态：DRAFT(草稿)/PUBLISHED(已上线)")
    publish_time: Optional[datetime] = Field(default=None, description="上线时间")
    publish_by: Optional[str] = Field(default=None, description="上线人")
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_deleted: int = 0


class PluginResponse(PluginInDB):
    """Plugin response schema"""
    pass


# ========== 变量映射配置相关 Schemas ==========

class VariableMappingConfigRequest(BaseSchema):
    """更新变量映射配置请求"""
    strategy_id: int = Field(..., description="绑定的内容策略ID")
    variable_mappings: List[VariableMapping] = Field(..., description="变量映射配置列表")


class VariableMappingConfigResponse(BaseSchema):
    """变量映射配置响应"""
    plugin_id: int = Field(..., description="插件ID")
    plugin_code: str = Field(..., description="插件编码")
    strategy_id: Optional[int] = Field(None, description="绑定的内容策略ID")
    strategy_name: Optional[str] = Field(None, description="内容策略名称")
    strategy_labels: List[str] = Field(default_factory=list, description="策略中可用的 label 列表")
    variable_mappings: List[VariableMapping] = Field(default_factory=list, description="变量映射配置列表")

