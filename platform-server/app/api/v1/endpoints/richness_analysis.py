"""
内容丰富度分析 API

提供基于多维度分值的文章池丰富度分析能力，
包括综合评分、各维度详情、缺口分析和生成指导权重。
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.services.richness_analysis_service import RichnessAnalysisService
from app.schemas.richness_analysis import (
    RichnessAnalysisRequest,
    RichnessAnalysisResponse,
    DEFAULT_RICHNESS_DIMENSIONS
)

router = APIRouter()


@router.post(
    "/analyze",
    response_model=ResponseData[RichnessAnalysisResponse],
    summary="执行丰富度分析",
    description="分析指定 Job 下文章的内容丰富度，返回综合评分、各维度详情、缺口分析和生成指导权重"
)
async def analyze_richness(
    request: RichnessAnalysisRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    执行丰富度分析
    
    - **job_id**: Job ID，分析该 Job 下的所有文章
    - **dimensions**: 要分析的维度列表（可选，默认分析 9 个丰富度维度）
    - **include_invalid**: 是否包含无效文章
    - **include_test**: 是否包含测试文章
    - **weight_***: 综合评分权重配置
    - **combo_dimensions**: 要分析的维度组合
    
    返回：
    - **richness_score**: 综合丰富度评分 (0-100)
    - **score_breakdown**: 评分分解（均匀度、覆盖度、高分比）
    - **dimensions**: 各维度的详细分析
    - **gaps**: 单维度缺口分析
    - **combo_gaps**: 组合缺口分析
    - **generation_guidance**: 生文指导权重
    """
    service = RichnessAnalysisService(db)
    result = await service.analyze(request)
    return ResponseData(data=result)


@router.get(
    "/score/{job_id}",
    response_model=ResponseData[dict],
    summary="获取丰富度评分",
    description="快速获取指定 Job 的丰富度综合评分"
)
async def get_richness_score(
    job_id: str,
    dimensions: Optional[str] = Query(
        default=None,
        description="要分析的维度，逗号分隔"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    获取丰富度评分
    
    返回格式:
    ```json
    {
        "job_id": "xxx",
        "total_articles": 100,
        "richness_score": 78.5,
        "score_breakdown": {
            "distribution_uniformity": 82.0,
            "coverage_rate": 75.0,
            "high_score_ratio": 80.0
        }
    }
    ```
    """
    service = RichnessAnalysisService(db)
    
    dim_list = None
    if dimensions:
        dim_list = [d.strip() for d in dimensions.split(",")]
    
    result = await service.get_richness_summary(job_id, dim_list)
    return ResponseData(data=result)


@router.get(
    "/summary/{job_id}",
    response_model=ResponseData[dict],
    summary="获取丰富度摘要",
    description="快速查看各维度的丰富度情况摘要"
)
async def get_richness_summary(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取丰富度摘要
    
    返回简化格式：
    ```json
    {
        "job_id": "xxx",
        "total_articles": 100,
        "richness_score": 78.5,
        "dimensions": {
            "信息密度": {
                "avg": 6.5,
                "coverage": "80%",
                "high_ratio": "45%"
            },
            ...
        },
        "top_gaps": ["缺少信息密度=10的文章", ...]
    }
    ```
    """
    service = RichnessAnalysisService(db)
    
    request = RichnessAnalysisRequest(
        job_id=job_id,
        include_invalid=False,
        include_test=False
    )
    
    result = await service.analyze(request)
    
    # 转换为简化格式
    summary = {
        "job_id": result.job_id,
        "total_articles": result.total_articles,
        "richness_score": result.richness_score,
        "score_breakdown": result.score_breakdown.model_dump(),
        "dimensions": {},
        "top_gaps": []
    }
    
    # 各维度摘要
    for dim in result.dimensions:
        summary["dimensions"][dim.dimension_name] = {
            "count": dim.total_count,
            "avg": dim.stats.avg,
            "std": dim.stats.std,
            "uniformity": f"{dim.uniformity_score:.1f}%",
            "coverage": f"{dim.coverage_score:.1f}%",
            "high_ratio": f"{dim.high_score_ratio:.1f}%"
        }
    
    # 取前 5 个缺口建议
    for gap in result.gaps[:5]:
        summary["top_gaps"].append(gap.suggestion)
    
    return ResponseData(data=summary)


@router.get(
    "/guidance/{job_id}",
    response_model=ResponseData[dict],
    summary="获取生成指导权重",
    description="获取各维度按档位（低/中/高）的生成指导权重"
)
async def get_generation_guidance(
    job_id: str,
    dimensions: Optional[str] = Query(
        default=None,
        description="要分析的维度，逗号分隔"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    获取生成指导权重
    
    返回格式:
    ```json
    {
        "信息密度": {
            "低": 0.5,
            "中": 0.3,
            "高": 0.2
        },
        "情绪强度": {
            "低": 0.2,
            "中": 0.3,
            "高": 0.5
        }
    }
    ```
    
    权重说明：
    - 权重值在 0-1 之间，各档位权重之和为 1
    - 权重越高，表示该档位的文章越少，应该优先生成
    """
    service = RichnessAnalysisService(db)
    
    dim_list = None
    if dimensions:
        dim_list = [d.strip() for d in dimensions.split(",")]
    
    request = RichnessAnalysisRequest(
        job_id=job_id,
        dimensions=dim_list,
        include_invalid=False,
        include_test=False
    )
    
    result = await service.analyze(request)
    return ResponseData(data=result.generation_guidance)


@router.get(
    "/gaps/{job_id}",
    response_model=ResponseData[dict],
    summary="获取缺口分析",
    description="获取详细的内容缺口分析"
)
async def get_gaps_analysis(
    job_id: str,
    combo_dimensions: Optional[str] = Query(
        default=None,
        description="要分析的组合维度对，格式如: '信息密度:结构复杂度,质量档位:真实感程度'"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    获取缺口分析
    
    返回：
    - **single_gaps**: 单维度缺口（缺失的分值、数量过少的分值）
    - **combo_gaps**: 组合缺口（缺失的维度组合）
    """
    service = RichnessAnalysisService(db)
    
    # 解析组合维度
    combo_dims = None
    if combo_dimensions:
        combo_dims = []
        for pair in combo_dimensions.split(","):
            dims = [d.strip() for d in pair.split(":")]
            if len(dims) == 2:
                combo_dims.append(dims)
    
    request = RichnessAnalysisRequest(
        job_id=job_id,
        include_invalid=False,
        include_test=False,
        combo_dimensions=combo_dims
    )
    
    result = await service.analyze(request)
    
    return ResponseData(data={
        "job_id": result.job_id,
        "total_articles": result.total_articles,
        "single_gaps": [gap.model_dump() for gap in result.gaps],
        "combo_gaps": [gap.model_dump() for gap in result.combo_gaps],
        "gap_summary": {
            "single_gap_count": len(result.gaps),
            "combo_gap_count": len(result.combo_gaps),
            "total_gap_count": len(result.gaps) + len(result.combo_gaps)
        }
    })


@router.get(
    "/dimensions",
    response_model=ResponseData[list],
    summary="获取默认分析维度",
    description="返回默认的丰富度分析维度列表"
)
async def get_default_dimensions():
    """
    获取默认的丰富度分析维度列表
    
    返回 9 个默认维度：
    - 信息密度
    - 情绪强度
    - 表达精度
    - 质量档位
    - 瑕疵容忍度
    - 真实感程度
    - 细节颗粒度
    - 结构复杂度
    - 场景描述+妈妈痛点+产品卖点+关键词
    """
    return ResponseData(data=DEFAULT_RICHNESS_DIMENSIONS)
