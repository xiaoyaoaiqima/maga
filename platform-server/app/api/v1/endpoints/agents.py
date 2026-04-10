"""
Agent 产品管理 API
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_username
from app.services.agent_service import AgentService
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentListResponse,
    AgentFilters,
    AgentSimpleItem,
    AgentTypeEnum,
    AgentListRequest,
    AgentListResponseData,
    AgentCopyRequest,
    AgentTagResponse,
    AgentTagUpdate,
    AgentInfoUpdate,
)
from app.core.logger import logger
from app.schemas.base import ResponseModel

router = APIRouter(prefix="/agents", tags=["Agent 产品管理"])


def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    """获取 Agent 服务实例"""
    return AgentService(db)


@router.post("", response_model=ResponseModel, summary="创建 Agent")
async def create_agent(
    data: AgentCreate,
    service: AgentService = Depends(get_agent_service),
    username: str = Depends(get_current_username)
):
    """
    创建 Agent 产品

    - **agent_code**: Agent 编码（唯一）
    - **agent_name**: Agent 名称
    - **agent_type**: 类型（BATCH_GENERATION/REALTIME_CHAT/REPORT_ANALYSIS）
    - **expert_config_code_list**: Expert 编排顺序
    - **default_model_code**: 默认模型编码
    - **default_config**: 默认参数配置
    - **description**: 功能描述
    - **input_schema**: 输入参数 schema
    - **output_schema**: 输出格式 schema
    - **tenant_id**: 租户ID（NULL 表示全局共享）
    - **rate_limit**: 限流配置
    """
    try:
        agent = await service.create_agent(data, created_by=username)
        return ResponseModel(code=200, message="创建成功", data=agent.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=ResponseModel, summary="获取 Agent 列表")
async def list_agents(
    agent_code: Optional[str] = Query(None, description="Agent 编码（模糊匹配）"),
    agent_name: Optional[str] = Query(None, description="Agent 名称（模糊匹配）"),
    agent_type: Optional[str] = Query(None, description="Agent 类型"),
    tenant_id: Optional[int] = Query(None, description="租户ID（含全局共享）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    service: AgentService = Depends(get_agent_service)
):
    """获取 Agent 列表（分页）"""
    filters = AgentFilters(
        agent_code=agent_code,
        agent_name=agent_name,
        agent_type=agent_type,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size
    )
    total, items = await service.list_agents(filters)
    return ResponseModel(
        code=200,
        message="success",
        data=AgentListResponse(total=total, items=items).model_dump()
    )


@router.get("/simple", response_model=ResponseModel, summary="获取简单 Agent 列表")
async def list_agents_simple(
    tenant_id: Optional[int] = Query(None, description="租户ID（含全局共享）"),
    service: AgentService = Depends(get_agent_service)
):
    """获取简单 Agent 列表（用于下拉框）"""
    items = await service.list_simple(tenant_id)
    return ResponseModel(
        code=200,
        message="success",
        data=[item.model_dump() for item in items]
    )


@router.get("/types", response_model=ResponseModel, summary="获取 Agent 类型列表")
async def list_agent_types():
    """获取 Agent 类型列表"""
    types = [
        {"value": "BATCH_GENERATION", "label": "批量文章生成", "description": "批量任务（Job → Content）"},
        {"value": "REVIEW_IMAGE", "label": "图片审核", "description": "实时图片审核"},
        {"value": "REALTIME_CHAT", "label": "实时聊天", "description": "实时会话（Session → Message）"},
        {"value": "REPORT_ANALYSIS", "label": "报告分析", "description": "单次分析（Request → Result）"},
    ]
    return ResponseModel(code=200, message="success", data=types)


@router.get("/exists", response_model=ResponseModel, summary="检查 Agent 名称是否存在")
async def check_agent_name_exists(
    agent_name: str = Query(..., description="Agent 名称"),
    exclude_code: Optional[str] = Query(None, description="排除的 Agent 编码"),
    service: AgentService = Depends(get_agent_service),
):
    exists = await service.agent_name_exists(agent_name, exclude_code=exclude_code)
    return ResponseModel(code=200, message="success", data={"exists": exists})


@router.get("/{agent_code}", response_model=ResponseModel, summary="获取 Agent 详情")
async def get_agent(
    agent_code: str,
    service: AgentService = Depends(get_agent_service)
):
    """获取 Agent 详情（按编码）"""
    agent = await service.get_agent_by_code(agent_code)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return ResponseModel(code=200, message="success", data=agent.model_dump())


@router.put("/{agent_code}", response_model=ResponseModel, summary="更新 Agent")
async def update_agent(
    agent_code: str,
    data: AgentUpdate,
    service: AgentService = Depends(get_agent_service),
    username: str = Depends(get_current_username)
):
    """更新 Agent 信息"""
    try:
        agent = await service.update_agent(agent_code, data, updated_by=username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return ResponseModel(code=200, message="更新成功", data=agent.model_dump())


@router.delete("/{agent_code}", response_model=ResponseModel, summary="删除 Agent")
async def delete_agent(
    agent_code: str,
    service: AgentService = Depends(get_agent_service)
):
    """删除 Agent（软删除）"""
    success = await service.delete_agent(agent_code)
    if not success:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return ResponseModel(code=200, message="删除成功")


@router.get("/agent/detail/{agent_id}", response_model=ResponseModel, summary="获取 Agent 详情（按ID）")
async def get_agent_by_id(
    agent_id: int,
    service: AgentService = Depends(get_agent_service)
):
    """
    获取 Agent 详情（按 ID）
    
    - **agent_id**: Agent ID
    """
    try:
        agent = await service.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent 不存在")
        return ResponseModel(code=200, message="success", data=agent.model_dump())
    except Exception as e:
        logger.error(f"获取 Agent 详情异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取 Agent 详情异常: {str(e)}")


# ============== 新增接口 ==============

@router.get("/agent/list", response_model=ResponseModel, summary="获取 Agent 列表（支持筛选）")
async def get_agent_list(
    agent_code: Optional[str] = Query(None, description="Agent 编码（模糊匹配）"),
    agent_name: Optional[str] = Query(None, description="Agent 名称（模糊匹配）"),
    agent_type: Optional[str] = Query(None, description="Agent 类型"),
    remark: Optional[str] = Query(None, description="备注（模糊匹配）"),
    enabled: Optional[bool] = Query(1, description="是否启用"),
    tenant_id: Optional[int] = Query(1, description="租户id"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    service: AgentService = Depends(get_agent_service)
):
    """
    获取 Agent 列表（支持筛选）
    
    - **agent_code**: Agent 编码（模糊匹配，可选）
    - **agent_name**: Agent 名称（模糊匹配，可选）
    - **agent_type**: Agent 类型（可选）
    - **remark**: 备注（模糊匹配，可选）
    - **enabled**: 是否启用（可选）
    - **tenant_id**: 租户名称（模糊匹配，可选）
    - **page**: 页码（默认：1）
    - **page_size**: 每页数量（默认：10，最大：100）
    """
    try:
        request = AgentListRequest(
            agent_code=agent_code,
            agent_name=agent_name,
            agent_type=agent_type,
            remark=remark,
            enabled=enabled,
            tenant_id=tenant_id,
            page=page,
            page_size=page_size
        )
        
        result = await service.get_agent_list(request)
        return ResponseModel(code=200, message="success", data=result.model_dump())
        
    except Exception as e:
        logger.error(f"获取 Agent 列表异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取 Agent 列表异常: {str(e)}")


@router.post("/agent/copy", response_model=ResponseModel, summary="复制 Agent")
async def copy_agent(
    request: AgentCopyRequest,
    service: AgentService = Depends(get_agent_service),
    username: str = Depends(get_current_username)
):
    """
    复制 Agent
    
    创建一个新的 Agent，名称带【复制】与时间戳后缀，并复制所有配置。
    
    - **agent_id**: 要复制的 Agent 编码
    """
    try:
        logger.info(f"复制 Agent: agent_id={request.agent_id}")

        result = await service.copy_agent(request, created_by=username)
        return ResponseModel(code=200, message="复制成功", data=result.model_dump())
        
    except ValueError as e:
        logger.error(f"复制 Agent 失败: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"复制 Agent 异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"复制 Agent 异常: {str(e)}")


@router.get("/agent/get_tags/{agent_id}", response_model=ResponseModel, summary="获取 Agent 标签")
async def get_agent_tags(
    agent_id: int,
    service: AgentService = Depends(get_agent_service)
):
    """
    获取 Agent 的标签配置
    
    - **agent_id**: Agent 编码
    """
    try:
        result = await service.get_agent_tags(agent_id)
        return ResponseModel(code=200, message="success", data=result.model_dump())
        
    except ValueError as e:
        logger.error(f"获取 Agent 标签失败: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取 Agent 标签异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取 Agent 标签异常: {str(e)}")


@router.post("/agent/update_tags/{agent_id}", response_model=ResponseModel, summary="更新 Agent 标签")
async def update_agent_tags(
    agent_id: int,
    request: AgentTagUpdate,
    service: AgentService = Depends(get_agent_service),
    username: str = Depends(get_current_username)
):
    """
    更新 Agent 的标签配置

    - **agent_id**: Agent 编码
    - **tags_config**: 标签配置（JSON格式）
    """
    try:
        logger.info(f"更新 Agent 标签: agent_id={agent_id}")

        result = await service.update_agent_tags(agent_id, request, updated_by=username)
        return ResponseModel(code=200, message="更新成功", data=result.model_dump())
        
    except ValueError as e:
        logger.error(f"更新 Agent 标签失败: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"更新 Agent 标签异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新 Agent 标签异常: {str(e)}")


@router.post("/agent/update_info/{agent_id}", response_model=ResponseModel, summary="更新 Agent 信息")
async def update_agent_info(
    agent_id: int,
    request: AgentInfoUpdate,
    service: AgentService = Depends(get_agent_service),
    username: str = Depends(get_current_username)
):
    """
    更新 Agent 信息（名称和备注）

    - **agent_id**: Agent 编码
    - **agent_name**: Agent 名称（可选）
    - **remark**: 备注（可选）
    """
    try:
        logger.info(f"更新 Agent 信息: agent_id={agent_id}")

        result = await service.update_agent_info(agent_id, request, updated_by=username)
        return ResponseModel(code=200, message="更新成功", data=result.model_dump())
        
    except ValueError as e:
        detail = str(e)
        logger.error(f"更新 Agent 信息失败: {detail}")
        status_code = 400 if "已存在" in detail else 404
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        logger.error(f"更新 Agent 信息异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新 Agent 信息异常: {str(e)}")


@router.delete("/agent/delete/{agent_id}", response_model=ResponseModel, summary="删除 Agent（新）")
async def soft_delete_agent(
    agent_id: int,
    service: AgentService = Depends(get_agent_service),
    username: str = Depends(get_current_username)
):
    """
    删除 Agent（软删除）

    - **agent_id**: Agent 编码
    """
    try:
        logger.info(f"删除 Agent: agent_id={agent_id}")

        success = await service.soft_delete_agent(agent_id, deleted_by=username)

        if success:
            return ResponseModel(code=200, message="删除成功", data={"success": True})
        else:
            raise HTTPException(status_code=500, detail="删除失败")
        
    except ValueError as e:
        logger.error(f"删除 Agent 失败: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"删除 Agent 异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除 Agent 异常: {str(e)}")
