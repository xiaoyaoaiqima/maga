"""
PluginContext service - Business logic for plugin_context operations
"""
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plugin_context import PluginContext
from app.schemas.plugin_context import PluginContextCreate, PluginContextUpdate


class PluginContextService:
    """PluginContext service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get(self, context_id: int) -> Optional[PluginContext]:
        """Get plugin_context by ID"""
        result = await self.db.execute(
            select(PluginContext).where(PluginContext.id == context_id, PluginContext.is_deleted == 0)
        )
        return result.scalar_one_or_none()
    
    async def get_by_context_name(self, context_name: str) -> Optional[PluginContext]:
        """Get plugin_context by context_name (returns the first one if multiple exist)"""
        result = await self.db.execute(
            select(PluginContext)
            .where(
                PluginContext.context_name == context_name,
                PluginContext.is_deleted == 0
            )
            .order_by(PluginContext.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_context_names_batch(
        self, context_names: List[str]
    ) -> dict[str, PluginContext]:
        """
        批量获取 plugin_context（性能优化：1次查询替代N次）

        Args:
            context_names: context_name 列表

        Returns:
            dict[context_name, PluginContext] 映射
        """
        if not context_names:
            return {}

        # 去重
        unique_names = list(set(context_names))

        result = await self.db.execute(
            select(PluginContext).where(
                PluginContext.context_name.in_(unique_names),
                PluginContext.is_deleted == 0,
            )
        )
        contexts = result.scalars().all()

        # 构建映射（如果有重复 context_name，取最新的）
        context_map: dict[str, PluginContext] = {}
        for ctx in contexts:
            existing = context_map.get(ctx.context_name)
            if existing is None or ctx.id > existing.id:
                context_map[ctx.context_name] = ctx

        return context_map
    
    async def list(
        self,
        variable_name: Optional[str] = None,
        context_name: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[PluginContext]:
        """List plugin_contexts with optional filters"""
        query = select(PluginContext).where(PluginContext.is_deleted == 0)
        
        if variable_name:
            query = query.where(PluginContext.variable_name == variable_name)
        if context_name:
            query = query.where(PluginContext.context_name == context_name)
        
        result = await self.db.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())
    
    async def create(self, context_in: PluginContextCreate) -> PluginContext:
        """Create plugin_context"""
        context = PluginContext(**context_in.model_dump())
        self.db.add(context)
        await self.db.commit()
        await self.db.refresh(context)
        return context
    
    async def update(self, context_id: int, context_in: PluginContextUpdate) -> Optional[PluginContext]:
        """Update plugin_context"""
        context = await self.get(context_id)
        if not context:
            return None
        
        update_data = context_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(context, field, value)
        
        await self.db.commit()
        await self.db.refresh(context)
        return context
    
    async def delete(self, context_id: int) -> bool:
        """Soft delete plugin_context"""
        context = await self.get(context_id)
        if not context:
            return False
        
        context.is_deleted = 1
        await self.db.commit()
        return True

