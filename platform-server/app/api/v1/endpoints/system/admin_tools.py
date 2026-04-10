"""
系统设置-管理工具：异步任务 API

表单提交 -> 创建任务记录 -> 后台异步执行 -> 前端轮询任务状态/结果
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_perm_code
from app.schemas.base import ResponseData
from app.schemas.admin_tools import (
    AdminToolTaskCreateRequest,
    AdminToolTaskResponse,
    AdminToolTaskListResponse,
)
from app.services.admin_tools_service import AdminToolTaskService, AdminToolTaskRunner


router = APIRouter(prefix="/admin-tools", tags=["管理工具"])


@router.post("/tasks", response_model=ResponseData[AdminToolTaskResponse], summary="创建管理工具任务（异步）")
async def create_admin_tool_task(
    req: AdminToolTaskCreateRequest,
    user_id: str = Depends(require_perm_code("system:management:tools")),
    db: AsyncSession = Depends(get_db),
):
    svc = AdminToolTaskService(db)
    task = await svc.create_task(task_type=req.task_type, params=req.params, created_by=user_id)
    # 异步执行（不阻塞请求）
    AdminToolTaskRunner.enqueue(task.id)
    return ResponseData(data=AdminToolTaskResponse.model_validate(task))


@router.get("/tasks", response_model=ResponseData[AdminToolTaskListResponse], summary="查询任务列表")
async def list_admin_tool_tasks(
    status: str | None = Query(None),
    task_type: str | None = Query(None),
    created_by: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _user_id: str = Depends(require_perm_code("system:management:tools")),
    db: AsyncSession = Depends(get_db),
):
    svc = AdminToolTaskService(db)
    items, total = await svc.list_tasks(
        status=status,
        task_type=task_type,
        created_by=created_by,
        page=page,
        page_size=page_size,
    )
    return ResponseData(
        data=AdminToolTaskListResponse(
            items=[AdminToolTaskResponse.model_validate(x) for x in items],
            total=total,
        )
    )


@router.get("/tasks/{task_id}", response_model=ResponseData[AdminToolTaskResponse], summary="查询任务详情")
async def get_admin_tool_task(
    task_id: int,
    _user_id: str = Depends(require_perm_code("system:management:tools")),
    db: AsyncSession = Depends(get_db),
):
    svc = AdminToolTaskService(db)
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return ResponseData(data=AdminToolTaskResponse.model_validate(task))


