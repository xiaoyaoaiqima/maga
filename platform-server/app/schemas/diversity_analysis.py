"""
内容多样性/人设分布分析 Schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import Field

from app.schemas.base import BaseSchema


class DimensionDistribution(BaseSchema):
    """单个维度的分布统计"""
    dimension_name: str = Field(..., description="维度名称，如: 写者、platform")
    total_count: int = Field(..., description="该维度的总文章数")
    distribution: Dict[str, int] = Field(
        default_factory=dict, 
        description="各选项的文章数量，如: {'通勤战士': 50, '斜杠妈妈': 140}"
    )
    percentage: Dict[str, float] = Field(
        default_factory=dict, 
        description="各选项的占比(0-100)，如: {'通勤战士': 26.3, '斜杠妈妈': 73.7}"
    )
    recommended_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="推荐生文权重(0-1)，占比低的权重高，如: {'通勤战士': 0.7, '斜杠妈妈': 0.3}"
    )


class DiversityAnalysisRequest(BaseSchema):
    """多样性分析请求"""
    job_id: str = Field(..., description="Job ID，分析该 Job 下的所有文章")
    dimensions: Optional[List[str]] = Field(
        default=None,
        description="要分析的维度列表，如: ['写者', 'platform']。为空则分析所有维度"
    )
    include_invalid: bool = Field(
        default=False,
        description="是否包含无效文章 (is_valid=0)"
    )
    include_test: bool = Field(
        default=False,
        description="是否包含测试文章 (is_test_case=1)"
    )


class DiversityAnalysisResponse(BaseSchema):
    """多样性分析响应"""
    job_id: str = Field(..., description="Job ID")
    total_articles: int = Field(..., description="分析的文章总数")
    analysis_time: datetime = Field(default_factory=datetime.now, description="分析时间")
    
    # 各维度分布
    dimensions: List[DimensionDistribution] = Field(
        default_factory=list,
        description="各维度的分布统计"
    )
    
    # 汇总信息
    low_coverage_alerts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="低覆盖率告警，格式: [{'dimension': '写者', 'option': '生活美学家', 'count': 2, 'percentage': 1.0}]"
    )
    
    generation_guidance: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="生文指导权重，格式: {'写者': {'通勤战士': 0.7, '斜杠妈妈': 0.3}}"
    )
