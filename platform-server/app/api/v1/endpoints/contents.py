"""
Content Endpoints - 内容管理与分发
"""
import csv
import io
import json
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query, UploadFile, File, Form, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, desc, asc, and_, case

from app.core.database import get_db
from app.services.content_service import ContentService
from app.services.content_pool_service import ContentPoolService
from app.models.content import Content
from app.models.agent import Agent
from app.models.critic_score_record import CriticScoreRecord
from app.schemas.content import (
    ContentMatchRequest,
    ContentMatchResponse,
    MatchedContentItem,
    ContentUseRequest,
    ContentUseResponse,
    ContentImportResponse,
    ContentOnlineUpdateRequest,
    ContentBatchOnlineRequest,
    ContentBatchValidUpdateRequest,
    ContentStatsResponse,
    ExpertScoreFilter,
)
from app.schemas.base import ResponseData
from app.schemas.common import PageResult
from app.schemas.job_execution import ContentDetail, ContentCriticSummary, CriticScoreItem
from app.schemas.content_pool import (
    ContentAcquireRequest, ContentAcquireResponse, ContentItem,
    ContentAckRequest, ContentAckResponse, ContentAvailabilityResponse,
    ContentTransferRequest, ContentTransferResponse
)
from app.models.tenant import Tenant

router = APIRouter(prefix="/contents", tags=["contents"])

# 列表接口最大分页限制（防止一次性拉取过多数据导致 OOM）
MAX_PAGE_SIZE = 200
MAX_PAGE_SIZE_EXPERT = 1000


# Placeholder for auth dependency
async def get_current_tenant_by_apikey(
    request: Request,
    # 统一鉴权入口会将 Consumer 的 username 放入 X-Consumer-Username Header
    # 我们假设 Consumer username 就是 tenant_code
    x_consumer_username: str = Header(..., alias="X-Consumer-Username"),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Verify API Key signature and return Tenant.
    这里采用【信任网关模式】：
    1. 外部请求通过统一鉴权入口校验签名
    2. 请求进入平台服务并注入 X-Consumer-Username: tenant_code
    3. Orchestrator 信任该 Header，直接加载 Tenant

    注意：必须确保平台服务只通过统一入口对外暴露，避免绕过签名校验。
    """
    # 查找 Tenant
    stmt = select(Tenant).where(Tenant.tenant_code == x_consumer_username)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    if not tenant:
        # 虽然签名校验通过，但可能是旧的 tenant_code 或者数据不一致
        raise HTTPException(status_code=401, detail="Tenant not found (Identity propagation failed)")

    return tenant


@router.post("/match", response_model=ContentMatchResponse, summary="按 agent_id + user_tags 获取并锁定内容")
async def match_contents(
    request: ContentMatchRequest,
    db: AsyncSession = Depends(get_db),
) -> ContentMatchResponse:
    """
    获取 content（入参：agent_id、user_id、user_tags），并将命中的内容锁定给 user_id。
    返回结构遵循前端/调用方约定：
    {
      "contents": [{"content_id":"","title":"", "content":""}],
      "success": True,
      "message": "成功匹配并锁定X条内容"
    }
    """
    try:
        service = ContentService(db)
        items = await service.match_and_lock_contents(
            agent_id=request.agent_id,
            agent_id_list=request.agent_id_list,
            user_id=request.user_id,
            user_tags=request.user_tags,
            limit=request.count,
            lock_minutes=request.lock_minutes
        )

        contents = [
            MatchedContentItem(
                content_id=item.id,
                title=(item.title or ""),
                content=(item.content or ""),
            )
            for item in items
        ]

        return ContentMatchResponse(
            contents=contents,
            success=True,
            message=f"成功匹配并锁定{len(contents)}条内容",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 content 失败: {str(e)}")


@router.post("/use", response_model=ContentUseResponse, summary="使用内容（标记为已使用）")
async def use_content(
    request: ContentUseRequest,
    db: AsyncSession = Depends(get_db),
) -> ContentUseResponse:
    """
    使用内容（入参：content_id、user_id）。
    出参：
    {
      "content_id": 1,
      "title": 1,
      "content": 1,
      "success": true,
      "message": "成功使用 1 内容"
    }
    """
    try:
        service = ContentService(db)
        ok, title, content = await service.use_content(content_id=request.content_id, user_id=request.user_id)
        if not ok:
            return ContentUseResponse(
                content_id=request.content_id,
                title=title,
                content=content,
                success=False,
                message=f"使用失败：内容不存在或未被该用户锁定",
            )
        return ContentUseResponse(
            content_id=request.content_id,
            title=title,
            content=content,
            success=True,
            message=f"成功使用 {request.content_id} 内容",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"使用 content 失败: {str(e)}")


@router.post("/acquire", response_model=ResponseData[ContentAcquireResponse], summary="内容池-获取库存")
async def acquire_content(
    request: ContentAcquireRequest,
    tenant: Tenant = Depends(get_current_tenant_by_apikey),
    db: AsyncSession = Depends(get_db)
):
    """
    获取内容
    """
    try:
        service = ContentPoolService(db)
        contents = await service.acquire_contents(tenant.id, request)

        return ResponseData(
            code=0,
            msg="success" if contents else "partial success", # Or inventory shortage
            data=ContentAcquireResponse(
                acquired_count=len(contents),
                contents=[ContentItem.model_validate(c) for c in contents]
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Acquire failed: {str(e)}")


@router.post("/ack", response_model=ResponseData[ContentAckResponse], summary="内容池-确认消费")
async def ack_content(
    request: ContentAckRequest,
    tenant: Tenant = Depends(get_current_tenant_by_apikey),
    db: AsyncSession = Depends(get_db)
):
    """
    确认消费
    """
    try:
        service = ContentPoolService(db)
        count = await service.ack_contents(tenant.id, request.content_ids)

        return ResponseData(
            code=0,
            msg="success",
            data=ContentAckResponse(success_count=count)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ack failed: {str(e)}")


@router.get("/availability", response_model=ResponseData[ContentAvailabilityResponse], summary="内容池-库存查询")
async def check_availability(
    activity_code: str,
    agent_code: Optional[str] = None,
    min_score: int = 60,
    tenant: Tenant = Depends(get_current_tenant_by_apikey),
    db: AsyncSession = Depends(get_db)
):
    """
    库存查询
    """
    try:
        service = ContentPoolService(db)
        count = await service.check_availability(
            tenant.id,
            activity_code,
            agent_code,
            min_score
        )

        return ResponseData(
            code=0,
            data=ContentAvailabilityResponse(available_count=count)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Check availability failed: {str(e)}")


@router.get("/context-stats", response_model=ResponseData, summary="获取 Context 变量分布统计")
async def get_context_stats(
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    activity_id: Optional[int] = Query(None, description="活动ID"),
    job_id: Optional[str] = Query(None, description="任务ID"),
    agent_code: Optional[str] = Query(None, description="Agent编码"),
    is_valid: Optional[int] = Query(None, description="是否有效"),
    is_test_case: Optional[int] = Query(None, description="是否测试用例"),
    variable_name: Optional[str] = Query(None, description="要统计的变量名"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取 Context 变量分布统计
    - 不传 variable_name 时，返回所有可用的变量名列表
    - 传入 variable_name 时，返回该变量值的分布统计

    性能优化：
    1. 使用数据库聚合 COUNT，避免加载大量数据到内存
    2. 只查询必要的字段，减少网络传输
    3. 建议配合使用 tenant_id、agent_code 等筛选条件减少数据量
    """
    try:
        # 优化：先统计符合条件的记录总数
        count_query = select(func.count(Content.id)).where(Content.is_deleted == 0)

        if tenant_id:
            count_query = count_query.where(Content.tenant_id == tenant_id)
        if activity_id:
            count_query = count_query.where(Content.activity_id == activity_id)
        if job_id:
            count_query = count_query.where(Content.job_id == job_id)
        if agent_code:
            count_query = count_query.where(Content.agent_code == agent_code)
        if is_valid is not None:
            count_query = count_query.where(Content.is_valid == is_valid)
        if is_test_case is not None:
            count_query = count_query.where(Content.is_test_case == is_test_case)
        count_query = count_query.where(Content.context_list.isnot(None))

        total_count = (await db.execute(count_query)).scalar() or 0

        # 如果没有数据，直接返回
        if total_count == 0:
            return ResponseData(
                data={
                    "keys": [],
                    "distribution": [],
                    "sample_count": 0,
                    "max_limit": None
                }
            )

        # 优化：限制采样数量，只统计部分数据
        MAX_SAMPLE_SIZE = 5000  # 降低采样上限到 5000

        # 如果数据量超过采样上限，使用采样
        if total_count > MAX_SAMPLE_SIZE:
            # 使用表采样（TABLESAMPLE SYSTEM）或随机采样
            query = select(Content.context_list).where(Content.is_deleted == 0)

            if tenant_id:
                query = query.where(Content.tenant_id == tenant_id)
            if activity_id:
                query = query.where(Content.activity_id == activity_id)
            if job_id:
                query = query.where(Content.job_id == job_id)
            if agent_code:
                query = query.where(Content.agent_code == agent_code)
            if is_valid is not None:
                query = query.where(Content.is_valid == is_valid)
            if is_test_case is not None:
                query = query.where(Content.is_test_case == is_test_case)
            query = query.where(Content.context_list.isnot(None))

            # 随机采样：使用 ORDER BY RANDOM() LIMIT
            # 注意：SQLite 使用 RANDOM()，MySQL 使用 RAND()
            query = query.order_by(func.random()).limit(MAX_SAMPLE_SIZE)

            result = await db.execute(query)
            context_lists = result.scalars().all()
        else:
            # 数据量不大，直接查询全部
            query = select(Content.context_list).where(Content.is_deleted == 0)

            if tenant_id:
                query = query.where(Content.tenant_id == tenant_id)
            if activity_id:
                query = query.where(Content.activity_id == activity_id)
            if job_id:
                query = query.where(Content.job_id == job_id)
            if agent_code:
                query = query.where(Content.agent_code == agent_code)
            if is_valid is not None:
                query = query.where(Content.is_valid == is_valid)
            if is_test_case is not None:
                query = query.where(Content.is_test_case == is_test_case)
            query = query.where(Content.context_list.isnot(None))

            result = await db.execute(query)
            context_lists = result.scalars().all()

        sample_count = len(context_lists)

        # 收集所有变量名
        all_keys = set()
        for ctx in context_lists:
            if isinstance(ctx, dict):
                all_keys.update(ctx.keys())

        if not variable_name:
            # 返回所有可用的变量名
            return ResponseData(
                data={
                    "keys": sorted(list(all_keys)),
                    "distribution": [],
                    "sample_count": sample_count,
                    "total_count": total_count,
                    "is_sampled": total_count > MAX_SAMPLE_SIZE
                }
            )

        # 统计指定变量的值分布
        value_counts: dict = {}
        for ctx in context_lists:
            if isinstance(ctx, dict) and variable_name in ctx:
                value = ctx.get(variable_name)
                value_str = str(value).strip() if value else "(空)"
                value_counts[value_str] = value_counts.get(value_str, 0) + 1

        # 排序后返回
        distribution = [
            {"name": k, "value": v}
            for k, v in sorted(value_counts.items(), key=lambda x: -x[1])
        ]

        return ResponseData(
            data={
                "keys": sorted(list(all_keys)),
                "distribution": distribution,
                "sample_count": sample_count,
                "total_count": total_count,
                "is_sampled": total_count > MAX_SAMPLE_SIZE
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 Context 统计失败: {str(e)}")


@router.get("/stats", response_model=ResponseData[ContentStatsResponse], summary="获取文章统计数据")
async def get_content_stats(
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    activity_id: Optional[int] = Query(None, description="活动ID"),
    job_id: Optional[str] = Query(None, description="任务ID"),
    agent_code: Optional[str] = Query(None, description="Agent编码"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取文章统计数据
    
    使用数据库聚合查询直接返回统计数据，避免加载大量数据到内存。
    性能优化：使用 COUNT 和条件聚合，只查询必要的统计信息。
    """
    try:
        from datetime import datetime
        
        # 构建基础筛选条件
        conditions = [Content.is_deleted == 0]
        
        if tenant_id:
            conditions.append(Content.tenant_id == tenant_id)
        if activity_id:
            conditions.append(Content.activity_id == activity_id)
        if job_id:
            conditions.append(Content.job_id == job_id)
        if agent_code:
            conditions.append(Content.agent_code == agent_code)
        
        # 文章总数
        total_query = select(func.count(Content.id)).where(*conditions)
        total = (await db.execute(total_query)).scalar() or 0
        
        # 有效文章数 (is_valid = 1)
        valid_conditions = conditions + [Content.is_valid == 1]
        valid_query = select(func.count(Content.id)).where(*valid_conditions)
        valid = (await db.execute(valid_query)).scalar() or 0
        
        # 无效文章数 (is_valid = 0)
        invalid_conditions = conditions + [Content.is_valid == 0]
        invalid_query = select(func.count(Content.id)).where(*invalid_conditions)
        invalid = (await db.execute(invalid_query)).scalar() or 0
        
        # 待定文章数 (is_valid is null)
        pending_conditions = conditions + [Content.is_valid.is_(None)]
        pending_query = select(func.count(Content.id)).where(*pending_conditions)
        pending = (await db.execute(pending_query)).scalar() or 0
        
        # 测试文章数 (is_test_case = 1)
        test_conditions = conditions + [Content.is_test_case == 1]
        test_query = select(func.count(Content.id)).where(*test_conditions)
        test = (await db.execute(test_query)).scalar() or 0
        
        # 正式有效文章数 (is_valid = 1 and is_test_case = 0)
        formal_valid_conditions = conditions + [
            Content.is_valid == 1,
            Content.is_test_case == 0
        ]
        formal_valid_query = select(func.count(Content.id)).where(*formal_valid_conditions)
        formal_valid = (await db.execute(formal_valid_query)).scalar() or 0
        
        # 上线文章数 (online_status = 'ONLINE' and is_valid = 1 and is_test_case = 0)
        online_conditions = conditions + [
            Content.online_status == 'ONLINE',
            Content.is_valid == 1,
            Content.is_test_case == 0
        ]
        online_query = select(func.count(Content.id)).where(*online_conditions)
        online = (await db.execute(online_query)).scalar() or 0
        
        # 锁定文章数 (is_locked = 1 and (lock_expire_time > now() or is_used = 1))
        now = datetime.now()
        locked_conditions = conditions + [
            Content.is_locked == 1,
            or_(
                Content.lock_expire_time > now,
                Content.is_used == 1
            )
        ]
        locked_query = select(func.count(Content.id)).where(*locked_conditions)
        locked = (await db.execute(locked_query)).scalar() or 0
        
        # 被使用文章数 (is_used = 1)
        used_conditions = conditions + [Content.is_used == 1]
        used_query = select(func.count(Content.id)).where(*used_conditions)
        used = (await db.execute(used_query)).scalar() or 0
        
        # 计算衍生统计
        unlocked = max(0, online - locked)  # 未被锁定文章数
        unused = max(0, online - used)  # 未被使用文章数
        
        stats = ContentStatsResponse(
            total=total,
            valid=valid,
            invalid=invalid,
            pending=pending,
            test=test,
            formal_valid=formal_valid,
            online=online,
            locked=locked,
            unlocked=unlocked,
            used=used,
            unused=unused
        )
        
        return ResponseData(data=stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文章统计失败: {str(e)}")


@router.post("/import", response_model=ResponseData[ContentImportResponse], summary="CSV 导入文章")
async def import_contents(
    file: UploadFile = File(..., description="CSV 文件"),
    tenant_id: int = Form(..., description="租户ID"),
    agent_code: str = Form(..., description="Agent 编码"),
    is_test_case: int = Form(0, description="是否测试用例（0=业务，1=测试）"),
    db: AsyncSession = Depends(get_db)
):
    """
    从 CSV 文件导入文章内容到 content 表
    
    CSV 文件格式要求：
    - 必须列：content（正文内容）
    - 可选列：title（标题）、context_list（JSON 格式的上下文变量）
    
    导入规则：
    - job_id 和 sub_job_id 自动设置为 import_from_{filename}
    - content_id 自动生成 UUID
    - 默认 is_valid = 1（有效）
    """
    try:
        # 读取并解析 CSV 文件
        content_bytes = await file.read()
        
        # 尝试多种编码（优先 utf-8-sig 处理 BOM）
        csv_content = None
        for encoding in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']:
            try:
                csv_content = content_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if csv_content is None:
            raise HTTPException(status_code=400, detail="无法解析 CSV 文件编码，请使用 UTF-8 或 GBK 编码")
        
        # 解析 CSV
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        # 检查必须列（处理可能的空格和特殊字符）
        fieldnames = csv_reader.fieldnames or []
        # 清理列名（去除空格和 BOM 字符），并建立映射
        fieldname_map = {}
        for f in fieldnames:
            cleaned = f.strip().replace('\ufeff', '')
            fieldname_map[cleaned] = f  # 记录原始列名
        
        if 'content' not in fieldname_map:
            raise HTTPException(status_code=400, detail="CSV 文件缺少必须列：content")
        
        # 生成 job_id（模仿真实格式：job-{uuid16}）
        job_id = f"job-{uuid.uuid4().hex[:16]}"
        # sub_job_id 格式：gen-{uuid16}
        sub_job_id_prefix = f"gen-{uuid.uuid4().hex[:10]}"
        
        success_count = 0
        failed_count = 0
        errors: List[str] = []
        
        # 辅助函数：根据清理后的列名获取值
        def get_value(row: dict, key: str) -> str:
            """根据清理后的列名获取对应的原始列值"""
            original_key = fieldname_map.get(key)
            if original_key and original_key in row:
                return row[original_key]
            return ''
        
        for row_num, row in enumerate(csv_reader, start=2):  # 从第2行开始（第1行是表头）
            try:
                # 获取内容（使用映射获取原始列名）
                content_text = get_value(row, 'content').strip()
                if not content_text:
                    errors.append(f"第 {row_num} 行：content 为空，跳过")
                    failed_count += 1
                    continue
                
                # 获取标题
                title = get_value(row, 'title').strip() or None
                
                # 解析 context_list（JSON 格式，或自动封装）
                context_list = None
                context_list_str = get_value(row, 'context_list').strip()
                if context_list_str:
                    try:
                        context_list = json.loads(context_list_str)
                    except json.JSONDecodeError:
                        # 如果不是 JSON 格式，按下划线分割并封装成固定格式
                        # 格式：scene_persona -> {"scene": "xxx", "persona": "xxx"}
                        parts = context_list_str.split('_', 1)  # 最多分割一次
                        if len(parts) == 2:
                            context_list = {
                                "scene": parts[0].strip(),
                                "persona": parts[1].strip()
                            }
                        elif len(parts) == 1 and parts[0]:
                            # 只有一个部分，作为 scene
                            context_list = {
                                "scene": parts[0].strip(),
                                "persona": ""
                            }
                        # 如果分割后为空，context_list 保持 None
                
                # 生成唯一的 sub_job_id 和 content_id
                sub_job_id = f"{sub_job_id_prefix}{uuid.uuid4().hex[:6]}"
                content_id = f"icontent_{uuid.uuid4().hex[:8]}"
                
                # 创建 Content 记录（使用 func.now() 让数据库生成时间）
                new_content = Content(
                    job_id=job_id,
                    sub_job_id=sub_job_id,
                    content_id=content_id,
                    tenant_id=tenant_id,
                    agent_code=agent_code,
                    title=title,
                    content=content_text,
                    context_list=context_list,
                    is_valid=1,  # 导入的内容默认有效
                    is_test_case=is_test_case,
                    distribution_status="AVAILABLE",  # 直接上架
                    create_time=func.now(),
                    update_time=func.now(),
                )
                
                db.add(new_content)
                success_count += 1
                
            except Exception as e:
                errors.append(f"第 {row_num} 行：处理失败 - {str(e)}")
                failed_count += 1
        
        # 提交事务
        await db.commit()
        
        return ResponseData(
            data=ContentImportResponse(
                success_count=success_count,
                failed_count=failed_count,
                job_id=job_id,
                errors=errors if errors else None
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.get("", response_model=ResponseData[PageResult[ContentDetail]], summary="获取文章列表")
async def list_contents(
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    activity_id: Optional[int] = Query(None, description="活动ID"),
    job_id: Optional[str] = Query(None, description="任务ID"),
    agent_code: Optional[str] = Query(None, description="Agent编码"),
    expert_config_code: Optional[str] = Query(None, description="专家配置编码（按专家筛选文章）"),
    is_valid: Optional[int] = Query(None, description="是否有效"),
    is_test_case: Optional[int] = Query(None, description="是否测试用例（0=业务，1=测试）"),
    online_status: Optional[str] = Query(None, description="上线状态（ONLINE/OFFLINE）"),
    keyword: Optional[str] = Query(None, description="关键词筛选（标题/内容）"),
    score_status: Optional[str] = Query(
        None,
        description="评分通过状态筛选：all_passed=全部通过, has_ban=存在违规, partial=部分通过, no_score=未评分"
    ),
    avg_score_min: Optional[int] = Query(None, ge=0, le=100, description="平均分最小值"),
    avg_score_max: Optional[int] = Query(None, ge=0, le=100, description="平均分最大值"),
    expert_score_filters: Optional[str] = Query(None, description="细化专家评分筛选（JSON 字符串）"),
    content_length_min: Optional[int] = Query(None, ge=0, description="正文字数最小值（去除空格换行后）"),
    content_length_max: Optional[int] = Query(None, ge=0, description="正文字数最大值（去除空格换行后）"),
    create_time_start: Optional[str] = Query(None, description="创建时间开始（ISO 8601格式，如：2024-01-01T00:00:00）"),
    create_time_end: Optional[str] = Query(None, description="创建时间结束（ISO 8601格式，如：2024-12-31T23:59:59）"),
    order_by_create_time: Optional[str] = Query(None, description="创建时间排序（asc=升序，desc=降序，默认降序）"),
    id_min: Optional[int] = Query(None, ge=1, description="ID范围筛选 - 最小ID（大于）"),
    id_max: Optional[int] = Query(None, ge=1, description="ID范围筛选 - 最大ID（小于）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=10000, description="每页数量"),
    offset: Optional[int] = Query(None, ge=0, description="偏移量（优先级高于 page）"),
    limit: Optional[int] = Query(None, ge=1, le=10000, description="返回数量（优先级高于 page_size）"),
    db: AsyncSession = Depends(get_db)
):
    """
    分页查询文章内容列表，包含 Critic 评分汇总

    评分筛选参数：
    - score_status: 评分通过状态（all_passed/has_ban/partial/no_score）
    - avg_score_min/avg_score_max: 平均分范围筛选
    - expert_score_filters: 专家评分细化筛选 [{\"expert_config_code\": \"...\", \"min_score\": 0, \"max_score\": 100}]

    字数筛选参数：
    - content_length_min/content_length_max: 正文字数范围筛选（去除空格换行后）

    分页参数：
    - page/page_size: 标准分页
    - offset/limit: 增量加载分页（推荐，性能更好）
    """
    try:
        # 确定最终使用的 offset 和 limit
        final_limit = limit if limit is not None else page_size
        final_offset = offset if offset is not None else (page - 1) * page_size

        if final_limit > MAX_PAGE_SIZE:
            final_limit = MAX_PAGE_SIZE
        if expert_config_code and final_limit > MAX_PAGE_SIZE_EXPERT:
            final_limit = MAX_PAGE_SIZE_EXPERT

        # 解析专家评分细化筛选
        parsed_expert_filters: Optional[List[ExpertScoreFilter]] = None
        if expert_score_filters:
            try:
                # 尝试解析 JSON 字符串
                filter_data = json.loads(expert_score_filters)
                if isinstance(filter_data, list):
                    parsed_expert_filters = [ExpertScoreFilter(**f) for f in filter_data]
                elif isinstance(filter_data, dict):
                    parsed_expert_filters = [ExpertScoreFilter(**filter_data)]
            except Exception as e:
                # 如果不是标准 JSON，可能是被展开的参数，这里记录日志方便排查
                print(f"Error parsing expert_score_filters JSON: {e}, value: {expert_score_filters}")

        # 方案二：专家筛选直接基于 critic_score_record 表
        # 先找到该专家评分过的所有 content_id，再关联 content 表查询文章
        expert_content_ids_subq = None
        if expert_config_code:
            # 查找该专家评分过的所有 content_id（去重）
            expert_content_ids_query = (
                select(CriticScoreRecord.content_id)
                .where(CriticScoreRecord.expert_config_code == expert_config_code)
                .distinct()
                .subquery()
            )
            expert_content_ids_subq = expert_content_ids_query

            # 如果指定了 agent_code，需要进一步验证交集
            # 如果 agent_code 指定的 Agent 没有配置该专家，直接返回空
            if agent_code:
                # 检查该 Agent 是否配置了该专家
                agent_has_expert = await _check_agent_has_expert_config(
                    db, agent_code, expert_config_code, tenant_id
                )
                if not agent_has_expert:
                    # Agent 没有配置该专家，返回空结果
                    return ResponseData(
                        data=PageResult(
                            items=[],
                            total=0,
                            page=page,
                            page_size=page_size,
                            offset=final_offset,
                            limit=final_limit
                        )
                    )

        # 如果需要评分筛选，使用不同的查询策略
        # 只有在确实解析出有效的专家评分筛选条件时，才触发评分筛选逻辑
        need_score_filter = (
            score_status is not None or 
            avg_score_min is not None or 
            avg_score_max is not None or
            (parsed_expert_filters is not None and len(parsed_expert_filters) > 0)
        )

        if need_score_filter:
            # 使用子查询计算每个 content 的评分汇总
            return await _list_contents_with_score_filter(
                db, tenant_id, activity_id, job_id, agent_code, expert_content_ids_subq, is_valid, is_test_case,
                online_status, keyword, score_status, avg_score_min, avg_score_max,
                parsed_expert_filters, content_length_min, content_length_max, create_time_start, create_time_end, order_by_create_time,
                id_min, id_max,
                page, page_size, offset, limit
            )

        # 无评分筛选时，使用原有的简单查询
        query = select(Content).where(Content.is_deleted == 0)

        if tenant_id:
            query = query.where(Content.tenant_id == tenant_id)
        if activity_id:
            query = query.where(Content.activity_id == activity_id)
        if job_id:
            query = query.where(Content.job_id == job_id)
        if agent_code:
            query = query.where(Content.agent_code == agent_code)

        # 方案二：专家筛选基于 critic_score_record 表的 content_id 子查询
        if expert_content_ids_subq is not None:
            query = query.where(Content.content_id.in_(expert_content_ids_subq))

        if is_valid is not None:
            query = query.where(Content.is_valid == is_valid)
        if is_test_case is not None:
            query = query.where(Content.is_test_case == is_test_case)
        if online_status:
            query = query.where(Content.online_status == online_status)

        if keyword:
            query = query.where(
                or_(
                    Content.title.ilike(f"%{keyword}%"),
                    Content.content.ilike(f"%{keyword}%")
                )
            )

        # ID 范围筛选
        if id_min is not None:
            query = query.where(Content.id > id_min)
        if id_max is not None:
            query = query.where(Content.id < id_max)

        # 时间范围筛选
        if create_time_start:
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(create_time_start.replace('Z', '+00:00'))
                query = query.where(Content.create_time >= start_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"create_time_start 格式错误: {create_time_start}")
        if create_time_end:
            try:
                from datetime import datetime
                end_dt = datetime.fromisoformat(create_time_end.replace('Z', '+00:00'))
                query = query.where(Content.create_time <= end_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"create_time_end 格式错误: {create_time_end}")

        # 字数筛选（去除所有空白字符后的字符数）
        if content_length_min is not None or content_length_max is not None:
            # 使用 SQL 函数计算去除所有空白字符后的字数
            # 与前端 JS 的 /\s/g 保持完全一致
            # JS 的 /\s/g 匹配：\t\n\r\f\v 以及其他 Unicode 空白字符
            # 注意：使用 CHAR_LENGTH 而非 LENGTH，因为 LENGTH 返回字节数，CHAR_LENGTH 返回字符数
            # 这对于多字节字符（如中文）很重要，确保前后端计算方式一致

            # 第一遍：去除 ASCII 空白字符
            content_length_expr = func.replace(
                func.replace(
                    func.replace(
                        func.replace(
                            func.replace(
                                func.replace(Content.content, ' ', ''),  # U+0020 空格
                                '\t', '',                                  # U+0009 制表符
                            ),
                            '\n', '',                                      # U+000A 换行符
                        ),
                        '\r', '',                                          # U+000D 回车符
                    ),
                    '\f', '',                                              # U+000C 换页符
                ),
                '\v', '',                                                  # U+000B 垂直制表符
            )
            # 第二遍：去除常见 Unicode 空白字符（这些字符可能在复制粘贴时进入文本）
            # U+00A0 不间断空格 (No-Break Space, NBSP) - 最常见
            # U+2002-U+2009 各种宽度的空格（从编辑器复制时常见）
            # U+3000 表意文字空格（中文输入常见）
            content_length_expr = func.replace(content_length_expr, '\u00A0', '')  # NBSP
            content_length_expr = func.replace(content_length_expr, '\u2002', '')  # En Space
            content_length_expr = func.replace(content_length_expr, '\u2003', '')  # Em Space
            content_length_expr = func.replace(content_length_expr, '\u2009', '')  # Thin Space
            content_length_expr = func.replace(content_length_expr, '\u3000', '')  # Ideographic Space (全角空格)

            if content_length_min is not None:
                query = query.where(func.char_length(content_length_expr) >= content_length_min)
            if content_length_max is not None:
                query = query.where(func.char_length(content_length_expr) <= content_length_max)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Paging and ordering
        # 添加 id 作为第二排序字段,确保排序稳定性,避免分页时出现重复数据
        if order_by_create_time == 'asc':
            query = query.order_by(asc(Content.create_time), asc(Content.id))
        else:
            # 默认降序
            query = query.order_by(desc(Content.create_time), desc(Content.id))
        query = query.offset(final_offset).limit(final_limit)
        
        result = await db.execute(query)
        items = result.scalars().all()

        # 批量获取 critic_score_record 汇总数据
        content_ids = [item.content_id for item in items]
        critic_summary_map = await _get_critic_summary_map(db, content_ids)

        # 构建返回数据，附带 critic_summary
        content_details = []
        for item in items:
            detail = ContentDetail.model_validate(item)
            detail.critic_summary = critic_summary_map.get(item.content_id)
            content_details.append(detail)

        return ResponseData(
            data=PageResult(
                items=content_details,
                total=total,
                page=page,
                page_size=page_size,
                offset=final_offset,
                limit=final_limit
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询文章列表失败: {str(e)}")


@router.post("/online", response_model=ResponseData, summary="更新单篇文章上线状态")
async def update_content_online_status(
    request: ContentOnlineUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    更新单篇文章上线状态 (ONLINE/OFFLINE)
    
    注意：下线时会检查文章状态
    - 已锁定(is_locked=1)的文章不允许下线
    - 已使用(is_used=1)的文章不允许下线
    """
    try:
        service = ContentService(db)
        result = await service.update_online_status(request.content_id, request.online_status)
        if not result["success"]:
            return ResponseData(code=400, message=result["message"], data={"skipped_reason": result.get("skipped_reason")})
        return ResponseData(code=200, message="成功")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新上线状态失败: {str(e)}")


@router.post("/batch-online", response_model=ResponseData, summary="批量更新文章上线状态")
async def batch_update_content_online_status(
    request: ContentBatchOnlineRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    批量更新文章上线状态 (ONLINE/OFFLINE)

    支持两种模式：
    1. 按任务ID批量更新：更新该任务下所有有效且非测试的文章
    2. 按文章ID列表批量更新：更新指定的文章列表

    注意：下线时会检查文章状态
    - 已锁定(is_locked=1)的文章会被跳过
    - 已使用(is_used=1)的文章会被跳过

    返回数据包含：
    - updated_count: 成功更新的数量
    - skipped_locked: 因锁定跳过的数量
    - skipped_used: 因已使用跳过的数量
    - total: 符合条件的文章总数
    """
    try:
        service = ContentService(db)
        result = await service.batch_update_online_status(
            job_id=request.job_id,
            online_status=request.online_status,
            content_ids=request.content_ids,
        )

        # 构建消息
        msg_parts = [f"成功更新 {result['updated_count']} 条记录"]
        if result['skipped_locked'] > 0:
            msg_parts.append(f"跳过 {result['skipped_locked']} 条已锁定")
        if result['skipped_used'] > 0:
            msg_parts.append(f"跳过 {result['skipped_used']} 条已使用")

        return ResponseData(code=200, message="，".join(msg_parts), data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量更新上线状态失败: {str(e)}")


@router.post("/batch-valid", response_model=ResponseData, summary="批量更新文章有效状态")
async def batch_update_content_valid_status(
    request: ContentBatchValidUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    批量更新文章有效状态 (is_valid)
    
    用于批量下线/上线文章：
    - is_valid=0: 标记为无效（下线）
    - is_valid=1: 标记为有效（上线）
    
    返回数据包含：
    - updated_count: 成功更新的数量
    - total: 请求的文章总数
    """
    try:
        if not request.content_ids:
            return ResponseData(code=400, message="请选择要更新的文章", data={"updated_count": 0, "total": 0})
        
        if request.is_valid not in (0, 1):
            return ResponseData(code=400, message="is_valid 必须为 0 或 1", data={"updated_count": 0, "total": 0})
        
        # 批量更新
        stmt = select(Content).where(
            Content.id.in_(request.content_ids),
            Content.is_deleted == 0
        )
        result = await db.execute(stmt)
        items = result.scalars().all()
        
        updated_count = 0
        for item in items:
            item.is_valid = request.is_valid
            updated_count += 1
        
        await db.commit()
        
        status_text = "无效" if request.is_valid == 0 else "有效"
        return ResponseData(
            code=200, 
            message=f"成功将 {updated_count} 篇文章标记为{status_text}", 
            data={
                "updated_count": updated_count,
                "total": len(request.content_ids)
            }
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"批量更新有效状态失败: {str(e)}")


@router.post("/transfer", response_model=ResponseData[ContentTransferResponse], summary="文章池转移-将文章从一个Agent转移到另一个Agent")
async def transfer_contents(
    source_agent_code: str = Query(..., description="源 Agent 编码"),
    target_agent_code: str = Query(..., description="目标 Agent 编码"),
    request: ContentTransferRequest = Body(default=ContentTransferRequest()),
    db: AsyncSession = Depends(get_db)
):
    """
    将文章从一个 Agent 的文章池转移到另一个 Agent

    支持两种模式：
    1. 指定 content_ids：直接转移指定的文章
       ```json
       {
         "content_ids": ["content_id1", "content_id2", ...]
       }
       ```

    2. 按条件筛选：根据筛选条件批量转移文章
       ```json
       {
         "tenant_id": 1,
         "activity_id": 100,
         "job_id": "job-xxx",
         "is_valid": 1,
         "is_test_case": 0,
         "online_status": "ONLINE",
         "max_count": 1000,
         "skip_locked": true,
         "skip_used": true
       }
       ```

    转移规则：
    - 只修改 agent_code 字段，其他字段保持不变
    - 已锁定的文章会被跳过（除非 skip_locked=false）
    - 已使用的文章会被跳过（除非 skip_used=false）
    - 转移记录会保存在 remark 字段中

    返回数据包含：
    - success_count: 成功转移的数量
    - skipped_locked_count: 跳过已锁定的数量
    - skipped_used_count: 跳过已使用的数量
    - skipped_content_ids: 被跳过的文章 ID 列表
    """
    try:
        if source_agent_code == target_agent_code:
            raise HTTPException(
                status_code=400,
                detail="源 Agent 和目标 Agent 不能相同"
            )

        service = ContentPoolService(db)
        result = await service.transfer_contents(
            source_agent_code,
            target_agent_code,
            request
        )

        msg_parts = [f"成功转移 {result.success_count} 篇文章"]
        if result.skipped_locked_count > 0:
            msg_parts.append(f"跳过 {result.skipped_locked_count} 篇已锁定")
        if result.skipped_used_count > 0:
            msg_parts.append(f"跳过 {result.skipped_used_count} 篇已使用")

        return ResponseData(
            code=200,
            message="，".join(msg_parts),
            data=result
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文章转移失败: {str(e)}")



async def _list_contents_with_score_filter(
    db: AsyncSession,
    tenant_id: Optional[int],
    activity_id: Optional[int],
    job_id: Optional[str],
    agent_code: Optional[str],
    expert_content_ids_subq,  # 方案二：改为接收专家筛选的 content_id 子查询
    is_valid: Optional[int],
    is_test_case: Optional[int],
    online_status: Optional[str],
    keyword: Optional[str],
    score_status: Optional[str],
    avg_score_min: Optional[int],
    avg_score_max: Optional[int],
    expert_score_filters: Optional[List[ExpertScoreFilter]],
    content_length_min: Optional[int],
    content_length_max: Optional[int],
    create_time_start: Optional[str],
    create_time_end: Optional[str],
    order_by_create_time: Optional[str],
    id_min: Optional[int],
    id_max: Optional[int],
    page: int,
    page_size: int,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
):
    """
    带评分筛选的文章列表查询

    策略：先获取所有符合基本条件的 content_id，计算评分汇总，再根据评分条件过滤

    方案二：专家筛选通过 expert_content_ids_subq 子查询实现，确保筛选出的文章一定有该专家的评分
    """
    # 确定最终使用的 offset 和 limit
    final_limit = limit if limit is not None else page_size
    final_offset = offset if offset is not None else (page - 1) * page_size
    # 基础查询条件（内容过滤）
    content_conditions = [Content.is_deleted == 0]

    if tenant_id:
        content_conditions.append(Content.tenant_id == tenant_id)
    if activity_id:
        content_conditions.append(Content.activity_id == activity_id)
    if job_id:
        content_conditions.append(Content.job_id == job_id)
    if agent_code:
        content_conditions.append(Content.agent_code == agent_code)

    # 方案二：专家筛选通过子查询关联
    if expert_content_ids_subq is not None:
        content_conditions.append(Content.content_id.in_(expert_content_ids_subq))

    if is_valid is not None:
        content_conditions.append(Content.is_valid == is_valid)
    if is_test_case is not None:
        content_conditions.append(Content.is_test_case == is_test_case)
    if online_status:
        content_conditions.append(Content.online_status == online_status)
    if keyword:
        content_conditions.append(
            or_(
                Content.title.ilike(f"%{keyword}%"),
                Content.content.ilike(f"%{keyword}%")
            )
        )

    # ID 范围筛选
    if id_min is not None:
        content_conditions.append(Content.id > id_min)
    if id_max is not None:
        content_conditions.append(Content.id < id_max)

    # 时间范围筛选
    if create_time_start:
        try:
            from datetime import datetime
            start_dt = datetime.fromisoformat(create_time_start.replace('Z', '+00:00'))
            content_conditions.append(Content.create_time >= start_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"create_time_start 格式错误: {create_time_start}")
    if create_time_end:
        try:
            from datetime import datetime
            end_dt = datetime.fromisoformat(create_time_end.replace('Z', '+00:00'))
            content_conditions.append(Content.create_time <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"create_time_end 格式错误: {create_time_end}")

    # 构建基础查询
    # 字数筛选需要在选择 content 字段后应用
    base_query_builder = select(Content.content_id, Content.create_time, Content.content).where(Content.is_deleted == 0)

    # 应用所有基础条件
    for condition in content_conditions[1:]:  # 跳过 is_deleted == 0，因为已经在上面设置了
        base_query_builder = base_query_builder.where(condition)

    # 字数筛选（需要在 content 字段可用时应用）
    if content_length_min is not None or content_length_max is not None:
        # 使用 SQL 函数计算去除所有空白字符后的字数
        # 与前端 JS 的 /\s/g 保持完全一致
        # JS 的 /\s/g 匹配：\t\n\r\f\v 以及其他 Unicode 空白字符
        # 注意：使用 CHAR_LENGTH 而非 LENGTH，因为 LENGTH 返回字节数，CHAR_LENGTH 返回字符数
        # 这对于多字节字符（如中文）很重要，确保前后端计算方式一致

        # 第一遍：去除 ASCII 空白字符
        content_length_expr = func.replace(
            func.replace(
                func.replace(
                    func.replace(
                        func.replace(
                            func.replace(Content.content, ' ', ''),  # U+0020 空格
                            '\t', '',                                  # U+0009 制表符
                        ),
                        '\n', '',                                      # U+000A 换行符
                    ),
                    '\r', '',                                          # U+000D 回车符
                ),
                '\f', '',                                              # U+000C 换页符
            ),
            '\v', '',                                                  # U+000B 垂直制表符
        )
        # 第二遍：去除常见 Unicode 空白字符（这些字符可能在复制粘贴时进入文本）
        # U+00A0 不间断空格 (No-Break Space, NBSP) - 最常见
        # U+2002-U+2009 各种宽度的空格（从编辑器复制时常见）
        # U+3000 表意文字空格（中文输入常见）
        content_length_expr = func.replace(content_length_expr, '\u00A0', '')  # NBSP
        content_length_expr = func.replace(content_length_expr, '\u2002', '')  # En Space
        content_length_expr = func.replace(content_length_expr, '\u2003', '')  # Em Space
        content_length_expr = func.replace(content_length_expr, '\u2009', '')  # Thin Space
        content_length_expr = func.replace(content_length_expr, '\u3000', '')  # Ideographic Space (全角空格)

        if content_length_min is not None:
            base_query_builder = base_query_builder.where(func.char_length(content_length_expr) >= content_length_min)
        if content_length_max is not None:
            base_query_builder = base_query_builder.where(func.char_length(content_length_expr) <= content_length_max)

    base_query = base_query_builder.subquery()

    # 计算每个 content_id + expert_func 的最新版本
    latest_version_subq = (
        select(
            CriticScoreRecord.content_id.label("content_id"),
            CriticScoreRecord.expert_func.label("expert_func"),
            func.max(CriticScoreRecord.version).label("max_version"),
        )
        .join(base_query, CriticScoreRecord.content_id == base_query.c.content_id)
        .group_by(CriticScoreRecord.content_id, CriticScoreRecord.expert_func)
        .subquery()
    )

    latest_records_subq = (
        select(
            CriticScoreRecord.content_id.label("content_id"),
            CriticScoreRecord.expert_config_code.label("expert_config_code"),
            CriticScoreRecord.expert_type.label("expert_type"),
            CriticScoreRecord.score.label("score"),
            CriticScoreRecord.passed.label("passed"),
        )
        .join(
            latest_version_subq,
            and_(
                CriticScoreRecord.content_id == latest_version_subq.c.content_id,
                CriticScoreRecord.expert_func == latest_version_subq.c.expert_func,
                CriticScoreRecord.version == latest_version_subq.c.max_version,
            )
        )
        .subquery()
    )

    summary_subq = (
        select(
            latest_records_subq.c.content_id.label("content_id"),
            func.count().label("total_critics"),
            func.sum(
                case((latest_records_subq.c.passed == 1, 1), else_=0)
            ).label("passed_count"),
            func.max(
                case(
                    (
                        and_(
                            latest_records_subq.c.expert_type == "BAN",
                            latest_records_subq.c.passed == 0,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("has_ban_issue"),
            func.avg(
                case(
                    (latest_records_subq.c.expert_type != "BAN", latest_records_subq.c.score),
                    else_=None,
                )
            ).label("avg_score"),
        )
        .group_by(latest_records_subq.c.content_id)
        .subquery()
    )

    filtered_query = select(
        base_query.c.content_id,
        base_query.c.create_time,
    ).select_from(
        base_query.outerjoin(
            summary_subq, base_query.c.content_id == summary_subq.c.content_id
        )
    )

    failed_count_expr = summary_subq.c.total_critics - summary_subq.c.passed_count

    if score_status:
        if score_status == "no_score":
            filtered_query = filtered_query.where(summary_subq.c.content_id.is_(None))
        elif score_status == "all_passed":
            filtered_query = filtered_query.where(
                summary_subq.c.content_id.is_not(None),
                failed_count_expr == 0,
            )
        elif score_status == "has_ban":
            filtered_query = filtered_query.where(summary_subq.c.has_ban_issue == 1)
        elif score_status == "partial":
            filtered_query = filtered_query.where(
                summary_subq.c.content_id.is_not(None),
                failed_count_expr > 0,
                summary_subq.c.has_ban_issue == 0,
            )

    if avg_score_min is not None or avg_score_max is not None:
        filtered_query = filtered_query.where(summary_subq.c.avg_score.is_not(None))
        if avg_score_min is not None:
            filtered_query = filtered_query.where(summary_subq.c.avg_score >= avg_score_min)
        if avg_score_max is not None:
            filtered_query = filtered_query.where(summary_subq.c.avg_score <= avg_score_max)

    # 细化专家评分筛选 (AND 关系)
    # 策略：对每个专家筛选条件，找出符合要求的 content_id 集合，多个条件之间取交集
    if expert_score_filters and len(expert_score_filters) > 0:
        for filter_item in expert_score_filters:
            # 为每个专家构建独立的子查询：
            # 1. 先找出该专家对每篇文章的最新版本号
            latest_version_for_expert = (
                select(
                    CriticScoreRecord.content_id,
                    func.max(CriticScoreRecord.version).label('max_version')
                )
                .where(CriticScoreRecord.expert_config_code == filter_item.expert_config_code)
                .group_by(CriticScoreRecord.content_id)
                .subquery()
            )
            
            # 2. 根据最新版本和评分区间，筛选出满足条件的 content_id
            qualified_content_ids = (
                select(CriticScoreRecord.content_id)
                .join(
                    latest_version_for_expert,
                    and_(
                        CriticScoreRecord.content_id == latest_version_for_expert.c.content_id,
                        CriticScoreRecord.version == latest_version_for_expert.c.max_version
                    )
                )
                .where(CriticScoreRecord.expert_config_code == filter_item.expert_config_code)
            )
            
            # 3. 添加评分区间条件或通过条件
            if filter_item.passed is not None:
                # BAN类型: 按passed筛选(0=不通过, 1=通过)
                qualified_content_ids = qualified_content_ids.where(
                    CriticScoreRecord.passed == (1 if filter_item.passed else 0)
                )
            else:
                # CRITIC类型: 按分数区间筛选
                if filter_item.min_score is not None:
                    qualified_content_ids = qualified_content_ids.where(CriticScoreRecord.score >= filter_item.min_score)
                if filter_item.max_score is not None:
                    qualified_content_ids = qualified_content_ids.where(CriticScoreRecord.score <= filter_item.max_score)

            # 4. 将当前专家的筛选结果作为 AND 条件叠加到主查询
            filtered_query = filtered_query.where(
                base_query.c.content_id.in_(qualified_content_ids)
            )

    count_query = select(func.count()).select_from(filtered_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    if total == 0:
        return ResponseData(
            data=PageResult(
                items=[], 
                total=0, 
                page=page, 
                page_size=page_size,
                offset=final_offset,
                limit=final_limit
            )
        )

    filtered_subq = filtered_query.subquery()
    paged_query = (
        select(Content)
        .join(filtered_subq, Content.content_id == filtered_subq.c.content_id)
    )

    # 根据参数动态排序
    # 添加 Content.id 作为第二排序字段,确保排序稳定性,避免分页时出现重复数据
    if order_by_create_time == 'asc':
        paged_query = paged_query.order_by(asc(filtered_subq.c.create_time), asc(Content.id))
    else:
        # 默认降序
        paged_query = paged_query.order_by(desc(filtered_subq.c.create_time), desc(Content.id))

    paged_query = paged_query.offset(final_offset).limit(final_limit)
    result = await db.execute(paged_query)
    items = result.scalars().all()

    content_ids = [item.content_id for item in items]
    critic_summary_map = await _get_critic_summary_map(db, content_ids)

    content_details = []
    for item in items:
        detail = ContentDetail.model_validate(item)
        detail.critic_summary = critic_summary_map.get(item.content_id)
        content_details.append(detail)

    return ResponseData(
        data=PageResult(
            items=content_details,
            total=total,
            page=page,
            page_size=page_size,
            offset=final_offset,
            limit=final_limit
        )
    )


async def _check_agent_has_expert_config(
    db: AsyncSession,
    agent_code: str,
    expert_config_code: str,
    tenant_id: Optional[int],
) -> bool:
    """
    检查指定的 Agent 是否配置了某个专家

    返回 True 表示该 Agent 配置了该专家，False 表示未配置
    """
    conditions = [
        Agent.agent_code == agent_code,
        Agent.is_deleted == 0,
        Agent.enabled == 1,
        func.json_contains(Agent.expert_config_code_list, f'"{expert_config_code}"'),
    ]

    if tenant_id is not None:
        conditions.append(
            or_(
                Agent.tenant_id == tenant_id,
                Agent.tenant_id.is_(None)
            )
        )

    stmt = select(func.count()).where(and_(*conditions))
    result = await db.execute(stmt)
    count = result.scalar() or 0
    return count > 0


async def _get_critic_summary_map(
    db: AsyncSession,
    content_ids: List[str]
) -> dict:
    """
    批量获取多个 content 的 Critic 评分汇总

    返回格式：{ content_id: ContentCriticSummary }

    注意：每个 content_id + expert_func 组合只取最新版本（version 最大）的记录
    """
    if not content_ids:
        return {}

    # 查询所有相关的 critic_score_record
    query = select(CriticScoreRecord).where(
        CriticScoreRecord.content_id.in_(content_ids)
    )
    result = await db.execute(query)
    all_records = result.scalars().all()

    # 按 content_id 分组，并对每个 expert_func 只保留最新版本
    from collections import defaultdict
    grouped: dict = defaultdict(list)

    for record in all_records:
        grouped[record.content_id].append(record)

    # 构建汇总（每个 expert_func 只取最新版本）
    summary_map = {}
    for content_id, content_records in grouped.items():
        # 按 expert_func 分组，取每个 expert_func 的最新版本（version 最大）
        expert_latest: dict = {}
        for r in content_records:
            key = r.expert_func
            if key not in expert_latest or r.version > expert_latest[key].version:
                expert_latest[key] = r

        # 只使用每个 expert_func 的最新记录
        latest_records = list(expert_latest.values())

        total_critics = len(latest_records)
        passed_count = sum(1 for r in latest_records if r.passed == 1)
        failed_count = total_critics - passed_count

        # 平均分和最低分只计算 CRITIC 类型的评分（BAN 类型只有 0/1 分，不参与平均分计算）
        critic_score_values = [
            r.score for r in latest_records
            if r.score is not None and r.expert_type != "BAN"
        ]
        avg_score = round(sum(critic_score_values) / len(critic_score_values), 1) if critic_score_values else None
        min_score = min(critic_score_values) if critic_score_values else None

        # 检查是否有 BAN 类专家不通过（合规问题）
        has_ban_issue = any(
            r.expert_type == "BAN" and r.passed == 0
            for r in latest_records
        )

        # 统计问题总数（problem_tags 或 problem_snippets 的长度之和）
        problem_count = 0
        for r in latest_records:
            if r.problem_tags and isinstance(r.problem_tags, list):
                problem_count += len(r.problem_tags)
            elif r.problem_snippets and isinstance(r.problem_snippets, list):
                problem_count += len(r.problem_snippets)

        # 构建每个专家的评分详情（只取最新版本）
        score_items = [
            CriticScoreItem(
                expert_func=r.expert_func,
                expert_type=r.expert_type or "CRITIC",
                score=r.score or 0,
                passed=r.passed == 1,
                reason=r.reason,
            )
            for r in latest_records
        ]

        summary_map[content_id] = ContentCriticSummary(
            total_critics=total_critics,
            passed_count=passed_count,
            failed_count=failed_count,
            avg_score=avg_score,
            min_score=min_score,
            has_ban_issue=has_ban_issue,
            problem_count=problem_count,
            scores=score_items,
        )

    return summary_map
