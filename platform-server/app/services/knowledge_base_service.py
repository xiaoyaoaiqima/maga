"""
知识库 Service（KnowledgeBase - 知识库容器）
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase
from app.schemas.base import ResponseData
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseItem,
    KnowledgeBaseListQuery,
    KnowledgeBaseUpdate,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """知识库服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_list(
        self,
        keyword: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> list[KnowledgeBaseItem]:
        """获取知识库列表"""
        stmt = select(KnowledgeBase).where(KnowledgeBase.is_deleted == 0)

        if enabled is not None:
            stmt = stmt.where(KnowledgeBase.enabled == (1 if enabled else 0))
        if keyword:
            stmt = stmt.where(
                (KnowledgeBase.name.like(f"%{keyword}%"))
                | (KnowledgeBase.code.like(f"%{keyword}%"))
            )

        stmt = stmt.order_by(KnowledgeBase.id.desc())

        result = await self.db.execute(stmt)
        return [KnowledgeBaseItem.model_validate(row) for row in result.scalars()]

    async def get_by_id(self, pool_id: int) -> Optional[KnowledgeBaseItem]:
        """根据ID获取知识库"""
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.id == pool_id,
            KnowledgeBase.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            return KnowledgeBaseItem.model_validate(row)
        return None

    async def get_by_code(
        self, code: str
    ) -> Optional[KnowledgeBaseItem]:
        """根据编码获取知识库"""
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.code == code,
            KnowledgeBase.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            return KnowledgeBaseItem.model_validate(row)
        return None

    async def create(self, data: KnowledgeBaseCreate) -> KnowledgeBaseItem:
        """创建知识库"""
        # 如果没有指定 code，自动生成
        code = data.code
        if not code:
            # 基于时间戳生成
            import time

            timestamp = str(int(time.time()))
            code = f"pool_{timestamp}"

        # 检查 code 是否重复
        existing = await self.get_by_code(code)
        if existing:
            raise ValueError(f"编码 {code} 已存在")

        pool = KnowledgeBase(
            code=code,
            name=data.name,
            description=data.description,
            enabled=data.enabled,
            file_count=0,
            total_parsed_count=0,
            created_by=data.created_by,
        )
        self.db.add(pool)
        await self.db.commit()
        await self.db.refresh(pool)

        logger.info(f"创建知识库: {pool.id} - {pool.name}")
        return KnowledgeBaseItem.model_validate(pool)

    async def update(
        self, pool_id: int, data: KnowledgeBaseUpdate
    ) -> Optional[KnowledgeBaseItem]:
        """更新知识库"""
        pool = await self.db.get(KnowledgeBase, pool_id)
        if not pool or pool.is_deleted:
            return None

        if data.name is not None:
            pool.name = data.name
        if data.description is not None:
            pool.description = data.description
        if data.enabled is not None:
            pool.enabled = data.enabled

        await self.db.commit()
        await self.db.refresh(pool)

        logger.info(f"更新知识库: {pool_id}")
        return KnowledgeBaseItem.model_validate(pool)

    async def delete(self, pool_id: int) -> bool:
        """软删除知识库"""
        pool = await self.db.get(KnowledgeBase, pool_id)
        if not pool or pool.is_deleted:
            return False

        pool.is_deleted = 1
        await self.db.commit()

        logger.info(f"删除知识库: {pool_id} - {pool.name}")
        return True

    async def toggle_enabled(self, pool_id: int) -> Optional[KnowledgeBaseItem]:
        """切换启用状态"""
        pool = await self.db.get(KnowledgeBase, pool_id)
        if not pool or pool.is_deleted:
            return None

        pool.enabled = 1 if pool.enabled == 0 else 0
        await self.db.commit()
        await self.db.refresh(pool)

        logger.info(f"切换知识库状态: {pool_id} - enabled={pool.enabled}")
        return KnowledgeBaseItem.model_validate(pool)

    async def increment_file_count(
        self, pool_id: int, count: int = 1
    ) -> None:
        """增加文件计数"""
        await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == pool_id)
        )
        pool = await self.db.get(KnowledgeBase, pool_id)
        if pool and not pool.is_deleted:
            pool.file_count += count
            await self.db.commit()

    async def decrement_file_count(
        self, pool_id: int, count: int = 1
    ) -> None:
        """减少文件计数"""
        await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == pool_id)
        )
        pool = await self.db.get(KnowledgeBase, pool_id)
        if pool and not pool.is_deleted:
            pool.file_count = max(0, pool.file_count - count)
            await self.db.commit()

    async def update_parsed_count(
        self, pool_id: int, parsed_count: int
    ) -> None:
        """更新解析计数"""
        await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == pool_id)
        )
        pool = await self.db.get(KnowledgeBase, pool_id)
        if pool and not pool.is_deleted:
            pool.total_parsed_count += parsed_count
            await self.db.commit()
