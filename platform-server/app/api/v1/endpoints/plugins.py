"""
Plugin endpoints

v2 重构：
- 新增变量映射配置 API
- 新增策略预览 API
"""
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import get_logger
from app.schemas.base import ResponseData
from app.schemas.plugin import (
    PluginCreate, 
    PluginResponse, 
    PluginUpdate,
    VariableMapping,
    VariableMappingConfigRequest,
    VariableMappingConfigResponse,
)
from app.schemas.config_snapshot import EntityType
from app.services.plugin_service import PluginService
from app.services.config_snapshot_service import ConfigSnapshotService
from app.services.snapshot_service import SnapshotBuilder
from app.utils.plugin_renderer import PluginRenderer

logger = get_logger()
router = APIRouter()

# Dapr 调用 keyword-corpus 服务
KEYWORD_CORPUS_APP_ID = "raap-service-keyword-corpus"


@router.post("", response_model=ResponseData[PluginResponse])
async def create_plugin(
    plugin_in: PluginCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PluginResponse]:
    """Create new plugin"""
    service = PluginService(db)
    snapshot_service = ConfigSnapshotService(db)
    
    try:
        plugin = await service.create(plugin_in)
        
        # 创建初始版本快照
        await snapshot_service.create_version(
            entity_type=EntityType.PLUGIN,
            entity_id=plugin.id,
            entity_code=plugin.plugin_code,
            content=PluginResponse.model_validate(plugin).model_dump(mode='json'),
            description="初始版本"
        )
        
        return ResponseData(
            code=200,
            message="创建成功",
            data=PluginResponse.model_validate(plugin)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{plugin_id}", response_model=ResponseData[PluginResponse])
async def get_plugin(
    plugin_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PluginResponse]:
    """Get plugin by ID"""
    service = PluginService(db)
    plugin = await service.get(plugin_id)

    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found"
        )

    return ResponseData(
        data=PluginResponse.model_validate(plugin)
    )


@router.get("", response_model=ResponseData[list[PluginResponse]])
async def list_plugins(
    skip: int = 0,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[PluginResponse]]:
    """List all plugins"""
    service = PluginService(db)
    plugins = await service.list(skip=skip, limit=limit)

    return ResponseData(
        data=[PluginResponse.model_validate(plugin) for plugin in plugins]
    )


@router.put("/{plugin_id}", response_model=ResponseData[PluginResponse])
async def update_plugin(
    plugin_id: int,
    plugin_in: PluginUpdate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PluginResponse]:
    """Update plugin"""
    service = PluginService(db)
    snapshot_service = ConfigSnapshotService(db)
    
    plugin = await service.update(plugin_id, plugin_in)

    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found"
        )

    # 创建版本快照
    await snapshot_service.create_version(
        entity_type=EntityType.PLUGIN,
        entity_id=plugin.id,
        entity_code=plugin.plugin_code,
        content=PluginResponse.model_validate(plugin).model_dump(mode='json'),
        description=None  # 自动生成版本号描述
    )

    return ResponseData(
        message="Plugin updated successfully",
        data=PluginResponse.model_validate(plugin)
    )


@router.delete("/{plugin_id}", response_model=ResponseData[None])
async def delete_plugin(
    plugin_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[None]:
    """Delete plugin"""
    service = PluginService(db)
    success = await service.delete(plugin_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found"
        )

    return ResponseData(
        message="Plugin deleted successfully",
        data=None
    )


@router.post("/{plugin_id}/copy", response_model=ResponseData[PluginResponse])
async def copy_plugin(
    plugin_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PluginResponse]:
    """复制插件"""
    service = PluginService(db)
    snapshot_service = ConfigSnapshotService(db)
    
    # 获取原插件
    original = await service.get(plugin_id)
    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found"
        )
    
    # 生成新的 plugin_code（添加 _copy 后缀，如果已存在则添加数字）
    # 注意：使用 code_exists 检查包括软删除的记录，避免唯一索引冲突
    base_code = f"{original.plugin_code}_copy"
    new_code = base_code
    counter = 1
    while await service.code_exists(new_code):
        new_code = f"{base_code}_{counter}"
        counter += 1
    
    # 创建新插件
    new_plugin_data = PluginCreate(
        plugin_code=new_code,
        plugin_name=f"{original.plugin_name} (副本)",
        plugin_type=original.plugin_type,
        variable_list=original.variable_list or [],
        context_template=original.context_template,
        enabled=False,  # 默认禁用，避免误用
        remark=f"复制自 {original.plugin_code}",
    )
    
    try:
        new_plugin = await service.create(new_plugin_data)
        
        # 创建初始版本快照
        await snapshot_service.create_version(
            entity_type=EntityType.PLUGIN,
            entity_id=new_plugin.id,
            entity_code=new_plugin.plugin_code,
            content=PluginResponse.model_validate(new_plugin).model_dump(mode='json'),
            description=f"复制自 {original.plugin_code}"
        )
        
        return ResponseData(
            code=200,
            message=f"插件已复制为 {new_code}",
            data=PluginResponse.model_validate(new_plugin)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ========== v2 新增 API：变量映射配置 ==========

async def _fetch_strategy_detail(strategy_id: int, tenant_code: str = "default") -> Optional[Dict[str, Any]]:
    """获取策略详情（内部函数）"""
    dapr_url = (
        f"http://localhost:{settings.DAPR_HTTP_PORT}"
        f"/v1.0/invoke/{KEYWORD_CORPUS_APP_ID}/method/api/v1/content-strategies/{strategy_id}"
    )
    # 注意：不能用 localhost，因为那会连接到 Orchestrator 自身
    direct_urls = [
        f"http://{KEYWORD_CORPUS_APP_ID}:80/api/v1/content-strategies/{strategy_id}",
        f"http://{KEYWORD_CORPUS_APP_ID}:5100/api/v1/content-strategies/{strategy_id}",
    ]
    
    async def try_fetch(url: str) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params={"tenant_code": tenant_code})
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.debug(f"调用失败: url={url}, error={e}")
        return None
    
    result = await try_fetch(dapr_url)
    if result:
        return result
    for url in direct_urls:
        result = await try_fetch(url)
        if result:
            return result
    return None


@router.get("/{plugin_id}/variable-mappings", response_model=ResponseData[VariableMappingConfigResponse])
async def get_variable_mappings(
    plugin_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[VariableMappingConfigResponse]:
    """
    获取插件的变量映射配置
    
    返回：
    - 当前绑定的策略ID和策略信息
    - 策略中可用的 label 列表
    - 当前的变量映射配置
    """
    service = PluginService(db)
    plugin = await service.get(plugin_id)
    
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found"
        )
    
    # 获取策略详情（如果已绑定）
    strategy_name = None
    strategy_labels: List[str] = []
    
    if plugin.strategy_id:
        strategy = await _fetch_strategy_detail(plugin.strategy_id, "default")
        if strategy:
            strategy_name = strategy.get("name")
            node_pools = strategy.get("node_pools") or {}
            strategy_labels = list(node_pools.keys())
    
    # 构建响应
    variable_mappings = []
    if plugin.variable_mappings:
        for mapping in plugin.variable_mappings:
            variable_mappings.append(VariableMapping(
                variable_name=mapping.get("variable_name", ""),
                label=mapping.get("label", "")
            ))
    
    return ResponseData(
        data=VariableMappingConfigResponse(
            plugin_id=plugin.id,
            plugin_code=plugin.plugin_code,
            strategy_id=plugin.strategy_id,
            strategy_name=strategy_name,
            strategy_labels=strategy_labels,
            variable_mappings=variable_mappings,
        )
    )


@router.put("/{plugin_id}/variable-mappings", response_model=ResponseData[VariableMappingConfigResponse])
async def update_variable_mappings(
    plugin_id: int,
    request: VariableMappingConfigRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[VariableMappingConfigResponse]:
    """
    更新插件的变量映射配置
    
    请求体：
    - strategy_id: 绑定的内容策略ID
    - variable_mappings: 变量映射配置列表
    """
    service = PluginService(db)
    snapshot_service = ConfigSnapshotService(db)
    
    plugin = await service.get(plugin_id)
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found"
        )
    
    # 验证策略是否存在
    strategy = await _fetch_strategy_detail(request.strategy_id, "default")
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"策略不存在: strategy_id={request.strategy_id}"
        )
    
    # 验证变量映射：检查每个 label 是否在策略的 node_pools 中
    node_pools = strategy.get("node_pools") or {}
    strategy_labels = set(node_pools.keys())
    
    for mapping in request.variable_mappings:
        if mapping.label not in strategy_labels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"策略中没有 label '{mapping.label}'，可用: {list(strategy_labels)}"
            )
    
    # 更新插件
    plugin.strategy_id = request.strategy_id
    plugin.variable_mappings = [m.model_dump() for m in request.variable_mappings]
    
    await db.commit()
    await db.refresh(plugin)
    
    # 创建版本快照
    await snapshot_service.create_version(
        entity_type=EntityType.PLUGIN,
        entity_id=plugin.id,
        entity_code=plugin.plugin_code,
        content=PluginResponse.model_validate(plugin).model_dump(mode='json'),
        description="更新变量映射配置"
    )
    
    return ResponseData(
        code=200,
        message="变量映射配置已保存",
        data=VariableMappingConfigResponse(
            plugin_id=plugin.id,
            plugin_code=plugin.plugin_code,
            strategy_id=plugin.strategy_id,
            strategy_name=strategy.get("name"),
            strategy_labels=list(strategy_labels),
            variable_mappings=request.variable_mappings,
        )
    )


class SnapshotPreviewRequest(BaseModel):
    """快照预览请求"""
    tenant_code: str = Field(default="default", description="租户编码")


class SnapshotPreviewResponse(BaseModel):
    """快照预览响应"""
    plugin_code: str
    snapshot: Dict[str, Any]
    rendered_template: str


@router.post("/{plugin_id}/preview-snapshot", response_model=ResponseData[SnapshotPreviewResponse])
async def preview_snapshot(
    plugin_id: int,
    request: SnapshotPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[SnapshotPreviewResponse]:
    """
    预览插件的快照生成结果
    
    根据当前配置的 strategy_id 和 variable_mappings 生成一次快照
    用于前端预览效果
    """
    service = PluginService(db)
    plugin = await service.get(plugin_id)
    
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found"
        )
    
    if not plugin.strategy_id or not plugin.variable_mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="插件未配置策略绑定或变量映射"
        )
    
    try:
        # 生成快照
        builder = SnapshotBuilder(request.tenant_code)
        snapshot = await builder.build_snapshot(plugin)
        
        # 渲染模板
        rendered_template = await PluginRenderer.render_with_snapshot(db, plugin, snapshot)
        
        return ResponseData(
            data=SnapshotPreviewResponse(
                plugin_code=plugin.plugin_code,
                snapshot=snapshot,
                rendered_template=rendered_template,
            )
        )
    except Exception as e:
        logger.error(f"预览快照失败: plugin_id={plugin_id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预览快照失败: {str(e)}"
        )


@router.get("/{plugin_id}/extract-variables", response_model=ResponseData[List[str]])
async def extract_variables(
    plugin_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[List[str]]:
    """
    从插件模板中提取变量列表
    
    用于前端显示需要配置映射的变量
    """
    service = PluginService(db)
    plugin = await service.get(plugin_id)
    
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found"
        )
    
    variables = PluginRenderer.extract_variables_from_template(plugin.context_template or "")
    
    return ResponseData(
        data=variables
    )


@router.get("/{plugin_code}/related-experts", response_model=ResponseData[Dict[str, Any]])
async def get_related_experts(
    plugin_code: str,
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[Dict[str, Any]]:
    """
    查询引用了指定插件的所有专家配置

    Args:
        plugin_code: 插件编码
        page: 页码（默认 1）
        page_size: 每页大小（默认 10）

    Returns:
        - items: 专家配置列表
        - total: 总数量
        - 每个专家包含：
            - id: 专家配置 ID
            - expert_config_code: 专家配置编码
            - expert_config_name: 专家配置名称
            - expert_type: 专家类型
            - plugin_config_snapshot: 该专家如何配置此插件的快照
    """
    from sqlalchemy import and_, func as sqla_func, select
    from app.models.expert_config import ExpertConfig

    # 查询条件
    conditions = [
        ExpertConfig.is_deleted == 0,
        # JSON 查询：plugin_config 数组中包含该 plugin_code
        # MySQL 语法：JSON_CONTAINS(plugin_config, '"plugin_code"')
    ]

    # 构建查询 - 查找 plugin_config 中包含指定 plugin_code 的记录
    # 使用 JSON_CONTAINS 函数检查 plugin_config 数组中是否有该 plugin_code
    json_search = f'JSON_CONTAINS(plugin_config, \'\{{"plugin_code": "{plugin_code}"}}\' )'

    stmt = (
        select(ExpertConfig)
        .where(and_(*conditions))
        .where(text(json_search))
        .order_by(ExpertConfig.update_time.desc())
    )

    # 执行查询
    result = await db.execute(stmt)
    all_experts = result.scalars().all()

    # 分页
    total = len(all_experts)
    start = (page - 1) * page_size
    end = start + page_size
    paged_experts = all_experts[start:end]

    # 构建响应数据
    items = []
    for expert in paged_experts:
        # 提取该专家如何配置此插件的快照
        plugin_config_snapshot = None
        if expert.plugin_config:
            for pc in expert.plugin_config:
                if pc.get("plugin_code") == plugin_code:
                    plugin_config_snapshot = pc
                    break

        items.append({
            "id": expert.id,
            "expert_config_code": expert.expert_config_code,
            "expert_config_name": expert.expert_config_name,
            "expert_type": expert.expert_type,
            "enabled": expert.enabled,
            "update_time": expert.update_time.isoformat() if expert.update_time else None,
            "plugin_config_snapshot": plugin_config_snapshot,
        })

    logger.info(f"查询插件关联专家: plugin_code={plugin_code}, total={total}, page={page}, page_size={page_size}")

    return ResponseData(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )



# ========== 插件版本检查 API ==========

class PluginVersionCheckRequest(BaseModel):
    """插件版本检查请求"""
    plugin_codes: List[str] = Field(..., description="要检查的插件编码列表")


class PluginVersionInfo(BaseModel):
    """单个插件的版本信息"""
    plugin_code: str
    plugin_name: Optional[str] = None
    latest_version: int = Field(default=0, description="最新版本号")
    update_time: Optional[str] = Field(default=None, description="最后更新时间")


class PluginVersionCheckResponse(BaseModel):
    """插件版本检查响应"""
    versions: Dict[str, PluginVersionInfo] = Field(
        default_factory=dict,
        description="插件版本信息，key 为 plugin_code"
    )


@router.post("/check-versions", response_model=ResponseData[PluginVersionCheckResponse])
async def check_plugin_versions(
    request: PluginVersionCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PluginVersionCheckResponse]:
    """
    批量检查插件的最新版本号
    
    用于专家配置页面检测插件是否有更新，提示用户升级插件版本
    
    Args:
        request: 包含要检查的插件编码列表
    
    Returns:
        每个插件的最新版本号和更新时间
    """
    if not request.plugin_codes:
        return ResponseData(
            data=PluginVersionCheckResponse(versions={})
        )
    
    snapshot_service = ConfigSnapshotService(db)
    plugin_service = PluginService(db)
    
    versions: Dict[str, PluginVersionInfo] = {}
    
    for plugin_code in request.plugin_codes:
        # 获取插件基本信息
        plugin = await plugin_service.get_by_code(plugin_code)
        plugin_name = plugin.plugin_name if plugin else None
        update_time = plugin.update_time.isoformat() if plugin and plugin.update_time else None
        
        # 获取最新版本号
        version_list = await snapshot_service.get_versions(
            entity_type=EntityType.PLUGIN,
            entity_code=plugin_code,
            limit=1  # 只需要最新的一个
        )
        
        latest_version = version_list[0].version if version_list else 0
        
        versions[plugin_code] = PluginVersionInfo(
            plugin_code=plugin_code,
            plugin_name=plugin_name,
            latest_version=latest_version,
            update_time=update_time,
        )
    
    return ResponseData(
        data=PluginVersionCheckResponse(versions=versions)
    )
