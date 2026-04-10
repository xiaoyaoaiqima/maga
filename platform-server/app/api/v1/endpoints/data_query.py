"""
统一数据查询 API
通过 Redash 提供统一的数据查询接口
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
import asyncio
import hashlib
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logger import logger
from app.services.redash_service import (
    get_redash_service,
    RedashService,
    RedashServiceError,
    RedashQueryResult,
    RedashQuery,
    RedashDataSource,
)

# ✅ v1.5: Dashboard 缓存支持
from app.services.dashboard_data_cache_service import MySQLDashboardDataCacheService
from app.core.database import async_session_factory, get_analytics_db_context

# 环境变量控制
DASHBOARD_CACHE_ENABLED = getattr(settings, "DASHBOARD_CACHE_ENABLED", False)

router = APIRouter(prefix="/data-query", tags=["数据查询"])


# ==================== 请求/响应模型 ====================

class QueryExecuteRequest(BaseModel):
    """查询执行请求"""
    query_id: int = Field(..., description="Redash 查询 ID")
    parameters: Optional[Dict[str, Any]] = Field(None, description="查询参数")
    use_cache: bool = Field(True, description="是否使用缓存")
    max_age: int = Field(300, description="缓存最大年龄（秒）")


class QueryCreateRequest(BaseModel):
    """创建查询请求"""
    name: str = Field(..., description="查询名称")
    query: str = Field(..., description="SQL 查询语句")
    data_source_id: int = Field(..., description="数据源 ID")
    description: str = Field("", description="查询描述")


class QueryUpdateRequest(BaseModel):
    """更新查询请求"""
    name: Optional[str] = Field(None, description="查询名称")
    query: Optional[str] = Field(None, description="SQL 查询语句")
    description: Optional[str] = Field(None, description="查询描述")


class QuerySyncRequest(BaseModel):
    """查询同步请求"""
    data_source_id: int = Field(..., description="数据源 ID")
    queries: List[Dict[str, Any]] = Field(..., description="查询配置列表")


class DataSourceCreateRequest(BaseModel):
    """创建数据源请求"""
    name: str = Field(..., description="数据源名称")
    type: str = Field(..., description="数据源类型（mysql, pg, etc.）")
    options: Dict[str, Any] = Field(..., description="连接配置")


class QueryResultResponse(BaseModel):
    """查询结果响应"""
    query_id: int
    query_name: str
    data: List[Dict[str, Any]]
    columns: List[Dict[str, str]]
    rows_count: int
    retrieved_at: str


class ApiResponse(BaseModel):
    """通用 API 响应"""
    code: int = 200
    message: str = "success"
    data: Any = None


# ==================== 依赖注入 ====================

def get_service() -> RedashService:
    """获取 Redash 服务"""
    if not settings.REDASH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Redash 服务未启用",
        )
    if not settings.REDASH_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Redash API Key 未配置",
        )
    return get_redash_service()


# ==================== 健康检查 ====================

@router.get("/health", summary="Redash 服务健康检查")
async def health_check(service: RedashService = Depends(get_service)):
    """检查 Redash 服务连接状态"""
    try:
        data_sources = await service.list_data_sources()
        return ApiResponse(
            data={
                "status": "healthy",
                "redash_url": settings.REDASH_BASE_URL,
                "data_sources_count": len(data_sources),
            }
        )
    except RedashServiceError as e:
        raise HTTPException(status_code=503, detail=f"Redash 服务不可用: {e.message}")


# ==================== 数据源管理 ====================

@router.get("/data-sources", summary="获取数据源列表")
async def list_data_sources(
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """获取所有已配置的数据源"""
    try:
        data_sources = await service.list_data_sources()
        return ApiResponse(
            data=[ds.model_dump() for ds in data_sources]
        )
    except RedashServiceError as e:
        raise HTTPException(status_code=500, detail=e.message)


@router.post("/data-sources", summary="创建数据源")
async def create_data_source(
    request: DataSourceCreateRequest,
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """创建新的数据源"""
    try:
        data_source = await service.create_data_source(
            name=request.name,
            ds_type=request.type,
            options=request.options,
        )
        return ApiResponse(
            message="数据源创建成功",
            data=data_source.model_dump(),
        )
    except RedashServiceError as e:
        raise HTTPException(status_code=500, detail=e.message)


# ==================== 查询管理 ====================

@router.get("/queries", summary="获取查询列表")
async def list_queries(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(25, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """获取查询列表（分页）"""
    try:
        result = await service.list_queries(
            page=page,
            page_size=page_size,
            search=search,
        )
        return ApiResponse(data=result)
    except RedashServiceError as e:
        raise HTTPException(status_code=500, detail=e.message)


@router.get("/queries/{query_id}", summary="获取查询详情")
async def get_query(
    query_id: int,
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """获取单个查询的详细信息"""
    try:
        query = await service.get_query(query_id)
        return ApiResponse(data=query.model_dump())
    except RedashServiceError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="查询不存在")
        raise HTTPException(status_code=500, detail=e.message)


@router.post("/queries", summary="创建查询")
async def create_query(
    request: QueryCreateRequest,
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """创建新的查询"""
    try:
        query = await service.create_query(
            name=request.name,
            query=request.query,
            data_source_id=request.data_source_id,
            description=request.description,
        )
        logger.info(f"创建查询成功: {query.name} (ID: {query.id})")
        return ApiResponse(
            message="查询创建成功",
            data=query.model_dump(),
        )
    except RedashServiceError as e:
        raise HTTPException(status_code=500, detail=e.message)


@router.put("/queries/{query_id}", summary="更新查询")
async def update_query(
    query_id: int,
    request: QueryUpdateRequest,
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """更新已存在的查询"""
    try:
        query = await service.update_query(
            query_id=query_id,
            name=request.name,
            query=request.query,
            description=request.description,
        )
        return ApiResponse(
            message="查询更新成功",
            data=query.model_dump(),
        )
    except RedashServiceError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="查询不存在")
        raise HTTPException(status_code=500, detail=e.message)


@router.delete("/queries/{query_id}", summary="删除查询")
async def delete_query(
    query_id: int,
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """归档（删除）查询"""
    try:
        await service.archive_query(query_id)
        return ApiResponse(message="查询已删除")
    except RedashServiceError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="查询不存在")
        raise HTTPException(status_code=500, detail=e.message)


# ==================== 查询执行 ====================

@router.get("/queries/{query_id}/results", summary="获取查询结果（缓存）")
async def get_query_results(
    query_id: int,
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """获取查询的缓存结果"""
    try:
        result = await service.get_query_results(query_id)
        return ApiResponse(
            data=QueryResultResponse(
                query_id=result.query_id,
                query_name=result.query_name,
                data=result.data,
                columns=result.columns,
                rows_count=result.rows_count,
                retrieved_at=result.retrieved_at,
            ).model_dump()
        )
    except RedashServiceError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="查询或结果不存在")
        raise HTTPException(status_code=500, detail=e.message)


class ExecuteQueryRequest(BaseModel):
    """执行查询请求体"""
    parameters: Optional[Dict[str, Any]] = Field(None, description="查询参数")
    max_age: int = Field(0, description="缓存最大年龄（秒），0 表示不使用缓存")


@router.post("/queries/{query_id}/execute", summary="执行查询")
async def execute_query(
    query_id: int,
    request: Optional[ExecuteQueryRequest] = Body(None),
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """
    执行查询（支持参数化）
    
    - **query_id**: Redash 查询 ID
    - **parameters**: 查询参数（如 {"start_date": "2024-01-01", "end_date": "2024-12-31"}）
    - **max_age**: 缓存最大年龄（秒），0 表示每次都重新执行
    """
    try:
        # 从请求体中提取参数
        parameters = request.parameters if request else None
        max_age = request.max_age if request else 0
        
        result = await service.execute_query(
            query_id=query_id,
            parameters=parameters,
            max_age=max_age,
        )
        return ApiResponse(
            data=QueryResultResponse(
                query_id=result.query_id,
                query_name=result.query_name,
                data=result.data,
                columns=result.columns,
                rows_count=result.rows_count,
                retrieved_at=result.retrieved_at,
            ).model_dump()
        )
    except RedashServiceError as e:
        logger.error(f"执行查询失败 [Query ID: {query_id}]: {e.message}")
        raise HTTPException(status_code=500, detail=e.message)


@router.post("/execute", summary="执行查询（批量请求）")
async def execute_query_batch(
    request: QueryExecuteRequest,
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """
    执行查询（通过请求体传参）
    
    适用于复杂的参数化查询
    """
    try:
        if request.use_cache and request.max_age > 0:
            result = await service.execute_query(
                query_id=request.query_id,
                parameters=request.parameters,
                max_age=request.max_age,
            )
        else:
            result = await service.execute_query(
                query_id=request.query_id,
                parameters=request.parameters,
                max_age=0,
            )
        
        return ApiResponse(
            data=QueryResultResponse(
                query_id=result.query_id,
                query_name=result.query_name,
                data=result.data,
                columns=result.columns,
                rows_count=result.rows_count,
                retrieved_at=result.retrieved_at,
            ).model_dump()
        )
    except RedashServiceError as e:
        logger.error(f"执行查询失败 [Query ID: {request.query_id}]: {e.message}")
        raise HTTPException(status_code=500, detail=e.message)


# ==================== 查询同步 ====================

@router.post("/sync", summary="同步查询配置")
async def sync_queries(
    request: QuerySyncRequest,
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """
    从配置同步查询到 Redash
    
    - 如果查询已存在（按名称匹配），则更新
    - 如果查询不存在，则创建
    
    请求示例:
    ```json
    {
        "data_source_id": 1,
        "queries": [
            {
                "name": "成本汇总-总LLM Token成本",
                "query": "SELECT DATE(created_at) as date, SUM(total_cost) as cost FROM llm_calls GROUP BY DATE(created_at)",
                "description": "LLM Token 成本统计"
            }
        ]
    }
    ```
    """
    try:
        results = await service.sync_queries_from_config(
            queries_config=request.queries,
            data_source_id=request.data_source_id,
        )
        return ApiResponse(
            message=f"同步完成，共处理 {len(results)} 个查询",
            data={
                "synced_count": len(results),
                "queries": [q.model_dump() for q in results],
            },
        )
    except RedashServiceError as e:
        raise HTTPException(status_code=500, detail=e.message)


from sqlalchemy import text
from app.core.database import get_db_context
from app.constants.metrics import RAAP_METRIC_QUERIES, DIMENSION_FILTER_TEMPLATE


def _build_metric_query(metric_key: str, params: Dict[str, Any]) -> str:
    """构建指标查询 SQL"""
    if metric_key not in RAAP_METRIC_QUERIES:
        raise ValueError(f"未知的指标 key: {metric_key}")
    
    query_template = RAAP_METRIC_QUERIES[metric_key]["query"]

class MetricQueryRequest(BaseModel):
    """指标查询请求"""
    metric_key: str = Field(..., description="指标 key（如 total_llm_token_cost）")
    start_date: str = Field(..., description="开始日期（YYYY-MM-DD）")
    end_date: str = Field(..., description="结束日期（YYYY-MM-DD）")
    tenant_id: Optional[int | List[int]] = Field(None, description="租户 ID（可选，支持多选）")
    activity_id: Optional[int | List[int]] = Field(None, description="活动 ID（可选，支持多选）")
    agent_code: Optional[str | List[str]] = Field(None, description="Agent 编码（可选，支持多选）")


class MetricBatchQueryRequest(BaseModel):
    """批量指标查询请求"""
    metric_keys: List[str] = Field(..., description="指标 key 列表")
    start_date: str = Field(..., description="开始日期（YYYY-MM-DD）")
    end_date: str = Field(..., description="结束日期（YYYY-MM-DD）")
    tenant_id: Optional[int | List[int]] = Field(None, description="租户 ID（可选，支持多选）")
    activity_id: Optional[int | List[int]] = Field(None, description="活动 ID（可选，支持多选）")
    agent_code: Optional[str | List[str]] = Field(None, description="Agent 编码（可选，支持多选）")


class MetricPaginatedQueryRequest(BaseModel):
    """分页指标查询请求"""
    metric_key: str = Field(..., description="指标 key（如 cost_by_job）")
    start_date: str = Field(..., description="开始日期（YYYY-MM-DD）")
    end_date: str = Field(..., description="结束日期（YYYY-MM-DD）")
    tenant_id: Optional[int | List[int]] = Field(None, description="租户 ID（可选，支持多选）")
    activity_id: Optional[int | List[int]] = Field(None, description="活动 ID（可选，支持多选）")
    agent_code: Optional[str | List[str]] = Field(None, description="Agent 编码（可选，支持多选）")
    status: Optional[str | List[str]] = Field(None, description="Job 状态（用于 job_task_list）")
    tag_id: Optional[int] = Field(None, description="反馈标签 ID（用于 rlhf_feedback_tag_articles）")
    page: int = Field(1, ge=1, description="页码（从1开始）")
    page_size: int = Field(10, ge=1, le=1000, description="每页条数")



@router.get("/metrics/predefined", summary="获取预定义指标列表")
async def list_predefined_metrics() -> ApiResponse:
    """获取 RAAP 预定义的指标查询列表"""
    # 按类别分组
    categories = {
            "cost": [],      # AI算力看板
            "generation": [], # 生成中心
        "ag": [],        # 对齐治理
        "rlhf": [],      # RLHF
        "dashboard": [], # 概览
    }
    
    for key, value in RAAP_METRIC_QUERIES.items():
        metric_info = {
            "key": key,
            "name": value["name"],
            "description": value["description"],
        }
        if key.startswith("rlhf_"):
            categories["rlhf"].append(metric_info)
        elif key.startswith("ge_"):
            categories["generation"].append(metric_info)
        elif key.startswith("ag_"):
            categories["ag"].append(metric_info)
        elif key.startswith("dashboard") or key.startswith("daily"):
            categories["dashboard"].append(metric_info)
        else:
            categories["cost"].append(metric_info)
    
    return ApiResponse(
        data={
            "count": len(RAAP_METRIC_QUERIES),
            "categories": categories,
            "metrics": [
                {
                    "key": key,
                    "name": value["name"],
                    "description": value["description"],
                }
                for key, value in RAAP_METRIC_QUERIES.items()
            ],
        }
    )


@router.post("/metrics/init", summary="初始化预定义指标查询")
async def init_predefined_metrics(
    data_source_id: int = Query(..., description="数据源 ID"),
    service: RedashService = Depends(get_service),
) -> ApiResponse:
    """
    将预定义的 RAAP 指标查询同步到 Redash
    
    这将创建所有预定义的查询，如果同名查询已存在则更新
    """
    try:
        queries_config = [
            {
                "name": value["name"],
                "query": value["query"],
                "description": value["description"],
            }
            for value in RAAP_METRIC_QUERIES.values()
        ]
        
        results = await service.sync_queries_from_config(
            queries_config=queries_config,
            data_source_id=data_source_id,
        )
        
        return ApiResponse(
            message=f"初始化完成，共创建/更新 {len(results)} 个指标查询",
            data={
                "synced_count": len(results),
                "queries": [
                    {"id": q.id, "name": q.name}
                    for q in results
                ],
            },
        )
    except RedashServiceError as e:
        raise HTTPException(status_code=500, detail=e.message)


# ==================== 直接指标查询（不依赖 Redash） ====================

from sqlalchemy import text
from app.core.database import get_db_context


def _build_metric_query(metric_key: str, params: Dict[str, Any]) -> str:
    """构建指标查询 SQL"""
    if metric_key not in RAAP_METRIC_QUERIES:
        raise ValueError(f"未知的指标 key: {metric_key}")
    
    query_template = RAAP_METRIC_QUERIES[metric_key]["query"]
    
    # 替换参数
    query = query_template
    query = query.replace("{{start_date}}", params.get("start_date", "2024-01-01"))
    query = query.replace("{{end_date}}", params.get("end_date", "2099-12-31"))
    
    # 处理可选的维度过滤参数
    tenant_ids = params.get("tenant_id")
    activity_ids = params.get("activity_id")
    agent_codes = params.get("agent_code")
    
    # 构建过滤条件
    # Tenant Filter
    if tenant_ids:
        if isinstance(tenant_ids, list):
            ids_str = ",".join(map(str, tenant_ids))
            tenant_filter = f"j.tenant_id IN ({ids_str})"
        else:
            tenant_filter = f"j.tenant_id = {tenant_ids}"
    else:
        tenant_filter = "1=1"  # No filter
    
    # Activity Filter
    if activity_ids:
        if isinstance(activity_ids, list):
            ids_str = ",".join(map(str, activity_ids))
            activity_filter = f"j.activity_id IN ({ids_str})"
        else:
            activity_filter = f"j.activity_id = {activity_ids}"
    else:
        activity_filter = "1=1"
    
    # Agent Filter (使用 j.agent_code，适用于 JOIN job 表的查询)
    if agent_codes:
        if isinstance(agent_codes, list):
            codes_str = ",".join(f"'{c}'" for c in agent_codes)
            agent_filter = f"j.agent_code IN ({codes_str})"
            content_agent_filter = f"c.agent_code IN ({codes_str})"
        else:
            agent_filter = f"j.agent_code = '{agent_codes}'"
            content_agent_filter = f"c.agent_code = '{agent_codes}'"
    else:
        agent_filter = "1=1"
        content_agent_filter = "1=1"
    
    # Content 表的过滤条件（使用 c. 前缀）
    if tenant_ids:
        if isinstance(tenant_ids, list):
            ids_str = ",".join(map(str, tenant_ids))
            content_tenant_filter = f"c.tenant_id IN ({ids_str})"
        else:
            content_tenant_filter = f"c.tenant_id = {tenant_ids}"
    else:
        content_tenant_filter = "1=1"
    
    if activity_ids:
        if isinstance(activity_ids, list):
            ids_str = ",".join(map(str, activity_ids))
            content_activity_filter = f"c.activity_id IN ({ids_str})"
        else:
            content_activity_filter = f"c.activity_id = {activity_ids}"
    else:
        content_activity_filter = "1=1"
        
    query = query.replace("{{tenant_filter}}", tenant_filter)
    query = query.replace("{{activity_filter}}", activity_filter)
    query = query.replace("{{agent_filter}}", agent_filter)
    query = query.replace("{{content_tenant_filter}}", content_tenant_filter)
    query = query.replace("{{content_activity_filter}}", content_activity_filter)
    query = query.replace("{{content_agent_filter}}", content_agent_filter)
    
    # Status Filter（用于 job_task_list 指标）
    status_list = params.get("status")
    if status_list:
        if isinstance(status_list, list):
            status_str = ",".join(f"'{s}'" for s in status_list)
            status_filter = f"j.status IN ({status_str})"
        else:
            status_filter = f"j.status = '{status_list}'"
    else:
        status_filter = "1=1"
    query = query.replace("{{status_filter}}", status_filter)
    
    # 处理 tag_id 参数（用于 rlhf_feedback_tag_articles 指标）
    tag_id = params.get("tag_id")
    if tag_id is not None:
        query = query.replace("{{tag_id}}", str(tag_id))
    
    return query


@router.post("/metrics/query", summary="直接查询指标数据")
async def query_metric(
    request: MetricQueryRequest,
) -> ApiResponse:
    """
    直接查询指标数据（不依赖 Redash）

    - 支持所有预定义指标
    - 支持 tenant_id / activity_id / agent_code 多维度过滤
    - 直接从数据库查询，无需先同步到 Redash
    """
    if request.metric_key not in RAAP_METRIC_QUERIES:
        raise HTTPException(
            status_code=400,
            detail=f"未知的指标 key: {request.metric_key}，可用指标: {list(RAAP_METRIC_QUERIES.keys())}"
        )

    # 构建请求参数
    params = {
        "metric_key": request.metric_key,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "tenant_id": request.tenant_id,
        "activity_id": request.activity_id,
        "agent_code": request.agent_code,
    }

    # ✅ v1.5: 尝试从缓存获取
    if DASHBOARD_CACHE_ENABLED:
        async with async_session_factory() as db:
            cache_service = MySQLDashboardDataCacheService(db)

            cache_key = cache_service.generate_cache_key(
                endpoint="/v1/data-query/metrics/query",
                params=params,
                tenant_id=params.get("tenant_id"),
            )

            cached = await cache_service.get(
                cache_key=cache_key,
                cache_group="metric_query",
                check_demo=True,
            )

            if cached:
                logger.info(f"缓存命中: /metrics/query - {request.metric_key}")
                # ✅ v1.5.3: 添加缓存更新时间
                response_data = cached["data"].copy()
                response_data["last_updated_at"] = cached["meta"]["cache_watermark"]

                return ApiResponse(
                    code=200,
                    message="success (cached)",
                    data=response_data,
                )

    # 缓存未命中，执行查询
    try:
        query_sql = _build_metric_query(
            request.metric_key,
            {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "tenant_id": request.tenant_id,
                "activity_id": request.activity_id,
                "agent_code": request.agent_code,
            }
        )

        async with get_db_context() as session:
            result = await session.execute(text(query_sql))
            rows = result.fetchall()
            columns = list(result.keys())

            # 转换为字典列表
            data = [dict(zip(columns, row)) for row in rows]

            response_data = {
                "metric_key": request.metric_key,
                "metric_name": RAAP_METRIC_QUERIES[request.metric_key]["name"],
                "filters": {
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "tenant_id": request.tenant_id,
                    "activity_id": request.activity_id,
                    "agent_code": request.agent_code,
                },
                "columns": columns,
                "data": data,
                "rows_count": len(data),
                "last_updated_at": datetime.now().isoformat(),  # ✅ v1.5.3: 添加当前时间
            }

            # ✅ v1.8: 写入缓存（演示环境 - 24小时超长TTL）
            if DASHBOARD_CACHE_ENABLED:
                # 根据 metric_key 动态调整 TTL（演示环境优化）
                ttl_map = {
                    # 所有指标统一 24 小时（演示环境 - 追求极致速度）
                    "cost_total_by_currency": 86400,
                    "cost_by_agent": 86400,
                    "cost_by_job": 86400,

                    "generation_total_calls": 86400,
                    "generation_agent_stats": 86400,
                    "generation_agent_daily_trend": 86400,
                    "generation_agent_content_daily_trend": 86400,

                    "critic_content_stats": 86400,
                    "critic_expert_stats": 86400,
                    "critic_quality_dimensions": 86400,
                    "critic_expert_score_distribution": 86400,
                    "critic_expert_score_distribution_10": 86400,

                    "rlhf_inspection_stats": 86400,
                    "rlhf_inspection_issue_tag_distribution": 86400,
                    "rlhf_inspection_issue_tag_wordcloud": 86400,
                    "rlhf_feedback_tag_articles": 86400,

                    "statistics_agent_persona_heatmap": 86400,
                    "statistics_expert_stats": 86400,

                    "content_funnel": 86400,

                    "dashboard_overview": 86400,
                    "daily_trend": 86400,
                }
                ttl_seconds = ttl_map.get(request.metric_key, 86400)  # 默认 24小时

                async with async_session_factory() as db:
                    cache_service = MySQLDashboardDataCacheService(db)
                    await cache_service.set(
                        cache_key=cache_key,
                        logical_key=cache_service._generate_logical_key(
                            "metric_query",
                            params,
                        ),
                        cache_group="metric_query",
                        data=response_data,
                        ttl_seconds=ttl_seconds,
                        request_params=params,
                        tenant_id=params.get("tenant_id"),
                        auto_refresh_enabled=False,  # ✅ v1.7: 禁用自动刷新（查询函数未注册）
                    )

            return ApiResponse(data=response_data)
    except Exception as e:
        logger.error(f"查询指标失败 [{request.metric_key}]: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/metrics/query-paginated", summary="分页查询指标数据")
async def query_metric_paginated(
    request: MetricPaginatedQueryRequest,
) -> ApiResponse:
    """
    分页查询指标数据（支持大数据量场景）

    - 支持分页的指标：cost_by_job 等
    - 返回总数和分页数据
    - ✅ 支持 Dashboard 缓存（每页单独缓存）
    """
    if request.metric_key not in RAAP_METRIC_QUERIES:
        raise HTTPException(
            status_code=400,
            detail=f"未知的指标 key: {request.metric_key}，可用指标: {list(RAAP_METRIC_QUERIES.keys())}"
        )

    # 构建请求参数（用于缓存键生成）
    params = {
        "metric_key": request.metric_key,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "tenant_id": request.tenant_id,
        "activity_id": request.activity_id,
        "agent_code": request.agent_code,
        "status": request.status,
        "tag_id": request.tag_id,
        "page": request.page,
        "page_size": request.page_size,
    }

    # ✅ v1.5: 尝试从缓存获取
    if DASHBOARD_CACHE_ENABLED:
        async with async_session_factory() as db:
            cache_service = MySQLDashboardDataCacheService(db)

            cache_key = cache_service.generate_cache_key(
                endpoint="/v1/data-query/metrics/query-paginated",
                params=params,
                tenant_id=params.get("tenant_id"),
            )

            cached = await cache_service.get(
                cache_key=cache_key,
                cache_group="metric_query_paginated",
                check_demo=True,
            )

            if cached:
                logger.info(f"缓存命中: /metrics/query-paginated - {request.metric_key} (page={request.page})")
                # ✅ v1.5.3: 添加缓存更新时间
                response_data = cached["data"].copy()
                response_data["last_updated_at"] = cached["meta"]["cache_watermark"]

                return ApiResponse(
                    code=200,
                    message="success (cached)",
                    data=response_data,
                )

    # 缓存未命中，执行查询
    try:
        # 构建基础查询 SQL
        base_query = _build_metric_query(
            request.metric_key,
            {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "tenant_id": request.tenant_id,
                "activity_id": request.activity_id,
                "agent_code": request.agent_code,
                "status": request.status,
                "tag_id": request.tag_id,
            }
        )

        async with get_db_context() as session:
            # 1. 先查询总数（用 CTE 包装）
            count_sql = f"SELECT COUNT(*) as total FROM ({base_query}) AS t"
            count_result = await session.execute(text(count_sql))
            total = count_result.scalar() or 0

            # 2. 添加分页参数
            offset = (request.page - 1) * request.page_size
            paginated_sql = f"{base_query} LIMIT {request.page_size} OFFSET {offset}"

            result = await session.execute(text(paginated_sql))
            rows = result.fetchall()
            columns = list(result.keys())
            data = [dict(zip(columns, row)) for row in rows]

            # 计算分页信息
            total_pages = (total + request.page_size - 1) // request.page_size if total > 0 else 0

            response_data = {
                "metric_key": request.metric_key,
                "metric_name": RAAP_METRIC_QUERIES[request.metric_key]["name"],
                "filters": {
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "tenant_id": request.tenant_id,
                    "activity_id": request.activity_id,
                    "agent_code": request.agent_code,
                    "tag_id": request.tag_id,
                },
                "columns": columns,
                "data": data,
                "pagination": {
                    "page": request.page,
                    "page_size": request.page_size,
                    "total": total,
                    "total_pages": total_pages,
                },
                "last_updated_at": datetime.now().isoformat(),  # ✅ v1.5.3: 添加当前时间
            }

            # ✅ v1.8: 写入缓存（演示环境 - 24小时超长TTL）
            if DASHBOARD_CACHE_ENABLED:
                # 根据 metric_key 动态调整 TTL（演示环境优化）
                ttl_map = {
                    # 所有指标统一 24 小时（演示环境 - 追求极致速度）
                    "cost_by_job": 86400,
                    "cost_by_agent": 86400,
                    "cost_total_by_currency": 86400,

                    "job_task_list": 86400,

                    "rlhf_feedback_tag_articles": 86400,

                    # 其他分页指标
                    "generation_total_calls": 86400,
                    "generation_agent_stats": 86400,
                    "critic_content_stats": 86400,
                    "critic_expert_stats": 86400,
                    "statistics_agent_persona_heatmap": 86400,
                    "content_funnel": 86400,
                }
                ttl_seconds = ttl_map.get(request.metric_key, 86400)  # 默认 24小时

                async with async_session_factory() as db:
                    cache_service = MySQLDashboardDataCacheService(db)
                    await cache_service.set(
                        cache_key=cache_key,
                        logical_key=cache_service._generate_logical_key(
                            "metric_query_paginated",
                            params,
                        ),
                        cache_group="metric_query_paginated",
                        data=response_data,
                        ttl_seconds=ttl_seconds,
                        request_params=params,
                        tenant_id=params.get("tenant_id"),
                        auto_refresh_enabled=False,  # ✅ v1.7: 禁用自动刷新（查询函数未注册）
                    )

            return ApiResponse(data=response_data)
    except Exception as e:
        logger.error(f"分页查询指标失败 [{request.metric_key}]: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/metrics/batch", summary="批量查询指标数据")
async def query_metrics_batch(
    request: MetricBatchQueryRequest,
) -> ApiResponse:
    """
    批量查询多个指标数据
    
    - 一次请求查询多个指标
    - 所有指标共享相同的过滤条件
    """
    results = {}
    errors = {}
    
    for metric_key in request.metric_keys:
        if metric_key not in RAAP_METRIC_QUERIES:
            errors[metric_key] = f"未知的指标 key"
            continue
        
        try:
            query_sql = _build_metric_query(
                metric_key,
                {
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "tenant_id": request.tenant_id,
                    "activity_id": request.activity_id,
                    "agent_code": request.agent_code,
                }
            )
            
            async with get_db_context() as session:
                result = await session.execute(text(query_sql))
                rows = result.fetchall()
                columns = list(result.keys())
                data = [dict(zip(columns, row)) for row in rows]
                
                results[metric_key] = {
                    "metric_name": RAAP_METRIC_QUERIES[metric_key]["name"],
                    "columns": columns,
                    "data": data,
                    "rows_count": len(data),
                }
        except Exception as e:
            logger.error(f"查询指标失败 [{metric_key}]: {str(e)}")
            errors[metric_key] = str(e)
    
    return ApiResponse(
        data={
            "filters": {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "tenant_id": request.tenant_id,
                "activity_id": request.activity_id,
                "agent_code": request.agent_code,
            },
            "results": results,
            "errors": errors if errors else None,
            "success_count": len(results),
            "error_count": len(errors),
        }
    )


@router.get("/metrics/dashboard", summary="Dashboard 概览数据")
async def get_dashboard_overview(
    start_date: str = Query(..., description="开始日期（YYYY-MM-DD）"),
    end_date: str = Query(..., description="结束日期（YYYY-MM-DD）"),
    tenant_id: Optional[List[int]] = Query(None, description="租户 ID（支持多选）"),
    activity_id: Optional[List[int]] = Query(None, description="活动 ID（支持多选）"),
    agent_code: Optional[List[str]] = Query(None, description="Agent 编码（支持多选）"),
) -> ApiResponse:
    """
    获取 Dashboard 概览数据

    包含：概览统计 + 日趋势
    """
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "tenant_id": tenant_id,
        "activity_id": activity_id,
        "agent_code": agent_code,
    }

    # ✅ v1.5: 尝试从缓存获取
    if DASHBOARD_CACHE_ENABLED:
        async with async_session_factory() as db:
            cache_service = MySQLDashboardDataCacheService(db)

            # 生成缓存键
            cache_key = cache_service.generate_cache_key(
                endpoint="/v1/data-query/metrics/dashboard",
                params=params,
                tenant_id=tenant_id[0] if tenant_id else None,  # 取第一个租户
            )

            # 尝试获取缓存
            cached = await cache_service.get(
                cache_key=cache_key,
                cache_group="dashboard_overview",
                check_demo=True,
            )

            if cached:
                logger.info(f"缓存命中: /metrics/dashboard - {cache_key}")
                # ✅ v1.5.3: 添加缓存更新时间
                response_data = cached["data"].copy()
                response_data["last_updated_at"] = cached["meta"]["cache_watermark"]

                return ApiResponse(
                    code=200,
                    message="success (cached)",
                    data=response_data,
                )

    # 缓存未命中，执行查询
    try:
        async with get_db_context() as session:
            # 查询概览统计
            overview_sql = _build_metric_query("dashboard_overview", params)
            overview_result = await session.execute(text(overview_sql))
            overview_row = overview_result.fetchone()
            overview_columns = list(overview_result.keys())
            overview_data = dict(zip(overview_columns, overview_row)) if overview_row else {}

            # 查询日趋势
            trend_sql = _build_metric_query("daily_trend", params)
            trend_result = await session.execute(text(trend_sql))
            trend_rows = trend_result.fetchall()
            trend_columns = list(trend_result.keys())
            trend_data = [dict(zip(trend_columns, row)) for row in trend_rows]

            response_data = {
                "filters": params,
                "overview": overview_data,
                "trend": trend_data,
                "last_updated_at": datetime.now().isoformat(),  # ✅ v1.5.3: 添加当前时间
            }

            # ✅ v1.5: 写入缓存
            if DASHBOARD_CACHE_ENABLED:
                async with async_session_factory() as db:
                    cache_service = MySQLDashboardDataCacheService(db)
                    await cache_service.set(
                        cache_key=cache_key,
                        logical_key=cache_service._generate_logical_key(
                            "dashboard_overview",
                            params,
                        ),
                        cache_group="dashboard_overview",
                        data=response_data,
                        ttl_seconds=86400,  # ✅ v1.8: 24小时（演示环境优化）
                        request_params=params,
                        tenant_id=tenant_id[0] if tenant_id else None,
                        auto_refresh_enabled=False,
                    )

            return ApiResponse(data=response_data)
    except Exception as e:
        logger.error(f"获取 Dashboard 数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ==================== AI Dashboard 批量查询优化 ====================

# 简单的内存缓存
_dashboard_cache: Dict[str, tuple] = {}
_cache_lock = asyncio.Lock()


def _generate_cache_key(params: Dict[str, Any]) -> str:
    """生成缓存键"""
    # 排序后序列化，确保相同参数生成相同 key
    params_str = json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(params_str.encode()).hexdigest()


async def _get_cached_or_execute(
    cache_key: str,
    cache_ttl: int,
    execute_func: callable,
) -> Any:
    """获取缓存或执行查询"""
    now = datetime.now()

    async with _cache_lock:
        if cache_key in _dashboard_cache:
            cached_data, cached_time = _dashboard_cache[cache_key]
            age = (now - cached_time).total_seconds()
            if age < cache_ttl:
                logger.debug(f"缓存命中: {cache_key}, age={age:.1f}s")
                return cached_data

    # 缓存未命中或过期，执行查询
    result = await execute_func()

    # 更新缓存
    async with _cache_lock:
        _dashboard_cache[cache_key] = (result, now)

        # 清理过期缓存（保留最近 100 个）
        if len(_dashboard_cache) > 100:
            sorted_keys = sorted(
                _dashboard_cache.keys(),
                key=lambda k: _dashboard_cache[k][1],
            )
            for old_key in sorted_keys[:50]:
                del _dashboard_cache[old_key]

    return result


async def _query_single_metric(
    metric_key: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """查询单个指标（使用分析库，带自动降级）"""
    query_sql = _build_metric_query(metric_key, params)

    # 使用分析库查询（失败时自动降级到主库）
    async with get_analytics_db_context() as session:
        result = await session.execute(text(query_sql))
        rows = result.fetchall()
        columns = list(result.keys())
        data = [dict(zip(columns, row)) for row in rows]

    return {
        "metric_key": metric_key,
        "metric_name": RAAP_METRIC_QUERIES.get(metric_key, {}).get("name", metric_key),
        "data": data,
        "rows_count": len(data),
    }


@router.post("/metrics/dashboard-summary", summary="AI Dashboard 批量查询（优化版）")
async def get_dashboard_summary(
    request: MetricBatchQueryRequest,
    use_cache: bool = Query(True, description="是否使用缓存"),
    cache_ttl: int = Query(30, description="缓存时间（秒），默认 30 秒"),
) -> ApiResponse:
    """
    批量查询 AI Dashboard 所需的所有指标

    **性能优化**：
    - 并行查询所有指标（asyncio.gather）
    - 内存缓存（默认 30 秒）
    - 一次请求替代 16+ 个独立请求

    **请求示例**：
    ```json
    {
        "metric_keys": [
            "cost_total_by_currency",
            "cost_by_agent",
            "generation_total_calls",
            "generation_agent_stats",
            "generation_agent_daily_trend",
            "generation_agent_content_daily_trend",
            "critic_content_stats",
            "critic_expert_stats",
            "critic_quality_dimensions",
            "rlhf_inspection_stats",
            "rlhf_inspection_issue_tag_distribution",
            "rlhf_inspection_issue_tag_wordcloud",
            "statistics_agent_persona_heatmap",
            "statistics_expert_stats",
            "critic_expert_score_distribution",
            "critic_expert_score_distribution_10"
        ],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "tenant_id": [1],
        "activity_id": [100],
        "agent_code": ["agent_001"]
    }
    ```

    **缓存策略**：
    - 静态数据（如 Agent 统计）：缓存 60 秒
    - 趋势数据（如日趋势）：缓存 30 秒
    - 实时数据（如成本）：缓存 10 秒
    """
    params = {
        "start_date": request.start_date,
        "end_date": request.end_date,
        "tenant_id": request.tenant_id,
        "activity_id": request.activity_id,
        "agent_code": request.agent_code,
    }

    # 生成缓存键
    cache_key = _generate_cache_key({
        "metric_keys": sorted(request.metric_keys),
        "params": params,
    })

    # 定义查询函数
    async def execute_all_queries():
        results = {}
        errors = {}

        # 创建所有查询任务（每个任务使用独立的会话）
        tasks = [
            _query_single_metric(metric_key, params)
            for metric_key in request.metric_keys
            if metric_key in RAAP_METRIC_QUERIES
        ]

        # 并行执行所有查询
        if tasks:
            try:
                metric_results = await asyncio.gather(*tasks, return_exceptions=True)

                for i, result in enumerate(metric_results):
                    metric_key = request.metric_keys[i]

                    if isinstance(result, Exception):
                        logger.error(f"查询指标失败 [{metric_key}]: {str(result)}")
                        errors[metric_key] = str(result)
                    else:
                        results[metric_key] = result
            except Exception as e:
                logger.error(f"批量查询失败: {str(e)}")
                errors["batch_query"] = str(e)

        return {
            "results": results,
            "errors": errors,
            "success_count": len(results),
            "error_count": len(errors),
        }

    # 使用缓存或执行查询
    if use_cache:
        data = await _get_cached_or_execute(
            cache_key=cache_key,
            cache_ttl=cache_ttl,
            execute_func=execute_all_queries,
        )
    else:
        data = await execute_all_queries()

    return ApiResponse(
        data={
            "filters": params,
            "cached": use_cache,
            **data,
        }
    )
