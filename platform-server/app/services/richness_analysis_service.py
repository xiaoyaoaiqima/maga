"""
内容丰富度分析服务

基于 content 表的 context_list 字段中预标注的维度分数（1-10），
分析文章池的内容丰富度，包括：
- 单维度分析：分布、均匀度、覆盖度、高分比
- 综合评分：加权计算多指标综合分
- 缺口分析：识别缺失的分值和组合
- 生成指导：提供反向权重用于后续生文
"""
import math
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Content
from app.schemas.richness_analysis import (
    RichnessAnalysisRequest,
    RichnessAnalysisResponse,
    RichnessDimensionDetail,
    DimensionStats,
    ScoreBreakdown,
    GapInfo,
    ComboGapInfo,
    DEFAULT_RICHNESS_DIMENSIONS,
)
from app.core.logger import get_logger

logger = get_logger()


class RichnessAnalysisService:
    """内容丰富度分析服务"""
    
    # 分值范围配置
    MIN_SCORE = 1
    MAX_SCORE = 10
    HIGH_SCORE_THRESHOLD = 7  # >= 7 视为高分
    
    # 分档配置（用于组合分析）
    LEVEL_LOW = "低"      # 1-3
    LEVEL_MID = "中"      # 4-6
    LEVEL_HIGH = "高"     # 7-10
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def analyze(self, request: RichnessAnalysisRequest) -> RichnessAnalysisResponse:
        """
        执行丰富度分析
        
        Args:
            request: 分析请求参数
            
        Returns:
            RichnessAnalysisResponse: 分析结果
        """
        logger.info(f"[RichnessAnalysis] Starting analysis for job_id={request.job_id}")
        
        # 1. 查询 content 记录
        contents = await self._query_contents(request)
        
        if not contents:
            logger.warning(f"[RichnessAnalysis] No content found for job_id={request.job_id}")
            return self._empty_response(request.job_id)
        
        logger.info(f"[RichnessAnalysis] Found {len(contents)} articles to analyze")
        
        # 2. 获取要分析的维度
        dimensions = request.dimensions or DEFAULT_RICHNESS_DIMENSIONS
        
        # 3. 提取各维度的分值数据
        dimension_scores = self._extract_dimension_scores(contents, dimensions)
        
        # 4. 计算各维度详情
        dimension_details: List[RichnessDimensionDetail] = []
        all_uniformity_scores: List[float] = []
        all_coverage_scores: List[float] = []
        all_high_score_ratios: List[float] = []
        
        for dim_name in dimensions:
            scores = dimension_scores.get(dim_name, [])
            if not scores:
                continue
            
            detail = self._calculate_dimension_detail(dim_name, scores)
            dimension_details.append(detail)
            
            all_uniformity_scores.append(detail.uniformity_score)
            all_coverage_scores.append(detail.coverage_score)
            all_high_score_ratios.append(detail.high_score_ratio)
        
        # 5. 计算综合评分
        if dimension_details:
            avg_uniformity = sum(all_uniformity_scores) / len(all_uniformity_scores)
            avg_coverage = sum(all_coverage_scores) / len(all_coverage_scores)
            avg_high_score = sum(all_high_score_ratios) / len(all_high_score_ratios)
            
            # 加权综合分
            richness_score = (
                request.weight_uniformity * avg_uniformity +
                request.weight_coverage * avg_coverage +
                request.weight_high_score * avg_high_score
            )
            
            score_breakdown = ScoreBreakdown(
                distribution_uniformity=round(avg_uniformity, 2),
                coverage_rate=round(avg_coverage, 2),
                high_score_ratio=round(avg_high_score, 2)
            )
        else:
            richness_score = 0.0
            score_breakdown = ScoreBreakdown(
                distribution_uniformity=0.0,
                coverage_rate=0.0,
                high_score_ratio=0.0
            )
        
        # 6. 缺口分析
        gaps = self._analyze_gaps(dimension_details, request.low_count_threshold)
        
        # 7. 组合缺口分析
        combo_gaps = []
        if request.combo_dimensions:
            combo_gaps = self._analyze_combo_gaps(
                contents, 
                dimension_scores, 
                request.combo_dimensions
            )
        
        # 8. 生成指导权重
        generation_guidance = self._calculate_generation_guidance(dimension_details)
        
        logger.info(
            f"[RichnessAnalysis] Analysis completed: "
            f"richness_score={richness_score:.2f}, dimensions={len(dimension_details)}, "
            f"gaps={len(gaps)}, combo_gaps={len(combo_gaps)}"
        )
        
        return RichnessAnalysisResponse(
            job_id=request.job_id,
            total_articles=len(contents),
            analysis_time=datetime.now(),
            richness_score=round(richness_score, 2),
            score_breakdown=score_breakdown,
            dimensions=dimension_details,
            gaps=gaps,
            combo_gaps=combo_gaps,
            generation_guidance=generation_guidance
        )
    
    async def _query_contents(
        self, 
        request: RichnessAnalysisRequest
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
    
    def _extract_dimension_scores(
        self, 
        contents: List[Content],
        dimensions: List[str]
    ) -> Dict[str, List[float]]:
        """
        提取各维度的分值数据
        
        Args:
            contents: 文章列表
            dimensions: 维度列表
            
        Returns:
            Dict[str, List[float]]: {维度名: [分值列表]}
        """
        result: Dict[str, List[float]] = defaultdict(list)
        
        for content in contents:
            context_list = content.context_list
            if not context_list or not isinstance(context_list, dict):
                continue
            
            for dim_name in dimensions:
                value = context_list.get(dim_name)
                if value is not None:
                    # 尝试转换为数值
                    try:
                        score = float(value)
                        # 确保在有效范围内
                        if self.MIN_SCORE <= score <= self.MAX_SCORE:
                            result[dim_name].append(score)
                    except (ValueError, TypeError):
                        # 非数值类型，跳过
                        pass
        
        return dict(result)
    
    def _calculate_dimension_detail(
        self, 
        dim_name: str, 
        scores: List[float]
    ) -> RichnessDimensionDetail:
        """
        计算单维度的详情
        
        Args:
            dim_name: 维度名称
            scores: 分值列表
            
        Returns:
            RichnessDimensionDetail: 维度详情
        """
        if not scores:
            return self._empty_dimension_detail(dim_name)
        
        # 1. 基础统计
        min_val = min(scores)
        max_val = max(scores)
        avg_val = sum(scores) / len(scores)
        std_val = self._calculate_std(scores, avg_val)
        
        stats = DimensionStats(
            min=round(min_val, 2),
            max=round(max_val, 2),
            avg=round(avg_val, 2),
            std=round(std_val, 2)
        )
        
        # 2. 分布统计（按整数分值统计）
        distribution: Dict[str, int] = defaultdict(int)
        for score in scores:
            # 四舍五入到整数
            int_score = round(score)
            distribution[str(int_score)] += 1
        
        # 3. 计算占比
        total = len(scores)
        percentage = {
            k: round(v / total * 100, 2)
            for k, v in distribution.items()
        }
        
        # 4. 计算均匀度（基于信息熵）
        uniformity_score = self._calculate_uniformity(distribution, total)
        
        # 5. 计算覆盖度
        coverage_score = self._calculate_coverage(distribution)
        
        # 6. 计算高分占比
        high_score_count = sum(1 for s in scores if s >= self.HIGH_SCORE_THRESHOLD)
        high_score_ratio = round(high_score_count / total * 100, 2)
        
        return RichnessDimensionDetail(
            dimension_name=dim_name,
            total_count=total,
            stats=stats,
            distribution=dict(distribution),
            percentage=percentage,
            uniformity_score=round(uniformity_score, 2),
            coverage_score=round(coverage_score, 2),
            high_score_ratio=high_score_ratio
        )
    
    def _calculate_std(self, scores: List[float], mean: float) -> float:
        """计算标准差"""
        if len(scores) < 2:
            return 0.0
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        return math.sqrt(variance)
    
    def _calculate_uniformity(
        self, 
        distribution: Dict[str, int], 
        total: int
    ) -> float:
        """
        基于信息熵计算分布均匀度
        
        信息熵越高，分布越均匀
        归一化到 0-100 分
        
        Args:
            distribution: 分值分布
            total: 总数
            
        Returns:
            float: 均匀度评分 (0-100)
        """
        if total == 0 or not distribution:
            return 0.0
        
        # 计算实际信息熵
        entropy = 0.0
        for count in distribution.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        
        # 最大信息熵（完全均匀分布）
        num_categories = len(distribution)
        max_entropy = math.log2(num_categories) if num_categories > 1 else 1.0
        
        # 归一化到 0-100
        if max_entropy > 0:
            uniformity = (entropy / max_entropy) * 100
        else:
            uniformity = 100.0
        
        return uniformity
    
    def _calculate_coverage(self, distribution: Dict[str, int]) -> float:
        """
        计算分值覆盖度
        
        覆盖的分值种类占总可能分值的比例
        1-10 分制，满分覆盖 10 种
        
        Args:
            distribution: 分值分布
            
        Returns:
            float: 覆盖度评分 (0-100)
        """
        possible_values = self.MAX_SCORE - self.MIN_SCORE + 1  # 10
        covered_values = len(distribution)
        return (covered_values / possible_values) * 100
    
    def _analyze_gaps(
        self, 
        dimension_details: List[RichnessDimensionDetail],
        low_count_threshold: int
    ) -> List[GapInfo]:
        """
        分析单维度缺口
        
        Args:
            dimension_details: 各维度详情
            low_count_threshold: 低数量阈值
            
        Returns:
            List[GapInfo]: 缺口列表
        """
        gaps = []
        all_possible = set(str(i) for i in range(self.MIN_SCORE, self.MAX_SCORE + 1))
        
        for detail in dimension_details:
            covered = set(detail.distribution.keys())
            missing = all_possible - covered
            
            # 缺失的分值
            if missing:
                gaps.append(GapInfo(
                    dimension=detail.dimension_name,
                    gap_type="missing_values",
                    missing_values=[int(v) for v in sorted(missing)],
                    suggestion=f"缺少 {detail.dimension_name} 分值为 {sorted([int(v) for v in missing])} 的文章"
                ))
            
            # 数量过少的分值
            low_count = {
                k: v for k, v in detail.distribution.items()
                if v < low_count_threshold
            }
            if low_count:
                gaps.append(GapInfo(
                    dimension=detail.dimension_name,
                    gap_type="low_count",
                    low_count_values=low_count,
                    suggestion=f"{detail.dimension_name} 部分分值文章数量过少: {low_count}"
                ))
        
        return gaps
    
    def _analyze_combo_gaps(
        self,
        contents: List[Content],
        dimension_scores: Dict[str, List[float]],
        combo_dimensions: List[List[str]]
    ) -> List[ComboGapInfo]:
        """
        分析组合缺口
        
        将分值离散化为 低/中/高 三档，分析维度组合的覆盖情况
        
        Args:
            contents: 文章列表
            dimension_scores: 各维度分值
            combo_dimensions: 要分析的维度组合
            
        Returns:
            List[ComboGapInfo]: 组合缺口列表
        """
        combo_gaps = []
        levels = [self.LEVEL_LOW, self.LEVEL_MID, self.LEVEL_HIGH]
        
        for dims in combo_dimensions:
            if len(dims) < 2:
                continue
            
            # 只分析两个维度的组合（避免组合爆炸）
            dim1, dim2 = dims[0], dims[1]
            
            # 统计已覆盖的组合
            covered_combos = set()
            
            for content in contents:
                context_list = content.context_list
                if not context_list:
                    continue
                
                val1 = context_list.get(dim1)
                val2 = context_list.get(dim2)
                
                if val1 is None or val2 is None:
                    continue
                
                try:
                    level1 = self._score_to_level(float(val1))
                    level2 = self._score_to_level(float(val2))
                    covered_combos.add((level1, level2))
                except (ValueError, TypeError):
                    pass
            
            # 所有可能的组合
            all_combos = set((l1, l2) for l1 in levels for l2 in levels)
            missing_combos = all_combos - covered_combos
            
            if missing_combos:
                missing_list = [
                    {dim1: l1, dim2: l2}
                    for l1, l2 in sorted(missing_combos)
                ]
                
                combo_gaps.append(ComboGapInfo(
                    dimensions=[dim1, dim2],
                    gap_type="combo",
                    missing_combos=missing_list,
                    description=f"缺少 {dim1} 与 {dim2} 的以下组合: {[f'{c[dim1]}+{c[dim2]}' for c in missing_list]}"
                ))
        
        return combo_gaps
    
    def _score_to_level(self, score: float) -> str:
        """将分值转换为档位"""
        if score <= 3:
            return self.LEVEL_LOW
        elif score <= 6:
            return self.LEVEL_MID
        else:
            return self.LEVEL_HIGH
    
    def _calculate_generation_guidance(
        self, 
        dimension_details: List[RichnessDimensionDetail]
    ) -> Dict[str, Dict[str, float]]:
        """
        计算生成指导权重
        
        使用反向权重：分布占比低的档位获得更高权重
        
        Args:
            dimension_details: 各维度详情
            
        Returns:
            Dict[str, Dict[str, float]]: {维度名: {档位: 权重}}
        """
        guidance = {}
        
        for detail in dimension_details:
            # 按档位统计
            level_counts = {
                self.LEVEL_LOW: 0,
                self.LEVEL_MID: 0,
                self.LEVEL_HIGH: 0
            }
            
            for score_str, count in detail.distribution.items():
                try:
                    score = float(score_str)
                    level = self._score_to_level(score)
                    level_counts[level] += count
                except ValueError:
                    pass
            
            total = sum(level_counts.values())
            if total == 0:
                continue
            
            # 计算反向权重
            inverse_weights = {}
            for level, count in level_counts.items():
                pct = count / total * 100
                inverse_weights[level] = max(100 - pct, 1)
            
            # 归一化
            weight_sum = sum(inverse_weights.values())
            guidance[detail.dimension_name] = {
                level: round(w / weight_sum, 3)
                for level, w in inverse_weights.items()
            }
        
        return guidance
    
    def _empty_response(self, job_id: str) -> RichnessAnalysisResponse:
        """返回空结果"""
        return RichnessAnalysisResponse(
            job_id=job_id,
            total_articles=0,
            analysis_time=datetime.now(),
            richness_score=0.0,
            score_breakdown=ScoreBreakdown(
                distribution_uniformity=0.0,
                coverage_rate=0.0,
                high_score_ratio=0.0
            ),
            dimensions=[],
            gaps=[],
            combo_gaps=[],
            generation_guidance={}
        )
    
    def _empty_dimension_detail(self, dim_name: str) -> RichnessDimensionDetail:
        """返回空维度详情"""
        return RichnessDimensionDetail(
            dimension_name=dim_name,
            total_count=0,
            stats=DimensionStats(min=0, max=0, avg=0, std=0),
            distribution={},
            percentage={},
            uniformity_score=0.0,
            coverage_score=0.0,
            high_score_ratio=0.0
        )
    
    async def get_richness_summary(
        self,
        job_id: str,
        dimensions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        获取丰富度摘要（简化接口）
        
        Args:
            job_id: Job ID
            dimensions: 要分析的维度
            
        Returns:
            丰富度摘要字典
        """
        request = RichnessAnalysisRequest(
            job_id=job_id,
            dimensions=dimensions,
            include_invalid=False,
            include_test=False
        )
        
        result = await self.analyze(request)
        
        return {
            "job_id": result.job_id,
            "total_articles": result.total_articles,
            "richness_score": result.richness_score,
            "score_breakdown": result.score_breakdown.model_dump(),
            "dimension_count": len(result.dimensions),
            "gap_count": len(result.gaps) + len(result.combo_gaps),
            "generation_guidance": result.generation_guidance
        }
