"""
Agent schemas - Agent 产品相关 Pydantic 模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from app.schemas.base import TimestampSchema


# ============== 基础 Schema ==============

class AgentBase(BaseModel):
    """Agent 基础信息"""
    agent_code: str = Field(..., min_length=1, max_length=64, description="Agent 编码")
    agent_name: str = Field(..., min_length=1, max_length=255, description="Agent 名称")
    agent_type: str = Field(
        default="BATCH_GENERATION", 
        description="类型：BATCH_GENERATION/REALTIME_CHAT/REPORT_ANALYSIS"
    )
    expert_config_code_list: List[str] = Field(..., min_length=1, description="Expert 编排顺序")
    zero_score_invalid_expert_codes: Optional[List[str]] = Field(
        default=None,
        description=(
            "当这些打分型 Expert 返回 score==0 时，将内容判定为不可用；"
            "None 表示兼容旧逻辑（任意打分 Expert score==0 都判无效）；[] 表示不启用 score==0 判无效"
        ),
    )
    tags_config: Optional[Dict[str, Any]] = Field(None,  description="要素标签配置")
    expert_prepared_job_list: Optional[List[str]] = Field(None,  description="Expert 预备好的任务列表（job_id 列表）")
    default_model_code: Optional[str] = Field(None, max_length=64, description="默认模型编码")
    default_config: Optional[Dict[str, Any]] = Field(None, description="默认参数配置")
    description: Optional[str] = Field(None, description="功能描述")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="输入参数 schema")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="输出格式 schema")
    tenant_id: Optional[int] = Field(None, description="租户ID（NULL 表示全局共享）")
    rate_limit: Optional[Dict[str, Any]] = Field(None, description="限流配置")
    remark: Optional[str] = Field(None, description="备注")


class AgentCreate(AgentBase):
    """创建 Agent"""
    pass


class AgentUpdate(BaseModel):
    """更新 Agent"""
    agent_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Agent 名称")
    agent_type: Optional[str] = Field(None, description="类型")
    expert_config_code_list: Optional[List[str]] = Field(None, min_length=1, description="Expert 编排顺序")
    zero_score_invalid_expert_codes: Optional[List[str]] = Field(
        default=None,
        description="0 分判无效 Expert 列表（None=兼容旧逻辑；[]/list=新逻辑）",
    )
    default_model_code: Optional[str] = Field(None, max_length=64, description="默认模型编码")
    default_config: Optional[Dict[str, Any]] = Field(None, description="默认参数配置")
    description: Optional[str] = Field(None, description="功能描述")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="输入参数 schema")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="输出格式 schema")
    tenant_id: Optional[int] = Field(None, description="租户ID")
    rate_limit: Optional[Dict[str, Any]] = Field(None, description="限流配置")
    remark: Optional[str] = Field(None, description="备注")


class AgentResponse(AgentBase, TimestampSchema):
    """Agent 响应"""
    id: int = Field(..., description="Agent ID")
    enabled: int = Field(..., description="是否启用")
    publish_status: str = Field(default="DRAFT", description="上线状态：DRAFT(草稿)/PUBLISHED(已上线)")
    publish_time: Optional[datetime] = Field(default=None, description="上线时间")
    publish_by: Optional[str] = Field(default=None, description="上线人")
    created_by: Optional[str] = Field(None, description="创建人")
    updated_by: Optional[str] = Field(None, description="更新人")

    # 关联信息
    tenant_name: Optional[str] = Field(None, description="租户名称")
    tenant_code: Optional[str] = Field(None, description="租户编码")

    class Config:
        from_attributes = True


class AgentListResponse(BaseModel):
    """Agent 列表响应"""
    total: int = Field(..., description="总数")
    items: List[AgentResponse] = Field(..., description="Agent 列表")


# ============== 查询参数 ==============

class AgentFilters(BaseModel):
    """Agent 查询过滤"""
    agent_code: Optional[str] = Field(None, description="Agent 编码（模糊匹配）")
    agent_name: Optional[str] = Field(None, description="Agent 名称（模糊匹配）")
    agent_type: Optional[str] = Field(None, description="Agent 类型")
    tenant_id: Optional[int] = Field(None, description="租户ID（含全局共享）")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量")


# ============== 简单 Agent 列表（下拉框用）==============

class AgentSimpleItem(BaseModel):
    """简单 Agent 项"""
    id: int = Field(..., description="Agent ID")
    agent_code: str = Field(..., description="Agent 编码")
    agent_name: str = Field(..., description="Agent 名称")
    agent_type: str = Field(..., description="Agent 类型")
    
    class Config:
        from_attributes = True


# ============== Agent 类型枚举 ==============

class AgentTypeEnum:
    """Agent 类型枚举"""
    BATCH_GENERATION = "BATCH_GENERATION"
    REALTIME_CHAT = "REALTIME_CHAT"
    REPORT_ANALYSIS = "REPORT_ANALYSIS"
    
    @classmethod
    def values(cls) -> List[str]:
        return [cls.BATCH_GENERATION, cls.REALTIME_CHAT, cls.REPORT_ANALYSIS]


# ============== Agent 列表请求 ==============

class AgentListRequest(BaseModel):
    """Agent 列表请求"""
    agent_code: Optional[str] = Field(None, description="Agent 编码（模糊匹配）")
    agent_name: Optional[str] = Field(None, description="Agent 名称（模糊匹配）")
    agent_type: Optional[str] = Field(None, description="Agent 类型")
    remark: Optional[str] = Field(None, description="备注（模糊匹配）")
    enabled: Optional[bool] = Field(None, description="是否启用")
    tenant_id: Optional[int] = Field(None, description="租户名称（模糊匹配）")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量")


class AgentListResponseData(BaseModel):
    """Agent 列表响应数据"""
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    total: int = Field(..., description="总数")
    total_pages: int = Field(..., description="总页数")
    items: List[AgentResponse] = Field(..., description="Agent 列表")


# ============== Agent 复制请求 ==============

class AgentCopyRequest(BaseModel):
    """Agent 复制请求"""
    agent_id: int = Field(..., description="要复制的 Agent id")


# ============== Agent 标签相关 ==============

class TagItem(BaseModel):
    """标签项"""
    tag_name: str = Field(..., description="标签名称")


class TagTypeConfig(BaseModel):
    """标签类型配置"""
    tag_type: str = Field(..., description="标签类型名称")
    tag_choose_type: int = Field(..., description="选择类型：0=单选，1=多选")
    tag_list: List[TagItem] = Field(..., description="标签列表")


class AgentTagConfig(BaseModel):
    """Agent标签配置"""
    brand_tag_list: Optional[List[TagTypeConfig]] = Field(None, description="品牌标签列表")
    product_tag_list: Optional[List[TagTypeConfig]] = Field(None, description="产品标签列表")
    activity_tag_list: Optional[List[TagTypeConfig]] = Field(None, description="活动标签列表")


class AgentTagResponse(BaseModel):
    """Agent 标签响应"""
    brand_tag_list: Optional[List[Dict[str, Any]]] = Field(None, description="品牌标签列表（数组）")
    product_tag_list: Optional[List[Dict[str, Any]]] = Field(None, description="产品标签列表（数组）")
    activity_tag_list: Optional[List[Dict[str, Any]]] = Field(None, description="活动标签列表（数组）")


class AgentTagUpdate(BaseModel):
    """Agent 标签更新请求"""
    brand_tag_list: Optional[List[Dict[str, Any]]] = Field(None, description="品牌标签列表（JSON格式，数组）")
    product_tag_list: Optional[List[Dict[str, Any]]] = Field(None, description="产品标签列表（JSON格式，数组）")
    activity_tag_list: Optional[List[Dict[str, Any]]] = Field(None, description="活动标签列表（JSON格式，数组）")


# ============== Agent 信息更新 ==============

class AgentInfoUpdate(BaseModel):
    """Agent 信息更新请求（名称和备注）"""
    agent_name: Optional[str] = Field(None, description="Agent 名称", max_length=128)
    remark: Optional[str] = Field(None, description="备注", max_length=500)
