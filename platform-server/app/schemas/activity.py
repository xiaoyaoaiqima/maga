"""
Activity schemas - 活动相关 Pydantic 模型
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.base import TimestampSchema


# ============== 问题选项 Schema ==============

class ActivityQuestionOptionBase(BaseModel):
    """问题选项基础信息"""
    display_label: str = Field(..., min_length=1, max_length=255, description="小程序展示可替换标签")
    aigc_tag: str = Field(..., min_length=1, max_length=128, description="AIGC对应标签")
    weight: Decimal = Field(default=Decimal("1.0"), description="标签对应权重")
    sort_order: int = Field(default=0, description="排序")


class ActivityQuestionOptionCreate(ActivityQuestionOptionBase):
    """创建问题选项"""
    pass


class ActivityQuestionOptionUpdate(BaseModel):
    """更新问题选项"""
    id: Optional[int] = Field(None, description="选项ID（更新时需要）")
    display_label: Optional[str] = Field(None, min_length=1, max_length=255, description="小程序展示可替换标签")
    aigc_tag: Optional[str] = Field(None, min_length=1, max_length=128, description="AIGC对应标签")
    weight: Optional[Decimal] = Field(None, description="标签对应权重")
    sort_order: Optional[int] = Field(None, description="排序")


class ActivityQuestionOptionResponse(ActivityQuestionOptionBase):
    """问题选项响应"""
    id: int = Field(..., description="选项ID")
    question_id: int = Field(..., description="问题ID")
    enabled: int = Field(..., description="是否启用")
    
    model_config = ConfigDict(from_attributes=True)


# ============== 问题 Schema ==============

class ActivityQuestionBase(BaseModel):
    """活动问题基础信息"""
    question_text: str = Field(..., min_length=1, max_length=500, description="问题内容")
    min_select: Optional[int] = Field(None, ge=0, description="最小选择数（空则不限制）")
    max_select: Optional[int] = Field(None, ge=1, description="最大选择数（空则不限制）")
    sort_order: int = Field(default=0, description="排序")


class ActivityQuestionCreate(ActivityQuestionBase):
    """创建活动问题"""
    options: List[ActivityQuestionOptionCreate] = Field(default=[], description="问题选项列表")


class ActivityQuestionUpdate(BaseModel):
    """更新活动问题"""
    id: Optional[int] = Field(None, description="问题ID（更新时需要）")
    question_text: Optional[str] = Field(None, min_length=1, max_length=500, description="问题内容")
    min_select: Optional[int] = Field(None, ge=0, description="最小选择数（空则不限制）")
    max_select: Optional[int] = Field(None, ge=1, description="最大选择数（空则不限制）")
    sort_order: Optional[int] = Field(None, description="排序")
    options: Optional[List[ActivityQuestionOptionCreate]] = Field(None, description="问题选项列表（全量替换）")


class ActivityQuestionResponse(ActivityQuestionBase):
    """活动问题响应"""
    id: int = Field(..., description="问题ID")
    activity_id: int = Field(..., description="活动ID")
    enabled: int = Field(..., description="是否启用")
    options: List[ActivityQuestionOptionResponse] = Field(default=[], description="问题选项列表")
    
    model_config = ConfigDict(from_attributes=True)


# ============== 活动基础 Schema ==============

class ActivityBase(BaseModel):
    """活动基础信息"""
    activity_code: str = Field(..., min_length=1, max_length=64, description="活动编码")
    activity_name: str = Field(..., min_length=1, max_length=255, description="活动名称")
    tenant_id: int = Field(..., description="租户ID")
    agent_code_list: Optional[List[str]] = Field(None, description="使用 Agent（产品模板）编码列表")
    channel: Optional[str] = Field(None, max_length=64, description="渠道")
    target_audience: Optional[str] = Field(None, max_length=255, description="目标人群")
    budget: Optional[Decimal] = Field(None, description="预算")
    config_json: Optional[Dict[str, Any]] = Field(None, description="活动配置")
    start_time: Optional[datetime] = Field(None, description="活动开始时间")
    end_time: Optional[datetime] = Field(None, description="活动结束时间")
    status: str = Field(default="DRAFT", description="状态：DRAFT/RUNNING/PAUSED/COMPLETED")
    remark: Optional[str] = Field(None, description="备注")


class ActivityCreate(ActivityBase):
    """创建活动"""
    questions: Optional[List[ActivityQuestionCreate]] = Field(None, description="活动问题列表")


class ActivityUpdate(BaseModel):
    """更新活动"""
    activity_name: Optional[str] = Field(None, min_length=1, max_length=255, description="活动名称")
    tenant_id: Optional[int] = Field(None, description="租户ID")
    agent_code_list: Optional[List[str]] = Field(None, description="使用 Agent（产品模板）编码列表")
    channel: Optional[str] = Field(None, max_length=64, description="渠道")
    target_audience: Optional[str] = Field(None, max_length=255, description="目标人群")
    budget: Optional[Decimal] = Field(None, description="预算")
    config_json: Optional[Dict[str, Any]] = Field(None, description="活动配置")
    start_time: Optional[datetime] = Field(None, description="活动开始时间")
    end_time: Optional[datetime] = Field(None, description="活动结束时间")
    status: Optional[str] = Field(None, description="状态")
    remark: Optional[str] = Field(None, description="备注")
    questions: Optional[List[ActivityQuestionUpdate]] = Field(None, description="活动问题列表（全量替换）")


class ActivityResponse(ActivityBase, TimestampSchema):
    """活动响应"""
    id: int = Field(..., description="活动ID")
    enabled: int = Field(..., description="是否启用")
    created_by: Optional[str] = Field(None, description="创建人")
    updated_by: Optional[str] = Field(None, description="更新人")
    
    # 关联信息
    tenant_name: Optional[str] = Field(None, description="租户名称")
    tenant_code: Optional[str] = Field(None, description="租户编码")
    
    # 问题列表
    questions: Optional[List[ActivityQuestionResponse]] = Field(None, description="活动问题列表")
    
    model_config = ConfigDict(from_attributes=True)


class ActivityListResponse(BaseModel):
    """活动列表响应"""
    total: int = Field(..., description="总数")
    items: List[ActivityResponse] = Field(..., description="活动列表")


# ============== 查询参数 ==============

class ActivityFilters(BaseModel):
    """活动查询过滤"""
    tenant_id: Optional[int] = Field(None, description="租户ID")
    activity_code: Optional[str] = Field(None, description="活动编码（模糊匹配）")
    activity_name: Optional[str] = Field(None, description="活动名称（模糊匹配）")
    channel: Optional[str] = Field(None, description="渠道")
    status: Optional[str] = Field(None, description="状态")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量")


# ============== 状态变更 ==============

class ActivityStatusUpdate(BaseModel):
    """活动状态变更"""
    status: str = Field(..., description="新状态：DRAFT/RUNNING/PAUSED/COMPLETED")


# ============== 简单活动列表（下拉框用）==============

class ActivitySimpleItem(BaseModel):
    """简单活动项"""
    id: int = Field(..., description="活动ID")
    activity_code: str = Field(..., description="活动编码")
    activity_name: str = Field(..., description="活动名称")
    tenant_id: int = Field(..., description="租户ID")
    status: str = Field(..., description="状态")
    
    model_config = ConfigDict(from_attributes=True)


# ============== 问题与标签单独操作 ==============

class ActivityQuestionsUpdate(BaseModel):
    """活动问题批量更新（全量替换）"""
    questions: List[ActivityQuestionCreate] = Field(..., description="活动问题列表")
