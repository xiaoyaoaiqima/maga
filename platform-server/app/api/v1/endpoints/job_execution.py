"""
Job Execution Tracking API endpoints
用于追踪 Job 执行情况的 API
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.job import Job
from app.models.sub_job import SubJob
from app.models.content import Content
from app.models.expert_business_result import ExpertBusinessResult
from app.models.expert_config import ExpertConfig
from app.schemas.base import ResponseData, ResponseModel
from app.schemas.job_execution import (
    JobExecutionStats,
    JobExecutionDetail,
    SubJobDetail,
    ContentDetail,
    ExpertBusinessResultDetail,
)

router = APIRouter()


@router.get("/stats", response_model=ResponseModel, summary="获取所有 Job 执行统计")
async def get_all_job_execution_stats(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """
    获取所有 Job 的执行统计信息（批量优化版本）
    """
    # 获取总数
    total_result = await db.execute(
        select(func.count(Job.id)).where(Job.is_deleted == 0)
    )
    total = total_result.scalar() or 0
    
    # 计算 offset
    skip = (page - 1) * page_size
    
    # 获取所有 Job
    jobs_result = await db.execute(
        select(Job)
        .where(Job.is_deleted == 0)
        .order_by(Job.create_time.desc())
        .offset(skip)
        .limit(page_size)
    )
    jobs = jobs_result.scalars().all()
    
    if not jobs:
        return ResponseModel(
            code=200,
            message="success",
            data={"total": total, "items": []}
        )
    
    job_ids = [job.job_id for job in jobs]
    job_map = {job.job_id: job for job in jobs}
    
    # 批量查询 SubJob 统计
    sub_job_stats_result = await db.execute(
        select(
            SubJob.job_id,
            SubJob.status,
            func.count(SubJob.id).label("count")
        )
        .where(SubJob.job_id.in_(job_ids), SubJob.is_deleted == 0)
        .group_by(SubJob.job_id, SubJob.status)
    )
    sub_job_stats_map: dict[str, dict[str, int]] = {}
    for row in sub_job_stats_result:
        if row.job_id not in sub_job_stats_map:
            sub_job_stats_map[row.job_id] = {}
        sub_job_stats_map[row.job_id][row.status] = row.count
    
    # 批量查询 Content 统计
    content_stats_result = await db.execute(
        select(
            Content.job_id,
            Content.is_valid,
            Content.is_test_case,
            func.count(Content.id).label("count")
        )
        .where(Content.job_id.in_(job_ids), Content.is_deleted == 0)
        .group_by(Content.job_id, Content.is_valid, Content.is_test_case)
    )
    content_stats_map: dict[str, list[tuple]] = {}
    for row in content_stats_result:
        if row.job_id not in content_stats_map:
            content_stats_map[row.job_id] = []
        content_stats_map[row.job_id].append((row.is_valid, row.is_test_case, row.count))
    
    # 批量查询时间范围
    time_range_result = await db.execute(
        select(
            SubJob.job_id,
            func.min(SubJob.create_time).label("first_time"),
            func.max(SubJob.create_time).label("last_time")
        )
        .where(SubJob.job_id.in_(job_ids), SubJob.is_deleted == 0)
        .group_by(SubJob.job_id)
    )
    time_range_map = {row.job_id: (row.first_time, row.last_time) for row in time_range_result}
    
    # 组装结果
    stats_list = []
    for job_id in job_ids:
        job = job_map[job_id]
        sub_job_counts = sub_job_stats_map.get(job_id, {})
        content_rows = content_stats_map.get(job_id, [])
        time_range = time_range_map.get(job_id, (None, None))
        
        total_sub_jobs = sum(sub_job_counts.values())
        running_sub_jobs = sub_job_counts.get("RUNNING", 0)
        completed_sub_jobs = sub_job_counts.get("COMPLETED", 0)
        failed_sub_jobs = sub_job_counts.get("FAILED", 0)
        
        total_contents = 0
        valid_contents = 0
        invalid_contents = 0
        pending_contents = 0
        test_contents = 0
        
        for is_valid, is_test_case, count in content_rows:
            total_contents += count
            if is_test_case == 1:
                test_contents += count
            if is_test_case == 0:
                if is_valid == 1:
                    valid_contents += count
                elif is_valid == 0:
                    invalid_contents += count
                else:
                    pending_contents += count
        
        target = job.article_count or 0
        progress = (valid_contents / target * 100) if target > 0 else 0
        
        stats_list.append(JobExecutionStats(
            job_id=job_id,
            job_name=job.job_name,
            status=job.status,
            total_sub_jobs=total_sub_jobs,
            running_sub_jobs=running_sub_jobs,
            completed_sub_jobs=completed_sub_jobs,
            failed_sub_jobs=failed_sub_jobs,
            total_contents=total_contents,
            valid_contents=valid_contents,
            invalid_contents=invalid_contents,
            pending_contents=pending_contents,
            test_contents=test_contents,
            target_article_count=target,
            progress_percentage=round(progress, 2),
            first_sub_job_time=time_range[0],
            last_sub_job_time=time_range[1],
        ))
    
    return ResponseModel(
        code=200,
        message="success",
        data={"total": total, "items": [s.model_dump() for s in stats_list]}
    )


@router.get("/{job_id}/stats", response_model=ResponseData[JobExecutionStats])
async def get_job_execution_stats(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[JobExecutionStats]:
    """
    获取指定 Job 的执行统计信息
    """
    # 获取 Job
    job_result = await db.execute(
        select(Job).where(Job.job_id == job_id, Job.is_deleted == 0)
    )
    job = job_result.scalar_one_or_none()
    
    stats = await _build_job_stats(db, job)
    return ResponseData(data=stats)


@router.get("/{job_id}/detail", response_model=ResponseData[JobExecutionDetail])
async def get_job_execution_detail(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    include_test: bool = Query(False, description="是否包含测试数据"),
) -> ResponseData[JobExecutionDetail]:
    """
    获取指定 Job 的执行详情（包含 sub_job 和 content 列表）
    """
    # 获取 Job
    job_result = await db.execute(
        select(Job).where(Job.job_id == job_id, Job.is_deleted == 0)
    )
    job = job_result.scalar_one_or_none()
    
    # 获取统计信息
    stats = await _build_job_stats(db, job)
    
    # 获取 SubJob 列表
    sub_jobs_query = (
        select(SubJob)
        .where(SubJob.job_id == job_id, SubJob.is_deleted == 0)
        .order_by(SubJob.create_time.desc())
    )
    sub_jobs_result = await db.execute(sub_jobs_query)
    sub_jobs = sub_jobs_result.scalars().all()
    
    # 获取所有 Content 用于关联（不过滤测试数据）
    all_contents_result = await db.execute(
        select(Content).where(Content.job_id == job_id, Content.is_deleted == 0)
    )
    all_contents = all_contents_result.scalars().all()
    
    # 构建 content_id -> content 映射（用于 SubJob 关联）
    content_map = {c.content_id: c for c in all_contents}
    
    # 获取 Content 列表（可能过滤测试数据）
    if not include_test:
        contents = [c for c in all_contents if c.is_test_case == 0]
    else:
        contents = all_contents
    # 按创建时间倒序排序（None 排在最后）
    from datetime import datetime as dt
    contents = sorted(contents, key=lambda x: x.create_time or dt.min, reverse=True)
    
    # 构建 SubJobDetail 列表
    sub_job_details = []
    for sj in sub_jobs:
        content = content_map.get(sj.content_id)
        sub_job_details.append(SubJobDetail(
            id=sj.id,
            job_id=sj.job_id,
            sub_job_id=sj.sub_job_id,
            content_id=sj.content_id,
            expert_list=sj.expert_list or [],
            expert_complete_list=sj.expert_complete_list,
            status=sj.status,
            error_message=sj.error_message,
            create_time=sj.create_time,
            update_time=sj.update_time,
            plan_index=sj.plan_index,
            content_title=content.title if content else None,
            content_is_valid=content.is_valid if content else None,
            content_is_test=content.is_test_case if content else None,
        ))
    
    # 构建 sub_job_id -> sub_job 映射
    sub_job_map = {sj.sub_job_id: sj for sj in sub_jobs}
    
    # 构建 ContentDetail 列表
    content_details = []
    for c in contents:
        sub_job = sub_job_map.get(c.sub_job_id)
        content_details.append(ContentDetail(
            id=c.id,
            job_id=c.job_id,
            sub_job_id=c.sub_job_id,
            content_id=c.content_id,
            prompt=c.prompt,
            context_list=c.context_list,
            title=c.title,
            content=c.content,
            is_valid=c.is_valid,
            is_test_case=c.is_test_case,
            online_status=c.online_status,
            create_time=c.create_time,
            update_time=c.update_time,
            sub_job_status=sub_job.status if sub_job else None,
        ))
    
    return ResponseData(data=JobExecutionDetail(
        stats=stats,
        sub_jobs=sub_job_details,
        contents=content_details,
    ))


@router.get("/{job_id}/sub-jobs", response_model=ResponseData[List[SubJobDetail]])
async def get_job_sub_jobs(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, description="按状态筛选"),
    is_valid: Optional[int] = Query(None, description="按文章有效性筛选 (0/1)"),
    is_test_case: Optional[int] = Query(None, description="按测试用例筛选 (0/1)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> ResponseData[List[SubJobDetail]]:
    """
    获取指定 Job 的 SubJob 列表
    """
    # 如果需要按 content 属性筛选，使用 join 查询
    if is_valid is not None or is_test_case is not None:
        query = (
            select(SubJob)
            .join(Content, SubJob.content_id == Content.content_id)
            .where(SubJob.job_id == job_id, SubJob.is_deleted == 0)
        )
        if status:
            query = query.where(SubJob.status == status)
        if is_valid is not None:
            if is_valid == 2:
                query = query.where(Content.is_valid.is_(None))
            else:
                query = query.where(Content.is_valid == is_valid)
        if is_test_case is not None:
            query = query.where(Content.is_test_case == is_test_case)
    else:
        query = (
            select(SubJob)
            .where(SubJob.job_id == job_id, SubJob.is_deleted == 0)
        )
        if status:
            query = query.where(SubJob.status == status)
    
    query = query.order_by(SubJob.create_time.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    sub_jobs = result.scalars().all()
    
    # 获取关联的 content
    content_ids = [sj.content_id for sj in sub_jobs]
    if content_ids:
        contents_result = await db.execute(
            select(Content).where(Content.content_id.in_(content_ids))
        )
        content_map = {c.content_id: c for c in contents_result.scalars().all()}
    else:
        content_map = {}
    
    # 构建响应
    details = []
    for sj in sub_jobs:
        content = content_map.get(sj.content_id)
        details.append(SubJobDetail(
            id=sj.id,
            job_id=sj.job_id,
            sub_job_id=sj.sub_job_id,
            content_id=sj.content_id,
            expert_list=sj.expert_list or [],
            expert_complete_list=sj.expert_complete_list,
            status=sj.status,
            error_message=sj.error_message,
            create_time=sj.create_time,
            update_time=sj.update_time,
            plan_index=sj.plan_index,
            content_title=content.title if content else None,
            content_is_valid=content.is_valid if content else None,
            content_is_test=content.is_test_case if content else None,
        ))
    
    return ResponseData(data=details)


@router.get("/{job_id}/contents", response_model=ResponseData[List[ContentDetail]])
async def get_job_contents(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    is_valid: Optional[int] = Query(None, description="按有效性筛选 (0/1)"),
    is_test_case: Optional[int] = Query(None, description="按测试用例筛选 (0/1)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> ResponseData[List[ContentDetail]]:
    """
    获取指定 Job 的 Content 列表
    """
    query = (
        select(Content)
        .where(Content.job_id == job_id, Content.is_deleted == 0)
    )
    if is_valid is not None:
        if is_valid == 2:
            query = query.where(Content.is_valid.is_(None))
        else:
            query = query.where(Content.is_valid == is_valid)
    if is_test_case is not None:
        query = query.where(Content.is_test_case == is_test_case)
    query = query.order_by(Content.create_time.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    contents = result.scalars().all()
    
    # 获取关联的 sub_job
    sub_job_ids = list(set(c.sub_job_id for c in contents))
    if sub_job_ids:
        sub_jobs_result = await db.execute(
            select(SubJob).where(SubJob.sub_job_id.in_(sub_job_ids))
        )
        sub_job_map = {sj.sub_job_id: sj for sj in sub_jobs_result.scalars().all()}
    else:
        sub_job_map = {}
    
    # 构建响应
    details = []
    for c in contents:
        sub_job = sub_job_map.get(c.sub_job_id)
        details.append(ContentDetail(
            id=c.id,
            job_id=c.job_id,
            sub_job_id=c.sub_job_id,
            content_id=c.content_id,
            prompt=c.prompt,
            context_list=c.context_list,
            title=c.title,
            content=c.content,
            is_valid=c.is_valid,
            is_test_case=c.is_test_case,
            online_status=c.online_status,
            create_time=c.create_time,
            update_time=c.update_time,
            sub_job_status=sub_job.status if sub_job else None,
        ))
    
    return ResponseData(data=details)


@router.get("/{job_id}/business-results", response_model=ResponseData[List[ExpertBusinessResultDetail]])
async def get_job_business_results(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    expert_config_code: Optional[str] = Query(None, description="按 expert_config_code 筛选"),
    content_id: Optional[str] = Query(None, description="按 content_id 筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> ResponseData[List[ExpertBusinessResultDetail]]:
    """
    获取指定 Job 的 Expert 业务结果列表
    """
    query = (
        select(ExpertBusinessResult)
        .where(ExpertBusinessResult.job_id == job_id, ExpertBusinessResult.is_deleted == 0)
    )
    if expert_config_code:
        query = query.where(ExpertBusinessResult.expert_config_code == expert_config_code)
    if content_id:
        query = query.where(ExpertBusinessResult.content_id == content_id)
    # 按时间升序排序，显示 Expert 执行顺序（最早的在前面）
    query = query.order_by(ExpertBusinessResult.create_time.asc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    results = result.scalars().all()
    
    # 获取所有 expert_config_code 对应的 expert_func 和 expert_type
    config_codes = list(set(r.expert_config_code for r in results))
    expert_config_map: dict[str, tuple[str | None, str | None]] = {}
    if config_codes:
        config_result = await db.execute(
            select(ExpertConfig.expert_config_code, ExpertConfig.expert_func, ExpertConfig.expert_type)
            .where(ExpertConfig.expert_config_code.in_(config_codes))
        )
        for row in config_result:
            expert_config_map[row.expert_config_code] = (row.expert_func, row.expert_type)
    
    details = [
        ExpertBusinessResultDetail(
            id=r.id,
            job_id=r.job_id,
            sub_job_id=r.sub_job_id,
            content_id=r.content_id,
            expert_task_id=r.expert_task_id,
            expert_config_code=r.expert_config_code,
            expert_config_name=r.expert_config_name,
            expert_func=expert_config_map.get(r.expert_config_code, (None, None))[0],
            expert_type=expert_config_map.get(r.expert_config_code, (None, None))[1],
            model_code=r.model_code,
            business_type=r.business_type,
            plugin_config_snapshot=r.plugin_config_snapshot,
            prompt=r.prompt,
            business_result=r.business_result,
            status=r.status,
            error_message=r.error_message,
            create_time=r.create_time,
        )
        for r in results
    ]
    
    return ResponseData(data=details)


async def _build_job_stats(db: AsyncSession, job: Optional[Job]) -> JobExecutionStats:
    """构建 Job 执行统计信息"""
    if not job:
        return JobExecutionStats(
            job_id="",
            total_sub_jobs=0,
            total_contents=0,
            valid_contents=0,
            invalid_contents=0,
        )
    
    job_id = job.job_id
    
    # 统计 SubJob
    sub_job_stats = await db.execute(
        select(
            SubJob.status,
            func.count(SubJob.id).label("count")
        )
        .where(SubJob.job_id == job_id, SubJob.is_deleted == 0)
        .group_by(SubJob.status)
    )
    sub_job_counts = {row.status: row.count for row in sub_job_stats}
    
    total_sub_jobs = sum(sub_job_counts.values())
    running_sub_jobs = sub_job_counts.get("RUNNING", 0)
    completed_sub_jobs = sub_job_counts.get("COMPLETED", 0)
    failed_sub_jobs = sub_job_counts.get("FAILED", 0)
    
    # 统计 Content
    content_stats = await db.execute(
        select(
            Content.is_valid,
            Content.is_test_case,
            func.count(Content.id).label("count")
        )
        .where(Content.job_id == job_id, Content.is_deleted == 0)
        .group_by(Content.is_valid, Content.is_test_case)
    )
    
    total_contents = 0
    valid_contents = 0
    invalid_contents = 0
    pending_contents = 0
    test_contents = 0
    
    for row in content_stats:
        total_contents += row.count
        if row.is_test_case == 1:
            test_contents += row.count
        
        # 统计非测试文章的有效性
        if row.is_test_case == 0:
            if row.is_valid == 1:
                valid_contents += row.count
            elif row.is_valid == 0:
                invalid_contents += row.count
            else:
                # is_valid 为 None
                pending_contents += row.count
    
    # 获取时间范围
    time_range = await db.execute(
        select(
            func.min(SubJob.create_time).label("first_time"),
            func.max(SubJob.create_time).label("last_time")
        )
        .where(SubJob.job_id == job_id, SubJob.is_deleted == 0)
    )
    time_row = time_range.first()
    
    # 计算进度
    target = job.article_count or 0
    progress = (valid_contents / target * 100) if target > 0 else 0
    
    return JobExecutionStats(
        job_id=job_id,
        job_name=job.job_name,
        status=job.status,
        total_sub_jobs=total_sub_jobs,
        running_sub_jobs=running_sub_jobs,
        completed_sub_jobs=completed_sub_jobs,
        failed_sub_jobs=failed_sub_jobs,
        total_contents=total_contents,
        valid_contents=valid_contents,
        invalid_contents=invalid_contents,
        pending_contents=pending_contents,
        test_contents=test_contents,
        target_article_count=target,
        progress_percentage=round(progress, 2),
        first_sub_job_time=time_row.first_time if time_row else None,
        last_sub_job_time=time_row.last_time if time_row else None,
    )
