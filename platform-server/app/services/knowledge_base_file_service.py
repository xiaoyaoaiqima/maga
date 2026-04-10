"""
知识库文件服务 - 管理单个上传文件

注意：KnowledgeBaseFile 表示单个上传的文件，属于某个 KnowledgeBase
一个 KnowledgeBase 可以包含多个 KnowledgeBaseFile
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base_file import KnowledgeBaseFile
from app.schemas.knowledge_base_file import (
    KnowledgeBaseFileCreate,
    KnowledgeBaseFileItem,
    KnowledgeBaseFileUpdate,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseFileService:
    """知识库文件服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_list(
        self,
        knowledge_base_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[KnowledgeBaseFileItem]:
        """获取知识库文件列表"""
        conditions = [KnowledgeBaseFile.is_deleted == 0]

        if knowledge_base_id:
            conditions.append(KnowledgeBaseFile.knowledge_base_id == knowledge_base_id)
        if status:
            conditions.append(KnowledgeBaseFile.status == status)

        stmt = (
            select(KnowledgeBaseFile)
            .where(and_(*conditions))
            .order_by(KnowledgeBaseFile.id.desc())
        )

        result = await self.db.execute(stmt)
        file_pools = result.scalars().all()

        return [self._to_item(fp) for fp in file_pools]

    async def get_by_id(self, id: int) -> Optional[KnowledgeBaseFileItem]:
        """根据 ID 获取文件"""
        stmt = select(KnowledgeBaseFile).where(
            and_(
                KnowledgeBaseFile.id == id,
                KnowledgeBaseFile.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        file_pool = result.scalar_one_or_none()

        if not file_pool:
            return None

        return self._to_item(file_pool)

    async def create(self, data: KnowledgeBaseFileCreate) -> KnowledgeBaseFileItem:
        """创建知识库文件记录"""
        file_pool = KnowledgeBaseFile(
            knowledge_base_id=data.knowledge_base_id,
            file_name=data.file_name,
            file_path=data.file_path,
            file_size=data.file_size,
            file_type=data.file_type,
            created_by=data.created_by,
            status="pending",
        )

        self.db.add(file_pool)
        await self.db.commit()
        await self.db.refresh(file_pool)

        logger.info(f"创建知识库文件记录: {file_pool.id} - {data.file_name}")
        return self._to_item(file_pool)

    async def update_status(
        self,
        id: int,
        status: str,
        parsed_count: Optional[int] = None,
        total_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Optional[KnowledgeBaseFileItem]:
        """更新文件处理状态"""
        stmt = select(KnowledgeBaseFile).where(
            and_(
                KnowledgeBaseFile.id == id,
                KnowledgeBaseFile.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        file_pool = result.scalar_one_or_none()

        if not file_pool:
            return None

        file_pool.status = status
        if parsed_count is not None:
            file_pool.parsed_count = parsed_count
        if total_count is not None:
            file_pool.total_count = total_count
        if error_message is not None:
            file_pool.error_message = error_message

        await self.db.commit()
        await self.db.refresh(file_pool)

        logger.info(f"更新知识库文件状态: {id} -> {status}")
        return self._to_item(file_pool)

    async def update(self, id: int, data: KnowledgeBaseFileUpdate) -> Optional[KnowledgeBaseFileItem]:
        """更新知识库文件信息"""
        stmt = select(KnowledgeBaseFile).where(
            and_(
                KnowledgeBaseFile.id == id,
                KnowledgeBaseFile.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        file_pool = result.scalar_one_or_none()

        if not file_pool:
            return None

        if data.status is not None:
            file_pool.status = data.status
        if data.parsed_count is not None:
            file_pool.parsed_count = data.parsed_count
        if data.total_count is not None:
            file_pool.total_count = data.total_count
        if data.error_message is not None:
            file_pool.error_message = data.error_message

        await self.db.commit()
        await self.db.refresh(file_pool)

        return self._to_item(file_pool)

    async def delete(self, id: int, delete_file: bool = False) -> bool:
        """删除知识库文件记录（软删除）"""
        stmt = select(KnowledgeBaseFile).where(
            and_(
                KnowledgeBaseFile.id == id,
                KnowledgeBaseFile.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        file_pool = result.scalar_one_or_none()

        if not file_pool:
            return False

        # 可选：删除物理文件
        if delete_file and file_pool.file_path:
            try:
                file_path = Path(file_pool.file_path)
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"删除物理文件: {file_pool.file_path}")
            except Exception as e:
                logger.warning(f"删除物理文件失败: {e}")

        file_pool.is_deleted = 1
        await self.db.commit()

        logger.info(f"删除知识库文件记录: {id}")
        return True

    async def get_by_knowledge_base(
        self,
        knowledge_base_id: int,
    ) -> list[KnowledgeBaseFileItem]:
        """根据知识库 ID 获取文件列表"""
        stmt = (
            select(KnowledgeBaseFile)
            .where(
                and_(
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                    KnowledgeBaseFile.is_deleted == 0,
                )
            )
            .order_by(KnowledgeBaseFile.id.desc())
        )
        result = await self.db.execute(stmt)
        file_pools = result.scalars().all()

        return [self._to_item(fp) for fp in file_pools]

    async def count_by_knowledge_base(self, knowledge_base_id: int) -> int:
        """统计知识库下的文件数量"""
        stmt = select(KnowledgeBaseFile).where(
            and_(
                KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseFile.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        return len(result.scalars().all())

    async def get_total_parsed_count(self, knowledge_base_id: int) -> int:
        """获取知识库的总解析记录数"""
        stmt = select(KnowledgeBaseFile).where(
            and_(
                KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseFile.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        file_pools = result.scalars().all()

        return sum(fp.parsed_count for fp in file_pools)

    async def update_parse_result(
        self,
        id: int,
        parsed_count: int,
        total_count: int,
        error_message: Optional[str] = None,
    ) -> Optional[KnowledgeBaseFileItem]:
        """更新解析结果"""
        return await self.update_status(
            id,
            status="parsed" if error_message is None else "failed",
            parsed_count=parsed_count,
            total_count=total_count,
            error_message=error_message,
        )

    def _to_item(self, file_pool: KnowledgeBaseFile) -> KnowledgeBaseFileItem:
        """转换为响应项"""
        return KnowledgeBaseFileItem(
            id=file_pool.id,
            knowledge_base_id=file_pool.knowledge_base_id,
            file_name=file_pool.file_name,
            file_path=file_pool.file_path,
            file_size=file_pool.file_size,
            file_type=file_pool.file_type,
            status=file_pool.status,
            parsed_count=file_pool.parsed_count,
            total_count=file_pool.total_count,
            error_message=file_pool.error_message,
            created_at=file_pool.created_at,
            updated_at=file_pool.updated_at,
            created_by=file_pool.created_by,
        )
