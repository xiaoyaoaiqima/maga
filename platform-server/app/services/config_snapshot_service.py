"""
配置快照服务
"""
from typing import Optional, List, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func, delete

from app.models.config_snapshot import ConfigSnapshot
from app.schemas.config_snapshot import (
    SnapshotSave, 
    SnapshotResponse, 
    EntityType, 
    SnapshotType
)


def get_enum_value(val: Union[str, EntityType, SnapshotType]) -> str:
    """获取枚举值，兼容字符串和枚举类型"""
    if hasattr(val, 'value'):
        return val.value
    return str(val)


class ConfigSnapshotService:
    """配置快照服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def save_draft(
        self, 
        entity_type: Union[str, EntityType],
        entity_code: str,
        content: dict,
        entity_id: Optional[int] = None,
        created_by: Optional[str] = None
    ) -> ConfigSnapshot:
        """
        保存草稿（自动保存）
        同一实体只保留一个草稿，新的会覆盖旧的
        """
        entity_type_str = get_enum_value(entity_type)
        
        # 查找现有草稿
        stmt = select(ConfigSnapshot).where(
            and_(
                ConfigSnapshot.entity_type == entity_type_str,
                ConfigSnapshot.entity_code == entity_code,
                ConfigSnapshot.snapshot_type == SnapshotType.DRAFT.value,
                ConfigSnapshot.is_deleted == False
            )
        )
        result = await self.db.execute(stmt)
        existing_draft = result.scalar_one_or_none()
        
        if existing_draft:
            # 更新现有草稿
            existing_draft.content = content
            existing_draft.entity_id = entity_id
            existing_draft.create_time = func.now()
            existing_draft.created_by = created_by
        else:
            # 创建新草稿
            existing_draft = ConfigSnapshot(
                entity_type=entity_type_str,
                entity_id=entity_id,
                entity_code=entity_code,
                snapshot_type=SnapshotType.DRAFT.value,
                content=content,
                version=0,
                created_by=created_by
            )
            self.db.add(existing_draft)
        
        await self.db.commit()
        await self.db.refresh(existing_draft)
        return existing_draft
    
    async def get_draft(
        self, 
        entity_type: Union[str, EntityType],
        entity_code: str
    ) -> Optional[ConfigSnapshot]:
        """获取草稿"""
        entity_type_str = get_enum_value(entity_type)
        
        stmt = select(ConfigSnapshot).where(
            and_(
                ConfigSnapshot.entity_type == entity_type_str,
                ConfigSnapshot.entity_code == entity_code,
                ConfigSnapshot.snapshot_type == SnapshotType.DRAFT.value,
                ConfigSnapshot.is_deleted == False
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def delete_draft(
        self, 
        entity_type: Union[str, EntityType],
        entity_code: str
    ) -> bool:
        """删除草稿（正式保存后调用）"""
        entity_type_str = get_enum_value(entity_type)
        
        stmt = select(ConfigSnapshot).where(
            and_(
                ConfigSnapshot.entity_type == entity_type_str,
                ConfigSnapshot.entity_code == entity_code,
                ConfigSnapshot.snapshot_type == SnapshotType.DRAFT.value,
                ConfigSnapshot.is_deleted == False
            )
        )
        result = await self.db.execute(stmt)
        draft = result.scalar_one_or_none()
        
        if draft:
            draft.is_deleted = True
            await self.db.commit()
            return True
        return False
    
    async def create_version(
        self, 
        entity_type: Union[str, EntityType],
        entity_id: int,
        entity_code: str,
        content: dict,
        description: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> ConfigSnapshot:
        """
        创建版本快照（正式保存时调用）
        """
        entity_type_str = get_enum_value(entity_type)
        
        # 获取当前最大版本号
        stmt = select(func.max(ConfigSnapshot.version)).where(
            and_(
                ConfigSnapshot.entity_type == entity_type_str,
                ConfigSnapshot.entity_code == entity_code,
                ConfigSnapshot.snapshot_type == SnapshotType.VERSION.value,
                ConfigSnapshot.is_deleted == False
            )
        )
        result = await self.db.execute(stmt)
        max_version = result.scalar() or 0
        
        # 创建新版本
        snapshot = ConfigSnapshot(
            entity_type=entity_type_str,
            entity_id=entity_id,
            entity_code=entity_code,
            snapshot_type=SnapshotType.VERSION.value,
            content=content,
            version=max_version + 1,
            description=description or f"版本 {max_version + 1}",
            created_by=created_by
        )
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        
        # 删除该实体的草稿
        await self.delete_draft(entity_type_str, entity_code)
        
        return snapshot
    
    async def get_versions(
        self, 
        entity_type: Union[str, EntityType],
        entity_code: str,
        limit: int = 50
    ) -> List[ConfigSnapshot]:
        """获取版本历史列表"""
        entity_type_str = get_enum_value(entity_type)
        
        stmt = select(ConfigSnapshot).where(
            and_(
                ConfigSnapshot.entity_type == entity_type_str,
                ConfigSnapshot.entity_code == entity_code,
                ConfigSnapshot.snapshot_type == SnapshotType.VERSION.value,
                ConfigSnapshot.is_deleted == False
            )
        ).order_by(desc(ConfigSnapshot.version)).limit(limit)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_snapshot_by_id(self, snapshot_id: int) -> Optional[ConfigSnapshot]:
        """根据ID获取快照"""
        stmt = select(ConfigSnapshot).where(
            and_(
                ConfigSnapshot.id == snapshot_id,
                ConfigSnapshot.is_deleted == False
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_version_count(
        self, 
        entity_type: Union[str, EntityType],
        entity_code: str
    ) -> int:
        """获取版本数量"""
        entity_type_str = get_enum_value(entity_type)
        
        stmt = select(func.count(ConfigSnapshot.id)).where(
            and_(
                ConfigSnapshot.entity_type == entity_type_str,
                ConfigSnapshot.entity_code == entity_code,
                ConfigSnapshot.snapshot_type == SnapshotType.VERSION.value,
                ConfigSnapshot.is_deleted == False
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

