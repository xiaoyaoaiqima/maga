"""
上线管理 API

提供实体上线/下线管理功能，包括：
- Activity/Agent 上线/下线
- 上线预检查
- 编辑/删除权限检查
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.services.publish_service import (
    PublishService,
    PublishStatus,
    EntityType,
)
from app.schemas.base import ResponseModel


router = APIRouter(prefix="/publish", tags=["上线管理"])


# ==================== 请求/响应模型 ====================

class PublishRequest(BaseModel):
    """上线请求"""
    operator: str = Field(..., description="操作人")


class UnpublishRequest(BaseModel):
    """下线请求"""
    operator: str = Field(..., description="操作人")


class ModifyCheckRequest(BaseModel):
    """编辑/删除检查请求"""
    entity_type: str = Field(
        ..., 
        description="实体类型：Activity/Agent/ExpertConfig/Plugin/PluginContext"
    )
    entity_id: str = Field(..., description="实体 ID 或编码")


# ==================== 依赖注入 ====================

def get_publish_service(db: AsyncSession = Depends(get_db)) -> PublishService:
    """获取上线管理服务实例"""
    return PublishService(db)


# ==================== Activity 上线/下线 ====================

@router.post(
    "/activity/{activity_id}/publish", 
    response_model=ResponseModel, 
    summary="上线 Activity"
)
async def publish_activity(
    activity_id: int,
    request: PublishRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    上线 Activity 及其所有依赖
    
    - 级联上线关联的 Agent、ExpertConfig、Plugin、PluginContext
    - 上线后的实体不可编辑和删除
    
    **参数**：
    - **activity_id**: Activity ID
    - **operator**: 操作人
    """
    try:
        logger.info(f"上线 Activity: activity_id={activity_id}, operator={request.operator}")
        
        result = await service.publish_activity(activity_id, request.operator)
        
        if result.success:
            return ResponseModel(
                code=200, 
                message=result.message, 
                data=result.to_dict()
            )
        else:
            return ResponseModel(
                code=400, 
                message=result.message, 
                data=result.to_dict()
            )
            
    except Exception as e:
        logger.error(f"上线 Activity 异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上线失败: {str(e)}")


@router.post(
    "/activity/{activity_id}/unpublish", 
    response_model=ResponseModel, 
    summary="下线 Activity"
)
async def unpublish_activity(
    activity_id: int,
    request: UnpublishRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    下线 Activity
    
    - 下线后可以编辑和删除 Activity
    - 不影响下层实体（Agent、ExpertConfig 等保持上线状态）
    
    **参数**：
    - **activity_id**: Activity ID
    - **operator**: 操作人
    """
    try:
        logger.info(f"下线 Activity: activity_id={activity_id}, operator={request.operator}")
        
        result = await service.unpublish_activity(activity_id, request.operator)
        
        if result.success:
            return ResponseModel(
                code=200, 
                message=result.message, 
                data=result.to_dict()
            )
        else:
            return ResponseModel(
                code=400, 
                message=result.message, 
                data=result.to_dict()
            )
            
    except Exception as e:
        logger.error(f"下线 Activity 异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下线失败: {str(e)}")


@router.get(
    "/activity/{activity_id}/preview", 
    response_model=ResponseModel, 
    summary="预检查 Activity 上线"
)
async def preview_publish_activity(
    activity_id: int,
    service: PublishService = Depends(get_publish_service)
):
    """
    预检查 Activity 上线（不实际执行）
    
    返回：
    - 是否可以上线
    - 依赖清单（Agent、ExpertConfig、Plugin、PluginContext）
    - 验证结果（错误和警告）
    
    **参数**：
    - **activity_id**: Activity ID
    """
    try:
        logger.info(f"预检查 Activity 上线: activity_id={activity_id}")
        
        result = await service.preview_publish_activity(activity_id)
        
        return ResponseModel(
            code=200 if result.get("can_publish") else 400,
            message="可以上线" if result.get("can_publish") else "无法上线",
            data=result
        )
        
    except Exception as e:
        logger.error(f"预检查 Activity 上线异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"预检查失败: {str(e)}")


# ==================== Agent 上线/下线 ====================

@router.post(
    "/agent/{agent_code}/publish", 
    response_model=ResponseModel, 
    summary="上线 Agent"
)
async def publish_agent(
    agent_code: str,
    request: PublishRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    上线 Agent 及其依赖（不上线 Activity）
    
    - 级联上线关联的 ExpertConfig、Plugin、PluginContext
    - 上线后的实体不可编辑和删除
    
    **参数**：
    - **agent_code**: Agent 编码
    - **operator**: 操作人
    """
    try:
        logger.info(f"上线 Agent: agent_code={agent_code}, operator={request.operator}")
        
        result = await service.publish_agent(agent_code, request.operator)
        
        if result.success:
            return ResponseModel(
                code=200, 
                message=result.message, 
                data=result.to_dict()
            )
        else:
            return ResponseModel(
                code=400, 
                message=result.message, 
                data=result.to_dict()
            )
            
    except Exception as e:
        logger.error(f"上线 Agent 异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上线失败: {str(e)}")


@router.post(
    "/agent/{agent_code}/unpublish", 
    response_model=ResponseModel, 
    summary="下线 Agent"
)
async def unpublish_agent(
    agent_code: str,
    request: UnpublishRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    下线 Agent
    
    - 需要先下线所有引用该 Agent 的已上线 Activity
    - 下线后可以编辑和删除 Agent
    - 不影响下层实体（ExpertConfig 等保持上线状态）
    
    **参数**：
    - **agent_code**: Agent 编码
    - **operator**: 操作人
    """
    try:
        logger.info(f"下线 Agent: agent_code={agent_code}, operator={request.operator}")
        
        result = await service.unpublish_agent(agent_code, request.operator)
        
        if result.success:
            return ResponseModel(
                code=200, 
                message=result.message, 
                data=result.to_dict()
            )
        else:
            return ResponseModel(
                code=400, 
                message=result.message, 
                data=result.to_dict()
            )
            
    except Exception as e:
        logger.error(f"下线 Agent 异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下线失败: {str(e)}")


# ==================== ExpertConfig/Plugin/PluginContext（只上不下） ====================

@router.post(
    "/expert-config/{expert_config_code}/unpublish", 
    response_model=ResponseModel, 
    summary="下线 ExpertConfig（不支持）"
)
async def unpublish_expert_config(
    expert_config_code: str,
    request: UnpublishRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    ExpertConfig 不支持下线
    
    ExpertConfig 是底层配置，可能被多个上层实体共享，下线会影响所有依赖方。
    如需修改，请创建新版本。
    """
    result = await service.unpublish_expert_config(expert_config_code, request.operator)
    return ResponseModel(
        code=400, 
        message=result.message, 
        data=result.to_dict()
    )


@router.post(
    "/plugin/{plugin_code}/unpublish", 
    response_model=ResponseModel, 
    summary="下线 Plugin（不支持）"
)
async def unpublish_plugin(
    plugin_code: str,
    request: UnpublishRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    Plugin 不支持下线
    
    Plugin 是底层配置，可能被多个上层实体共享，下线会影响所有依赖方。
    如需修改，请创建新版本。
    """
    result = await service.unpublish_plugin(plugin_code, request.operator)
    return ResponseModel(
        code=400, 
        message=result.message, 
        data=result.to_dict()
    )


@router.post(
    "/plugin-context/{context_name}/unpublish", 
    response_model=ResponseModel, 
    summary="下线 PluginContext（不支持）"
)
async def unpublish_plugin_context(
    context_name: str,
    request: UnpublishRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    PluginContext 不支持下线
    
    PluginContext 是底层配置，可能被多个上层实体共享，下线会影响所有依赖方。
    如需修改，请创建新版本。
    """
    result = await service.unpublish_plugin_context(context_name, request.operator)
    return ResponseModel(
        code=400, 
        message=result.message, 
        data=result.to_dict()
    )


# ==================== 编辑/删除权限检查 ====================

@router.get(
    "/can-modify", 
    response_model=ResponseModel, 
    summary="检查实体是否可以编辑/删除"
)
async def check_can_modify(
    entity_type: str = Query(
        ..., 
        description="实体类型：Activity/Agent/ExpertConfig/Plugin/PluginContext"
    ),
    entity_id: str = Query(..., description="实体 ID 或编码"),
    service: PublishService = Depends(get_publish_service)
):
    """
    检查实体是否可以编辑/删除
    
    返回结果：
    - **allowed**: 是否允许操作
    - **action**: 操作建议
      - `reject`: 直接拒绝（已上线）
      - `confirm`: 需要用户确认（有引用关系）
      - `allow`: 直接允许
    - **reason**: 原因说明
    - **references**: 引用列表（仅当 action=confirm 时）
    
    **参数**：
    - **entity_type**: 实体类型
    - **entity_id**: 实体 ID 或编码
    """
    try:
        # 验证 entity_type
        valid_types = [e.value for e in EntityType]
        if entity_type not in valid_types:
            return ResponseModel(
                code=400,
                message=f"无效的实体类型，有效值: {', '.join(valid_types)}",
                data=None
            )
        
        result = await service.check_can_modify(entity_type, entity_id)
        
        return ResponseModel(
            code=200 if result.allowed else 403,
            message=result.reason if result.reason else "允许操作",
            data=result.to_dict()
        )
        
    except Exception as e:
        logger.error(f"检查编辑权限异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")


@router.post(
    "/can-modify", 
    response_model=ResponseModel, 
    summary="检查实体是否可以编辑/删除（POST）"
)
async def check_can_modify_post(
    request: ModifyCheckRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    检查实体是否可以编辑/删除（POST 版本）
    
    与 GET 版本功能相同，适用于复杂参数场景。
    """
    try:
        # 验证 entity_type
        valid_types = [e.value for e in EntityType]
        if request.entity_type not in valid_types:
            return ResponseModel(
                code=400,
                message=f"无效的实体类型，有效值: {', '.join(valid_types)}",
                data=None
            )
        
        result = await service.check_can_modify(request.entity_type, request.entity_id)
        
        return ResponseModel(
            code=200 if result.allowed else 403,
            message=result.reason if result.reason else "允许操作",
            data=result.to_dict()
        )
        
    except Exception as e:
        logger.error(f"检查编辑权限异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")


# ==================== 上线状态查询 ====================

@router.get(
    "/status", 
    response_model=ResponseModel, 
    summary="查询实体上线状态"
)
async def get_publish_status(
    entity_type: str = Query(
        ..., 
        description="实体类型：Activity/Agent/ExpertConfig/Plugin/PluginContext"
    ),
    entity_id: str = Query(..., description="实体 ID 或编码"),
    service: PublishService = Depends(get_publish_service)
):
    """
    查询实体的上线状态
    
    返回：
    - **publish_status**: DRAFT（草稿）/ PUBLISHED（已上线）
    - **is_published**: 是否已上线
    
    **参数**：
    - **entity_type**: 实体类型
    - **entity_id**: 实体 ID 或编码
    """
    try:
        # 验证 entity_type
        valid_types = [e.value for e in EntityType]
        if entity_type not in valid_types:
            return ResponseModel(
                code=400,
                message=f"无效的实体类型，有效值: {', '.join(valid_types)}",
                data=None
            )
        
        status = await service.get_publish_status(entity_type, entity_id)
        
        if status is None:
            return ResponseModel(
                code=404,
                message=f"{entity_type} 不存在",
                data=None
            )
        
        return ResponseModel(
            code=200,
            message="success",
            data={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "publish_status": status,
                "is_published": status == PublishStatus.PUBLISHED.value,
            }
        )
        
    except Exception as e:
        logger.error(f"查询上线状态异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ==================== 批量查询上线状态 ====================

class BatchStatusRequest(BaseModel):
    """批量查询上线状态请求"""
    entities: list = Field(
        ..., 
        description="实体列表，格式: [{entity_type, entity_id}, ...]"
    )


@router.post(
    "/status/batch", 
    response_model=ResponseModel, 
    summary="批量查询实体上线状态"
)
async def get_publish_status_batch(
    request: BatchStatusRequest,
    service: PublishService = Depends(get_publish_service)
):
    """
    批量查询实体的上线状态
    
    **请求体**：
    ```json
    {
      "entities": [
        {"entity_type": "Activity", "entity_id": "1"},
        {"entity_type": "Agent", "entity_id": "agent_code_001"}
      ]
    }
    ```
    """
    try:
        results = []
        valid_types = [e.value for e in EntityType]
        
        for entity in request.entities:
            entity_type = entity.get("entity_type")
            entity_id = entity.get("entity_id")
            
            if entity_type not in valid_types:
                results.append({
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "error": f"无效的实体类型"
                })
                continue
            
            status = await service.get_publish_status(entity_type, entity_id)
            
            if status is None:
                results.append({
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "error": "实体不存在"
                })
            else:
                results.append({
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "publish_status": status,
                    "is_published": status == PublishStatus.PUBLISHED.value,
                })
        
        return ResponseModel(
            code=200,
            message="success",
            data=results
        )
        
    except Exception as e:
        logger.error(f"批量查询上线状态异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")



