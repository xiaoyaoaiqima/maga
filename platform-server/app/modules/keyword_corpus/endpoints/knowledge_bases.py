"""
知识库 API - 知识库容器管理

KnowledgeBase 是文档的集合/容器概念，用于组织和管理多个上传文件
一个 KnowledgeBase 可以包含多个 KnowledgeBaseFile（上传的文件）

注意：知识库文件只是纯粹的文件容器，与关键词类型无关
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.schemas.base import ResponseData
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseItem,
    KnowledgeBaseListQuery,
    KnowledgeBaseUpdate,
)
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.knowledge_base_file_service import KnowledgeBaseFileService

router = APIRouter(prefix="/knowledge-bases", tags=["知识库"])
logger = logging.getLogger(__name__)


@router.get("", summary="获取知识库列表")
async def get_knowledge_bases(
    db: AsyncSessionDep,
    keyword: Optional[str] = Query(None, description="搜索名称/编码"),
    enabled: Optional[bool] = Query(None, description="启用状态筛选"),
):
    """获取知识库列表"""
    service = KnowledgeBaseService(db)
    items = await service.get_list(keyword=keyword, enabled=enabled)
    return ResponseData(
        data={"items": [item.model_dump() for item in items], "total": len(items)}
    )


@router.get("/{pool_id}", summary="获取知识库详情")
async def get_knowledge_base(
    pool_id: int,
    db: AsyncSessionDep,
):
    """获取单个知识库详情"""
    service = KnowledgeBaseService(db)
    item = await service.get_by_id(pool_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"知识库 {pool_id} 不存在")

    # 获取关联的文件列表（不再按 tenant_code 过滤）
    file_service = KnowledgeBaseFileService(db)
    files = await file_service.get_by_knowledge_base(pool_id)

    return ResponseData(
        data={
            "pool": item.model_dump(),
            "files": [f.model_dump() for f in files],
        }
    )


@router.post("", summary="创建知识库")
async def create_knowledge_base(
    data: KnowledgeBaseCreate,
    db: AsyncSessionDep,
):
    """创建新的知识库"""
    logger.info(f"[KEYWORD-CORPUS] 创建知识库请求 - name: {data.name}, full: {data.model_dump()}")
    service = KnowledgeBaseService(db)
    try:
        item = await service.create(data)
        return ResponseData(data=item.model_dump(), message="知识库创建成功")
    except ValueError as e:
        logger.error(f"创建知识库业务错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建知识库失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {str(e)}")


@router.put("/{pool_id}", summary="更新知识库")
async def update_knowledge_base(
    pool_id: int,
    data: KnowledgeBaseUpdate,
    db: AsyncSessionDep,
):
    """更新知识库信息"""
    service = KnowledgeBaseService(db)
    item = await service.update(pool_id, data)
    if not item:
        raise HTTPException(status_code=404, detail=f"知识库 {pool_id} 不存在")
    return ResponseData(data=item.model_dump(), message="知识库更新成功")


@router.delete("/{pool_id}", summary="删除知识库")
async def delete_knowledge_base(
    pool_id: int,
    db: AsyncSessionDep,
):
    """删除知识库（软删除）"""
    service = KnowledgeBaseService(db)
    success = await service.delete(pool_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"知识库 {pool_id} 不存在")
    return ResponseData(data=None, message="知识库删除成功")


@router.put("/{pool_id}/toggle", summary="切换启用状态")
async def toggle_knowledge_base_enabled(
    pool_id: int,
    db: AsyncSessionDep,
):
    """切换知识库启用状态"""
    service = KnowledgeBaseService(db)
    item = await service.toggle_enabled(pool_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"知识库 {pool_id} 不存在")
    return ResponseData(data=item.model_dump(), message="启用状态已更新")


@router.get("/{pool_id}/files", summary="获取知识库下的文件列表")
async def get_knowledge_base_files(
    pool_id: int,
    db: AsyncSessionDep,
):
    """获取知识库下的所有文件"""
    # 先验证知识库是否存在
    pool_service = KnowledgeBaseService(db)
    pool = await pool_service.get_by_id(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail=f"知识库 {pool_id} 不存在")

    file_service = KnowledgeBaseFileService(db)
    files = await file_service.get_by_knowledge_base(pool_id)

    return ResponseData(
        data={"items": [f.model_dump() for f in files], "total": len(files)}
    )
