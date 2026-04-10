"""
内容多样性/人设分布分析服务

基于 content 表的 context_list 字段进行统计分析，
识别各维度（人设、活动场景、平台等）的分布情况，
为后续生文提供指导权重。
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Content
from app.schemas.diversity_analysis import (
    DiversityAnalysisRequest,
    DiversityAnalysisResponse,
    DimensionDistribution
)
from app.core.logger import get_logger

logger = get_logger()


class DiversityAnalysisService:
    """多样性分析服务"""
    
    # 低覆盖率阈值（低于此百分比会告警）
    LOW_COVERAGE_THRESHOLD = 5.0
    
    # 关键维度列表（用于默认分析）
    KEY_DIMENSIONS = [
        "写者",           # 用户人设
        "persona_user",   # 用户人设（英文 key）
        "persona_activity",  # 活动场景
        "persona_product",   # 产品卖点
        "platform",          # 平台
        "内容形式",          # 内容形式
        "行文结构",          # 行文结构
    ]
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def analyze(self, request: DiversityAnalysisRequest) -> DiversityAnalysisResponse:
        """
        执行多样性分析
        
        Args:
            request: 分析请求参数
            
        Returns:
            DiversityAnalysisResponse: 分析结果
        """
        logger.info(f"[DiversityAnalysis] Starting analysis for job_id={request.job_id}")
        
        # 1. 查询 content 记录
        contents = await self._query_contents(request)
        
        if not contents:
            logger.warning(f"[DiversityAnalysis] No content found for job_id={request.job_id}")
            return DiversityAnalysisResponse(
                job_id=request.job_id,
                total_articles=0,
                dimensions=[],
                low_coverage_alerts=[],
                generation_guidance={}
            )
        
        logger.info(f"[DiversityAnalysis] Found {len(contents)} articles to analyze")
        
        # 2. 统计各维度分布
        dimension_stats = self._calculate_distribution(
            contents, 
            request.dimensions or self.KEY_DIMENSIONS
        )
        
        # 3. 生成分析结果
        dimensions = []
        generation_guidance = {}
        low_coverage_alerts = []
        
        for dim_name, stats in dimension_stats.items():
            total_count = sum(stats.values())
            
            if total_count == 0:
                continue
            
            # 计算占比
            percentage = {
                option: round(count / total_count * 100, 2)
                for option, count in stats.items()
            }
            
            # 计算推荐权重（反向权重：占比低的权重高）
            recommended_weights = self._calculate_weights(percentage)
            
            # 识别低覆盖率选项
            for option, pct in percentage.items():
                if pct < self.LOW_COVERAGE_THRESHOLD:
                    low_coverage_alerts.append({
                        "dimension": dim_name,
                        "option": option,
                        "count": stats[option],
                        "percentage": pct
                    })
            
            dimensions.append(DimensionDistribution(
                dimension_name=dim_name,
                total_count=total_count,
                distribution=dict(stats),
                percentage=percentage,
                recommended_weights=recommended_weights
            ))
            
            generation_guidance[dim_name] = recommended_weights
        
        # 按低覆盖率排序告警
        low_coverage_alerts.sort(key=lambda x: x["percentage"])
        
        logger.info(
            f"[DiversityAnalysis] Analysis completed: "
            f"dimensions={len(dimensions)}, alerts={len(low_coverage_alerts)}"
        )
        
        return DiversityAnalysisResponse(
            job_id=request.job_id,
            total_articles=len(contents),
            analysis_time=datetime.now(),
            dimensions=dimensions,
            low_coverage_alerts=low_coverage_alerts,
            generation_guidance=generation_guidance
        )
    
    async def _query_contents(
        self, 
        request: DiversityAnalysisRequest
    ) -> List[Content]:
        """查询 content 记录"""
        query = select(Content).where(
            Content.job_id == request.job_id,
            Content.is_deleted == 0,
            Content.context_list.isnot(None)
        )
        
        # 过滤无效文章
        if not request.include_invalid:
            query = query.where(Content.is_valid == 1)
        
        # 过滤测试文章
        if not request.include_test:
            query = query.where(Content.is_test_case == 0)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    def _calculate_distribution(
        self, 
        contents: List[Content],
        dimensions: List[str]
    ) -> Dict[str, Dict[str, int]]:
        """
        计算各维度的分布
        
        Args:
            contents: 文章列表
            dimensions: 要分析的维度列表
            
        Returns:
            Dict[str, Dict[str, int]]: {维度名: {选项: 数量}}
        """
        # 初始化统计结构
        stats: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        for content in contents:
            context_list = content.context_list
            
            if not context_list or not isinstance(context_list, dict):
                continue
            
            # 遍历 context_list 中的每个变量
            for var_name, context_value in context_list.items():
                # 检查是否是我们关心的维度
                if dimensions and var_name not in dimensions:
                    continue
                
                # 跳过空值
                if not context_value:
                    continue
                
                # 统计
                stats[var_name][context_value] += 1
        
        return dict(stats)
    
    def _calculate_weights(self, percentage: Dict[str, float]) -> Dict[str, float]:
        """
        计算推荐权重（反向权重）
        
        占比低的选项获得更高的权重，用于指导后续生文时优先选择。
        
        算法：weight = (100 - percentage) / sum(100 - all_percentages)
        这样可以保证所有权重之和为 1
        
        Args:
            percentage: 各选项的占比
            
        Returns:
            Dict[str, float]: 各选项的推荐权重 (0-1)
        """
        if not percentage:
            return {}
        
        # 计算反向值
        inverse_values = {
            option: max(100 - pct, 1)  # 至少为1，避免权重为0
            for option, pct in percentage.items()
        }
        
        # 归一化
        total = sum(inverse_values.values())
        weights = {
            option: round(value / total, 3)
            for option, value in inverse_values.items()
        }
        
        return weights
    
    async def get_generation_guidance(
        self,
        job_id: str,
        dimensions: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        获取生文指导权重（简化接口）
        
        Args:
            job_id: Job ID
            dimensions: 要分析的维度
            
        Returns:
            生文指导权重字典
        """
        request = DiversityAnalysisRequest(
            job_id=job_id,
            dimensions=dimensions,
            include_invalid=False,
            include_test=False
        )
        
        result = await self.analyze(request)
        return result.generation_guidance
