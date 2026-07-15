"""
Expert Eval endpoints
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, async_session_factory
from app.schemas.base import ResponseData
from app.schemas.expert_eval import (
    CreateEvalRunRequest,
    CreateEvalRunResponse,
    EvalRunListResponse,
    EvalRunItem,
    EvalResultListResponse,
    EvalResultItem,
    EvalResultDetailResponse,
    EvalResultDetailTestCase,
)
from app.services.expert_eval_service import ExpertEvalService


router = APIRouter()


@router.post("/runs", response_model=ResponseData[CreateEvalRunResponse])
async def create_eval_run(
    data: CreateEvalRunRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[CreateEvalRunResponse]:
    service = ExpertEvalService(db)
    try:
        run = await service.create_run(
            expert_config_code=data.expert_config_code,
            test_set_code=data.test_set_code,
            test_case_ids=data.test_case_ids,
            max_count=data.max_count or 50,
            start_no=data.start_no,
            end_no=data.end_no,
            article_concurrency=data.article_concurrency or 4,
            created_by=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    async def _background_execute(run_id: int) -> None:
        async with async_session_factory() as session:
            svc = ExpertEvalService(session)
            await svc.execute_run(run_id=run_id)

    # 后台执行，避免前端长时间等待
    loop = asyncio.get_running_loop()
    loop.create_task(_background_execute(run.id))

    return ResponseData(
        message="创建成功（后台执行中）",
        data=CreateEvalRunResponse(run_id=run.id, run_code=run.run_code),
    )


@router.get("/runs", response_model=ResponseData[EvalRunListResponse])
async def list_eval_runs(
    expert_config_code: Optional[str] = Query(None, description="expert_config_code"),
    test_set_code: Optional[str] = Query(None, description="测试集编码"),
    status_: Optional[str] = Query(None, alias="status", description="状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[EvalRunListResponse]:
    service = ExpertEvalService(db)
    total, items = await service.list_runs(
        expert_config_code=expert_config_code,
        test_set_code=test_set_code,
        status=status_,
        page=page,
        page_size=page_size,
    )

    def _fmt_dt(dt) -> Optional[str]:
        if not dt:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _get_test_set_code(run) -> Optional[str]:
        if run.select_params and isinstance(run.select_params, dict):
            return run.select_params.get("test_set_code")
        return None

    return ResponseData(
        data=EvalRunListResponse(
            items=[
                EvalRunItem(
                    id=x.id,
                    run_code=x.run_code,
                    expert_config_code=x.expert_config_code,
                    test_set_code=_get_test_set_code(x),
                    status=x.status,  # type: ignore[arg-type]
                    total_count=x.total_count,
                    success_count=x.success_count,
                    failed_count=x.failed_count,
                    start_time=_fmt_dt(x.start_time),
                    end_time=_fmt_dt(x.end_time),
                    created_by=x.created_by,
                )
                for x in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/results", response_model=ResponseData[EvalResultListResponse])
async def list_eval_results(
    run_id: int = Query(..., description="run_id"),
    success: Optional[bool] = Query(None, description="是否成功"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[EvalResultListResponse]:
    service = ExpertEvalService(db)
    total, items = await service.list_results(
        run_id=run_id,
        success=success,
        page=page,
        page_size=page_size,
    )

    def _fmt_dt(dt) -> Optional[str]:
        if not dt:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    return ResponseData(
        data=EvalResultListResponse(
            items=[
                EvalResultItem(
                    id=x.id,
                    run_id=x.run_id,
                    test_case_id=x.test_case_id,
                    score=x.score,
                    reason=x.reason,
                    highlights=x.highlights,
                    problem_tags=x.problem_tags,
                    problem_snippets=x.problem_snippets,
                    success=bool(x.success),
                    error_message=x.error_message,
                    latency_ms=x.latency_ms,
                    model_code=x.model_code,
                    trace_id=x.trace_id,
                    create_time=_fmt_dt(x.create_time),
                )
                for x in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/results/{result_id}", response_model=ResponseData[EvalResultDetailResponse])
async def get_eval_result_detail(
    result_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[EvalResultDetailResponse]:
    service = ExpertEvalService(db)
    result, test_case = await service.get_result_detail(result_id=result_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="结果不存在")

    def _fmt_dt(dt) -> Optional[str]:
        if not dt:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    tc = None
    if test_case:
        tc = EvalResultDetailTestCase(
            id=test_case.id,
            test_set_code=test_case.test_set_code,
            title=test_case.title,
            content=test_case.content,
            image_url=test_case.image_url,
            meta=test_case.meta,
            tags=test_case.tags,
        )

    return ResponseData(
        data=EvalResultDetailResponse(
            id=result.id,
            run_id=result.run_id,
            test_case_id=result.test_case_id,
            score=result.score,
            reason=result.reason,
            highlights=result.highlights,
            problem_tags=result.problem_tags,
            problem_snippets=result.problem_snippets,
            success=bool(result.success),
            error_message=result.error_message,
            latency_ms=result.latency_ms,
            model_code=result.model_code,
            provider_code=result.provider_code,
            token_usage=result.token_usage,
            trace_id=result.trace_id,
            rendered_prompt=result.rendered_prompt,
            raw_output=result.raw_output,
            create_time=_fmt_dt(result.create_time),
            test_case=tc,
        )
    )
