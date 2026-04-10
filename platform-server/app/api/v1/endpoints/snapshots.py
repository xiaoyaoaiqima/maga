"""
配置快照 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.config_snapshot import (
    SnapshotSave,
    SnapshotResponse,
    SnapshotListResponse,
    DraftCheckResponse,
    EntityType,
    SnapshotType
)
from app.services.config_snapshot_service import ConfigSnapshotService


router = APIRouter(prefix="/snapshots", tags=["快照管理"])


@router.post("/draft", response_model=ResponseData[SnapshotResponse])
async def save_draft(
    data: SnapshotSave,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[SnapshotResponse]:
    """
    保存草稿（自动保存）
    - 同一实体只保留一个草稿
    - 新的草稿会覆盖旧的
    """
    service = ConfigSnapshotService(db)
    snapshot = await service.save_draft(
        entity_type=data.entity_type,
        entity_code=data.entity_code,
        content=data.content,
        entity_id=data.entity_id
    )
    
    return ResponseData(
        message="草稿已保存",
        data=SnapshotResponse.model_validate(snapshot)
    )


@router.get("/draft/{entity_type}/{entity_code}", response_model=ResponseData[DraftCheckResponse])
async def get_draft(
    entity_type: EntityType,
    entity_code: str,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[DraftCheckResponse]:
    """
    获取草稿
    - 用于检查是否有未完成的编辑
    """
    service = ConfigSnapshotService(db)
    draft = await service.get_draft(entity_type, entity_code)
    
    if draft:
        return ResponseData(
            data=DraftCheckResponse(
                has_draft=True,
                draft=SnapshotResponse.model_validate(draft)
            )
        )
    else:
        return ResponseData(
            data=DraftCheckResponse(
                has_draft=False,
                draft=None
            )
        )


@router.delete("/draft/{entity_type}/{entity_code}", response_model=ResponseData[None])
async def delete_draft(
    entity_type: EntityType,
    entity_code: str,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """
    删除草稿
    - 放弃编辑时调用
    """
    service = ConfigSnapshotService(db)
    await service.delete_draft(entity_type, entity_code)
    
    return ResponseData(
        message="草稿已删除",
        data=None
    )


@router.post("/version", response_model=ResponseData[SnapshotResponse])
async def create_version(
    data: SnapshotSave,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[SnapshotResponse]:
    """
    创建版本快照
    - 正式保存时调用
    - 自动递增版本号
    """
    if not data.entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entity_id is required for version snapshot"
        )
    
    service = ConfigSnapshotService(db)
    snapshot = await service.create_version(
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        entity_code=data.entity_code,
        content=data.content,
        description=data.description
    )
    
    return ResponseData(
        message="版本快照已创建",
        data=SnapshotResponse.model_validate(snapshot)
    )


@router.get("/versions/{entity_type}/{entity_code}", response_model=ResponseData[SnapshotListResponse])
async def get_versions(
    entity_type: EntityType,
    entity_code: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[SnapshotListResponse]:
    """
    获取版本历史
    - 按版本号倒序排列
    """
    service = ConfigSnapshotService(db)
    versions = await service.get_versions(entity_type, entity_code, limit)
    total = await service.get_version_count(entity_type, entity_code)
    
    return ResponseData(
        data=SnapshotListResponse(
            items=[SnapshotResponse.model_validate(v) for v in versions],
            total=total
        )
    )


@router.get("/{snapshot_id}", response_model=ResponseData[SnapshotResponse])
async def get_snapshot(
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[SnapshotResponse]:
    """
    获取指定快照详情
    """
    service = ConfigSnapshotService(db)
    snapshot = await service.get_snapshot_by_id(snapshot_id)
    
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot not found"
        )
    
    return ResponseData(
        data=SnapshotResponse.model_validate(snapshot)
    )

