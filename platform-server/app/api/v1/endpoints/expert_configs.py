"""
ExpertConfig endpoints
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import json

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.expert_config import (
    ExpertConfigCreate,
    ExpertConfigResponse,
    ExpertConfigUpdate,
    ExpertConfigCopyRequest,
)
from app.schemas.config_snapshot import EntityType
from app.schemas.expert_debug import (
    ExpertDebugRequest,
    ExpertDebugResponse,
    PreviewPromptRequest,
    PreviewPromptResponse,
    ExpertPluginVariablesResponse,
    DebugHistoryListResponse,
    StarHistoryRequest,
    TokenUsage,
    BatchDebugRequest,
    BatchDebugResponse,
    BatchDebugTaskResponse,
    BatchDebugTaskStatusResponse,
)
from app.schemas.expert_batch_score import (
    ExpertBatchScoreRequest,
    ExpertBatchScoreResponse,
    ExpertBatchScoreListParams,
    ExpertBatchScoreListResponse,
    BatchScoreTaskRequest,
    BatchScoreTaskResponse,
    BatchScoreTaskItem,
    BatchScoreTaskResultItem,
    BatchScoreTaskStatusResponse,
)
from app.services.expert_config_service import ExpertConfigService
from app.services.config_snapshot_service import ConfigSnapshotService
from app.services.expert_debug_service import ExpertDebugService
from app.models.agent import Agent

router = APIRouter()


# ==================== 静态路径路由（放在动态路径之前） ====================

@router.post("", response_model=ResponseData[ExpertConfigResponse])
async def create_expert_config(
        expert_config_in: ExpertConfigCreate,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertConfigResponse]:
    """Create new expert_config"""
    service = ExpertConfigService(db)
    snapshot_service = ConfigSnapshotService(db)

    try:
        expert_config = await service.create(expert_config_in)

        # 创建初始版本快照
        await snapshot_service.create_version(
            entity_type=EntityType.EXPERT_CONFIG,
            entity_id=expert_config.id,
            entity_code=expert_config.expert_config_code,
            content=ExpertConfigResponse.model_validate(expert_config).model_dump(mode="json", by_alias=True),
            description="初始版本"
        )

        return ResponseData(
            code=200,
            message="创建成功",
            data=ExpertConfigResponse.model_validate(expert_config)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/exists", response_model=ResponseData[dict])
async def check_expert_config_name_exists(
        expert_config_name: str = Query(..., description="Expert 名称"),
        exclude_id: Optional[int] = Query(None, description="排除的 ExpertConfig ID（编辑时传入当前记录 ID）"),
        db: AsyncSession = Depends(get_db),
) -> ResponseData[dict]:
    """检查 Expert 名称是否已存在（用于前端实时校验）"""
    service = ExpertConfigService(db)
    exists = await service.expert_config_name_exists(
        expert_config_name, exclude_id=exclude_id
    )
    return ResponseData(code=200, message="success", data={"exists": exists})


@router.get("", response_model=ResponseData[list[ExpertConfigResponse]])
async def list_expert_configs(
        expert_type: Optional[str] = Query(None, description="Filter by expert_type"),
        enabled: Optional[bool] = Query(None, description="Filter by enabled"),
        agent_code: Optional[str] = Query(None, description="Filter by agent_code"),
        is_deleted: Optional[bool] = Query(None, description="Filter by is_deleted"),
        skip: int = 0,
        limit: int = 1000,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[list[ExpertConfigResponse]]:
    """List all expert_configs"""
    service = ExpertConfigService(db)
    expert_config_code_list: Optional[List[str]] = None
    if agent_code:
        stmt = select(Agent.expert_config_code_list).where(
            Agent.agent_code == agent_code,
            Agent.is_deleted == 0,
            Agent.enabled == 1
        )
        result = await db.execute(stmt)
        expert_config_code_list = result.scalar_one_or_none() or []
        if not expert_config_code_list:
            return ResponseData(data=[])

    expert_configs = await service.list(
        expert_type=expert_type,
        enabled=enabled,
        is_deleted=is_deleted,
        expert_config_code_list=expert_config_code_list,
        skip=skip,
        limit=limit
    )

    return ResponseData(
        data=[ExpertConfigResponse.model_validate(ec) for ec in expert_configs]
    )


# ==================== Expert 调试 API（静态路径，放在 /{id} 之前） ====================

@router.post("/debug", response_model=ResponseData[ExpertDebugResponse])
async def debug_expert(
        request: ExpertDebugRequest,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertDebugResponse]:
    """
    调试 Expert 配置
    
    - 支持临时覆盖 model_code、model_config
    - 支持指定 plugin_config_snapshot
    - 支持直接覆盖渲染后的 prompt
    - 自动保存调试历史
    """
    service = ExpertDebugService(db)

    try:
        result = await service.debug(request)
        return ResponseData(
            message="调试完成" if result.success else "调试失败",
            data=result
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"调试执行失败: {str(e)}"
        )


@router.post("/preview-prompt", response_model=ResponseData[PreviewPromptResponse])
async def preview_prompt(
        request: PreviewPromptRequest,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[PreviewPromptResponse]:
    """
    预览 Prompt 渲染结果
    
    - 不执行实际调用，只渲染 Prompt
    - 可指定 plugin_config_snapshot，不传则随机选择
    """
    service = ExpertDebugService(db)

    try:
        result = await service.preview_prompt(request)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/debug-history", response_model=ResponseData[DebugHistoryListResponse])
async def get_debug_history(
        expert_config_code: Optional[str] = Query(None, description="筛选特定 Expert"),
        success: Optional[bool] = Query(None, description="筛选成功/失败"),
        is_starred: Optional[bool] = Query(None, description="筛选收藏"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        db: AsyncSession = Depends(get_db),
) -> ResponseData[DebugHistoryListResponse]:
    """获取调试历史列表"""
    service = ExpertDebugService(db)

    items, total = await service.get_history_list(
        expert_config_code=expert_config_code,
        success=success,
        is_starred=is_starred,
        page=page,
        page_size=page_size
    )

    # 转换为响应格式
    response_items: List[ExpertDebugResponse] = []
    for item in items:
        token_usage = None
        if item.token_usage:
            token_usage = TokenUsage(**item.token_usage)

        response_items.append(ExpertDebugResponse(
            id=item.id,
            success=item.success,
            expert_config_code=item.expert_config_code,
            expert_config_name=item.expert_config_name,
            model_code=item.model_code,
            model_config_used=item.model_config_used,
            prompt_template=item.prompt_template,
            plugin_config_snapshot=item.plugin_config_snapshot,
            rendered_prompt=item.rendered_prompt,
            prompt_override=item.prompt_override,
            input_content=item.input_content,
            output_content=item.output_content,
            expert_total_output=item.expert_total_output,  # 添加完整返回结果
            execution_time_ms=item.execution_time_ms,
            token_usage=token_usage,
            error_message=item.error_message,
            trace_id=item.trace_id,
            create_time=item.create_time,
            is_starred=bool(item.is_starred)
        ))

    return ResponseData(
        data=DebugHistoryListResponse(
            items=response_items,
            total=total,
            page=page,
            page_size=page_size
        )
    )


@router.get("/debug-history/{history_id}", response_model=ResponseData[ExpertDebugResponse])
async def get_debug_history_detail(
        history_id: int,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertDebugResponse]:
    """获取单条调试历史详情"""
    service = ExpertDebugService(db)

    item = await service.get_history_by_id(history_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="调试历史不存在"
        )

    token_usage = None
    if item.token_usage:
        token_usage = TokenUsage(**item.token_usage)

    return ResponseData(
        data=ExpertDebugResponse(
            id=item.id,
            success=item.success,
            expert_config_code=item.expert_config_code,
            expert_config_name=item.expert_config_name,
            model_code=item.model_code,
            model_config_used=item.model_config_used,
            prompt_template=item.prompt_template,
            plugin_config_snapshot=item.plugin_config_snapshot,
            rendered_prompt=item.rendered_prompt,
            prompt_override=item.prompt_override,
            input_content=item.input_content,
            output_content=item.output_content,
            expert_total_output=item.expert_total_output,  # 添加完整返回结果
            execution_time_ms=item.execution_time_ms,
            token_usage=token_usage,
            error_message=item.error_message,
            trace_id=item.trace_id,
            create_time=item.create_time,
            is_starred=bool(item.is_starred)
        )
    )


@router.put("/debug-history/{history_id}/star", response_model=ResponseData[None])
async def star_debug_history(
        history_id: int,
        request: StarHistoryRequest,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """收藏/取消收藏调试历史"""
    service = ExpertDebugService(db)

    success = await service.star_history(history_id, request.is_starred)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="调试历史不存在"
        )

    return ResponseData(
        data=None,
        message=("收藏" if request.is_starred else "取消收藏") + "成功"
    )


@router.delete("/debug-history/{history_id}", response_model=ResponseData[None])
async def delete_debug_history(
        history_id: int,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """删除调试历史"""
    service = ExpertDebugService(db)

    success = await service.delete_history(history_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="调试历史不存在"
        )

    return ResponseData(message="删除成功")


@router.post("/debug-batch", response_model=ResponseData[BatchDebugTaskResponse])
async def batch_debug_expert(
        request: BatchDebugRequest,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[BatchDebugTaskResponse]:
    """
    批量随机调试 Expert 配置（异步并行模式）
    
    - 立即返回 task_id
    - 后台异步并行执行调试任务
    - 通过 SSE 端点或轮询查询进度
    """
    from app.core.database import async_session_factory
    
    service = ExpertDebugService(db)

    try:
        # 创建任务
        task_id = await service.create_batch_debug_task(request)
        
        # 后台并行执行任务（使用独立的数据库会话工厂）
        from loguru import logger
        logger.info(f"[BatchRandom] Creating background task for {task_id}")
        
        async def run_task():
            try:
                async with async_session_factory() as db_inner:
                    inner_service = ExpertDebugService(db_inner)
                    await inner_service.execute_batch_debug_task(task_id, async_session_factory)
            except Exception as e:
                logger.error(f"[BatchRandom] Background task error: {e}", exc_info=True)
                async with async_session_factory() as db_inner:
                    result = await db_inner.execute(
                        select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
                    )
                    task_obj = result.scalar_one_or_none()
                    if task_obj:
                        task_obj.status = "failed"
                        task_obj.error_message = str(e)
                        await db_inner.commit()
        
        asyncio.create_task(run_task())
        logger.info(f"[BatchRandom] Background task scheduled for {task_id}")
        
        return ResponseData(
            message="批量随机生成任务已创建",
            data=BatchDebugTaskResponse(
                task_id=task_id,
                status="pending",
                expert_config_code=request.expert_config_code,
                total=request.count,
                message=f"任务已创建，正在并行执行 {request.count} 次生成..."
            )
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建批量随机生成任务失败: {str(e)}"
        )


@router.get("/debug-batch/{task_id}/stream")
async def batch_debug_task_stream(
        task_id: str,
        db: AsyncSession = Depends(get_db),
):
    """
    SSE 端点：实时推送批量调试任务进度
    
    - 返回 Server-Sent Events 流
    - 每完成一个任务推送一次进度
    - 任务完成后关闭连接
    """
    
    async def event_generator():
        """SSE 事件生成器"""
        service = ExpertDebugService(db)
        last_completed = 0
        
        try:
            while True:
                # 查询任务状态
                task = await service.get_batch_debug_task_status(task_id)
                
                if not task:
                    yield f"event: error\ndata: {json.dumps({'error': 'Task not found'})}\n\n"
                    break
                
                # 如果进度更新，推送事件
                if task.completed > last_completed or task.status in ["completed", "failed"]:
                    event_data = {
                        "task_id": task.task_id,
                        "status": task.status,
                        "total": task.total,
                        "completed": task.completed,
                        "success_count": task.success_count,
                        "failed_count": task.failed_count,
                        "results": task.results or [],
                    }
                    
                    yield f"event: progress\ndata: {json.dumps(event_data)}\n\n"
                    last_completed = task.completed
                
                # 任务完成，关闭连接
                if task.status in ["completed", "failed"]:
                    yield f"event: done\ndata: {json.dumps({'message': 'Task completed'})}\n\n"
                    break
                
                # 等待 1 秒后继续检查
                await asyncio.sleep(1)
                
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        }
    )


@router.get("/debug-batch", response_model=ResponseData[dict])
async def list_batch_debug_tasks(
        expert_config_code: Optional[str] = Query(None, description="筛选特定 Expert"),
        status: Optional[str] = Query(None, description="筛选状态"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        db: AsyncSession = Depends(get_db),
) -> ResponseData[dict]:
    """
    获取批量调试任务历史列表
    
    - 支持按 expert_config_code 和 status 筛选
    - 按创建时间倒序排列
    """
    from app.models.expert_debug_batch_task import ExpertDebugBatchTask
    from sqlalchemy import desc, func
    
    # 构建查询
    query = select(ExpertDebugBatchTask)
    
    if expert_config_code:
        query = query.where(ExpertDebugBatchTask.expert_config_code == expert_config_code)
    if status:
        query = query.where(ExpertDebugBatchTask.status == status)
    
    # 总数查询
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页查询
    query = query.order_by(desc(ExpertDebugBatchTask.create_time))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    items = []
    for task in tasks:
        items.append({
            "id": task.id,
            "task_id": task.task_id,
            "expert_config_code": task.expert_config_code,
            "expert_config_name": task.expert_config_name,
            "status": task.status,
            "total": task.total,
            "completed": task.completed,
            "success_count": task.success_count,
            "failed_count": task.failed_count,
            "start_time": task.start_time,
            "end_time": task.end_time,
            "create_time": task.create_time,
        })
    
    return ResponseData(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/debug-batch/{task_id}", response_model=ResponseData[BatchDebugTaskStatusResponse])
async def get_batch_debug_task_status(
        task_id: str,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[BatchDebugTaskStatusResponse]:
    """
    查询批量调试任务状态
    
    - 返回任务当前状态和结果
    """
    service = ExpertDebugService(db)
    
    task = await service.get_batch_debug_task_status(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    from app.schemas.expert_debug import BatchDebugResultItem
    results = [BatchDebugResultItem(**r) for r in (task.results or [])]
    
    return ResponseData(
        data=BatchDebugTaskStatusResponse(
            task_id=task.task_id,
            status=task.status,
            expert_config_code=task.expert_config_code,
            expert_config_name=task.expert_config_name,
            total=task.total,
            completed=task.completed,
            success_count=task.success_count,
            failed_count=task.failed_count,
            results=results,
            error_message=task.error_message,
            start_time=task.start_time,
            end_time=task.end_time,
            create_time=task.create_time
        )
    )


# ==================== 批量评分 API ====================

@router.post("/batch-score", response_model=ResponseData[ExpertBatchScoreResponse])
async def batch_score_expert(
        request: ExpertBatchScoreRequest,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertBatchScoreResponse]:
    """
    批量评分：获取文章，调用专家评分，保存结果
    
    - 可指定 content_ids 列表进行批量评分（支持业务文章和测试用例）
    - 不传 content_ids 时，根据 test_case_only 参数决定查询范围
    - 保存结果到 expert_batch_score_result 表，并更新 critic_score_record
    """
    service = ExpertDebugService(db)
    
    try:
        result = await service.batch_score(
            expert_config_code=request.expert_config_code,
            content_ids=request.content_ids,
            max_count=request.max_count,
            test_case_only=request.test_case_only,
        )
        
        # 转换为响应格式
        from app.schemas.expert_batch_score import ExpertBatchScoreResultResponse
        result_items = [
            ExpertBatchScoreResultResponse(
                id=r.id,
                expert_config_code=r.expert_config_code,
                content_id=r.content_id,
                title=r.title,
                content=r.content,
                score=r.score,
                reason=r.reason,
                highlights=r.highlights,
                problem_tags=r.problem_tags,
                problem_snippets=r.problem_snippets,
                model_code=r.model_code,
                execution_time_ms=r.execution_time_ms,
                error_message=r.error_message,
                success=r.success,
                create_time=r.create_time,
                created_by=r.created_by
            )
            for r in result["results"]
        ]
        
        return ResponseData(
            message=f"批量评分完成: 成功 {result['success_count']} 篇, 失败 {result['failed_count']} 篇",
            data=ExpertBatchScoreResponse(
                expert_config_code=result["expert_config_code"],
                total=result["total"],
                success_count=result["success_count"],
                failed_count=result["failed_count"],
                results=result_items
            )
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量评分失败: {str(e)}"
        )


@router.get("/batch-score-results", response_model=ResponseData[ExpertBatchScoreListResponse])
async def list_batch_score_results(
        expert_config_code: Optional[str] = Query(None, description="expert_config 配置 code"),
        content_id: Optional[str] = Query(None, description="测试用例 content_id"),
        success: Optional[bool] = Query(None, description="是否成功"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertBatchScoreListResponse]:
    """获取批量评分结果列表"""
    from app.models.expert_batch_score_result import ExpertBatchScoreResult
    from sqlalchemy import select, and_, func
    from app.schemas.expert_batch_score import ExpertBatchScoreResultResponse
    
    query = select(ExpertBatchScoreResult)
    filters = []
    
    if expert_config_code:
        filters.append(ExpertBatchScoreResult.expert_config_code == expert_config_code)
    if content_id:
        filters.append(ExpertBatchScoreResult.content_id == content_id)
    if success is not None:
        filters.append(ExpertBatchScoreResult.success == success)
    
    if filters:
        query = query.where(and_(*filters))
    
    # 总数
    count_query = select(func.count()).select_from(ExpertBatchScoreResult)
    if filters:
        count_query = count_query.where(and_(*filters))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(ExpertBatchScoreResult.create_time.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    results = await db.execute(query)
    items = results.scalars().all()
    
    return ResponseData(
        data=ExpertBatchScoreListResponse(
            items=[
                ExpertBatchScoreResultResponse(
                    id=item.id,
                    expert_config_code=item.expert_config_code,
                    content_id=item.content_id,
                    title=item.title,
                    content=item.content,
                    score=item.score,
                    reason=item.reason,
                    highlights=item.highlights,
                    problem_tags=item.problem_tags,
                    problem_snippets=item.problem_snippets,
                    model_code=item.model_code,
                    execution_time_ms=item.execution_time_ms,
                    error_message=item.error_message,
                    success=item.success,
                    create_time=item.create_time,
                    created_by=item.created_by
                )
                for item in items
            ],
            total=total,
            page=page,
            page_size=page_size
        )
    )


# ==================== 异步批量评分（任务模式） ====================

@router.post("/batch-score-async", response_model=ResponseData[BatchScoreTaskResponse])
async def create_batch_score_task(
        request: BatchScoreTaskRequest,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[BatchScoreTaskResponse]:
    """
    创建异步批量评分任务（支持多专家，立即返回 task_id 列表，后台并行执行）
    
    - 支持同时选择多个专家（CRITIC/BAN）
    - 为每个专家创建独立的任务，真正并行执行（使用 asyncio.create_task）
    - 前端通过 /batch-score-task/{task_id} 轮询查询每个任务进度
    """
    from app.core.database import async_session_factory
    from app.models.expert_debug_batch_task import ExpertDebugBatchTask
    from loguru import logger
    import uuid
    
    service = ExpertDebugService(db)
    
    if not request.expert_config_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少选择一个专家配置"
        )
    
    if not request.content_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少选择一篇文章"
        )
    
    try:
        created_tasks: list[BatchScoreTaskItem] = []
        tasks_to_run: list[tuple[str, str, list[str], bool]] = []
        
        # 为每个专家创建独立任务
        for expert_config_code in request.expert_config_codes:
            # 验证 expert_config 存在
            expert_config = await service.expert_config_service.get_by_code(expert_config_code)
            if not expert_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"ExpertConfig '{expert_config_code}' 不存在"
                )
            
            # 创建任务记录
            task_id = f"bscore-{uuid.uuid4().hex[:16]}"
            
            task = ExpertDebugBatchTask(
                task_id=task_id,
                expert_config_code=expert_config_code,
                expert_config_name=expert_config.expert_config_name,
                status="pending",
                total=len(request.content_ids),
                completed=0,
                success_count=0,
                failed_count=0,
                request_params={
                    "content_ids": request.content_ids,
                    "test_case_only": request.test_case_only,
                },
                results=[],
            )
            db.add(task)
            
            created_tasks.append(BatchScoreTaskItem(
                task_id=task_id,
                expert_config_code=expert_config_code,
                expert_config_name=expert_config.expert_config_name or "",
                status="pending",
                total=len(request.content_ids),
            ))
            
            # 收集任务参数，稍后并行启动
            tasks_to_run.append((task_id, expert_config_code, request.content_ids, request.test_case_only, request.concurrency))
        
        await db.commit()
        
        # 使用 asyncio.create_task 真正并行执行所有专家任务
        for task_id, expert_config_code, content_ids, test_case_only, concurrency in tasks_to_run:
            logger.info(f"[BatchScoreTask] Creating parallel task for {task_id} ({expert_config_code}), concurrency={concurrency}")
            asyncio.create_task(
                _execute_batch_score_task_wrapper(
                    task_id=task_id,
                    expert_config_code=expert_config_code,
                    content_ids=content_ids,
                    test_case_only=test_case_only,
                    concurrency=concurrency,
                    db_factory=async_session_factory,
                )
            )
        
        return ResponseData(
            message=f"已创建 {len(created_tasks)} 个批量评分任务，后台并行执行中",
            data=BatchScoreTaskResponse(
                tasks=created_tasks,
                total_experts=len(created_tasks),
                total_contents=len(request.content_ids),
                message="任务已创建，请轮询查询进度",
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建批量评分任务失败: {str(e)}"
        )


async def _execute_batch_score_task_wrapper(
    task_id: str,
    expert_config_code: str,
    content_ids: list[str],
    test_case_only: bool,
    concurrency: int,
    db_factory,
):
    """包装器：捕获异常并更新任务状态"""
    from loguru import logger
    from app.models.expert_debug_batch_task import ExpertDebugBatchTask
    from sqlalchemy import select, update
    from datetime import datetime
    
    try:
        await _execute_batch_score_task(
            task_id=task_id,
            expert_config_code=expert_config_code,
            content_ids=content_ids,
            test_case_only=test_case_only,
            concurrency=concurrency,
            db_factory=db_factory,
        )
    except Exception as e:
        logger.error(f"[BatchScoreTask] Task {task_id} failed with error: {e}", exc_info=True)
        # 更新任务状态为失败
        try:
            async with db_factory() as db:
                await db.execute(
                    update(ExpertDebugBatchTask)
                    .where(ExpertDebugBatchTask.task_id == task_id)
                    .values(
                        status="failed",
                        error_message=str(e),
                        end_time=datetime.now(),
                    )
                )
                await db.commit()
        except Exception as db_err:
            logger.error(f"[BatchScoreTask] Failed to update task status: {db_err}")


@router.get("/batch-score-task/{task_id}", response_model=ResponseData[BatchScoreTaskStatusResponse])
async def get_batch_score_task_status(
        task_id: str,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[BatchScoreTaskStatusResponse]:
    """查询批量评分任务状态和进度"""
    from app.models.expert_debug_batch_task import ExpertDebugBatchTask
    from sqlalchemy import select
    
    result = await db.execute(
        select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务 '{task_id}' 不存在"
        )
    
    # 转换结果格式
    results = []
    if task.results:
        for r in task.results:
            results.append(BatchScoreTaskResultItem(
                content_id=r.get("content_id", ""),
                title=r.get("title"),
                score=r.get("score"),
                reason=r.get("reason"),
                success=r.get("success", False),
                error_message=r.get("error_message"),
                execution_time_ms=r.get("execution_time_ms"),
            ))
    
    return ResponseData(
        data=BatchScoreTaskStatusResponse(
            task_id=task.task_id,
            status=task.status,
            total=task.total,
            completed=task.completed,
            success_count=task.success_count,
            failed_count=task.failed_count,
            results=results,
            error_message=task.error_message,
            start_time=task.start_time.strftime("%Y-%m-%d %H:%M:%S") if task.start_time else None,
            end_time=task.end_time.strftime("%Y-%m-%d %H:%M:%S") if task.end_time else None,
        )
    )


async def _execute_batch_score_task(
    task_id: str,
    expert_config_code: str,
    content_ids: List[str],
    test_case_only: bool,
    concurrency: int,
    db_factory,
):
    """后台执行批量评分任务"""
    from loguru import logger
    from datetime import datetime
    from app.models.expert_debug_batch_task import ExpertDebugBatchTask
    from app.models.content import Content
    from sqlalchemy import select, update
    import time
    
    logger.info(f"[BatchScoreTask] Starting task {task_id}, content_ids={len(content_ids)}")
    
    # 更新任务状态为 running
    async with db_factory() as db:
        await db.execute(
            update(ExpertDebugBatchTask)
            .where(ExpertDebugBatchTask.task_id == task_id)
            .values(status="running", start_time=datetime.now())
        )
        await db.commit()
    
    results = []
    success_count = 0
    failed_count = 0
    
    # 并发控制：使用请求中的并发数（LLM 调用较重）
    semaphore = asyncio.Semaphore(concurrency)
    
    async def score_single(content_id: str) -> dict:
        """评分单篇文章"""
        nonlocal success_count, failed_count
        
        async with semaphore:
            start_time = time.time()
            try:
                async with db_factory() as session:
                    service = ExpertDebugService(session)
                    
                    # 获取文章内容
                    content_result = await session.execute(
                        select(Content).where(Content.content_id == content_id)
                    )
                    content_obj = content_result.scalar_one_or_none()
                    
                    if not content_obj:
                        return {
                            "content_id": content_id,
                            "title": None,
                            "score": None,
                            "reason": None,
                            "success": False,
                            "error_message": f"文章 {content_id} 不存在",
                            "execution_time_ms": int((time.time() - start_time) * 1000),
                        }
                    
                    # 执行评分
                    score_result = await service.batch_score(
                        expert_config_code=expert_config_code,
                        content_ids=[content_id],
                        max_count=1,
                        test_case_only=test_case_only,
                        concurrency=1,
                    )
                    
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    
                    if score_result["success_count"] > 0 and score_result["results"]:
                        result_item = score_result["results"][0]
                        return {
                            "content_id": content_id,
                            "title": getattr(result_item, "title", None) or content_obj.title,
                            "score": getattr(result_item, "score", None),
                            "reason": getattr(result_item, "reason", None),
                            "success": True,
                            "error_message": None,
                            "execution_time_ms": execution_time_ms,
                        }
                    else:
                        return {
                            "content_id": content_id,
                            "title": content_obj.title,
                            "score": None,
                            "reason": None,
                            "success": False,
                            "error_message": "评分失败",
                            "execution_time_ms": execution_time_ms,
                        }
            except Exception as e:
                logger.error(f"[BatchScoreTask] Error scoring {content_id}: {e}")
                return {
                    "content_id": content_id,
                    "title": None,
                    "score": None,
                    "reason": None,
                    "success": False,
                    "error_message": str(e),
                    "execution_time_ms": int((time.time() - start_time) * 1000),
                }
    
    try:
        # 并行执行所有评分任务
        tasks = [score_single(cid) for cid in content_ids]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for r in all_results:
            if isinstance(r, Exception):
                failed_count += 1
                results.append({
                    "content_id": "unknown",
                    "title": None,
                    "score": None,
                    "reason": None,
                    "success": False,
                    "error_message": str(r),
                    "execution_time_ms": 0,
                })
            elif isinstance(r, dict):
                results.append(r)
                if r.get("success"):
                    success_count += 1
                else:
                    failed_count += 1
        
        # 更新任务为完成
        async with db_factory() as db:
            await db.execute(
                update(ExpertDebugBatchTask)
                .where(ExpertDebugBatchTask.task_id == task_id)
                .values(
                    status="completed",
                    completed=len(content_ids),
                    success_count=success_count,
                    failed_count=failed_count,
                    results=results,
                    end_time=datetime.now(),
                )
            )
            await db.commit()
        
        logger.info(f"[BatchScoreTask] Task {task_id} completed: success={success_count}, failed={failed_count}")
        
    except Exception as e:
        logger.error(f"[BatchScoreTask] Task {task_id} failed: {e}")
        async with db_factory() as db:
            await db.execute(
                update(ExpertDebugBatchTask)
                .where(ExpertDebugBatchTask.task_id == task_id)
                .values(
                    status="failed",
                    error_message=str(e),
                    end_time=datetime.now(),
                )
            )
            await db.commit()


# ==================== 有前缀的动态路径（放在 /{id} 之前） ====================

@router.post("/{expert_config_id}/copy", response_model=ResponseData[ExpertConfigResponse])
async def copy_expert_config(
        expert_config_id: int,
        request: ExpertConfigCopyRequest,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertConfigResponse]:
    """复制 ExpertConfig（仅修改 code/name，其余字段全量复制）"""
    service = ExpertConfigService(db)
    snapshot_service = ConfigSnapshotService(db)

    try:
        expert_config = await service.copy(
            expert_config_id,
            expert_config_code=request.expert_config_code,
            expert_config_name=request.expert_config_name,
        )

        await snapshot_service.create_version(
            entity_type=EntityType.EXPERT_CONFIG,
            entity_id=expert_config.id,
            entity_code=expert_config.expert_config_code,
            content=ExpertConfigResponse.model_validate(expert_config).model_dump(mode="json", by_alias=True),
            description="复制创建"
        )

        return ResponseData(
            code=200,
            message="复制成功",
            data=ExpertConfigResponse.model_validate(expert_config),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/code/{expert_config_code}", response_model=ResponseData[ExpertConfigResponse])
async def get_expert_config_by_code(
        expert_config_code: str,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertConfigResponse]:
    """Get expert_config by code"""
    service = ExpertConfigService(db)
    expert_config = await service.get_by_code(expert_config_code)

    if not expert_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertConfig not found"
        )

    return ResponseData(
        data=ExpertConfigResponse.model_validate(expert_config)
    )


@router.get("/{expert_config_code}/plugin-variables", response_model=ResponseData[ExpertPluginVariablesResponse])
async def get_plugin_variables(
        expert_config_code: str,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertPluginVariablesResponse]:
    """
    获取 Expert 关联的所有 Plugin 变量选项
    
    - 用于前端变量选择器
    - 返回每个变量的可选值列表
    """
    service = ExpertDebugService(db)

    try:
        result = await service.get_plugin_variables(expert_config_code)
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


# ==================== 纯动态路径（放在最后） ====================

@router.get("/{expert_config_id}", response_model=ResponseData[ExpertConfigResponse])
async def get_expert_config(
        expert_config_id: int,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertConfigResponse]:
    """Get expert_config by ID"""
    service = ExpertConfigService(db)
    expert_config = await service.get(expert_config_id)

    if not expert_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertConfig not found"
        )

    return ResponseData(
        data=ExpertConfigResponse.model_validate(expert_config)
    )


@router.put("/{expert_config_id}", response_model=ResponseData[ExpertConfigResponse])
async def update_expert_config(
        expert_config_id: int,
        expert_config_in: ExpertConfigUpdate,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[ExpertConfigResponse]:
    """Update expert_config"""
    service = ExpertConfigService(db)
    snapshot_service = ConfigSnapshotService(db)

    expert_config = await service.update(expert_config_id, expert_config_in)

    if not expert_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertConfig not found"
        )

    # 创建版本快照
    await snapshot_service.create_version(
        entity_type=EntityType.EXPERT_CONFIG,
        entity_id=expert_config.id,
        entity_code=expert_config.expert_config_code,
        content=ExpertConfigResponse.model_validate(expert_config).model_dump(mode="json", by_alias=True),
        description=None  # 自动生成版本号描述
    )

    return ResponseData(
        message="ExpertConfig updated successfully",
        data=ExpertConfigResponse.model_validate(expert_config)
    )


@router.delete("/{expert_config_id}", response_model=ResponseData[None])
async def delete_expert_config(
        expert_config_id: int,
        db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """Delete expert_config"""
    service = ExpertConfigService(db)
    success = await service.delete(expert_config_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ExpertConfig not found"
        )

    return ResponseData(
        message="ExpertConfig deleted successfully",
        data=None
    )


# ==================== 批量固定生成 API ====================

from pydantic import BaseModel, Field, ConfigDict
from typing import Any
import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.orm import attributes

from app.models.expert_debug_batch_task import ExpertDebugBatchTask


class BatchFixedGenerateRequest(BaseModel):
    """批量固定生成请求"""
    model_config = ConfigDict(protected_namespaces=())
    
    expert_config_code: str
    content: str = ""
    count: int = Field(default=5, ge=1, le=20)
    plugin_config_snapshot: Optional[List[dict]] = None
    prompt_override: Optional[str] = None  # 编辑后的提示词（覆盖自动渲染）
    model_code: Optional[str] = None
    model_config_override: Optional[dict] = None


class BatchFixedTaskResponse(BaseModel):
    """批量固定生成任务响应"""
    task_id: str
    status: str
    expert_config_code: str
    total: int
    message: str


class BatchFixedResultItem(BaseModel):
    """批量固定生成结果项"""
    index: int
    success: bool
    variable_summary: str = ""
    title: str = ""  # 生成内容的标题
    output_preview: str = ""
    output_content: Optional[str] = None
    execution_time_ms: int = 0
    error_message: Optional[str] = None
    history_id: Optional[int] = None


class BatchFixedTaskStatusResponse(BaseModel):
    """批量固定生成任务状态响应"""
    task_id: str
    status: str
    expert_config_code: str
    expert_config_name: Optional[str] = None
    total: int
    completed: int
    success_count: int
    failed_count: int
    results: List[BatchFixedResultItem]
    error_message: Optional[str] = None


async def _execute_batch_fixed_task(
    task_id: str,
    request: BatchFixedGenerateRequest,
    db_factory,
):
    """后台执行批量固定生成任务（并行执行）"""
    from loguru import logger
    from app.schemas.expert_debug import ExpertDebugRequest
    
    logger.info(f"[BatchFixed] Starting task {task_id}, count={request.count}")
    
    # 更新任务状态为 running
    async with db_factory() as db:
        result = await db.execute(
            select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            logger.error(f"[BatchFixed] Task not found in DB: {task_id}")
            return
        task.status = "running"
        await db.commit()
    
    async def execute_single(index: int) -> BatchFixedResultItem:
        """执行单次生成"""
        try:
            logger.info(f"[BatchFixed] Executing index {index}")
            async with db_factory() as db:
                service = ExpertDebugService(db)
                
                # 构造调试请求 - 使用编辑后的提示词（如有）
                debug_request = ExpertDebugRequest(
                    expert_config_code=request.expert_config_code,
                    content=request.content,
                    plugin_config_snapshot=request.plugin_config_snapshot,
                    prompt_override=request.prompt_override,  # 编辑后的提示词
                    model_code=request.model_code,
                    model_cfg_override=request.model_config_override,
                )
                
                # 执行调试
                result = await service.debug(debug_request)
                logger.info(f"[BatchFixed] Index {index} completed, success={result.success}")
                
                # 构建变量摘要
                var_summary = ""
                if request.plugin_config_snapshot:
                    parts = []
                    for item in request.plugin_config_snapshot:
                        for var_name, context_name in item.get("variable_mapping", {}).items():
                            parts.append(f"{var_name}={context_name}")
                    var_summary = ", ".join(parts[:3])
                    if len(parts) > 3:
                        var_summary += f"... (+{len(parts)-3})"
                
                # 提取标题：优先从 expert_total_output 获取，否则从 output_content 第一行提取
                title = ""
                if result.expert_total_output:
                    title = (
                        result.expert_total_output.get("title", "") or
                        result.expert_total_output.get("generatedTitle", "") or
                        result.expert_total_output.get("generated_title", "") or
                        ""
                    )
                # 如果没有从 expert_total_output 获取到，尝试从 output_content 第一行提取
                if not title and result.output_content:
                    first_line = result.output_content.strip().split("\n")[0]
                    # 移除常见的标题前缀符号
                    title = first_line.lstrip("#").lstrip("*").lstrip("-").strip()
                    # 限制标题长度
                    if len(title) > 100:
                        title = title[:100] + "..."
                
                return BatchFixedResultItem(
                    index=index,
                    success=result.success,
                    variable_summary=var_summary,
                    title=title,
                    output_preview=(result.output_content or "")[:200] if result.output_content else "",
                    output_content=result.output_content,
                    execution_time_ms=result.execution_time_ms,
                    error_message=result.error_message,
                    history_id=result.id,
                )
        except Exception as e:
            logger.error(f"[BatchFixed] Index {index} error: {e}")
            return BatchFixedResultItem(
                index=index,
                success=False,
                variable_summary="",
                output_preview="",
                execution_time_ms=0,
                error_message=str(e),
            )
    
    try:
        # 并行执行所有生成任务
        tasks = [execute_single(i + 1) for i in range(request.count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理可能的异常结果
        processed_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"[BatchFixed] Task {i+1} raised exception: {r}")
                processed_results.append(BatchFixedResultItem(
                    index=i + 1,
                    success=False,
                    variable_summary="",
                    output_preview="",
                    execution_time_ms=0,
                    error_message=str(r),
                ))
            else:
                processed_results.append(r)
        
        # 更新数据库中的任务状态
        async with db_factory() as db:
            result = await db.execute(
                select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task:
                task.results = [r.model_dump() for r in processed_results]
                task.completed = len(processed_results)
                task.success_count = sum(1 for r in processed_results if r.success)
                task.failed_count = sum(1 for r in processed_results if not r.success)
                task.status = "completed"
                attributes.flag_modified(task, 'results')
                await db.commit()
                logger.info(f"[BatchFixed] Task {task_id} completed: success={task.success_count}, failed={task.failed_count}")
    except Exception as e:
        logger.error(f"[BatchFixed] Task {task_id} failed: {e}")
        async with db_factory() as db:
            result = await db.execute(
                select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task:
                task.status = "failed"
                task.error_message = str(e)
                await db.commit()


@router.post("/debug-batch-fixed", response_model=ResponseData[BatchFixedTaskResponse])
async def create_batch_fixed_generate_task(
    request: BatchFixedGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[BatchFixedTaskResponse]:
    """
    创建批量固定生成任务
    
    使用固定的变量配置，并行生成多篇内容
    """
    from app.core.database import async_session_factory
    
    # 验证 Expert 配置存在
    service = ExpertConfigService(db)
    expert_config = await service.get_by_code(request.expert_config_code)
    if not expert_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ExpertConfig not found: {request.expert_config_code}"
        )
    
    # 创建任务并存储到数据库
    task_id = f"batch-fixed-{uuid.uuid4().hex[:12]}"
    task = ExpertDebugBatchTask(
        task_id=task_id,
        status="pending",
        expert_config_code=request.expert_config_code,
        expert_config_name=expert_config.expert_config_name,
        total=request.count,
        completed=0,
        success_count=0,
        failed_count=0,
        results=[],
    )
    db.add(task)
    await db.commit()
    
    # 后台执行任务
    from loguru import logger
    logger.info(f"[BatchFixed] Creating background task for {task_id}")
    
    async def run_task():
        try:
            await _execute_batch_fixed_task(task_id, request, async_session_factory)
        except Exception as e:
            logger.error(f"[BatchFixed] Background task error: {e}", exc_info=True)
            async with async_session_factory() as db_inner:
                result = await db_inner.execute(
                    select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
                )
                task_obj = result.scalar_one_or_none()
                if task_obj:
                    task_obj.status = "failed"
                    task_obj.error_message = str(e)
                    await db_inner.commit()
    
    asyncio.create_task(run_task())
    logger.info(f"[BatchFixed] Background task scheduled for {task_id}")
    
    return ResponseData(
        message="批量固定生成任务已创建",
        data=BatchFixedTaskResponse(
            task_id=task_id,
            status="pending",
            expert_config_code=request.expert_config_code,
            total=request.count,
            message="任务已创建，正在并行执行...",
        )
    )


@router.get("/debug-batch-fixed/{task_id}", response_model=ResponseData[BatchFixedTaskStatusResponse])
async def get_batch_fixed_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[BatchFixedTaskStatusResponse]:
    """获取批量固定生成任务状态"""
    result = await db.execute(
        select(ExpertDebugBatchTask).where(ExpertDebugBatchTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}"
        )
    
    return ResponseData(
        data=BatchFixedTaskStatusResponse(
            task_id=task.task_id,
            status=task.status,
            expert_config_code=task.expert_config_code,
            expert_config_name=task.expert_config_name,
            total=task.total,
            completed=task.completed,
            success_count=task.success_count,
            failed_count=task.failed_count,
            results=[BatchFixedResultItem(**r) for r in (task.results or [])],
            error_message=task.error_message,
        )
    )
