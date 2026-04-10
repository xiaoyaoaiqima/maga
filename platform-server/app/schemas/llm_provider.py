"""
LLM Provider schemas

包含：
- LLMProviderConfig：提供商配置
- LLMModelRoute：模型路由
- LLMCircuitBreaker：熔断状态
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema, TimestampSchema


# ==================== LLM Provider Config ====================

class LLMProviderConfigBase(BaseSchema):
    """LLM Provider 配置基础 Schema"""
    provider_code: str = Field(..., max_length=64, description="提供商编码（唯一标识）")
    provider_name: str = Field(..., max_length=128, description="提供商名称")
    provider_type: str = Field(
        default="openai_compatible",
        max_length=32,
        description="类型：openai_compatible/gemini_native/azure"
    )
    base_url: str = Field(..., max_length=512, description="API 端点地址")
    default_model: Optional[str] = Field(default=None, max_length=128, description="默认模型")
    available_models: Optional[List[str]] = Field(default=None, description="可用模型列表")
    default_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="默认参数（temperature/max_tokens/top_p）"
    )
    rate_limit: Optional[Dict[str, Any]] = Field(default=None, description="速率限制配置")
    timeout: int = Field(default=120, ge=1, le=600, description="超时时间（秒）")
    priority: int = Field(default=0, ge=0, le=1000, description="优先级（越大越优先）")
    enabled: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(default=None, description="描述")


class LLMProviderConfigCreate(LLMProviderConfigBase):
    """创建 LLM Provider 配置"""
    api_key: str = Field(..., min_length=1, description="API Key")


class LLMProviderConfigUpdate(BaseSchema):
    """更新 LLM Provider 配置"""
    provider_name: Optional[str] = Field(default=None, max_length=128)
    provider_type: Optional[str] = Field(default=None, max_length=32)
    base_url: Optional[str] = Field(default=None, max_length=512)
    api_key: Optional[str] = Field(default=None, description="API Key（留空表示不修改）")
    default_model: Optional[str] = Field(default=None, max_length=128)
    available_models: Optional[List[str]] = None
    default_params: Optional[Dict[str, Any]] = None
    rate_limit: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = Field(default=None, ge=1, le=600)
    priority: Optional[int] = Field(default=None, ge=0, le=1000)
    enabled: Optional[bool] = None
    description: Optional[str] = None


class LLMProviderConfigInDB(LLMProviderConfigBase):
    """数据库中的 LLM Provider 配置"""
    id: int
    api_key: str = Field(..., description="API Key（脱敏显示）")
    api_key_encrypted: int = Field(default=0, description="是否已加密")
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    is_deleted: Optional[int] = 0


class LLMProviderConfigResponse(BaseSchema):
    """LLM Provider 配置响应（API Key 脱敏）"""
    id: int
    provider_code: str
    provider_name: str
    provider_type: str
    base_url: str
    api_key_masked: str = Field(..., description="脱敏后的 API Key（如 sk-****Ac21）")
    default_model: Optional[str] = None
    available_models: Optional[List[str]] = None
    default_params: Optional[Dict[str, Any]] = None
    rate_limit: Optional[Dict[str, Any]] = None
    timeout: int = 120
    priority: int = 0
    enabled: bool = True
    description: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


class LLMProviderConfigDetail(LLMProviderConfigResponse):
    """LLM Provider 配置详情（内部接口，包含解密后的 API Key）"""
    api_key: str = Field(..., description="解密后的 API Key（仅内部使用）")


class LLMProviderConfigList(BaseSchema):
    """LLM Provider 配置列表响应"""
    items: List[LLMProviderConfigResponse]
    total: int


# ==================== LLM Model Route ====================

class LLMModelRouteBase(BaseSchema):
    """模型路由基础 Schema"""
    model_code: str = Field(..., max_length=64, description="统一模型编码（业务使用）")
    model_name: str = Field(..., max_length=128, description="模型显示名称")
    provider_code: str = Field(..., max_length=64, description="端点编码")
    provider_model: str = Field(..., max_length=128, description="该端点的实际模型名")
    priority: int = Field(default=0, ge=0, le=1000, description="优先级（越大越优先）")
    enabled: bool = Field(default=True, description="是否启用")
    max_context_length: Optional[int] = Field(default=None, ge=0, description="最大上下文长度")
    features: Optional[Dict[str, bool]] = Field(
        default=None,
        description="支持的功能（vision/function_calling/json_mode）"
    )
    cost_per_1k_input: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="输入成本（每 1K tokens，美元）"
    )
    cost_per_1k_output: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="输出成本（每 1K tokens，单位见 currency）"
    )
    currency: str = Field(
        default="USD",
        max_length=10,
        description="计价币种（USD/CNY）"
    )
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=600, description="超时时间")
    description: Optional[str] = Field(default=None, description="描述")


class LLMModelRouteCreate(LLMModelRouteBase):
    """创建模型路由"""
    pass


class LLMModelRouteUpdate(BaseSchema):
    """更新模型路由"""
    model_name: Optional[str] = Field(default=None, max_length=128)
    provider_model: Optional[str] = Field(default=None, max_length=128)
    priority: Optional[int] = Field(default=None, ge=0, le=1000)
    enabled: Optional[bool] = None
    max_context_length: Optional[int] = Field(default=None, ge=0)
    features: Optional[Dict[str, bool]] = None
    cost_per_1k_input: Optional[Decimal] = Field(default=None, ge=0)
    cost_per_1k_output: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=10)
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=600)
    description: Optional[str] = None


class LLMModelRouteResponse(LLMModelRouteBase):
    """模型路由响应"""
    id: int
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None


class LLMModelRouteList(BaseSchema):
    """模型路由列表响应"""
    items: List[LLMModelRouteResponse]
    total: int


# ==================== LLM Circuit Breaker ====================

class LLMCircuitBreakerResponse(BaseSchema):
    """熔断状态响应"""
    id: int
    provider_code: str
    state: str = Field(..., description="状态：closed/open/half_open")
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_failure_reason: Optional[str] = None
    open_until: Optional[datetime] = None
    update_time: Optional[datetime] = None


class LLMCircuitBreakerList(BaseSchema):
    """熔断状态列表响应"""
    items: List[LLMCircuitBreakerResponse]


# ==================== 可用模型列表 ====================

class AvailableModel(BaseSchema):
    """可用模型信息"""
    model_code: str = Field(..., description="统一模型编码")
    model_name: str = Field(..., description="模型显示名称")
    providers: List[str] = Field(..., description="支持该模型的端点列表")
    max_context_length: Optional[int] = None
    features: Optional[Dict[str, bool]] = None
    cost_per_1k_input: Optional[float] = Field(default=None, description="输入成本（/1K Token）")
    cost_per_1k_output: Optional[float] = Field(default=None, description="输出成本（/1K Token）")
    currency: str = Field(default="USD", description="计价币种")


class AvailableModelList(BaseSchema):
    """可用模型列表响应"""
    items: List[AvailableModel]
    total: int


# ==================== 远程模型 ====================

class RemoteModelInfo(BaseSchema):
    """远程模型信息（从 Provider API 获取）"""
    model_id: str = Field(..., description="模型 ID")
    model_name: str = Field(..., description="模型名称")
    description: Optional[str] = Field(default=None, description="模型描述")
    model_type: str = Field(default="llm", description="模型类型（llm/image_generation/embedding 等）")
    features: List[str] = Field(default_factory=list, description="支持的功能特性")
    input_modalities: List[str] = Field(default_factory=lambda: ["text"], description="支持的输入模态")
    max_output: Optional[int] = Field(default=None, description="最大输出 Token 数")
    context_length: Optional[int] = Field(default=None, description="上下文长度")
    cost_per_1k_input: Optional[float] = Field(default=None, description="输入成本（/1K Token）")
    cost_per_1k_output: Optional[float] = Field(default=None, description="输出成本（/1K Token）")
    currency: str = Field(default="USD", description="计价币种")


class RemoteModelList(BaseSchema):
    """远程模型列表响应"""
    items: List[RemoteModelInfo]
    total: int
    provider_code: str = Field(..., description="Provider 编码")


class SyncModelsRequest(BaseSchema):
    """同步模型请求"""
    model_ids: Optional[List[str]] = Field(
        default=None,
        description="要同步的模型 ID 列表，为空则同步所有 LLM 模型"
    )
    overwrite: bool = Field(
        default=False,
        description="是否覆盖已存在的路由"
    )


class SyncModelsResponse(BaseSchema):
    """同步模型响应"""
    synced_count: int = Field(..., description="成功同步的数量")
    skipped_count: int = Field(..., description="跳过的数量（已存在）")
    failed_count: int = Field(..., description="失败的数量")
    details: List[Dict[str, Any]] = Field(default_factory=list, description="同步详情")


# ==================== 连接测试 ====================

class ConnectionTestRequest(BaseSchema):
    """连接测试请求"""
    test_prompt: Optional[str] = Field(
        default="Hello, respond with 'OK' if you receive this.",
        description="测试 Prompt"
    )


class ConnectionTestResponse(BaseSchema):
    """连接测试响应"""
    success: bool
    latency_ms: Optional[int] = None
    response_preview: Optional[str] = Field(default=None, description="响应预览（前 100 字符）")
    error_message: Optional[str] = None


class FetchRemoteModelsRequest(BaseSchema):
    """获取远程模型请求（用于新增 Provider 时测试）"""
    base_url: str = Field(..., description="API 端点地址")
    api_key: str = Field(..., description="API Key")
    provider_type: str = Field(default="openai_compatible", description="Provider 类型")
    model_type: Optional[str] = Field(default="llm", description="模型类型过滤")


# ==================== 工具函数 ====================

def mask_api_key(api_key: str) -> str:
    """API Key 脱敏展示"""
    if not api_key:
        return "****"
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "****" + api_key[-4:]

