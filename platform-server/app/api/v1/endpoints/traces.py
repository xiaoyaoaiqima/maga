"""
Trace API 路由

提供追踪数据的查询、统计和管理接口
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_perm_code
from app.services.trace_service import TraceService
from app.schemas.base import ResponseData
from app.schemas.trace import (
    TraceListQuery,
    TraceListResponse,
    TraceSpanResponse,
    TraceDetailResponse,
    TraceStatsQuery,
    TraceStatsResponse,
    ReportTraceSpanRequest,
    BatchReportTraceSpansRequest,
    ReportTraceSpanResponse,
    ABExperimentCreate,
    ABExperimentUpdate,
    ABExperimentResponse,
    ABExperimentListResponse,
    GenerationContextResponse,
    TraceCostRecalcRequest,
    TraceCostRecalcSummary,
    TraceDailyStatsRebuildRequest,
    TraceDailyStatsRebuildSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ============ Trace Span Endpoints ============

@router.get("", response_model=ResponseData[TraceListResponse])
async def list_traces(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    job_id: Optional[str] = Query(None, description="Job ID 筛选"),
    sub_job_id: Optional[str] = Query(None, description="Sub Job ID 筛选"),
    content_id: Optional[str] = Query(None, description="内容ID 筛选"),
    trace_id: Optional[str] = Query(None, description="Trace ID 筛选"),
    stage: Optional[str] = Query(None, description="阶段筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    expert_config_code: Optional[str] = Query(None, description="Expert 编码筛选"),
    experiment_id: Optional[str] = Query(None, description="实验ID 筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取追踪列表
    
    支持多种筛选条件，分页返回
    """
    query = TraceListQuery(
        page=page,
        page_size=page_size,
        job_id=job_id,
        sub_job_id=sub_job_id,
        content_id=content_id,
        trace_id=trace_id,
        stage=stage,
        status=status,
        expert_config_code=expert_config_code,
        experiment_id=experiment_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    service = TraceService(db)
    items, total = await service.list_traces(query)
    
    return ResponseData(
        data=TraceListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[TraceSpanResponse.model_validate(item) for item in items],
        )
    )


@router.get("/stats", response_model=ResponseData[TraceStatsResponse])
async def get_trace_stats(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    stage: Optional[str] = Query(None, description="阶段筛选"),
    expert_config_code: Optional[str] = Query(None, description="Expert 编码筛选"),
    experiment_id: Optional[str] = Query(None, description="实验ID 筛选"),
    group_by: str = Query("date", description="分组维度：date/stage/expert/experiment"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取追踪统计
    
    按日期/阶段/Expert/实验分组统计
    """
    query = TraceStatsQuery(
        start_date=start_date,
        end_date=end_date,
        stage=stage,
        expert_config_code=expert_config_code,
        experiment_id=experiment_id,
        group_by=group_by,
    )
    
    service = TraceService(db)
    result = await service.get_trace_stats(query)
    
    return ResponseData(data=TraceStatsResponse(**result))


@router.get("/by-id/{id}", response_model=ResponseData[TraceSpanResponse])
async def get_trace_by_id(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    根据数据库 ID 获取追踪记录
    """
    service = TraceService(db)
    trace = await service.get_trace_by_id(id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"追踪记录不存在: {id}")
    
    return ResponseData(data=TraceSpanResponse.model_validate(trace))


# ============ Trace Report Endpoints（历史兼容：旧回调协议，当前统一走 HTTP）===========

@router.post("/report", response_model=ReportTraceSpanResponse)
async def report_trace_span(
    data: ReportTraceSpanRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    上报追踪数据（服务间调用：Dapr HTTP Invocation）
    
    用于其他服务上报追踪数据到 Orchestrator
    """
    try:
        # 详细日志记录
        logger.info(f"Report Trace Received: {data.json()}")
        if hasattr(data, 'total_cost'):
             logger.info(f"Report Trace Cost: input={data.input_cost}, output={data.output_cost}, total={data.total_cost}")
        
        service = TraceService(db)
        trace = await service.create_from_report(data)
        
        return ReportTraceSpanResponse(
            success=True,
            message="上报成功",
            trace_id=trace.id,
        )
    except Exception as e:
        logger.error(f"追踪上报失败: {e}", exc_info=True)
        return ReportTraceSpanResponse(
            success=False,
            message=str(e),
        )


@router.post("/report/batch", response_model=ReportTraceSpanResponse)
async def batch_report_trace_spans(
    data: BatchReportTraceSpansRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    批量上报追踪数据
    """
    try:
        service = TraceService(db)
        count = 0
        for span_data in data.spans:
            # 详细日志记录
            logger.info(f"Batch Report Span Received: {span_data.json()}")
            if hasattr(span_data, 'total_cost'):
                 logger.info(f"Batch Report Span Cost: input={span_data.input_cost}, output={span_data.output_cost}, total={span_data.total_cost}")
            
            await service.create_from_report(span_data)
            count += 1
        
        return ReportTraceSpanResponse(
            success=True,
            message=f"批量上报成功: {count} 条",
        )
    except Exception as e:
        logger.error(f"批量追踪上报失败: {e}", exc_info=True)
        return ReportTraceSpanResponse(
            success=False,
            message=str(e),
        )


# ============ A/B Experiment Endpoints ============

@router.get("/experiments", response_model=ResponseData[ABExperimentListResponse])
async def list_experiments(
    status: Optional[str] = Query(None, description="状态筛选"),
    target_type: Optional[str] = Query(None, description="目标类型筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    获取 A/B 实验列表
    """
    service = TraceService(db)
    items, total = await service.list_experiments(
        status=status,
        target_type=target_type,
        page=page,
        page_size=page_size,
    )
    
    return ResponseData(
        data=ABExperimentListResponse(
            total=total,
            items=[ABExperimentResponse.model_validate(item) for item in items],
        )
    )


@router.post("/experiments", response_model=ResponseData[ABExperimentResponse])
async def create_experiment(
    data: ABExperimentCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    创建 A/B 实验
    """
    service = TraceService(db)
    experiment = await service.create_experiment(data)
    return ResponseData(data=ABExperimentResponse.model_validate(experiment))


@router.get("/experiments/{experiment_id}", response_model=ResponseData[ABExperimentResponse])
async def get_experiment(
    experiment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取 A/B 实验详情
    """
    service = TraceService(db)
    experiment = await service.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"实验不存在: {experiment_id}")
    
    return ResponseData(data=ABExperimentResponse.model_validate(experiment))


@router.put("/experiments/{experiment_id}", response_model=ResponseData[ABExperimentResponse])
async def update_experiment(
    experiment_id: str,
    data: ABExperimentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    更新 A/B 实验
    """
    service = TraceService(db)
    experiment = await service.update_experiment(experiment_id, data)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"实验不存在: {experiment_id}")
    
    return ResponseData(data=ABExperimentResponse.model_validate(experiment))


@router.post("/experiments/{experiment_id}/start", response_model=ResponseData[ABExperimentResponse])
async def start_experiment(
    experiment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    启动 A/B 实验
    """
    service = TraceService(db)
    experiment = await service.start_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"实验不存在: {experiment_id}")
    
    return ResponseData(data=ABExperimentResponse.model_validate(experiment))


@router.post("/experiments/{experiment_id}/stop", response_model=ResponseData[ABExperimentResponse])
async def stop_experiment(
    experiment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    停止 A/B 实验
    """
    service = TraceService(db)
    experiment = await service.stop_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"实验不存在: {experiment_id}")
    
    return ResponseData(data=ABExperimentResponse.model_validate(experiment))


# ============ Generation Context Endpoint ============

@router.get("/generation-context/{content_id}", response_model=ResponseData[GenerationContextResponse])
async def get_generation_context(
    content_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取文章生成的背景信息（溯源）
    
    聚合业务背景、生成详情和完整执行链路。
    """
    service = TraceService(db)
    context = await service.get_generation_context(content_id)
    if not context:
        raise HTTPException(status_code=404, detail=f"未找到该内容的生成背景: {content_id}")
    
    return ResponseData(data=context)

# ============ Admin Backfill Endpoints ============

@router.post("/admin/recalc-cost", response_model=ResponseData[TraceCostRecalcSummary])
async def admin_recalc_trace_cost(
    req: TraceCostRecalcRequest,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(require_perm_code("system:management:tools")),
):
    """
    管理：按 DB 的 llm_model_route 定价回算 expert_call_trace 成本（分批游标）
    """
    service = TraceService(db)
    result = await service.recalc_trace_cost_batch(
        start_time=req.start_time,
        end_time=req.end_time,
        batch_size=req.batch_size,
        last_id=req.last_id,
        dry_run=req.dry_run,
        only_if_price_found=req.only_if_price_found,
    )
    return ResponseData(data=TraceCostRecalcSummary(**result))


@router.post("/admin/rebuild-daily-stats", response_model=ResponseData[TraceDailyStatsRebuildSummary])
async def admin_rebuild_trace_daily_stats(
    req: TraceDailyStatsRebuildRequest,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(require_perm_code("system:management:tools")),
):
    """
    管理：按日期范围重建 trace_daily_stats（逐日聚合）
    """
    if req.end_date < req.start_date:
        raise HTTPException(status_code=400, detail="end_date 必须大于等于 start_date")

    service = TraceService(db)
    result = await service.rebuild_trace_daily_stats(
        start_date=req.start_date,
        end_date=req.end_date,
    )
    return ResponseData(data=TraceDailyStatsRebuildSummary(**result))


# ============ Dynamic Trace ID Endpoint (must be last) ============

@router.get("/{trace_id}", response_model=ResponseData[TraceDetailResponse])
async def get_trace_detail(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取追踪详情
    
    返回指定 trace_id 的详细信息，包括完整的调用链路（GE → AG → RLHF）
    
    查询策略：
    1. 优先通过 content_id 获取完整生产链路（包含所有阶段）
    2. 如果没有 content_id，回退到 trace_id 查询
    
    注意：此路由必须放在所有静态路由之后，否则会匹配到其他路由
    """
    service = TraceService(db)
    
    # 获取主追踪记录
    trace = await service.get_trace_by_trace_id(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"追踪记录不存在: {trace_id}")
    
    # 获取完整生产链路的所有 span（通过 content_id 关联 GE/AG/RLHF）
    spans = await service.get_full_trace_spans(
        trace_id=trace_id,
        content_id=trace.content_id
    )
    
    return ResponseData(
        data=TraceDetailResponse(
            trace=TraceSpanResponse.model_validate(trace),
            spans=[TraceSpanResponse.model_validate(s) for s in spans],
        )
    )

