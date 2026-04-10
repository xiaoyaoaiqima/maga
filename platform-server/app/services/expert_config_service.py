"""
ExpertConfig service - Business logic for expert_config operations
"""
import copy
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expert_config import ExpertConfig
from app.schemas.expert_config import ExpertConfigCreate, ExpertConfigUpdate
from app.utils.plugin_renderer import PluginRenderer


class ExpertConfigService:
    """ExpertConfig service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get(self, expert_config_id: int) -> Optional[ExpertConfig]:
        """Get expert_config by ID"""
        result = await self.db.execute(
            select(ExpertConfig).where(
                ExpertConfig.id == expert_config_id,
                ExpertConfig.is_deleted == 0
            )
        )
        return result.scalar_one_or_none()
    
    async def get_by_code(self, expert_config_code: str) -> Optional[ExpertConfig]:
        """Get expert_config by code"""
        result = await self.db.execute(
            select(ExpertConfig).where(
                ExpertConfig.expert_config_code == expert_config_code,
                ExpertConfig.is_deleted == 0
            )
        )
        return result.scalar_one_or_none()

    async def expert_config_name_exists(
        self, expert_config_name: str, *, exclude_id: Optional[int] = None
    ) -> bool:
        """Check if expert_config_name already exists (non-deleted). exclude_id used when updating."""
        from sqlalchemy import and_
        name = (expert_config_name or "").strip()
        if not name:
            return False
        conditions = [
            ExpertConfig.expert_config_name == name,
            ExpertConfig.is_deleted == 0,
        ]
        if exclude_id is not None:
            conditions.append(ExpertConfig.id != exclude_id)
        stmt = select(ExpertConfig.id).where(and_(*conditions)).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _ensure_expert_config_name_unique(
        self, expert_config_name: str, *, exclude_id: Optional[int] = None
    ) -> None:
        if await self.expert_config_name_exists(
            expert_config_name, exclude_id=exclude_id
        ):
            raise ValueError(f"Expert 名称 '{expert_config_name}' 已存在")

    async def list(
        self,
        expert_type: Optional[str] = None,
        enabled: Optional[bool] = None,
        is_deleted: Optional[bool] = None,
        expert_config_code_list: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[ExpertConfig]:
        """List expert_configs with optional filters"""
        query = select(ExpertConfig)
        if is_deleted is None:
            query = query.where(ExpertConfig.is_deleted == 0)
        else:
            query = query.where(ExpertConfig.is_deleted == int(is_deleted))
        
        if expert_type:
            query = query.where(ExpertConfig.expert_type == expert_type)
        if enabled is not None:
            query = query.where(ExpertConfig.enabled == enabled)
        if expert_config_code_list is not None:
            if not expert_config_code_list:
                return []
            query = query.where(ExpertConfig.expert_config_code.in_(expert_config_code_list))
        
        result = await self.db.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())
    
    async def create(self, expert_config_in: ExpertConfigCreate) -> ExpertConfig:
        """Create expert_config"""
        # Check if expert_config_code already exists
        existing = await self.get_by_code(expert_config_in.expert_config_code)
        if existing:
            raise ValueError(f"ExpertConfig with code {expert_config_in.expert_config_code} already exists")
        await self._ensure_expert_config_name_unique(expert_config_in.expert_config_name)

        # Prepare data for creation
        # Use by_alias=True to get model_config instead of model_params
        config_data = expert_config_in.model_dump(by_alias=True)
        
        # Auto-generate prompt_template from plugin_config if provided
        if config_data.get("plugin_config") and not config_data.get("prompt_template"):
            try:
                prompt_template = await PluginRenderer.render_plugins(
                    self.db,
                    config_data["plugin_config"]
                )
                config_data["prompt_template"] = prompt_template
            except ValueError as e:
                raise ValueError(f"Failed to render plugins: {str(e)}")
        
        expert_config = ExpertConfig(**config_data)
        self.db.add(expert_config)
        await self.db.commit()
        await self.db.refresh(expert_config)
        return expert_config

    async def copy(
        self,
        expert_config_id: int,
        *,
        expert_config_code: str,
        expert_config_name: str,
    ) -> ExpertConfig:
        """复制 ExpertConfig（只覆盖 code/name，其他字段原样复制）"""
        source = await self.get(expert_config_id)
        if not source:
            raise ValueError("ExpertConfig not found")

        existing = await self.get_by_code(expert_config_code)
        if existing:
            raise ValueError(f"ExpertConfig with code {expert_config_code} already exists")
        await self._ensure_expert_config_name_unique(expert_config_name)

        expert_config = ExpertConfig(
            expert_config_code=expert_config_code,
            expert_config_name=expert_config_name,
            tenant_code=source.tenant_code,
            expert_type=source.expert_type,
            expert_app=source.expert_app,
            expert_service=source.expert_service,
            expert_func=source.expert_func,
            description=source.description,
            model_code=source.model_code,
            model_config=copy.deepcopy(source.model_config),
            plugin_config=copy.deepcopy(source.plugin_config),
            prompt_template=source.prompt_template,
            enabled=source.enabled,
            remark=source.remark,
        )

        self.db.add(expert_config)
        await self.db.commit()
        await self.db.refresh(expert_config)
        return expert_config
    
    async def update(
        self,
        expert_config_id: int,
        expert_config_in: ExpertConfigUpdate
    ) -> Optional[ExpertConfig]:
        """Update expert_config"""
        expert_config = await self.get(expert_config_id)
        if not expert_config:
            return None
        
        # Use by_alias=True to get model_config instead of model_params
        update_data = expert_config_in.model_dump(exclude_unset=True, by_alias=True)

        if "expert_config_name" in update_data and update_data["expert_config_name"] != expert_config.expert_config_name:
            await self._ensure_expert_config_name_unique(
                update_data["expert_config_name"], exclude_id=expert_config_id
            )

        # 只有当用户没有显式提供 prompt_template 时，才根据 plugin_config 自动渲染
        # 如果用户手动修改了 prompt_template，则使用用户的值
        user_provided_prompt = "prompt_template" in update_data and update_data["prompt_template"] is not None

        if "plugin_config" in update_data and not user_provided_prompt:
            plugin_config = update_data["plugin_config"]
            if plugin_config:
                try:
                    prompt_template = await PluginRenderer.render_plugins(
                        self.db,
                        plugin_config
                    )
                    update_data["prompt_template"] = prompt_template
                except ValueError as e:
                    raise ValueError(f"Failed to render plugins: {str(e)}")
            else:
                # If plugin_config is cleared and no user prompt provided, clear prompt_template too
                update_data["prompt_template"] = None
        
        for field, value in update_data.items():
            setattr(expert_config, field, value)
        
        await self.db.commit()
        await self.db.refresh(expert_config)
        return expert_config
    
    async def delete(self, expert_config_id: int) -> bool:
        """Soft delete expert_config"""
        expert_config = await self.get(expert_config_id)
        if not expert_config:
            return False
        
        expert_config.is_deleted = True
        await self.db.commit()
        return True

