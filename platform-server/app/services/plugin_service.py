"""
Plugin service - Business logic for plugin operations

v2 重构：
- 新增 update_variable_mappings 方法
- 新增 get_by_strategy 方法
"""
from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plugin import Plugin
from app.schemas.plugin import PluginCreate, PluginUpdate


class PluginService:
    """Plugin service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get(self, plugin_id: int) -> Optional[Plugin]:
        """Get plugin by ID"""
        result = await self.db.execute(
            select(Plugin).where(Plugin.id == plugin_id, Plugin.is_deleted == 0)
        )
        return result.scalar_one_or_none()
    
    async def get_by_code(self, plugin_code: str) -> Optional[Plugin]:
        """Get plugin by code"""
        result = await self.db.execute(
            select(Plugin).where(Plugin.plugin_code == plugin_code, Plugin.is_deleted == 0)
        )
        return result.scalar_one_or_none()
    
    async def code_exists(self, plugin_code: str) -> bool:
        """检查 plugin_code 是否存在（包括软删除的记录，用于唯一性检查）"""
        result = await self.db.execute(
            select(Plugin).where(Plugin.plugin_code == plugin_code)
        )
        return result.scalar_one_or_none() is not None
    
    async def list(self, skip: int = 0, limit: int = 100) -> List[Plugin]:
        """List plugins"""
        result = await self.db.execute(
            select(Plugin)
            .where(Plugin.is_deleted == 0)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def create(self, plugin_in: PluginCreate) -> Plugin:
        """Create plugin"""
        # Check if plugin_code already exists
        existing = await self.get_by_code(plugin_in.plugin_code)
        if existing:
            raise ValueError(f"Plugin with code {plugin_in.plugin_code} already exists")
        
        plugin = Plugin(**plugin_in.model_dump())
        self.db.add(plugin)
        await self.db.commit()
        await self.db.refresh(plugin)
        return plugin
    
    async def update(self, plugin_id: int, plugin_in: PluginUpdate) -> Optional[Plugin]:
        """Update plugin"""
        plugin = await self.get(plugin_id)
        if not plugin:
            return None
        
        update_data = plugin_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(plugin, field, value)
        
        await self.db.commit()
        await self.db.refresh(plugin)
        return plugin
    
    async def delete(self, plugin_id: int) -> bool:
        """Soft delete plugin"""
        plugin = await self.get(plugin_id)
        if not plugin:
            return False
        
        plugin.is_deleted = 1
        await self.db.commit()
        return True
    
    # ========== v2 新增方法 ==========
    
    async def update_variable_mappings(
        self,
        plugin_id: int,
        strategy_id: int,
        variable_mappings: List[Dict[str, Any]],
    ) -> Optional[Plugin]:
        """
        更新插件的变量映射配置
        
        Args:
            plugin_id: 插件ID
            strategy_id: 绑定的内容策略ID
            variable_mappings: 变量映射配置列表
        
        Returns:
            更新后的插件实例
        """
        plugin = await self.get(plugin_id)
        if not plugin:
            return None
        
        plugin.strategy_id = strategy_id
        plugin.variable_mappings = variable_mappings
        
        await self.db.commit()
        await self.db.refresh(plugin)
        return plugin
    
    async def get_by_strategy(self, strategy_id: int) -> List[Plugin]:
        """获取绑定到指定策略的所有插件"""
        result = await self.db.execute(
            select(Plugin)
            .where(Plugin.strategy_id == strategy_id, Plugin.is_deleted == 0)
        )
        return list(result.scalars().all())
    
    async def get_plugins_with_strategy(self) -> List[Plugin]:
        """获取所有配置了策略绑定的插件"""
        result = await self.db.execute(
            select(Plugin)
            .where(
                Plugin.strategy_id.isnot(None),
                Plugin.variable_mappings.isnot(None),
                Plugin.is_deleted == 0
            )
        )
        return list(result.scalars().all())

