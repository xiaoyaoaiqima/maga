"""
CriticScores API endpoints - Critic 评分记录 API
"""
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_analytics_db
from app.schemas.base import ResponseData
from app.schemas.critic_score import (
    CriticScoreRecordResponse,
    CriticScoreSummary,
    CriticScoreTrendItem,
    CriticScoreModelComparison,
    CriticScoreDistributionItem,
    CriticDimensionHeatmapResponse,
    CriticScatterDataItem,
    CriticProblemContextTopItem,
    CriticDatasetItem,
    CriticReasonWordCloudItem,
    ExpertConfigOptionItem,
)

router = APIRouter()


# ==================== 评分记录 API ====================

@router.get("", response_model=ResponseData[List[CriticScoreRecordResponse]])
async def list_critic_scores(
    job_id: Optional[str] = Query(None, description="Job ID"),
    content_id: Optional[str] = Query(None, description="内容 ID"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    # job 场景筛选
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    # eval_run 场景筛选
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    run_id: Optional[int] = Query(None, description="eval_run id"),
    test_case_id: Optional[int] = Query(None, description="test_case id"),
    # debug 场景筛选
    debug_history_id: Optional[int] = Query(None, description="调试历史ID（debug场景）"),
    # 通用筛选
    expert_func: Optional[str] = Query(None, description="Critic 函数名"),
    model_code: Optional[str] = Query(None, description="模型编码"),
    score_min: Optional[int] = Query(None, ge=0, le=100, description="最低分"),
    score_max: Optional[int] = Query(None, ge=0, le=100, description="最高分"),
    passed: Optional[bool] = Query(None, description="是否通过"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数"),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[List[CriticScoreRecordResponse]]:
    """
    列表查询评分记录
    
    支持多维度筛选：job_id, content_id, tenant_id, activity_id, expert_func, model_code, 分数范围, 是否通过, 日期范围
    """
    from app.services.critic_score_service import CriticScoreService
    service = CriticScoreService(db)
    records = await service.list_records(
        job_id=job_id,
        content_id=content_id,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        dataset_code=dataset_code,
        run_id=run_id,
        test_case_id=test_case_id,
        debug_history_id=debug_history_id,
        expert_func=expert_func,
        model_code=model_code,
        score_min=score_min,
        score_max=score_max,
        passed=passed,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )
    
    # 获取总数
    total = await service.count_records(
        job_id=job_id,
        content_id=content_id,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        dataset_code=dataset_code,
        run_id=run_id,
        test_case_id=test_case_id,
        debug_history_id=debug_history_id,
        expert_func=expert_func,
        model_code=model_code,
        passed=passed,
        start_date=start_date,
        end_date=end_date,
    )
    
    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticScoreRecordResponse.model_validate(r) for r in records],
        total=total,
    )


@router.get("/content/{content_id}/history", response_model=ResponseData[List[CriticScoreRecordResponse]])
async def get_content_score_history(
    content_id: str,
    expert_func: Optional[str] = Query(None, description="Critic 函数名"),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[List[CriticScoreRecordResponse]]:
    """获取某内容的历史评分记录"""
    from app.services.critic_score_service import CriticScoreService
    service = CriticScoreService(db)
    records = await service.get_content_history(
        content_id=content_id,
        expert_func=expert_func,
    )
    
    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticScoreRecordResponse.model_validate(r) for r in records],
    )


# ==================== 统计分析 API ====================

@router.get("/stats/summary", response_model=ResponseData[CriticScoreSummary])
async def get_stats_summary(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    expert_func: Optional[str] = Query(None, description="Critic 函数名"),
    model_code: Optional[str] = Query(None, description="模型编码"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    # job 场景筛选
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    job_id: Optional[str] = Query(None, description="Job ID（job场景）"),
    # eval_run 场景筛选
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    # expert_type 过滤
    expert_type: Optional[str] = Query(None, description="专家类型：BAN（合规封禁）/ CRITIC（质量评分）"),
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务查询
) -> ResponseData[CriticScoreSummary]:
    """获取汇总统计（总数/通过率/平均分等）"""
    from app.services.critic_score_service import CriticScoreService
    service = CriticScoreService(analytics_db)  # 使用分析库
    summary = await service.get_summary_stats(
        start_date=start_date,
        end_date=end_date,
        expert_func=expert_func,
        model_code=model_code,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        job_id=job_id,
        dataset_code=dataset_code,
        expert_type=expert_type,
    )

    return ResponseData(
        code=200,
        message="查询成功",
        data=CriticScoreSummary(**summary),
    )


@router.get("/stats/trend", response_model=ResponseData[List[CriticScoreTrendItem]])
async def get_stats_trend(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    expert_func: Optional[str] = Query(None, description="Critic 函数名"),
    model_code: Optional[str] = Query(None, description="模型编码"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    # job 场景筛选
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    job_id: Optional[str] = Query(None, description="Job ID（job场景）"),
    # eval_run 场景筛选
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    # expert_type 过滤
    expert_type: Optional[str] = Query(None, description="专家类型：BAN（合规封禁）/ CRITIC（质量评分）"),
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务查询
) -> ResponseData[List[CriticScoreTrendItem]]:
    """获取趋势数据（按天聚合）"""
    from app.services.critic_score_service import CriticScoreService
    service = CriticScoreService(analytics_db)  # 使用分析库
    trend_data = await service.get_trend_data(
        start_date=start_date,
        end_date=end_date,
        expert_func=expert_func,
        model_code=model_code,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        job_id=job_id,
        dataset_code=dataset_code,
        expert_type=expert_type,
    )

    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticScoreTrendItem(**item) for item in trend_data],
    )


@router.get("/stats/model-comparison", response_model=ResponseData[List[CriticScoreModelComparison]])
async def get_model_comparison(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    expert_func: Optional[str] = Query(None, description="Critic 函数名"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    # job 场景筛选
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    job_id: Optional[str] = Query(None, description="Job ID（job场景）"),
    # eval_run 场景筛选
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    # expert_type 过滤
    expert_type: Optional[str] = Query(None, description="专家类型：BAN（合规封禁）/ CRITIC（质量评分）"),
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务查询
) -> ResponseData[List[CriticScoreModelComparison]]:
    """获取模型对比数据（同一 expert_func 下不同模型的表现）"""
    from app.services.critic_score_service import CriticScoreService
    service = CriticScoreService(analytics_db)  # 使用分析库
    comparison_data = await service.get_model_comparison(
        start_date=start_date,
        end_date=end_date,
        expert_func=expert_func,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        job_id=job_id,
        dataset_code=dataset_code,
        expert_type=expert_type,
    )

    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticScoreModelComparison(**item) for item in comparison_data],
    )


@router.get("/stats/score-distribution", response_model=ResponseData[List[CriticScoreDistributionItem]])
async def get_score_distribution(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    expert_func: Optional[str] = Query(None, description="Critic 函数名"),
    model_code: Optional[str] = Query(None, description="模型编码"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    # job 场景筛选
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    job_id: Optional[str] = Query(None, description="Job ID（job场景）"),
    # eval_run 场景筛选
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    bucket_size: int = Query(10, ge=1, le=50, description="分数段大小"),
    # expert_type 过滤
    expert_type: Optional[str] = Query(None, description="专家类型：BAN（合规封禁）/ CRITIC（质量评分）"),
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务查询
) -> ResponseData[List[CriticScoreDistributionItem]]:
    """获取分数分布（直方图数据）"""
    from app.services.critic_score_service import CriticScoreService
    service = CriticScoreService(analytics_db)  # 使用分析库
    distribution_data = await service.get_score_distribution(
        start_date=start_date,
        end_date=end_date,
        expert_func=expert_func,
        model_code=model_code,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        job_id=job_id,
        dataset_code=dataset_code,
        bucket_size=bucket_size,
        expert_type=expert_type,
    )

    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticScoreDistributionItem(**item) for item in distribution_data],
    )


@router.get("/stats/dimension-heatmap", response_model=ResponseData[CriticDimensionHeatmapResponse])
async def get_dimension_heatmap(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    # job 场景筛选
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    job_id: Optional[str] = Query(None, description="Job ID（job场景）"),
    # eval_run 场景筛选
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    bucket_size: int = Query(10, ge=1, le=50, description="分数段大小"),
    # expert_type 过滤，默认只展示 CRITIC
    expert_type: Optional[str] = Query("CRITIC", description="专家类型：BAN（合规封禁）/ CRITIC（质量评分），默认 CRITIC"),
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务查询
) -> ResponseData[CriticDimensionHeatmapResponse]:
    """
    获取维度×分数段热力图数据

    - X轴：分数段（0-9, 10-19, ... 90-100）
    - Y轴：评分维度（内容质量、品牌匹配等）
    - 值：文章数量

    默认只展示 CRITIC 类型（质量评分维度），BAN 类型在合规卡片展示
    """
    from app.services.critic_score_service import CriticScoreService
    service = CriticScoreService(analytics_db)  # 使用分析库
    heatmap_data = await service.get_dimension_score_heatmap(
        start_date=start_date,
        end_date=end_date,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        job_id=job_id,
        dataset_code=dataset_code,
        bucket_size=bucket_size,
        expert_type=expert_type,
    )

    return ResponseData(
        code=200,
        message="查询成功",
        data=CriticDimensionHeatmapResponse(**heatmap_data),
    )


@router.get("/datasets", response_model=ResponseData[List[CriticDatasetItem]])
async def list_datasets(
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[List[CriticDatasetItem]]:
    """数据集下拉（来自 critic_score_record.dataset_code）"""
    from app.services.critic_score_service import CriticScoreService

    service = CriticScoreService(db)
    items = await service.list_dataset_codes(source_type=source_type)
    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticDatasetItem(**x) for x in items],
    )


@router.get("/expert-configs", response_model=ResponseData[List[ExpertConfigOptionItem]])
async def list_expert_config_options(
    expert_type: Optional[str] = Query(None, description="专家类型：BAN（合规封禁）/ CRITIC（质量评分），不传返回全部"),
    tenant_code: Optional[str] = Query(None, description="租户编码（匹配该租户或全局共享配置）"),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[List[ExpertConfigOptionItem]]:
    """
    获取 CRITIC/BAN 类型的 expert_config 列表（用于下拉选项）
    
    - 不传 expert_type：返回 CRITIC + BAN 类型的全部配置
    - expert_type=CRITIC：返回质量评分维度配置
    - expert_type=BAN：返回合规检测维度配置
    - tenant_code：按租户过滤（同时包含全局共享配置）
    
    返回字段：expert_config_code, expert_config_name, expert_type, expert_func
    前端使用 expert_config_code 进行筛选
    """
    from app.services.critic_score_service import CriticScoreService

    service = CriticScoreService(db)
    items = await service.list_expert_config_options(
        expert_type=expert_type,
        tenant_code=tenant_code,
    )
    return ResponseData(
        code=200,
        message="查询成功",
        data=[ExpertConfigOptionItem(**x) for x in items],
    )


@router.get("/stats/problem-contexts/top", response_model=ResponseData[List[CriticProblemContextTopItem]])
async def get_problem_context_top(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    expert_func: Optional[str] = Query(None, description="Critic 函数名"),
    model_code: Optional[str] = Query(None, description="模型编码"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    # job 场景筛选
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    job_id: Optional[str] = Query(None, description="Job ID（job场景）"),
    # eval_run 场景筛选
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    top_n: int = Query(10, ge=1, le=100, description="Top N"),
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务查询
) -> ResponseData[List[CriticProblemContextTopItem]]:
    """热门问题上下文 TopN"""
    from app.services.critic_score_service import CriticScoreService

    service = CriticScoreService(analytics_db)  # 使用分析库
    items = await service.get_problem_context_top(
        start_date=start_date,
        end_date=end_date,
        expert_func=expert_func,
        model_code=model_code,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        job_id=job_id,
        dataset_code=dataset_code,
        top_n=top_n,
    )
    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticProblemContextTopItem(**x) for x in items],
    )


@router.get("/stats/reasons/wordcloud", response_model=ResponseData[List[CriticReasonWordCloudItem]])
async def get_reason_wordcloud(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    expert_func: Optional[str] = Query(None, description="Critic 函数名"),
    model_code: Optional[str] = Query(None, description="模型编码"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    # job 场景筛选
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    job_id: Optional[str] = Query(None, description="Job ID（job场景）"),
    # eval_run 场景筛选
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    top_n: int = Query(80, ge=1, le=300, description="Top N"),
    sample_limit: int = Query(5000, ge=100, le=20000, description="抽样上限（用于后端聚合）"),
    min_len: int = Query(2, ge=1, le=10, description="最小词长"),
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务查询
) -> ResponseData[List[CriticReasonWordCloudItem]]:
    """评分理由词云（后端切词聚合）"""
    from app.services.critic_score_service import CriticScoreService

    service = CriticScoreService(analytics_db)  # 使用分析库
    items = await service.get_reason_wordcloud(
        start_date=start_date,
        end_date=end_date,
        expert_func=expert_func,
        model_code=model_code,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        job_id=job_id,
        dataset_code=dataset_code,
        top_n=top_n,
        sample_limit=sample_limit,
        min_len=min_len,
    )
    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticReasonWordCloudItem(**x) for x in items],
    )


@router.get("/stats/scatter-data", response_model=ResponseData[List[CriticScatterDataItem]])
async def get_scatter_data(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    model_code: Optional[str] = Query(None, description="模型编码"),
    source_type: Optional[str] = Query(None, description="来源类型：job/eval_run/debug"),
    tenant_id: Optional[int] = Query(None, description="租户ID（job场景）"),
    activity_id: Optional[int] = Query(None, description="活动ID（job场景）"),
    job_id: Optional[str] = Query(None, description="Job ID（job场景）"),
    dataset_code: Optional[str] = Query(None, description="数据集标识"),
    limit: int = Query(2000, ge=100, le=10000, description="最大返回条数"),
    # expert_type 过滤，默认只展示 CRITIC
    expert_type: Optional[str] = Query("CRITIC", description="专家类型：BAN（合规封禁）/ CRITIC（质量评分），默认 CRITIC"),
    db: AsyncSession = Depends(get_db),  # 主库 - 用于缓存读写
    analytics_db: AsyncSession = Depends(get_analytics_db),  # 分析库 - 用于业务查询
) -> ResponseData[List[CriticScatterDataItem]]:
    """获取散点图数据（x=维度，y=分数，每个点=文章），默认只展示 CRITIC 类型"""
    from app.services.critic_score_service import CriticScoreService

    service = CriticScoreService(analytics_db)  # 使用分析库
    items = await service.get_scatter_data(
        start_date=start_date,
        end_date=end_date,
        model_code=model_code,
        source_type=source_type,
        tenant_id=tenant_id,
        activity_id=activity_id,
        job_id=job_id,
        dataset_code=dataset_code,
        limit=limit,
        expert_type=expert_type,
    )
    return ResponseData(
        code=200,
        message="查询成功",
        data=[CriticScatterDataItem(**x) for x in items],
    )


@router.get("/expert-configs", response_model=ResponseData[List[ExpertConfigOptionItem]])
async def list_expert_configs(
    expert_type: Optional[str] = Query(None, description="专家类型：CRITIC / BAN"),
    tenant_code: Optional[str] = Query(None, description="租户编码"),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[List[ExpertConfigOptionItem]]:
    """获取 Expert 配置选项列表（用于下拉选择）"""
    from app.services.critic_score_service import CriticScoreService
    service = CriticScoreService(db)
    items = await service.list_expert_config_options(
        expert_type=expert_type,
        tenant_code=tenant_code,
    )
    return ResponseData(
        code=200,
        message="查询成功",
        data=[ExpertConfigOptionItem(**x) for x in items],
    )


# 注意：动态路由必须放在静态路由之后，否则会把 /datasets 等误匹配为 record_id
@router.get("/{record_id}", response_model=ResponseData[CriticScoreRecordResponse])
async def get_critic_score(
    record_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[CriticScoreRecordResponse]:
    """获取单条评分记录详情"""
    from app.services.critic_score_service import CriticScoreService

    service = CriticScoreService(db)
    record = await service.get_by_id(record_id)

    if not record:
        return ResponseData(code=404, message="记录不存在", data=None)

    return ResponseData(
        code=200,
        message="查询成功",
        data=CriticScoreRecordResponse.model_validate(record),
    )
