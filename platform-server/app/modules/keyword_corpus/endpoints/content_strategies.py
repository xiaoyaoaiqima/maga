"""
关键词策略 API 路由

v2 重构：
- 新增 GET /{id}/combinations 获取组合列表
- 保留 POST /{id}/generate 用于向后兼容
- 支持 node_pools 和 defined_combinations 字段
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.schemas.base import PageInfo
from app.schemas.content_strategy import (
    ContentStrategyCreate,
    ContentStrategyItem,
    ContentStrategyListResponse,
    ContentStrategyUpdate,
    GenerateCombinationsRequest,
    GenerateCombinationsResponse,
    GetCombinationsResponse,
    MergeStrategyCombinationsRequest,
    MergeStrategyCombinationsResponse,
)
from app.services.content_strategy_service import ContentStrategyService

router = APIRouter(prefix="/content-strategies", tags=["关键词策略"])


def _normalize_node_pools(node_pools) -> dict | None:
    """
    标准化 node_pools 格式，将旧格式（列表）转换为新格式（字典）

    旧格式: {"场景": ["id1", "id2"]}
    新格式: {"场景": {"node_ids": ["id1", "id2"], "select_mode": "random"}}
    """
    if not node_pools:
        return node_pools

    normalized = {}
    for dim_type, pool_data in node_pools.items():
        # 如果已经是新格式（字典），直接使用
        if isinstance(pool_data, dict):
            normalized[dim_type] = pool_data
        # 如果是旧格式（列表），转换为新格式
        elif isinstance(pool_data, list):
            normalized[dim_type] = {
                "node_ids": pool_data,
                "select_mode": "random",  # 默认随机选择
            }
        else:
            # 其他情况，跳过
            normalized[dim_type] = pool_data

    return normalized


def _strategy_to_item(strategy, service: ContentStrategyService) -> ContentStrategyItem:
    """将策略模型转换为响应项"""
    return ContentStrategyItem(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        node_pools=_normalize_node_pools(strategy.node_pools),
        defined_combinations=strategy.defined_combinations,
        combinations_count=service.get_combinations_count(strategy),
        max_combinations=strategy.max_combinations,
        settings=strategy.settings,
        scope_context=strategy.scope_context,
        tags=strategy.tags,
        tenant_code=strategy.tenant_code,
        is_active=strategy.is_active,
        created_by=strategy.created_by,
        updated_by=strategy.updated_by,
        create_time=strategy.create_time,
        update_time=strategy.update_time,
    )


@router.post("", response_model=ContentStrategyItem, summary="创建关键词策略")
async def create_strategy(
    data: ContentStrategyCreate,
    db: AsyncSessionDep,
):
    """创建关键词策略"""
    service = ContentStrategyService(db)

    # 处理 node_pools（v3 新结构，转换 Pydantic 对象为 dict）
    node_pools = None
    if data.node_pools is not None:
        node_pools = {
            dim_type: pool.model_dump() for dim_type, pool in data.node_pools.items()
        }

    # 处理 defined_combinations（使用 is not None 来区分空数组和 None）
    defined_combos = None
    if data.defined_combinations is not None:
        defined_combos = [c.model_dump() for c in data.defined_combinations]

    try:
        strategy = await service.create_strategy(
            name=data.name,
            description=data.description,
            node_pools=node_pools,
            defined_combinations=defined_combos,
            max_combinations=data.max_combinations,
            settings=data.settings.model_dump() if data.settings else None,
            scope_context=data.scope_context.model_dump() if data.scope_context else None,
            tags=data.tags,
            tenant_code=data.tenant_code,
        )
        return _strategy_to_item(strategy, service)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "", response_model=ContentStrategyListResponse, summary="获取关键词策略列表"
)
async def list_strategies(
    db: AsyncSessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_code: Optional[str] = Query(None, description="租户编码（兼容保留）"),
    brand_code: Optional[str] = Query(None, description="品牌编码"),
    name: Optional[str] = Query(None, description="策略名称（模糊搜索）"),
    tags: Optional[list[str]] = Query(None, description="标签筛选"),
    is_active: Optional[int] = Query(None, description="状态：0-禁用 1-启用"),
):
    """获取关键词策略列表"""
    service = ContentStrategyService(db)
    items, total = await service.list_strategies(
        tenant_code=tenant_code,
        brand_code=brand_code,
        name=name,
        tags=tags,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return ContentStrategyListResponse(
        items=[_strategy_to_item(s, service) for s in items],
        page_info=PageInfo(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/dimensions", summary="获取可用维度列表")
async def get_available_dimensions(
    db: AsyncSessionDep,
    tenant_code: str = Query("default", description="租户编码"),
    include_global: bool = Query(True, description="是否包含全局维度"),
):
    """
    获取可用的维度列表（从分类树根节点动态生成）

    返回所有顶级分类作为可选维度，不硬编码
    """
    service = ContentStrategyService(db)
    dimensions = await service.get_available_dimensions(
        tenant_code=tenant_code,
        include_global=include_global,
    )
    return {"dimensions": dimensions}


@router.get("/dimensions/{dimension_type}/nodes", summary="获取维度下的可选节点")
async def get_dimension_nodes(
    dimension_type: str,
    db: AsyncSessionDep,
    tenant_code: str = Query("default", description="租户编码"),
    include_global: bool = Query(True, description="是否包含全局节点"),
    brand_code: Optional[str] = Query(None, description="品牌编码（用于 Scope 过滤）"),
    product_name: Optional[str] = Query(
        None, description="产品名称（用于 Scope 过滤）"
    ),
):
    """
    获取指定维度下的可选节点

    支持 Scope 过滤（Fallback 优先级：Product > Brand > Global）
    """
    service = ContentStrategyService(db)
    nodes = await service.get_dimension_nodes(
        dimension_type=dimension_type,
        tenant_code=tenant_code,
        include_global=include_global,
        brand_code=brand_code,
        product_name=product_name,
    )
    return {"nodes": nodes}


@router.get(
    "/{strategy_id}", response_model=ContentStrategyItem, summary="获取关键词策略详情"
)
async def get_strategy(
    strategy_id: int,
    db: AsyncSessionDep,
):
    """获取关键词策略详情"""
    service = ContentStrategyService(db)
    strategy = await service.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    return _strategy_to_item(strategy, service)


@router.put(
    "/{strategy_id}", response_model=ContentStrategyItem, summary="更新关键词策略"
)
async def update_strategy(
    strategy_id: int,
    data: ContentStrategyUpdate,
    db: AsyncSessionDep,
):
    """更新关键词策略"""
    service = ContentStrategyService(db)

    # 处理 node_pools（v3 新结构，转换 Pydantic 对象为 dict）
    node_pools = None
    if data.node_pools is not None:
        node_pools = {
            dim_type: pool.model_dump() for dim_type, pool in data.node_pools.items()
        }

    # 处理 defined_combinations（使用 is not None 来区分空数组和 None）
    defined_combos = None
    if data.defined_combinations is not None:
        defined_combos = [c.model_dump() for c in data.defined_combinations]

    strategy = await service.update_strategy(
        strategy_id=strategy_id,
        name=data.name,
        description=data.description,
        node_pools=node_pools,
        defined_combinations=defined_combos,
        max_combinations=data.max_combinations,
        settings=data.settings.model_dump() if data.settings else None,
        scope_context=data.scope_context.model_dump() if data.scope_context else None,
        tags=data.tags,
        is_active=data.is_active,
    )
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    return _strategy_to_item(strategy, service)


@router.delete("/{strategy_id}", summary="删除关键词策略")
async def delete_strategy(
    strategy_id: int,
    db: AsyncSessionDep,
):
    """删除关键词策略（软删除）"""
    service = ContentStrategyService(db)
    success = await service.delete_strategy(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="策略不存在")
    return {"message": "删除成功"}


class CopyStrategyRequest(BaseModel):
    """复制策略请求"""

    new_name: Optional[str] = Field(
        None, description="新策略名称（默认添加'(副本)'后缀）"
    )
    new_description: Optional[str] = Field(None, description="新策略描述")


@router.post(
    "/{strategy_id}/copy", response_model=ContentStrategyItem, summary="复制关键词策略"
)
async def copy_strategy(
    strategy_id: int,
    db: AsyncSessionDep,
    data: CopyStrategyRequest = None,
):
    """
    复制关键词策略

    复制源策略的所有配置，创建一个新的策略副本。
    可用于快速创建新活动的策略配置。
    """
    service = ContentStrategyService(db)
    try:
        new_strategy = await service.copy_strategy(
            strategy_id=strategy_id,
            new_name=data.new_name if data else None,
            new_description=data.new_description if data else None,
        )
        return _strategy_to_item(new_strategy, service)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== 组合获取（v2 新接口）====================


@router.get(
    "/{strategy_id}/combinations",
    response_model=GetCombinationsResponse,
    summary="获取策略组合列表",
)
async def get_combinations(
    strategy_id: int,
    db: AsyncSessionDep,
    include_corpus: bool = Query(True, description="是否包含语料"),
):
    """
    获取策略的组合列表

    - cartesian 模式：返回笛卡尔积生成的所有组合
    - manual 模式：返回手动定义的组合
    """
    service = ContentStrategyService(db)
    try:
        result = await service.get_combinations(
            strategy_id=strategy_id,
            include_corpus=include_corpus,
        )
        return GetCombinationsResponse(
            strategy_id=result["strategy_id"],
            strategy_name=result["strategy_name"],
            combination_mode=result["combination_mode"],
            total_count=result["total_count"],
            combinations=result["combinations"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== 多策略合并（strategy_v3）====================


@router.post(
    "/merge-combinations",
    response_model=MergeStrategyCombinationsResponse,
    summary="合并多策略组合",
)
async def merge_strategy_combinations(
    data: MergeStrategyCombinationsRequest,
    db: AsyncSessionDep,
):
    """
    合并多个策略的组合（笛卡尔积）

    用于 strategy_v3 模式：一篇文章同时应用多个策略的参数。

    **注意**：
    - 多个策略的维度不能重叠，否则返回错误
    - 合并组合数量有上限（默认100，可配置）

    **采样模式**：
    - `first`: 智能控制，取前N个组合（兼容旧逻辑）
    - `primary_first`: 主维度优先（合并维度），确保每个主维度组合都被均匀使用

    **示例**：
    - 策略A（维度：卖点）+ 策略B（维度：人设+场景）
    - 合并后：每个组合包含 卖点+人设+场景 三个维度
    """
    service = ContentStrategyService(db)
    try:
        # 转换请求数据
        strategy_selections = [
            {
                "strategy_id": s.strategy_id,
                "selected_combo_ids": s.selected_combo_ids,
            }
            for s in data.strategy_selections
        ]

        result = await service.merge_strategy_combinations(
            strategy_selections=strategy_selections,
            include_corpus=data.include_corpus,
            target_count=data.target_count,
            sample_mode=data.sample_mode,
            primary_strategy_id=data.primary_strategy_id,
        )

        return MergeStrategyCombinationsResponse(
            merged_dimensions=result["merged_dimensions"],
            dimension_conflicts=result["dimension_conflicts"],
            source_strategies=result["source_strategies"],
            total_count=result["total_count"],
            merged_combinations=result["merged_combinations"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== 旧版接口（保留向后兼容）====================


@router.post(
    "/{strategy_id}/generate",
    response_model=GenerateCombinationsResponse,
    summary="生成关键词组合（已废弃）",
    deprecated=True,
)
async def generate_combinations(
    strategy_id: int,
    data: GenerateCombinationsRequest,
    db: AsyncSessionDep,
):
    """
    根据策略生成关键词组合

    ⚠️ **已废弃**，请使用 GET /{strategy_id}/combinations

    该接口将在 v3 版本中移除
    """
    service = ContentStrategyService(db)
    try:
        result = await service.generate_combinations(
            strategy_id=strategy_id,
            count=data.count,
            overrides=data.overrides,
        )
        response = GenerateCombinationsResponse(
            strategy_id=result["strategy_id"],
            strategy_name=result["strategy_name"],
            total_count=result["total_count"],
            combinations=result["combinations"],
        )
        # 添加 deprecation warning 响应头
        return Response(
            content=response.model_dump_json(),
            media_type="application/json",
            headers={
                "X-Deprecated": "true",
                "X-Deprecation-Message": "This endpoint is deprecated. Use GET /{strategy_id}/combinations instead.",
                "X-Removal-Version": "v3",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
