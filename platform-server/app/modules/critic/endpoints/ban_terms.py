"""
BAN 词表管理（ag 内部接口）

说明：
- 该接口默认只在集群内使用（由 orchestrator 代理对外暴露）
- 不在 ag 侧做权限校验，权限由 orchestrator 统一控制
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.sys_user import SysUser
from app.schemas.base import PageInfo, ResponseData
from app.schemas.ban_term import (
    BanTermCreate,
    BanTermItem,
    BanTermListQuery,
    BanTermListResponse,
    BanTermMetaResponse,
    BanTermOptionsResponse,
    BanTermUpdate,
)
from app.services import ban_term_service
from app.services.keyword_filter_service import get_keyword_filter_service

router = APIRouter(prefix="/keyword-corpus/ban-terms", tags=["keyword-corpus"])


async def get_username_by_id(*, session: AsyncSession, user_id: str) -> Optional[str]:
    """根据用户 ID 获取用户名"""
    if not user_id or user_id == "system":
        return user_id
    result = await session.execute(select(SysUser.username).where(SysUser.id == user_id))
    return result.scalar()


# ========== 固定路径路由必须在动态路径 /{term_id} 之前 ==========

@router.get("/options", response_model=ResponseData[BanTermOptionsResponse])
async def get_ban_terms_options(
    db: AsyncSession = Depends(get_db),
):
    """获取筛选选项（分类、名单类型）"""
    options = await ban_term_service.get_options(session=db)
    return ResponseData(
        code=200,
        message="success",
        data=BanTermOptionsResponse(**options),
    )


@router.get("/meta", response_model=ResponseData[BanTermMetaResponse])
async def get_ban_terms_meta(
    db: AsyncSession = Depends(get_db),
):
    active_version, whitelist_count, blacklist_count = await ban_term_service.get_meta(session=db)
    return ResponseData(
        code=200,
        message="success",
        data=BanTermMetaResponse(
            active_version=active_version,
            whitelist_count=whitelist_count,
            blacklist_count=blacklist_count,
        ),
    )


@router.post("/publish", response_model=ResponseData[dict])
async def publish_ban_terms(
    operator: Optional[str] = Query("system", description="操作者"),
    db: AsyncSession = Depends(get_db),
):
    active_version = await ban_term_service.publish(session=db, operator=operator or "system")
    # 立即刷新 KeywordFilterService 缓存，使更新立即生效
    keyword_filter_service = get_keyword_filter_service()
    await keyword_filter_service.refresh_from_db(session=db)
    return ResponseData(code=200, message="success", data={"active_version": active_version})


# ========== 列表/创建 ==========

@router.get("", response_model=ResponseData[BanTermListResponse])
async def list_ban_terms(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    tenant_code: Optional[str] = Query(None, description="租户编码"),
    keyword: Optional[str] = Query(None),
    list_type: Optional[str] = Query(None, description="WHITELIST/BLACKLIST"),
    category: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = BanTermListQuery(
        page=page,
        page_size=page_size,
        tenant_code=tenant_code,
        keyword=keyword,
        list_type=list_type,  # type: ignore[arg-type]
        category=category,
        enabled=enabled,
    )
    items, total = await ban_term_service.list_terms(session=db, query=query)
    total_pages = int((total + page_size - 1) // page_size) if page_size else 1
    return ResponseData(
        code=200,
        message="success",
        data=BanTermListResponse(
            items=[BanTermItem.model_validate(i) for i in items],
            page_info=PageInfo(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        ),
    )


@router.post("", response_model=ResponseData[BanTermItem])
async def create_ban_term(
    payload: BanTermCreate,
    operator: Optional[str] = Query("system", description="操作者"),
    db: AsyncSession = Depends(get_db),
):
    try:
        obj = await ban_term_service.create_term(session=db, payload=payload, operator=operator or "system")
        # 自动发布，使新词条立即生效（触发缓存刷新）
        await ban_term_service.publish(session=db, operator=operator or "system")
        # 立即刷新 KeywordFilterService 缓存，使更新立即生效
        keyword_filter_service = get_keyword_filter_service()
        await keyword_filter_service.refresh_from_db(session=db)
        # get_db 依赖会自动 commit，无需手动调用
        # 查询用户名并映射字段
        created_by_name = await get_username_by_id(session=db, user_id=obj.created_by)
        updated_by_name = await get_username_by_id(session=db, user_id=obj.updated_by)
        item_dict = {
            "id": obj.id,
            "tenant_code": obj.tenant_code,
            "term": obj.term,
            "list_type": obj.list_type,
            "category": obj.category,
            "enabled": obj.enabled,
            "created_by_name": created_by_name,
            "updated_by_name": updated_by_name,
            "create_time": obj.create_time,
            "update_time": obj.update_time,
        }
        return ResponseData(code=200, message="success", data=BanTermItem.model_validate(item_dict))
    except ValueError as e:
        # get_db 依赖会自动 rollback，但显式处理更清晰
        raise HTTPException(status_code=400, detail=str(e))


# ========== 动态路径路由 /{term_id} 放最后 ==========

@router.put("/{term_id}", response_model=ResponseData[BanTermItem])
async def update_ban_term(
    term_id: int,
    payload: BanTermUpdate,
    operator: Optional[str] = Query("system", description="操作者"),
    db: AsyncSession = Depends(get_db),
):
    try:
        obj = await ban_term_service.update_term(session=db, term_id=term_id, payload=payload, operator=operator or "system")
        if obj is None:
            raise HTTPException(status_code=404, detail="词条不存在")
        # 自动发布，使更新立即生效（触发缓存刷新）
        await ban_term_service.publish(session=db, operator=operator or "system")
        # 立即刷新 KeywordFilterService 缓存，使更新立即生效
        keyword_filter_service = get_keyword_filter_service()
        await keyword_filter_service.refresh_from_db(session=db)
        # get_db 依赖会自动 commit，无需手动调用
        # 查询用户名并映射字段
        created_by_name = await get_username_by_id(session=db, user_id=obj.created_by)
        updated_by_name = await get_username_by_id(session=db, user_id=obj.updated_by)
        item_dict = {
            "id": obj.id,
            "tenant_code": obj.tenant_code,
            "term": obj.term,
            "list_type": obj.list_type,
            "category": obj.category,
            "enabled": obj.enabled,
            "created_by_name": created_by_name,
            "updated_by_name": updated_by_name,
            "create_time": obj.create_time,
            "update_time": obj.update_time,
        }
        return ResponseData(code=200, message="success", data=BanTermItem.model_validate(item_dict))
    except ValueError as e:
        # get_db 依赖会自动 rollback，但显式处理更清晰
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{term_id}", response_model=ResponseData[dict])
async def delete_ban_term(
    term_id: int,
    operator: Optional[str] = Query("system", description="操作者"),
    db: AsyncSession = Depends(get_db),
):
    ok = await ban_term_service.delete_term(session=db, term_id=term_id, operator=operator or "system")
    if not ok:
        raise HTTPException(status_code=404, detail="词条不存在")
    # 自动发布，使删除立即生效（触发缓存刷新）
    await ban_term_service.publish(session=db, operator=operator or "system")
    # 立即刷新 KeywordFilterService 缓存，使更新立即生效
    keyword_filter_service = get_keyword_filter_service()
    await keyword_filter_service.refresh_from_db(session=db)
    # get_db 依赖会自动 commit，无需手动调用
    return ResponseData(code=200, message="success", data={"deleted": True})

