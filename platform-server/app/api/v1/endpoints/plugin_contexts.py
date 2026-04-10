"""
PluginContext endpoints
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.plugin_context import PluginContextCreate, PluginContextResponse, PluginContextUpdate
from app.schemas.config_snapshot import EntityType
from app.services.plugin_context_service import PluginContextService
from app.services.config_snapshot_service import ConfigSnapshotService

router = APIRouter()


@router.post("", response_model=ResponseData[PluginContextResponse])
async def create_plugin_context(
    context_in: PluginContextCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PluginContextResponse]:
    """Create new plugin_context"""
    service = PluginContextService(db)
    snapshot_service = ConfigSnapshotService(db)
    
    context = await service.create(context_in)
    
    # 创建初始版本快照（使用 variable_name + context_name 作为唯一标识）
    if context.variable_name and context.context_name:
        entity_code = f"{context.variable_name}:{context.context_name}"
        await snapshot_service.create_version(
            entity_type=EntityType.PLUGIN_CONTEXT,
            entity_id=context.id,
            entity_code=entity_code,
            content=PluginContextResponse.model_validate(context).model_dump(mode='json'),
            description="初始版本"
        )
    
    return ResponseData(
        code=200,
        message="创建成功",
        data=PluginContextResponse.model_validate(context)
    )


@router.get("/{context_id}", response_model=ResponseData[PluginContextResponse])
async def get_plugin_context(
    context_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PluginContextResponse]:
    """Get plugin_context by ID"""
    service = PluginContextService(db)
    context = await service.get(context_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PluginContext not found"
        )

    return ResponseData(
        data=PluginContextResponse.model_validate(context)
    )


@router.get("", response_model=ResponseData[list[PluginContextResponse]])
async def list_plugin_contexts(
    variable_name: Optional[str] = Query(None, description="Filter by variable_name"),
    context_name: Optional[str] = Query(None, description="Filter by context_name"),
    skip: int = 0,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[PluginContextResponse]]:
    """List all plugin_contexts"""
    service = PluginContextService(db)
    contexts = await service.list(
        variable_name=variable_name,
        context_name=context_name,
        skip=skip,
        limit=limit
    )

    return ResponseData(
        data=[PluginContextResponse.model_validate(context) for context in contexts]
    )


@router.put("/{context_id}", response_model=ResponseData[PluginContextResponse])
async def update_plugin_context(
    context_id: int,
    context_in: PluginContextUpdate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PluginContextResponse]:
    """Update plugin_context"""
    service = PluginContextService(db)
    snapshot_service = ConfigSnapshotService(db)
    
    context = await service.update(context_id, context_in)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PluginContext not found"
        )

    # 创建版本快照（使用 variable_name + context_name 作为唯一标识）
    if context.variable_name and context.context_name:
        entity_code = f"{context.variable_name}:{context.context_name}"
        await snapshot_service.create_version(
            entity_type=EntityType.PLUGIN_CONTEXT,
            entity_id=context.id,
            entity_code=entity_code,
            content=PluginContextResponse.model_validate(context).model_dump(mode='json'),
            description=None  # 自动生成版本号描述
        )

    return ResponseData(
        message="PluginContext updated successfully",
        data=PluginContextResponse.model_validate(context)
    )


@router.delete("/{context_id}", response_model=ResponseData[None])
async def delete_plugin_context(
    context_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """Delete plugin_context"""
    service = PluginContextService(db)
    success = await service.delete(context_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PluginContext not found"
        )

    return ResponseData(
        message="PluginContext deleted successfully"
    )

