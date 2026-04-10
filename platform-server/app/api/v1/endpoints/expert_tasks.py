"""
ExpertTask endpoints
"""
import asyncio
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.expert_task import ExpertTaskCreate, ExpertTaskResponse, ExpertTaskUpdate
from app.services.expert_task_service import ExpertTaskService
from app.scheduler import get_scheduler_manager
from app.scheduler.expert_task_executor import execute_expert_task_sync

router = APIRouter()


@router.post("", response_model=ResponseData[ExpertTaskResponse])
async def create_expert_task(
    expert_task_in: ExpertTaskCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertTaskResponse]:
    """Create new expert_task"""
    service = ExpertTaskService(db)
    
    expert_task = await service.create(expert_task_in)
    return ResponseData(
        code=200,
        message="创建成功",
        data=ExpertTaskResponse.model_validate(expert_task)
    )


@router.get("/{expert_task_id}", response_model=ResponseData[ExpertTaskResponse])
async def get_expert_task(
    expert_task_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertTaskResponse]:
    """Get expert_task by ID"""
    service = ExpertTaskService(db)
    expert_task = await service.get(expert_task_id)

    if not expert_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertTask not found"
        )

    return ResponseData(
        data=ExpertTaskResponse.model_validate(expert_task)
    )


@router.get("", response_model=ResponseData[list[ExpertTaskResponse]])
async def list_expert_tasks(
    job_id: Optional[str] = Query(None, description="Filter by job_id"),
    expert_config_code: Optional[str] = Query(None, description="Filter by expert_config_code"),
    status: Optional[int] = Query(None, description="Filter by status"),
    skip: int = 0,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[ExpertTaskResponse]]:
    """List all expert_tasks"""
    service = ExpertTaskService(db)
    expert_tasks = await service.list(
        job_id=job_id,
        expert_config_code=expert_config_code,
        status=status,
        skip=skip,
        limit=limit
    )

    return ResponseData(
        data=[ExpertTaskResponse.model_validate(task) for task in expert_tasks]
    )


@router.get("/job/{job_id}", response_model=ResponseData[list[ExpertTaskResponse]])
async def get_expert_tasks_by_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[ExpertTaskResponse]]:
    """Get expert_tasks by job_id"""
    service = ExpertTaskService(db)
    expert_tasks = await service.get_by_job_id(job_id)

    return ResponseData(
        data=[ExpertTaskResponse.model_validate(task) for task in expert_tasks]
    )


@router.put("/{expert_task_id}", response_model=ResponseData[ExpertTaskResponse])
async def update_expert_task(
    expert_task_id: int,
    expert_task_in: ExpertTaskUpdate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertTaskResponse]:
    """Update expert_task"""
    service = ExpertTaskService(db)
    expert_task = await service.update(expert_task_id, expert_task_in)

    if not expert_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertTask not found"
        )

    return ResponseData(
        message="ExpertTask updated successfully",
        data=ExpertTaskResponse.model_validate(expert_task)
    )


@router.delete("/{expert_task_id}", response_model=ResponseData[None])
async def delete_expert_task(
    expert_task_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """Delete expert_task"""
    service = ExpertTaskService(db)
    success = await service.delete(expert_task_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertTask not found"
        )

    return ResponseData(
        data=None,
        message="ExpertTask deleted successfully"
    )


# ==================== 调度器管理 API ====================

@router.get("/scheduler/jobs", response_model=ResponseData[list[dict]])
async def list_scheduled_jobs() -> ResponseData[list[dict]]:
    """获取所有已注册的定时任务"""
    scheduler_manager = get_scheduler_manager()
    jobs = scheduler_manager.get_jobs()
    
    job_list = []
    for job in jobs:
        job_info = {
            "id": job.id,
            "name": job.name,
            "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        job_list.append(job_info)
    
    return ResponseData(
        data=job_list
    )


@router.post("/{expert_task_id}/scheduler/register", response_model=ResponseData[None])
async def register_task_to_scheduler(
    expert_task_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """手动注册任务到调度器"""
    service = ExpertTaskService(db)
    expert_task = await service.get(expert_task_id)
    
    if not expert_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertTask not found"
        )
    
    from app.services.expert_config_service import ExpertConfigService
    expert_config_service = ExpertConfigService(db)
    expert_config = await expert_config_service.get_by_code(expert_task.expert_config_code)
    executor = 'generation' if expert_config and expert_config.expert_type.upper() == 'GENERATION' else 'critic'

    scheduler_manager = get_scheduler_manager()
    job_id = f"expert_task_{expert_task.id}"
    
    try:
        scheduler_manager.add_cron_job(
            func=execute_expert_task_sync,
            job_id=job_id,
            cron_expression=expert_task.cron_expression,
            args=(expert_task.id,),
            executor=executor,
            replace_existing=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register task: {str(e)}"
        )
    
    return ResponseData(
        data=None,
        message=f"Task {job_id} registered successfully"
    )


@router.delete("/{expert_task_id}/scheduler/remove", response_model=ResponseData[None])
async def remove_task_from_scheduler(
    expert_task_id: int,
) -> ResponseData[None]:
    """从调度器移除任务"""
    scheduler_manager = get_scheduler_manager()
    job_id = f"expert_task_{expert_task_id}"
    
    success = scheduler_manager.remove_job(job_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduled job {job_id} not found"
        )
    
    return ResponseData(
        data=None,
        message=f"Task {job_id} removed successfully"
    )


@router.post("/{expert_task_id}/scheduler/pause", response_model=ResponseData[None])
async def pause_scheduled_task(
    expert_task_id: int,
) -> ResponseData[None]:
    """暂停定时任务"""
    scheduler_manager = get_scheduler_manager()
    job_id = f"expert_task_{expert_task_id}"
    
    success = scheduler_manager.pause_job(job_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduled job {job_id} not found"
        )
    
    return ResponseData(
        data=None,
        message=f"Task {job_id} paused successfully"
    )


@router.post("/{expert_task_id}/scheduler/resume", response_model=ResponseData[None])
async def resume_scheduled_task(
    expert_task_id: int,
) -> ResponseData[None]:
    """恢复定时任务"""
    scheduler_manager = get_scheduler_manager()
    job_id = f"expert_task_{expert_task_id}"
    
    success = scheduler_manager.resume_job(job_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduled job {job_id} not found"
        )
    
    return ResponseData(
        data=None,
        message=f"Task {job_id} resumed successfully"
    )


@router.post("/{expert_task_id}/execute", response_model=ResponseData[None])
async def execute_task_now(
    expert_task_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """立即执行一次任务（手动触发）"""
    service = ExpertTaskService(db)
    expert_task = await service.get(expert_task_id)
    
    if not expert_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertTask not found"
        )
    
    # 异步执行任务
    import asyncio
    from app.scheduler.expert_task_executor import ExpertTaskExecutor
    
    asyncio.create_task(ExpertTaskExecutor.execute_expert_task(expert_task_id))
    
    return ResponseData(
        data=None,
        message=f"Task {expert_task_id} execution triggered"
    )
