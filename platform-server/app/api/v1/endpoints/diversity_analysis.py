"""
内容多样性/人设分布分析 API
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.services.diversity_analysis_service import DiversityAnalysisService
from app.schemas.diversity_analysis import (
    DiversityAnalysisRequest,
    DiversityAnalysisResponse
)

router = APIRouter()


@router.post(
    "/analyze",
    response_model=ResponseData[DiversityAnalysisResponse],
    summary="执行多样性分析",
    description="分析指定 Job 下文章的内容多样性/人设分布，返回各维度统计和生文指导权重"
)
async def analyze_diversity(
    request: DiversityAnalysisRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    执行多样性分析
    
    - **job_id**: Job ID，分析该 Job 下的所有文章
    - **dimensions**: 要分析的维度列表（可选，默认分析关键维度）
    - **include_invalid**: 是否包含无效文章
    - **include_test**: 是否包含测试文章
    
    返回：
    - **dimensions**: 各维度的分布统计
    - **low_coverage_alerts**: 低覆盖率告警
    - **generation_guidance**: 生文指导权重
    """
    service = DiversityAnalysisService(db)
    result = await service.analyze(request)
    return ResponseData(data=result)


@router.get(
    "/guidance/{job_id}",
    response_model=ResponseData[dict],
    summary="获取生文指导权重",
    description="快速获取指定 Job 的生文指导权重，用于后续内容生成时的变量选择"
)
async def get_generation_guidance(
    job_id: str,
    dimensions: Optional[str] = Query(
        default=None,
        description="要分析的维度，逗号分隔，如: '写者,platform'"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    获取生文指导权重
    
    返回格式:
    ```json
    {
        "写者": {
            "通勤战士": 0.7,
            "斜杠妈妈": 0.3
        },
        "platform": {
            "小红书": 0.5,
            "抖音": 0.5
        }
    }
    ```
    
    权重说明：
    - 权重值在 0-1 之间，所有选项权重之和为 1
    - 权重越高，表示该选项的文章越少，应该优先生成
    """
    service = DiversityAnalysisService(db)
    
    dim_list = None
    if dimensions:
        dim_list = [d.strip() for d in dimensions.split(",")]
    
    result = await service.get_generation_guidance(job_id, dim_list)
    return ResponseData(data=result)


@router.get(
    "/summary/{job_id}",
    response_model=ResponseData[dict],
    summary="获取多样性摘要",
    description="快速查看各维度的分布情况摘要"
)
async def get_diversity_summary(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取多样性分布摘要
    
    返回简化格式，方便快速查看：
    ```json
    {
        "total_articles": 190,
        "写者": {
            "家庭CEO": {"count": 50, "pct": "26.3%"},
            "斜杠妈妈": {"count": 140, "pct": "73.7%"}
        }
    }
    ```
    """
    service = DiversityAnalysisService(db)
    
    request = DiversityAnalysisRequest(
        job_id=job_id,
        include_invalid=False,
        include_test=False
    )
    
    result = await service.analyze(request)
    
    # 转换为简化格式
    summary = {
        "total_articles": result.total_articles,
        "low_coverage_count": len(result.low_coverage_alerts)
    }
    
    for dim in result.dimensions:
        summary[dim.dimension_name] = {
            option: {
                "count": dim.distribution.get(option, 0),
                "pct": f"{dim.percentage.get(option, 0)}%",
                "weight": dim.recommended_weights.get(option, 0)
            }
            for option in dim.distribution.keys()
        }
    
    return ResponseData(data=summary)
