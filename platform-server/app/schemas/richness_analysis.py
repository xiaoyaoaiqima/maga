"""
内容丰富度分析 Schemas

基于 content.context_list 字段中预先标注的维度分数（1-10），
分析指定 job_id 下文章池的内容丰富度。
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import Field

from app.schemas.base import BaseSchema


# 默认分析维度（中文名称）
DEFAULT_RICHNESS_DIMENSIONS = [
    "信息密度",
    "情绪强度",
    "表达精度",
    "质量档位",
    "瑕疵容忍度",
    "真实感程度",
    "细节颗粒度",
    "结构复杂度",
    "场景描述+妈妈痛点+产品卖点+关键词",
]


class DimensionStats(BaseSchema):
    """单维度的统计信息"""
    min: float = Field(..., description="最小值")
    max: float = Field(..., description="最大值")
    avg: float = Field(..., description="平均值")
    std: float = Field(..., description="标准差")


class RichnessDimensionDetail(BaseSchema):
    """单维度的丰富度详情"""
    dimension_name: str = Field(..., description="维度名称")
    total_count: int = Field(..., description="该维度有效文章数")
    stats: DimensionStats = Field(..., description="统计信息（min/max/avg/std）")
    distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="各分值的文章数量，如: {'1': 5, '2': 15, '3': 40, ...}"
    )
    percentage: Dict[str, float] = Field(
        default_factory=dict,
        description="各分值的占比(0-100)，如: {'1': 5.0, '2': 15.0, ...}"
    )
    uniformity_score: float = Field(
        ...,
        description="分布均匀度评分(0-100)，基于信息熵计算，越均匀分数越高"
    )
    coverage_score: float = Field(
        ...,
        description="分值覆盖度评分(0-100)，覆盖的分值种类越多分数越高"
    )
    high_score_ratio: float = Field(
        ...,
        description="高分占比(0-100)，分值>=7的文章占比（1-10分制）"
    )


class ScoreBreakdown(BaseSchema):
    """综合评分分解"""
    distribution_uniformity: float = Field(
        ...,
        description="分布均匀度（所有维度的平均均匀度）"
    )
    coverage_rate: float = Field(
        ...,
        description="分值覆盖度（所有维度的平均覆盖度）"
    )
    high_score_ratio: float = Field(
        ...,
        description="高分占比（所有维度的平均高分比）"
    )


class GapInfo(BaseSchema):
    """缺口信息"""
    dimension: str = Field(..., description="维度名称")
    gap_type: str = Field(
        default="missing_values",
        description="缺口类型: missing_values（缺少分值）, low_count（数量过少）, combo（组合缺失）"
    )
    missing_values: List[int] = Field(
        default_factory=list,
        description="缺失的分值列表"
    )
    low_count_values: Dict[str, int] = Field(
        default_factory=dict,
        description="数量过少的分值及其数量，如: {'1': 2, '2': 3}"
    )
    suggestion: str = Field(
        default="",
        description="补充建议"
    )


class ComboGapInfo(BaseSchema):
    """组合缺口信息"""
    dimensions: List[str] = Field(..., description="涉及的维度列表")
    gap_type: str = Field(default="combo", description="缺口类型")
    missing_combos: List[Dict[str, str]] = Field(
        default_factory=list,
        description="缺失的维度组合，如: [{'信息密度': '高', '结构复杂度': '高'}]"
    )
    description: str = Field(default="", description="缺口描述")


class RichnessAnalysisRequest(BaseSchema):
    """丰富度分析请求"""
    job_id: str = Field(..., description="Job ID，分析该 Job 下的所有文章")
    dimensions: Optional[List[str]] = Field(
        default=None,
        description="要分析的维度列表，为空则使用默认 9 个维度"
    )
    include_invalid: bool = Field(
        default=False,
        description="是否包含无效文章 (is_valid=0)"
    )
    include_test: bool = Field(
        default=False,
        description="是否包含测试文章 (is_test_case=1)"
    )
    # 权重配置（可选）
    weight_uniformity: float = Field(
        default=0.3,
        description="分布均匀度权重，默认 0.3"
    )
    weight_coverage: float = Field(
        default=0.4,
        description="分值覆盖度权重，默认 0.4"
    )
    weight_high_score: float = Field(
        default=0.3,
        description="高分占比权重，默认 0.3"
    )
    # 缺口分析阈值
    low_count_threshold: int = Field(
        default=3,
        description="低数量阈值，文章数少于此值视为数量过少"
    )
    # 组合分析配置
    combo_dimensions: Optional[List[List[str]]] = Field(
        default=None,
        description="要分析的维度组合，如: [['信息密度', '结构复杂度'], ['质量档位', '真实感程度']]"
    )


class RichnessAnalysisResponse(BaseSchema):
    """丰富度分析响应"""
    job_id: str = Field(..., description="Job ID")
    total_articles: int = Field(..., description="分析的文章总数")
    analysis_time: datetime = Field(
        default_factory=datetime.now,
        description="分析时间"
    )
    
    # 综合评分 (0-100)
    richness_score: float = Field(
        ...,
        description="综合丰富度评分(0-100)"
    )
    score_breakdown: ScoreBreakdown = Field(
        ...,
        description="综合评分分解"
    )
    
    # 各维度详情
    dimensions: List[RichnessDimensionDetail] = Field(
        default_factory=list,
        description="各维度的丰富度详情"
    )
    
    # 缺口分析
    gaps: List[GapInfo] = Field(
        default_factory=list,
        description="单维度缺口分析"
    )
    combo_gaps: List[ComboGapInfo] = Field(
        default_factory=list,
        description="组合缺口分析"
    )
    
    # 生成建议权重
    generation_guidance: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="生文指导权重，格式: {'维度名': {'低': 0.5, '中': 0.3, '高': 0.2}}"
    )
