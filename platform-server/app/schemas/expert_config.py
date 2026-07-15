"""
ExpertConfig schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


class ExpertConfigBase(BaseSchema):
    """ExpertConfig base schema"""
    expert_config_code: str = Field(..., max_length=64, description="expert_config 配置 code")
    expert_config_name: str = Field(..., max_length=255, description="expert_config 名称")
    tenant_code: Optional[str] = Field(default=None, max_length=64, description="归属租户编码（NULL 表示全局共享）")
    expert_type: str = Field(..., max_length=64, description="业务类型：GENERATION/SCORE/REWRITE/... 等")
    expert_app: str = Field(..., max_length=255, description="expert的app（Dapr app ID，如 maga-worker）")
    expert_service: str = Field(..., max_length=255, description="expert的service名称")
    expert_func: str = Field(..., max_length=255, description="expert的方法标识（历史遗留命名；当前作为 HTTP path 的一段，如 ReviewBan）")
    expert_func_name: Optional[str] = Field(default=None, max_length=128, description="expert_func 的显示名称（用于图表展示，如：内容质量、品牌匹配）")
    description: Optional[str] = Field(default=None, description="expert 配置描述")
    model_code: Optional[str] = Field(default=None, max_length=255, description="使用的模型编码")
    model_config_data: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="model_config", validation_alias="model_config", description="模型参数配置")
    plugin_config: Optional[List[Dict[str, Any]]] = Field(default=None, description="插件配置数组，格式: [{plugin_code, variable_mapping}]")
    prompt_template: Optional[str] = Field(default=None, description="prompt 模板（如果提供 plugin_config，将自动生成）")
    enabled: bool = Field(default=True, description="是否可用")
    remark: Optional[str] = Field(default=None, description="备注")


class ExpertConfigCreate(ExpertConfigBase):
    """ExpertConfig create schema"""
    pass


class ExpertConfigCopyRequest(BaseSchema):
    """复制 ExpertConfig 的请求体（仅允许覆盖 code/name，其余字段全量复制源配置）"""

    expert_config_code: str = Field(..., max_length=64, description="新 expert_config 配置 code")
    expert_config_name: str = Field(..., max_length=255, description="新 expert_config 名称")


class ExpertConfigUpdate(BaseSchema):
    """ExpertConfig update schema"""
    expert_config_name: Optional[str] = Field(default=None, max_length=255)
    tenant_code: Optional[str] = Field(default=None, max_length=64, description="归属租户编码")
    expert_type: Optional[str] = Field(default=None, max_length=64)
    expert_app: Optional[str] = Field(default=None, max_length=255)
    expert_service: Optional[str] = Field(default=None, max_length=255)
    expert_func: Optional[str] = Field(default=None, max_length=255)
    expert_func_name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = None
    model_code: Optional[str] = Field(default=None, max_length=255)
    model_config_data: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="model_config", validation_alias="model_config")
    plugin_config: Optional[List[Dict[str, Any]]] = None
    prompt_template: Optional[str] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = None


class ExpertConfigInDB(ExpertConfigBase, TimestampSchema):
    """ExpertConfig in database schema"""
    id: int
    tenant_code: Optional[str] = None
    publish_status: str = Field(default="DRAFT", description="上线状态：DRAFT(草稿)/PUBLISHED(已上线)")
    publish_time: Optional[datetime] = Field(default=None, description="上线时间")
    publish_by: Optional[str] = Field(default=None, description="上线人")
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_deleted: bool = Field(default=False, description="是否删除")


class ExpertConfigResponse(ExpertConfigInDB):
    """ExpertConfig response schema"""
    pass
