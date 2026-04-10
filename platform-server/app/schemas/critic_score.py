"""
CriticScore Schemas - Critic 评分相关 Schema
"""
from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, Field


# ==================== 评分记录 Schema ====================

class CriticScoreRecordBase(BaseModel):
    """评分记录基础 Schema"""
    job_id: str
    sub_job_id: str
    content_id: str
    source_type: Optional[str] = Field(default="job", description="来源类型：job/eval_run/debug")
    # job 场景专属字段
    tenant_id: Optional[int] = Field(default=None, description="租户ID（job场景）")
    activity_id: Optional[int] = Field(default=None, description="活动ID（job场景）")
    # eval_run 场景专属字段
    dataset_code: Optional[str] = Field(default=None, description="数据集标识")
    run_id: Optional[int] = Field(default=None, description="eval_run id")
    test_case_id: Optional[int] = Field(default=None, description="test_case id")
    # debug 场景专属字段
    debug_history_id: Optional[int] = Field(default=None, description="调试历史ID（debug场景）")
    # 通用字段
    expert_config_code: str
    expert_func: str
    score: int = Field(ge=0, le=100)
    passed: bool
    reason: Optional[str] = None
    highlights: Optional[str] = None
    # 兼容字段（旧）：problem_context_list
    problem_context_list: Optional[List[str]] = Field(
        default=None,
        description="问题上下文列表（旧字段，建议使用 problem_tags/problem_snippets）",
    )

    # 新字段（推荐）
    problem_tags: Optional[List[str]] = Field(default=None, description="问题标签列表")
    problem_snippets: Optional[List[str]] = Field(default=None, description="问题片段列表（用于高亮展示）")
    expert_task_id: Optional[int] = None
    model_code: Optional[str] = None
    provider_code: Optional[str] = None
    duration_ms: Optional[int] = None
    trace_id: Optional[str] = None


class CriticScoreRecordCreate(CriticScoreRecordBase):
    """创建评分记录 Schema"""
    ...


class CriticScoreRecordResponse(CriticScoreRecordBase):
    """评分记录响应 Schema"""
    id: int
    version: int
    create_time: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ==================== 查询参数 Schema ====================

class CriticScoreListQuery(BaseModel):
    """评分记录列表查询参数"""
    job_id: Optional[str] = None
    content_id: Optional[str] = None
    expert_func: Optional[str] = None
    model_code: Optional[str] = None
    score_min: Optional[int] = Field(None, ge=0, le=100)
    score_max: Optional[int] = Field(None, ge=0, le=100)
    passed: Optional[bool] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    skip: int = 0
    limit: int = Field(100, le=1000)


# ==================== 统计分析 Schema ====================

class CriticScoreSummary(BaseModel):
    """汇总统计响应"""
    total_count: int
    passed_count: int
    pass_rate: float
    avg_score: float
    min_score: int
    max_score: int
    avg_duration_ms: float


class CriticScoreTrendItem(BaseModel):
    """趋势数据项"""
    date: str
    total_count: int
    passed_count: int
    pass_rate: float
    avg_score: float


class CriticScoreModelComparison(BaseModel):
    """模型对比数据项"""
    model_code: str
    total_count: int
    passed_count: int
    pass_rate: float
    avg_score: float
    avg_duration_ms: float


class CriticScoreDistributionItem(BaseModel):
    """分数分布项"""
    range: str
    min: int
    max: int
    count: int


class CriticDimensionHeatmapResponse(BaseModel):
    """维度×分数段热力图数据"""
    dimensions: List[str] = Field(..., description="Y轴：维度名称列表")
    score_ranges: List[str] = Field(..., description="X轴：分数段标签")
    data: List[List[int]] = Field(..., description="热力图数据 [[dim_idx, range_idx, count], ...]")


class CriticScatterDataItem(BaseModel):
    """散点图数据项（用于 Scatter with Jittering）"""
    dimension: str = Field(..., description="评分维度")
    score: int = Field(..., description="分数")
    content_id: str = Field(..., description="文章ID")


# ==================== 热点统计 Schema ====================

class CriticProblemContextTopItem(BaseModel):
    """热门问题上下文 Top 项"""
    key: str
    count: int


class CriticDatasetItem(BaseModel):
    """数据集下拉项（来自 critic_score_record.dataset_code）"""
    dataset_code: str
    total: int


# ==================== 词云 Schema ====================

class CriticReasonWordCloudItem(BaseModel):
    """评分理由词云项（后端切词统计）"""
    word: str
    count: int


# ==================== 下拉选项 Schema ====================

class ExpertConfigOptionItem(BaseModel):
    """Expert Config 下拉选项（用于下拉选择和图表显示）"""
    expert_config_code: str = Field(..., description="Expert 配置编码")
    expert_config_name: str = Field(..., description="Expert 配置名称")
    expert_type: str = Field(..., description="Expert 类型：CRITIC / BAN")
    expert_func: str = Field(..., description="Expert 函数标识")
    expert_func_name: Optional[str] = Field(default=None, description="Expert 函数显示名称（用于图表）")


# ==================== 内容历史 Schema ====================

class ContentScoreHistory(BaseModel):
    """内容评分历史"""
    content_id: str
    expert_func: str
    records: List[CriticScoreRecordResponse]
