"""
PublishService - 上线管理服务

提供实体上线/下线管理，确保配置稳定性。

核心原则：
1. 上线 = 锁定：上线后的实体不可编辑、不可删除
2. 级联上线：上线上层实体时，自动上线所有下层依赖
3. 分层下线：下线必须从上往下，先下线上层实体
4. 底层配置只上不下：ExpertConfig/Plugin/PluginContext 上线后不可下线

实体层级（从上到下）：
    Activity → Agent → ExpertConfig → Plugin → PluginContext
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.agent import Agent
from app.models.expert_config import ExpertConfig
from app.models.plugin import Plugin
from app.models.plugin_context import PluginContext
from app.services.reference_check_service import ReferenceCheckService, ReferenceCheckResult

logger = logging.getLogger(__name__)


class PublishStatus(str, Enum):
    """上线状态"""
    DRAFT = "DRAFT"  # 草稿（未上线）
    PUBLISHED = "PUBLISHED"  # 已上线


class EntityType(str, Enum):
    """实体类型"""
    ACTIVITY = "Activity"
    AGENT = "Agent"
    EXPERT_CONFIG = "ExpertConfig"
    PLUGIN = "Plugin"
    PLUGIN_CONTEXT = "PluginContext"


# 可下线的实体类型（只有 Activity 和 Agent 可以下线）
UNPUBLISHABLE_ENTITY_TYPES = {EntityType.ACTIVITY, EntityType.AGENT}


@dataclass
class EntityInfo:
    """实体信息"""
    entity_type: str
    entity_id: Any  # ID 或 code
    entity_name: str
    current_status: str  # DRAFT / PUBLISHED


@dataclass
class DependencyCollection:
    """依赖收集结果"""
    activity: Optional[EntityInfo] = None
    agent: Optional[EntityInfo] = None
    expert_configs: List[EntityInfo] = field(default_factory=list)
    plugins: List[EntityInfo] = field(default_factory=list)
    plugin_contexts: List[EntityInfo] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result: Dict[str, Any] = {}
        
        if self.activity:
            result["activity"] = {
                "id": self.activity.entity_id,
                "name": self.activity.entity_name,
                "current_status": self.activity.current_status,
            }
        
        if self.agent:
            result["agent"] = {
                "code": self.agent.entity_id,
                "name": self.agent.entity_name,
                "current_status": self.agent.current_status,
            }
        
        if self.expert_configs:
            result["expert_configs"] = [
                {
                    "code": e.entity_id,
                    "name": e.entity_name,
                    "current_status": e.current_status,
                }
                for e in self.expert_configs
            ]
        
        if self.plugins:
            result["plugins"] = [
                {
                    "code": e.entity_id,
                    "name": e.entity_name,
                    "current_status": e.current_status,
                }
                for e in self.plugins
            ]
        
        if self.plugin_contexts:
            result["plugin_contexts"] = [
                {
                    "name": e.entity_id,
                    "context_name": e.entity_name,
                    "current_status": e.current_status,
                }
                for e in self.plugin_contexts
            ]
        
        return result
    
    def get_all_entities(self) -> List[EntityInfo]:
        """获取所有实体"""
        entities = []
        if self.activity:
            entities.append(self.activity)
        if self.agent:
            entities.append(self.agent)
        entities.extend(self.expert_configs)
        entities.extend(self.plugins)
        entities.extend(self.plugin_contexts)
        return entities


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class PublishResult:
    """上线结果"""
    success: bool
    message: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    published_entities: Optional[Dict[str, List[str]]] = None
    publish_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
            "message": self.message,
        }
        if self.errors:
            result["errors"] = self.errors
        if self.warnings:
            result["warnings"] = self.warnings
        if self.published_entities:
            result["published_entities"] = self.published_entities
        if self.publish_time:
            result["publish_time"] = self.publish_time
        return result


@dataclass
class UnpublishResult:
    """下线结果"""
    success: bool
    message: str = ""
    blockers: List[str] = field(default_factory=list)  # 阻止下线的上层实体
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
            "message": self.message,
        }
        if self.blockers:
            result["blockers"] = self.blockers
        return result


@dataclass
class ModifyCheckResult:
    """编辑/删除检查结果"""
    allowed: bool
    action: str  # "reject" | "confirm" | "allow"
    reason: str = ""
    references: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "allowed": self.allowed,
            "action": self.action,
            "reason": self.reason,
        }
        if self.references:
            result["references"] = self.references
        return result


class PublishService:
    """上线管理服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ref_check = ReferenceCheckService(db)
    
    # ==================== 上线操作 ====================
    
    async def publish_activity(self, activity_id: int, operator: str) -> PublishResult:
        """
        上线 Activity 及其所有依赖
        
        Args:
            activity_id: Activity ID
            operator: 操作人
            
        Returns:
            PublishResult: 上线结果
        """
        # 1. 获取 Activity
        activity = await self._get_activity(activity_id)
        if not activity:
            return PublishResult(
                success=False,
                message="Activity 不存在",
                errors=["Activity 不存在"]
            )
        
        # 检查是否已上线
        if getattr(activity, 'publish_status', None) == PublishStatus.PUBLISHED.value:
            return PublishResult(
                success=False,
                message="Activity 已上线",
                errors=["Activity 已上线，无需重复操作"]
            )
        
        # 检查是否配置了 Agent
        if not activity.agent_code_list:
            return PublishResult(
                success=False,
                message="Activity 未配置 Agent",
                errors=["请先为 Activity 配置 Agent"]
            )
        
        # 2. 收集所有依赖
        dependencies = await self.collect_publish_dependencies(activity_id)
        
        # 3. 验证依赖完整性
        validation = await self.validate_publish_dependencies(dependencies)
        if not validation.is_valid:
            return PublishResult(
                success=False,
                message="上线失败：存在无效依赖",
                errors=validation.errors,
                warnings=validation.warnings
            )
        
        # 4. 批量上线所有依赖
        now = datetime.now()
        published_entities: Dict[str, List[str]] = {
            "activity": [],
            "agent": [],
            "expert_config": [],
            "plugin": [],
            "plugin_context": [],
        }
        
        try:
            # 从下往上上线（先上线底层依赖）
            
            # 上线 PluginContext
            for ctx_info in dependencies.plugin_contexts:
                if ctx_info.current_status != PublishStatus.PUBLISHED.value:
                    await self._publish_plugin_context(ctx_info.entity_id, operator, now)
                    published_entities["plugin_context"].append(ctx_info.entity_name)
            
            # 上线 Plugin
            for plugin_info in dependencies.plugins:
                if plugin_info.current_status != PublishStatus.PUBLISHED.value:
                    await self._publish_plugin(plugin_info.entity_id, operator, now)
                    published_entities["plugin"].append(plugin_info.entity_id)
            
            # 上线 ExpertConfig
            for expert_info in dependencies.expert_configs:
                if expert_info.current_status != PublishStatus.PUBLISHED.value:
                    await self._publish_expert_config(expert_info.entity_id, operator, now)
                    published_entities["expert_config"].append(expert_info.entity_id)
            
            # 上线 Agent
            if dependencies.agent and dependencies.agent.current_status != PublishStatus.PUBLISHED.value:
                await self._publish_agent(dependencies.agent.entity_id, operator, now)
                published_entities["agent"].append(dependencies.agent.entity_id)
            
            # 上线 Activity
            await self._publish_activity(activity_id, operator, now)
            published_entities["activity"].append(str(activity_id))
            
            await self.db.commit()
            
            logger.info(f"Activity {activity_id} 上线成功，操作人: {operator}")
            
            return PublishResult(
                success=True,
                message="上线成功",
                warnings=validation.warnings,
                published_entities=published_entities,
                publish_time=now.strftime("%Y-%m-%d %H:%M:%S")
            )
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Activity {activity_id} 上线失败: {e}")
            return PublishResult(
                success=False,
                message=f"上线失败: {str(e)}",
                errors=[str(e)]
            )
    
    async def publish_agent(self, agent_code: str, operator: str) -> PublishResult:
        """
        单独上线 Agent 及其依赖（不上线 Activity）
        
        Args:
            agent_code: Agent 编码
            operator: 操作人
            
        Returns:
            PublishResult: 上线结果
        """
        # 获取 Agent
        agent = await self._get_agent(agent_code)
        if not agent:
            return PublishResult(
                success=False,
                message="Agent 不存在",
                errors=["Agent 不存在"]
            )
        
        if getattr(agent, 'publish_status', None) == PublishStatus.PUBLISHED.value:
            return PublishResult(
                success=False,
                message="Agent 已上线",
                errors=["Agent 已上线，无需重复操作"]
            )
        
        # 收集 Agent 的依赖
        dependencies = await self._collect_agent_dependencies(agent_code)
        
        # 验证
        validation = await self._validate_agent_dependencies(dependencies)
        if not validation.is_valid:
            return PublishResult(
                success=False,
                message="上线失败：存在无效依赖",
                errors=validation.errors,
                warnings=validation.warnings
            )
        
        now = datetime.now()
        published_entities: Dict[str, List[str]] = {
            "agent": [],
            "expert_config": [],
            "plugin": [],
            "plugin_context": [],
        }
        
        try:
            # 上线 PluginContext
            for ctx_info in dependencies.plugin_contexts:
                if ctx_info.current_status != PublishStatus.PUBLISHED.value:
                    await self._publish_plugin_context(ctx_info.entity_id, operator, now)
                    published_entities["plugin_context"].append(ctx_info.entity_name)
            
            # 上线 Plugin
            for plugin_info in dependencies.plugins:
                if plugin_info.current_status != PublishStatus.PUBLISHED.value:
                    await self._publish_plugin(plugin_info.entity_id, operator, now)
                    published_entities["plugin"].append(plugin_info.entity_id)
            
            # 上线 ExpertConfig
            for expert_info in dependencies.expert_configs:
                if expert_info.current_status != PublishStatus.PUBLISHED.value:
                    await self._publish_expert_config(expert_info.entity_id, operator, now)
                    published_entities["expert_config"].append(expert_info.entity_id)
            
            # 上线 Agent
            await self._publish_agent(agent_code, operator, now)
            published_entities["agent"].append(agent_code)
            
            await self.db.commit()
            
            logger.info(f"Agent {agent_code} 上线成功，操作人: {operator}")
            
            return PublishResult(
                success=True,
                message="上线成功",
                warnings=validation.warnings,
                published_entities=published_entities,
                publish_time=now.strftime("%Y-%m-%d %H:%M:%S")
            )
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Agent {agent_code} 上线失败: {e}")
            return PublishResult(
                success=False,
                message=f"上线失败: {str(e)}",
                errors=[str(e)]
            )
    
    # ==================== 下线操作 ====================
    
    async def unpublish_activity(self, activity_id: int, operator: str) -> UnpublishResult:
        """
        下线 Activity
        
        Activity 下线不影响下层实体，仅解锁自身
        
        Args:
            activity_id: Activity ID
            operator: 操作人
            
        Returns:
            UnpublishResult: 下线结果
        """
        activity = await self._get_activity(activity_id)
        if not activity:
            return UnpublishResult(
                success=False,
                message="Activity 不存在"
            )
        
        if getattr(activity, 'publish_status', None) != PublishStatus.PUBLISHED.value:
            return UnpublishResult(
                success=False,
                message="Activity 未上线，无需下线"
            )
        
        try:
            activity.publish_status = PublishStatus.DRAFT.value
            activity.updated_by = operator
            await self.db.commit()
            
            logger.info(f"Activity {activity_id} 下线成功，操作人: {operator}")
            
            return UnpublishResult(
                success=True,
                message="下线成功"
            )
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Activity {activity_id} 下线失败: {e}")
            return UnpublishResult(
                success=False,
                message=f"下线失败: {str(e)}"
            )
    
    async def unpublish_agent(self, agent_code: str, operator: str) -> UnpublishResult:
        """
        下线 Agent
        
        需要先检查是否有已上线的 Activity 引用此 Agent
        
        Args:
            agent_code: Agent 编码
            operator: 操作人
            
        Returns:
            UnpublishResult: 下线结果
        """
        agent = await self._get_agent(agent_code)
        if not agent:
            return UnpublishResult(
                success=False,
                message="Agent 不存在"
            )
        
        if getattr(agent, 'publish_status', None) != PublishStatus.PUBLISHED.value:
            return UnpublishResult(
                success=False,
                message="Agent 未上线，无需下线"
            )
        
        # 检查是否有已上线的 Activity 引用此 Agent
        blockers = await self._check_agent_unpublish_blockers(agent_code)
        if blockers:
            return UnpublishResult(
                success=False,
                message="无法下线：有已上线的 Activity 正在使用此 Agent",
                blockers=blockers
            )
        
        try:
            agent.publish_status = PublishStatus.DRAFT.value
            agent.updated_by = operator
            await self.db.commit()
            
            logger.info(f"Agent {agent_code} 下线成功，操作人: {operator}")
            
            return UnpublishResult(
                success=True,
                message="下线成功"
            )
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Agent {agent_code} 下线失败: {e}")
            return UnpublishResult(
                success=False,
                message=f"下线失败: {str(e)}"
            )
    
    async def unpublish_expert_config(
        self, expert_config_code: str, operator: str
    ) -> UnpublishResult:
        """
        ExpertConfig 不支持下线
        """
        return UnpublishResult(
            success=False,
            message="ExpertConfig 上线后不支持下线，如需修改请创建新版本"
        )
    
    async def unpublish_plugin(self, plugin_code: str, operator: str) -> UnpublishResult:
        """
        Plugin 不支持下线
        """
        return UnpublishResult(
            success=False,
            message="Plugin 上线后不支持下线，如需修改请创建新版本"
        )
    
    async def unpublish_plugin_context(
        self, context_name: str, operator: str
    ) -> UnpublishResult:
        """
        PluginContext 不支持下线
        """
        return UnpublishResult(
            success=False,
            message="PluginContext 上线后不支持下线，如需修改请创建新版本"
        )
    
    # ==================== 编辑/删除检查 ====================
    
    async def check_can_modify(
        self, 
        entity_type: str, 
        entity_id: Any
    ) -> ModifyCheckResult:
        """
        检查实体是否可以编辑/删除
        
        Args:
            entity_type: 实体类型 (Activity/Agent/ExpertConfig/Plugin/PluginContext)
            entity_id: 实体 ID 或编码
            
        Returns:
            ModifyCheckResult: 检查结果
        """
        # 获取实体
        entity = await self._get_entity(entity_type, entity_id)
        if not entity:
            return ModifyCheckResult(
                allowed=False,
                action="reject",
                reason=f"{entity_type} 不存在"
            )
        
        # 检查上线状态
        publish_status = getattr(entity, 'publish_status', PublishStatus.DRAFT.value)
        
        # 已上线：直接拒绝
        if publish_status == PublishStatus.PUBLISHED.value:
            return ModifyCheckResult(
                allowed=False,
                action="reject",
                reason=f"{entity_type} 已上线，不可编辑或删除。如需修改，请先下线。"
            )
        
        # 未上线：检查引用关系
        ref_result = await self._check_entity_references(entity_type, entity_id)
        
        if ref_result.reference_count > 0:
            return ModifyCheckResult(
                allowed=True,  # 允许但需确认
                action="confirm",
                reason=ref_result.warning_message,
                references=[
                    {
                        "entity_type": ref.entity_type,
                        "entity_id": ref.entity_id,
                        "entity_name": ref.entity_name,
                        "reference_field": ref.reference_field,
                    }
                    for ref in ref_result.references[:10]
                ]
            )
        
        # 无引用：直接允许
        return ModifyCheckResult(
            allowed=True,
            action="allow",
            reason=""
        )
    
    async def check_can_delete(
        self, 
        entity_type: str, 
        entity_id: Any
    ) -> ModifyCheckResult:
        """
        检查实体是否可以删除（与 check_can_modify 逻辑相同）
        """
        return await self.check_can_modify(entity_type, entity_id)
    
    # ==================== 上线预检查 ====================
    
    async def preview_publish_activity(self, activity_id: int) -> Dict[str, Any]:
        """
        预检查 Activity 上线（不实际执行，返回依赖清单）
        
        Args:
            activity_id: Activity ID
            
        Returns:
            预检查结果，包含依赖清单和验证结果
        """
        # 获取 Activity
        activity = await self._get_activity(activity_id)
        if not activity:
            return {
                "can_publish": False,
                "errors": ["Activity 不存在"],
                "dependencies": None,
                "validation": None,
            }
        
        if getattr(activity, 'publish_status', None) == PublishStatus.PUBLISHED.value:
            return {
                "can_publish": False,
                "errors": ["Activity 已上线"],
                "dependencies": None,
                "validation": None,
            }
        
        if not activity.agent_code_list:
            return {
                "can_publish": False,
                "errors": ["Activity 未配置 Agent"],
                "dependencies": None,
                "validation": None,
            }
        
        # 收集依赖
        dependencies = await self.collect_publish_dependencies(activity_id)
        
        # 验证
        validation = await self.validate_publish_dependencies(dependencies)
        
        return {
            "can_publish": validation.is_valid,
            "errors": validation.errors,
            "dependencies": dependencies.to_dict(),
            "validation": validation.to_dict(),
        }
    
    # ==================== 依赖收集 ====================
    
    async def collect_publish_dependencies(self, activity_id: int) -> DependencyCollection:
        """
        收集 Activity 上线需要的所有依赖实体
        
        Args:
            activity_id: Activity ID
            
        Returns:
            DependencyCollection: 依赖收集结果
        """
        collection = DependencyCollection()
        
        # 获取 Activity
        activity = await self._get_activity(activity_id)
        if not activity:
            return collection
        
        collection.activity = EntityInfo(
            entity_type=EntityType.ACTIVITY.value,
            entity_id=activity_id,
            entity_name=activity.activity_name,
            current_status=getattr(activity, 'publish_status', PublishStatus.DRAFT.value)
        )
        
        # 获取 Agent 列表的依赖
        if not activity.agent_code_list:
            return collection
        
        # 收集所有 Agent 的依赖（支持多个 Agent）
        for agent_code in activity.agent_code_list:
            agent_deps = await self._collect_agent_dependencies(agent_code)
            if agent_deps.agent:
                # 将第一个 Agent 作为主 Agent（兼容旧逻辑）
                if collection.agent is None:
                    collection.agent = agent_deps.agent
                # 合并 expert_configs（去重）
                existing_expert_ids = {e.entity_id for e in collection.expert_configs}
                for expert in agent_deps.expert_configs:
                    if expert.entity_id not in existing_expert_ids:
                        collection.expert_configs.append(expert)
                        existing_expert_ids.add(expert.entity_id)
                # 合并 plugins（去重）
                existing_plugin_ids = {p.entity_id for p in collection.plugins}
                for plugin in agent_deps.plugins:
                    if plugin.entity_id not in existing_plugin_ids:
                        collection.plugins.append(plugin)
                        existing_plugin_ids.add(plugin.entity_id)
                # 合并 plugin_contexts（去重）
                existing_ctx_ids = {c.entity_id for c in collection.plugin_contexts}
                for ctx in agent_deps.plugin_contexts:
                    if ctx.entity_id not in existing_ctx_ids:
                        collection.plugin_contexts.append(ctx)
                        existing_ctx_ids.add(ctx.entity_id)
        
        return collection
    
    async def _collect_agent_dependencies(self, agent_code: str) -> DependencyCollection:
        """
        收集 Agent 的依赖
        """
        collection = DependencyCollection()
        
        agent = await self._get_agent(agent_code)
        if not agent:
            return collection
        
        collection.agent = EntityInfo(
            entity_type=EntityType.AGENT.value,
            entity_id=agent_code,
            entity_name=agent.agent_name,
            current_status=getattr(agent, 'publish_status', PublishStatus.DRAFT.value)
        )
        
        # 收集 ExpertConfig
        expert_codes = agent.expert_config_code_list or []
        seen_plugins: Set[str] = set()
        seen_contexts: Set[str] = set()
        
        for expert_code in expert_codes:
            expert_config = await self._get_expert_config(expert_code)
            if expert_config:
                collection.expert_configs.append(EntityInfo(
                    entity_type=EntityType.EXPERT_CONFIG.value,
                    entity_id=expert_code,
                    entity_name=expert_config.expert_config_name,
                    current_status=getattr(
                        expert_config, 'publish_status', PublishStatus.DRAFT.value
                    )
                ))
                
                # 收集 Plugin 和 PluginContext
                plugin_configs = expert_config.plugin_config or []
                for pc in plugin_configs:
                    if isinstance(pc, dict):
                        plugin_code = pc.get("plugin_code")
                        if plugin_code and plugin_code not in seen_plugins:
                            seen_plugins.add(plugin_code)
                            plugin = await self._get_plugin(plugin_code)
                            if plugin:
                                collection.plugins.append(EntityInfo(
                                    entity_type=EntityType.PLUGIN.value,
                                    entity_id=plugin_code,
                                    entity_name=plugin.plugin_name,
                                    current_status=getattr(
                                        plugin, 'publish_status', PublishStatus.DRAFT.value
                                    )
                                ))
                        
                        # 收集 PluginContext
                        variable_mapping = pc.get("variable_mapping", {})
                        for var_name, context_names in variable_mapping.items():
                            # context_names 可能是单个值或列表
                            if isinstance(context_names, str):
                                context_names = [context_names]
                            elif not isinstance(context_names, list):
                                continue
                            
                            for context_name in context_names:
                                if context_name and context_name not in seen_contexts:
                                    seen_contexts.add(context_name)
                                    ctx = await self._get_plugin_context(context_name)
                                    if ctx:
                                        collection.plugin_contexts.append(EntityInfo(
                                            entity_type=EntityType.PLUGIN_CONTEXT.value,
                                            entity_id=ctx.id,
                                            entity_name=context_name,
                                            current_status=getattr(
                                                ctx, 'publish_status', PublishStatus.DRAFT.value
                                            )
                                        ))
        
        return collection
    
    # ==================== 依赖验证 ====================
    
    async def validate_publish_dependencies(
        self, dependencies: DependencyCollection
    ) -> ValidationResult:
        """
        验证上线依赖的完整性和有效性
        
        Args:
            dependencies: 依赖收集结果
            
        Returns:
            ValidationResult: 验证结果
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        # 检查 Activity
        if not dependencies.activity:
            errors.append("Activity 不存在")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        
        # 检查 Agent
        if not dependencies.agent:
            errors.append("Activity 未配置 Agent 或 Agent 不存在")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        
        # 验证 Agent 的依赖
        return await self._validate_agent_dependencies(dependencies)
    
    async def _validate_agent_dependencies(
        self, dependencies: DependencyCollection
    ) -> ValidationResult:
        """
        验证 Agent 的依赖完整性
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        if not dependencies.agent:
            errors.append("Agent 不存在")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        
        # 获取 Agent
        agent = await self._get_agent(dependencies.agent.entity_id)
        if not agent:
            errors.append(f"Agent '{dependencies.agent.entity_id}' 不存在")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        
        # 检查 Agent 是否启用
        if not agent.enabled:
            errors.append(f"Agent '{agent.agent_code}' 未启用")
        
        # 检查 ExpertConfig
        expert_codes = agent.expert_config_code_list or []
        found_expert_codes = {e.entity_id for e in dependencies.expert_configs}
        
        for code in expert_codes:
            if code not in found_expert_codes:
                errors.append(f"ExpertConfig '{code}' 不存在")
            else:
                expert_config = await self._get_expert_config(code)
                if expert_config and not expert_config.enabled:
                    warnings.append(f"ExpertConfig '{code}' 未启用")
        
        # 检查 Plugin
        for plugin_info in dependencies.plugins:
            plugin = await self._get_plugin(plugin_info.entity_id)
            if not plugin:
                errors.append(f"Plugin '{plugin_info.entity_id}' 不存在")
            elif not plugin.enabled:
                warnings.append(f"Plugin '{plugin_info.entity_id}' 未启用")
        
        # 检查 PluginContext
        for ctx_info in dependencies.plugin_contexts:
            ctx = await self._get_plugin_context(ctx_info.entity_name)
            if not ctx:
                errors.append(f"PluginContext '{ctx_info.entity_name}' 不存在")
            elif not ctx.context:
                warnings.append(f"PluginContext '{ctx_info.entity_name}' 内容为空")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    # ==================== 下线阻塞检查 ====================
    
    async def _check_agent_unpublish_blockers(self, agent_code: str) -> List[str]:
        """
        检查 Agent 下线的阻塞者（已上线的 Activity）
        
        Returns:
            阻塞者描述列表
        """
        blockers: List[str] = []
        
        # agent_code_list 是 JSON 数组，使用 JSON_CONTAINS 查询
        stmt = select(Activity).where(
            func.json_contains(Activity.agent_code_list, f'"{agent_code}"'),
            Activity.is_deleted == 0
        )
        result = await self.db.execute(stmt)
        activities = result.scalars().all()
        
        for activity in activities:
            if getattr(activity, 'publish_status', None) == PublishStatus.PUBLISHED.value:
                blockers.append(
                    f"Activity '{activity.activity_name}' (ID: {activity.id}) 已上线"
                )
        
        return blockers
    
    # ==================== 实体获取 ====================
    
    async def _get_activity(self, activity_id: int) -> Optional[Activity]:
        """获取 Activity"""
        stmt = select(Activity).where(
            Activity.id == activity_id,
            Activity.is_deleted == 0
        ).order_by(Activity.id.desc())  # 如果有多条，取最新的
        result = await self.db.execute(stmt)
        return result.scalars().first()
    
    async def _get_agent(self, agent_code: str) -> Optional[Agent]:
        """获取 Agent"""
        stmt = select(Agent).where(
            Agent.agent_code == agent_code,
            Agent.is_deleted == 0
        ).order_by(Agent.id.desc())  # 如果有多条，取最新的
        result = await self.db.execute(stmt)
        return result.scalars().first()
    
    async def _get_expert_config(self, expert_config_code: str) -> Optional[ExpertConfig]:
        """获取 ExpertConfig"""
        stmt = select(ExpertConfig).where(
            ExpertConfig.expert_config_code == expert_config_code,
            ExpertConfig.is_deleted == 0
        ).order_by(ExpertConfig.id.desc())  # 如果有多条，取最新的
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _get_plugin(self, plugin_code: str) -> Optional[Plugin]:
        """获取 Plugin"""
        stmt = select(Plugin).where(
            Plugin.plugin_code == plugin_code,
            Plugin.is_deleted == 0
        ).order_by(Plugin.id.desc())  # 如果有多条，取最新的
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _get_plugin_context(self, context_name: str) -> Optional[PluginContext]:
        """获取 PluginContext"""
        stmt = select(PluginContext).where(
            PluginContext.context_name == context_name,
            PluginContext.is_deleted == 0
        ).order_by(PluginContext.id.desc())  # 如果有多条，取最新的
        result = await self.db.execute(stmt)
        return result.scalars().first()
    
    async def _get_entity(self, entity_type: str, entity_id: Any) -> Optional[Any]:
        """通用实体获取"""
        if entity_type == EntityType.ACTIVITY.value:
            return await self._get_activity(int(entity_id))
        elif entity_type == EntityType.AGENT.value:
            return await self._get_agent(str(entity_id))
        elif entity_type == EntityType.EXPERT_CONFIG.value:
            return await self._get_expert_config(str(entity_id))
        elif entity_type == EntityType.PLUGIN.value:
            return await self._get_plugin(str(entity_id))
        elif entity_type == EntityType.PLUGIN_CONTEXT.value:
            return await self._get_plugin_context(str(entity_id))
        return None
    
    # ==================== 引用检查 ====================
    
    async def _check_entity_references(
        self, entity_type: str, entity_id: Any
    ) -> ReferenceCheckResult:
        """调用 ReferenceCheckService 检查引用"""
        if entity_type == EntityType.ACTIVITY.value:
            return await self.ref_check.check_activity_references(int(entity_id))
        elif entity_type == EntityType.AGENT.value:
            return await self.ref_check.check_agent_references(str(entity_id))
        elif entity_type == EntityType.EXPERT_CONFIG.value:
            return await self.ref_check.check_expert_config_references(str(entity_id))
        elif entity_type == EntityType.PLUGIN.value:
            return await self.ref_check.check_plugin_references(str(entity_id))
        elif entity_type == EntityType.PLUGIN_CONTEXT.value:
            return await self.ref_check.check_plugin_context_references(str(entity_id))
        
        return ReferenceCheckResult(can_delete=True, can_disable=True)
    
    # ==================== 上线执行 ====================
    
    async def _publish_activity(
        self, activity_id: int, operator: str, publish_time: datetime
    ) -> None:
        """执行 Activity 上线"""
        activity = await self._get_activity(activity_id)
        if activity:
            activity.publish_status = PublishStatus.PUBLISHED.value
            activity.publish_time = publish_time
            activity.publish_by = operator
            activity.updated_by = operator
    
    async def _publish_agent(
        self, agent_code: str, operator: str, publish_time: datetime
    ) -> None:
        """执行 Agent 上线"""
        agent = await self._get_agent(agent_code)
        if agent:
            agent.publish_status = PublishStatus.PUBLISHED.value
            agent.publish_time = publish_time
            agent.publish_by = operator
            agent.updated_by = operator
    
    async def _publish_expert_config(
        self, expert_config_code: str, operator: str, publish_time: datetime
    ) -> None:
        """执行 ExpertConfig 上线"""
        expert_config = await self._get_expert_config(expert_config_code)
        if expert_config:
            expert_config.publish_status = PublishStatus.PUBLISHED.value
            expert_config.publish_time = publish_time
            expert_config.publish_by = operator
            expert_config.updated_by = operator
    
    async def _publish_plugin(
        self, plugin_code: str, operator: str, publish_time: datetime
    ) -> None:
        """执行 Plugin 上线"""
        plugin = await self._get_plugin(plugin_code)
        if plugin:
            plugin.publish_status = PublishStatus.PUBLISHED.value
            plugin.publish_time = publish_time
            plugin.publish_by = operator
            plugin.updated_by = operator
    
    async def _publish_plugin_context(
        self, context_id: int, operator: str, publish_time: datetime
    ) -> None:
        """执行 PluginContext 上线"""
        stmt = select(PluginContext).where(
            PluginContext.id == context_id,
            PluginContext.is_deleted == 0
        ).order_by(PluginContext.id.desc())  # 如果有多条，取最新的
        result = await self.db.execute(stmt)
        ctx = result.scalars().first()
        if ctx:
            ctx.publish_status = PublishStatus.PUBLISHED.value
            ctx.publish_time = publish_time
            ctx.publish_by = operator
            ctx.updated_by = operator
    
    # ==================== 查询方法 ====================
    
    async def get_publish_status(self, entity_type: str, entity_id: Any) -> Optional[str]:
        """
        获取实体的上线状态
        
        Args:
            entity_type: 实体类型
            entity_id: 实体 ID 或编码
            
        Returns:
            上线状态（DRAFT/PUBLISHED）或 None（实体不存在）
        """
        entity = await self._get_entity(entity_type, entity_id)
        if not entity:
            return None
        return getattr(entity, 'publish_status', PublishStatus.DRAFT.value)
    
    async def is_published(self, entity_type: str, entity_id: Any) -> bool:
        """
        检查实体是否已上线
        """
        status = await self.get_publish_status(entity_type, entity_id)
        return status == PublishStatus.PUBLISHED.value


