"""
Job endpoints
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_active_user, get_current_user_id_optional
from app.schemas.base import ResponseData
from app.schemas.job import (
    JobCreate, JobResponse, JobUpdate, JobTestRequest, JobTestResponse,
    JobExportRequest, JobExportResponse, JobExecutionListResponse, JobDeployRequest,
    JobListResponse
)
from app.schemas.expert_task import ExpertTaskResponse
from app.schemas.trace import TraceSpanResponse
from app.services.job_service import JobService

router = APIRouter()


def get_job_service(db: AsyncSession = Depends(get_db)) -> JobService:
    """Dependency provider for JobService"""
    return JobService(db)


@router.post("", response_model=ResponseData[JobResponse])
async def create_job(
    job_in: JobCreate,
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobResponse]:
    """Create new job"""
    try:
        job = await service.create(job_in, created_by=user_id)
        return ResponseData(
            code=200,
            message="创建成功",
            data=JobResponse.model_validate(job)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )




@router.post("/{job_id}/copy", response_model=ResponseData[JobResponse])
async def copy_job(
    job_id: str,
    new_job_name: Optional[str] = Body(None, embed=True),
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobResponse]:
    """
    Copy an existing job (including job_generation_plan)
    
    This endpoint creates a new job by copying an existing one.
    Unlike the list endpoint, this will query the source job WITH job_generation_plan.
    
    If new_job_name is not provided, it will auto-generate one.
    """
    try:
        # Copy job (service will query WITH job_generation_plan)
        # Service method will auto-generate name if new_job_name is None
        new_job = await service.copy(job_id, new_job_name, created_by=user_id)
        
        return ResponseData(
            code=200,
            message="复制成功",
            data=JobResponse.model_validate(new_job)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/{job_id}", response_model=ResponseData[JobResponse])
async def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobResponse]:
    """Get job by ID"""
    job = await service.get(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    return ResponseData(
        data=JobResponse.model_validate(job)
    )


@router.get("", response_model=ResponseData[list[JobListResponse]])
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled"),
    tenant_id: Optional[int] = Query(None, description="Filter by tenant ID"),
    agent_code: Optional[str] = Query(None, description="Filter by agent code"),
    skip: int = 0,
    limit: int = 1000,
    service: JobService = Depends(get_job_service),
) -> ResponseData[list[JobResponse]]:
    """List all jobs"""
    jobs = await service.list(
        status=status,
        enabled=enabled,
        tenant_id=tenant_id,
        agent_code=agent_code,
        skip=skip,
        limit=limit
    )

    return ResponseData(
        data=[JobListResponse.model_validate(job) for job in jobs]
    )


@router.put("/{job_id}", response_model=ResponseData[JobResponse])
async def update_job(
    job_id: str,
    job_in: JobUpdate,
    user_id: Optional[str] = Depends(get_current_user_id_optional),
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobResponse]:
    """Update job"""
    try:
        job = await service.update(job_id, job_in, updated_by=user_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        return ResponseData(
            message="Job updated successfully",
            data=JobResponse.model_validate(job)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{job_id}/deploy", response_model=ResponseData[list[ExpertTaskResponse]])
async def deploy_job(
    job_id: str,
    deploy_request: JobDeployRequest,
    service: JobService = Depends(get_job_service),
) -> ResponseData[list[ExpertTaskResponse]]:
    """Deploy job - Create expert_tasks for each expert_config_code with custom configs"""
    import traceback
    from loguru import logger
    try:
        expert_tasks = await service.deploy(job_id, deploy_request.task_configs)
        return ResponseData(
            message="Job deployed successfully",
            data=[ExpertTaskResponse.model_validate(task) for task in expert_tasks]
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Deploy failed: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deploy failed: {str(e)}"
        )


@router.delete("/{job_id}", response_model=ResponseData[None])
async def delete_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> ResponseData[None]:
    """Delete job"""
    success = await service.delete(job_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    return ResponseData(
        message="Job deleted successfully"
    )


@router.post("/{job_id}/test", response_model=ResponseData[JobTestResponse])
async def test_job(
    job_id: str,
    test_request: JobTestRequest,
    background_tasks: BackgroundTasks,
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobTestResponse]:
    """
    Test job - Execute all experts in the job with optional plugin config snapshot
    
    Args:
        job_id: Job ID
        test_request: Test request with optional experts_plugin_config_snapshot and count
    
    Returns:
        Test results with response_data for each expert_config_code.
        所有测试均在后台执行，立即返回，请在执行追踪页查看进度。
    """
    try:
        # 统一放入后台执行，立即返回，不再阻塞等待
        background_tasks.add_task(
            service.test,
            job_id=job_id,
            experts_plugin_config_snapshot=test_request.experts_plugin_config_snapshot,
            count=test_request.count
        )
        
        return ResponseData(
            message=f"已成功启动 {test_request.count} 次后台测试任务，请在执行追踪页查看进度。",
            data=JobTestResponse(results={})
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job test failed: {str(e)}"
        )


@router.get("/{job_id}/tasks", response_model=ResponseData[list[ExpertTaskResponse]])
async def get_job_tasks(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> ResponseData[list[ExpertTaskResponse]]:
    """
    获取 Job 关联的所有 ExpertTask（子任务）
    
    Args:
        job_id: Job ID
    
    Returns:
        ExpertTask 列表
    """
    try:
        tasks = await service.get_tasks(job_id)
        return ResponseData(
            data=[ExpertTaskResponse.model_validate(task) for task in tasks]
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/{job_id}/executions", response_model=ResponseData[JobExecutionListResponse])
async def get_job_executions(
    job_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选：pending/running/success/failed/timeout"),
    expert_config_code: Optional[str] = Query(None, description="ExpertConfig 编码筛选"),
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobExecutionListResponse]:
    """
    获取 Job 的执行历史
    
    Args:
        job_id: Job ID
        page: 页码
        page_size: 每页数量
        status: 状态筛选
        expert_config_code: ExpertConfig 编码筛选
    
    Returns:
        执行历史列表（分页）
    """
    try:
        items, total = await service.get_executions(
            job_id=job_id,
            page=page,
            page_size=page_size,
            status=status,
            expert_config_code=expert_config_code,
        )
        
        # 转换为响应格式
        execution_items = []
        for trace in items:
            execution_items.append({
                "id": trace.id,
                "sub_job_id": trace.sub_job_id,
                "content_id": trace.content_id,
                "trace_id": trace.trace_id,
                "span_id": trace.span_id,
                "stage": trace.stage,
                "expert_config_code": trace.expert_config_code,
                "expert_type": trace.expert_type,
                "status": trace.status,
                "error_type": trace.error_type,
                "error_message": trace.error_message,
                "start_time": trace.start_time.isoformat() if trace.start_time else None,
                "end_time": trace.end_time.isoformat() if trace.end_time else None,
                "duration_ms": trace.duration_ms,
                "model_code": trace.model_code,
                "input_tokens": trace.input_tokens,
                "output_tokens": trace.output_tokens,
                "total_tokens": trace.total_tokens,
                "result_summary": trace.result_summary,
            })
        
        return ResponseData(
            data=JobExecutionListResponse(
                total=total,
                page=page,
                page_size=page_size,
                items=execution_items
            )
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/{job_id}/export", response_model=ResponseData[JobExportResponse])
async def export_job_results(
    job_id: str,
    export_request: JobExportRequest,
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobExportResponse]:
    """
    导出 Job 的执行结果
    
    Args:
        job_id: Job ID
        export_request: 导出请求（格式和是否包含详情）
    
    Returns:
        导出数据（包含汇总和执行记录）
    """
    try:
        export_data = await service.export_results(
            job_id=job_id,
            format=export_request.format,
            include_details=export_request.include_details,
        )
        return ResponseData(
            message="导出成功",
            data=JobExportResponse(**export_data)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出失败: {str(e)}"
        )


@router.post("/{job_id}/pause", response_model=ResponseData[JobResponse])
async def pause_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobResponse]:
    """Pause job and its tasks"""
    try:
        job = await service.pause(job_id)
        return ResponseData(
            message="Job paused successfully",
            data=JobResponse.model_validate(job)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{job_id}/resume", response_model=ResponseData[JobResponse])
async def resume_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobResponse]:
    """Resume job and its tasks"""
    try:
        job = await service.resume(job_id)
        return ResponseData(
            message="Job resumed successfully",
            data=JobResponse.model_validate(job)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{job_id}/complete", response_model=ResponseData[JobResponse])
async def complete_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> ResponseData[JobResponse]:
    """Complete job and its tasks"""
    try:
        job = await service.complete(job_id)
        return ResponseData(
            message="Job completed successfully",
            data=JobResponse.model_validate(job)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
