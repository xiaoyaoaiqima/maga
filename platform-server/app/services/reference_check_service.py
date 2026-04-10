"""
ReferenceCheckService - 引用检查服务

提供实体间引用关系检查，确保删除/禁用操作的数据完整性。

实体关系图：
    Tenant
       └─► Activity ─► Agent ─► ExpertConfig ─► Plugin ─► PluginContext
              └─► Job ─► SubJob ─► Content

核心能力：
1. 检查实体是否被引用（阻止删除）
2. 获取引用该实体的所有上游实体
3. 验证关联配置的有效性
"""
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.activity import Activity
from app.models.agent import Agent
from app.models.job import Job
from app.models.sub_job import SubJob
from app.models.content import Content
from app.models.expert_config import ExpertConfig
from app.models.plugin import Plugin
from app.models.plugin_context import PluginContext

logger = logging.getLogger(__name__)


@dataclass
class ReferenceInfo:
    """引用信息"""
    entity_type: str  # 引用方实体类型
    entity_id: Any    # 引用方 ID
    entity_name: str  # 引用方名称/编码
    reference_field: str  # 引用字段


@dataclass
class ReferenceCheckResult:
    """引用检查结果"""
    can_delete: bool  # 是否可以删除
    can_disable: bool  # 是否可以禁用
    references: List[ReferenceInfo] = field(default_factory=list)  # 引用列表
    warning_message: str = ""  # 警告信息
    
    @property
    def reference_count(self) -> int:
        return len(self.references)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "can_delete": self.can_delete,
            "can_disable": self.can_disable,
            "reference_count": self.reference_count,
            "references": [
                {
                    "entity_type": ref.entity_type,
                    "entity_id": ref.entity_id,
                    "entity_name": ref.entity_name,
                    "reference_field": ref.reference_field,
                }
                for ref in self.references[:20]  # 最多返回 20 条
            ],
            "warning_message": self.warning_message,
        }


class ReferenceCheckService:
    """引用检查服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ==================== Agent 引用检查 ====================
    
    async def check_agent_references(self, agent_code: str) -> ReferenceCheckResult:
        """
        检查 Agent 的引用情况
        
        Agent 被以下实体引用：
        - Activity.agent_code_list (JSON 数组)
        - Job.agent_code
        - JobVariant.agent_code
        - Content.agent_code
        """
        references: List[ReferenceInfo] = []
        
        # 检查 Activity 引用（agent_code_list 是 JSON 数组）
        stmt = select(Activity).where(
            func.json_contains(Activity.agent_code_list, f'"{agent_code}"'),
            Activity.is_deleted == 0
        )
        result = await self.db.execute(stmt)
        for activity in result.scalars().all():
            references.append(ReferenceInfo(
                entity_type="Activity",
                entity_id=activity.id,
                entity_name=activity.activity_name,
                reference_field="agent_code_list"
            ))
        
        # 检查 Job 引用
        stmt = select(Job).where(
            Job.agent_code == agent_code,
            Job.is_deleted == 0
        )
        result = await self.db.execute(stmt)
        for job in result.scalars().all():
            references.append(ReferenceInfo(
                entity_type="Job",
                entity_id=job.job_id,
                entity_name=job.job_name,
                reference_field="agent_code"
            ))
        
        # 检查 Content 引用（已上线或已使用的内容）
        stmt = select(func.count()).select_from(Content).where(
            Content.agent_code == agent_code,
            Content.is_deleted == 0,
            or_(
                Content.online_status == "ONLINE",
                Content.is_used == 1,
                Content.is_locked == 1
            )
        )
        result = await self.db.execute(stmt)
        active_content_count = result.scalar() or 0
        
        if active_content_count > 0:
            references.append(ReferenceInfo(
                entity_type="Content",
                entity_id=f"count:{active_content_count}",
                entity_name=f"{active_content_count} 篇活跃文章",
                reference_field="agent_code"
            ))
        
        # 判断是否可删除/禁用
        has_active_content = active_content_count > 0
        has_active_job = any(r.entity_type == "Job" for r in references)
        
        can_delete = len(references) == 0
        can_disable = not has_active_content and not has_active_job
        
        warning_parts = []
        if not can_delete:
            warning_parts.append(f"Agent 被 {len(references)} 个实体引用")
        if has_active_content:
            warning_parts.append(f"存在 {active_content_count} 篇活跃文章")
        
        return ReferenceCheckResult(
            can_delete=can_delete,
            can_disable=can_disable,
            references=references,
            warning_message="；".join(warning_parts) if warning_parts else ""
        )
    
    # ==================== ExpertConfig 引用检查 ====================
    
    async def check_expert_config_references(self, expert_config_code: str) -> ReferenceCheckResult:
        """
        检查 ExpertConfig 的引用情况
        
        ExpertConfig 被以下实体引用：
        - Agent.expert_config_code_list (JSON 数组)
        - Job.expert_config_code_list (JSON 数组)
        """
        references: List[ReferenceInfo] = []
        
        # 检查 Agent 引用（JSON 数组包含检查）
        stmt = select(Agent).where(Agent.is_deleted == 0)
        result = await self.db.execute(stmt)
        for agent in result.scalars().all():
            if expert_config_code in (agent.expert_config_code_list or []):
                references.append(ReferenceInfo(
                    entity_type="Agent",
                    entity_id=agent.agent_code,
                    entity_name=agent.agent_name,
                    reference_field="expert_config_code_list"
                ))
        
        # 检查 Job 引用（运行中或未完成的任务）
        stmt = select(Job).where(
            Job.is_deleted == 0,
            Job.status.in_(["PENDING", "RUNNING", "DEPLOYED"])
        )
        result = await self.db.execute(stmt)
        for job in result.scalars().all():
            if expert_config_code in (job.expert_config_code_list or []):
                references.append(ReferenceInfo(
                    entity_type="Job",
                    entity_id=job.job_id,
                    entity_name=job.job_name,
                    reference_field="expert_config_code_list"
                ))
        
        can_delete = len(references) == 0
        can_disable = not any(r.entity_type == "Job" for r in references)
        
        warning_parts = []
        if not can_delete:
            agent_count = sum(1 for r in references if r.entity_type == "Agent")
            job_count = sum(1 for r in references if r.entity_type == "Job")
            if agent_count > 0:
                warning_parts.append(f"被 {agent_count} 个 Agent 引用")
            if job_count > 0:
                warning_parts.append(f"被 {job_count} 个活跃 Job 引用")
        
        return ReferenceCheckResult(
            can_delete=can_delete,
            can_disable=can_disable,
            references=references,
            warning_message="；".join(warning_parts) if warning_parts else ""
        )
    
    # ==================== Plugin 引用检查 ====================
    
    async def check_plugin_references(self, plugin_code: str) -> ReferenceCheckResult:
        """
        检查 Plugin 的引用情况
        
        Plugin 被以下实体引用：
        - ExpertConfig.plugin_config (JSON 数组中的 plugin_code)
        """
        references: List[ReferenceInfo] = []
        
        # 检查 ExpertConfig 引用
        stmt = select(ExpertConfig).where(ExpertConfig.is_deleted == 0)
        result = await self.db.execute(stmt)
        for config in result.scalars().all():
            plugin_configs = config.plugin_config or []
            for pc in plugin_configs:
                if isinstance(pc, dict) and pc.get("plugin_code") == plugin_code:
                    references.append(ReferenceInfo(
                        entity_type="ExpertConfig",
                        entity_id=config.expert_config_code,
                        entity_name=config.expert_config_name,
                        reference_field="plugin_config"
                    ))
                    break
        
        can_delete = len(references) == 0
        can_disable = can_delete  # Plugin 被引用时不建议禁用
        
        return ReferenceCheckResult(
            can_delete=can_delete,
            can_disable=can_disable,
            references=references,
            warning_message=f"Plugin 被 {len(references)} 个 ExpertConfig 引用" if references else ""
        )
    
    # ==================== PluginContext 引用检查 ====================
    
    async def check_plugin_context_references(self, context_name: str) -> ReferenceCheckResult:
        """
        检查 PluginContext 的引用情况
        
        PluginContext 被 ExpertConfig.plugin_config 中的 variable_mapping 引用
        """
        references: List[ReferenceInfo] = []
        
        # 检查 ExpertConfig 引用
        stmt = select(ExpertConfig).where(ExpertConfig.is_deleted == 0)
        result = await self.db.execute(stmt)
        for config in result.scalars().all():
            plugin_configs = config.plugin_config or []
            for pc in plugin_configs:
                if isinstance(pc, dict):
                    variable_mapping = pc.get("variable_mapping", {})
                    if context_name in variable_mapping.values():
                        references.append(ReferenceInfo(
                            entity_type="ExpertConfig",
                            entity_id=config.expert_config_code,
                            entity_name=config.expert_config_name,
                            reference_field="plugin_config.variable_mapping"
                        ))
                        break
        
        can_delete = len(references) == 0
        can_disable = can_delete
        
        return ReferenceCheckResult(
            can_delete=can_delete,
            can_disable=can_disable,
            references=references,
            warning_message=f"PluginContext 被 {len(references)} 个 ExpertConfig 引用" if references else ""
        )
    
    # ==================== Activity 引用检查 ====================
    
    async def check_activity_references(self, activity_id: int) -> ReferenceCheckResult:
        """
        检查 Activity 的引用情况
        
        Activity 被以下实体引用：
        - Job.activity_id
        """
        references: List[ReferenceInfo] = []
        
        # 检查 Job 引用
        stmt = select(Job).where(
            Job.activity_id == activity_id,
            Job.is_deleted == 0
        )
        result = await self.db.execute(stmt)
        for job in result.scalars().all():
            references.append(ReferenceInfo(
                entity_type="Job",
                entity_id=job.job_id,
                entity_name=job.job_name,
                reference_field="activity_id"
            ))
        
        # 检查是否有运行中的 Job
        active_jobs = [r for r in references if r.entity_type == "Job"]
        
        can_delete = len(references) == 0
        can_disable = True  # Activity 禁用不影响已创建的 Job
        
        return ReferenceCheckResult(
            can_delete=can_delete,
            can_disable=can_disable,
            references=references,
            warning_message=f"Activity 下有 {len(active_jobs)} 个 Job" if active_jobs else ""
        )
    
    # ==================== 通用验证方法 ====================
    
    async def validate_agent_config(self, agent_code: str) -> Dict[str, Any]:
        """
        验证 Agent 配置的完整性
        
        检查：
        1. expert_config_code_list 中的所有 ExpertConfig 是否存在且启用
        2. 关联的 Plugin 是否存在且启用
        """
        errors = []
        warnings = []
        
        # 获取 Agent
        stmt = select(Agent).where(Agent.agent_code == agent_code, Agent.is_deleted == 0)
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            return {"valid": False, "errors": ["Agent 不存在"], "warnings": []}
        
        # 检查 ExpertConfig
        expert_codes = agent.expert_config_code_list or []
        for code in expert_codes:
            stmt = select(ExpertConfig).where(
                ExpertConfig.expert_config_code == code,
                ExpertConfig.is_deleted == 0
            )
            result = await self.db.execute(stmt)
            config = result.scalar_one_or_none()
            
            if not config:
                errors.append(f"ExpertConfig '{code}' 不存在")
            elif not config.enabled:
                warnings.append(f"ExpertConfig '{code}' 已禁用")
            else:
                # 检查 Plugin
                plugin_configs = config.plugin_config or []
                for pc in plugin_configs:
                    if isinstance(pc, dict):
                        plugin_code = pc.get("plugin_code")
                        if plugin_code:
                            stmt = select(Plugin).where(
                                Plugin.plugin_code == plugin_code,
                                Plugin.is_deleted == 0
                            )
                            result = await self.db.execute(stmt)
                            plugin = result.scalar_one_or_none()
                            
                            if not plugin:
                                errors.append(f"Plugin '{plugin_code}' (被 {code} 引用) 不存在")
                            elif not plugin.enabled:
                                warnings.append(f"Plugin '{plugin_code}' (被 {code} 引用) 已禁用")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
    
    async def get_entity_dependency_tree(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        """
        获取实体的依赖树
        
        返回该实体依赖的所有下游实体
        """
        if entity_type == "Agent":
            return await self._get_agent_dependency_tree(entity_id)
        elif entity_type == "ExpertConfig":
            return await self._get_expert_config_dependency_tree(entity_id)
        elif entity_type == "Plugin":
            return await self._get_plugin_dependency_tree(entity_id)
        return {}
    
    async def _get_agent_dependency_tree(self, agent_code: str) -> Dict[str, Any]:
        """获取 Agent 的依赖树"""
        stmt = select(Agent).where(Agent.agent_code == agent_code, Agent.is_deleted == 0)
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            return {}
        
        tree = {
            "type": "Agent",
            "code": agent_code,
            "name": agent.agent_name,
            "dependencies": []
        }
        
        for expert_code in (agent.expert_config_code_list or []):
            expert_tree = await self._get_expert_config_dependency_tree(expert_code)
            if expert_tree:
                tree["dependencies"].append(expert_tree)
        
        return tree
    
    async def _get_expert_config_dependency_tree(self, expert_config_code: str) -> Dict[str, Any]:
        """获取 ExpertConfig 的依赖树"""
        stmt = select(ExpertConfig).where(
            ExpertConfig.expert_config_code == expert_config_code,
            ExpertConfig.is_deleted == 0
        )
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()
        
        if not config:
            return {"type": "ExpertConfig", "code": expert_config_code, "status": "NOT_FOUND"}
        
        tree = {
            "type": "ExpertConfig",
            "code": expert_config_code,
            "name": config.expert_config_name,
            "enabled": config.enabled,
            "dependencies": []
        }
        
        for pc in (config.plugin_config or []):
            if isinstance(pc, dict):
                plugin_code = pc.get("plugin_code")
                if plugin_code:
                    plugin_tree = await self._get_plugin_dependency_tree(plugin_code)
                    if plugin_tree:
                        tree["dependencies"].append(plugin_tree)
        
        return tree
    
    async def _get_plugin_dependency_tree(self, plugin_code: str) -> Dict[str, Any]:
        """获取 Plugin 的依赖树"""
        stmt = select(Plugin).where(Plugin.plugin_code == plugin_code, Plugin.is_deleted == 0)
        result = await self.db.execute(stmt)
        plugin = result.scalar_one_or_none()
        
        if not plugin:
            return {"type": "Plugin", "code": plugin_code, "status": "NOT_FOUND"}
        
        return {
            "type": "Plugin",
            "code": plugin_code,
            "name": plugin.plugin_name,
            "enabled": plugin.enabled,
        }


