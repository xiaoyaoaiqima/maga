"""
TestCase service - 测试用例 CRUD
"""
# pylint: disable=not-callable

import hashlib
from typing import Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_case import TestCase
from app.schemas.expert_eval import (
    TestCaseCreate,
    TestCaseImportItem,
    TestCaseUpdate,
)


def _compute_md5(content: str) -> str:
    """计算内容 MD5"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


class TestCaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_test_cases(
        self,
        *,
        test_set_code: str,
        keyword: Optional[str] = None,
        enabled: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[TestCase]]:
        """
        获取指定测试集下的测试用例列表
        """
        conditions = [
            TestCase.is_deleted == 0,
            TestCase.test_set_code == test_set_code,
        ]

        if enabled is not None:
            conditions.append(TestCase.enabled == (1 if enabled else 0))

        if keyword:
            like = f"%{keyword}%"
            conditions.append(
                or_(
                    TestCase.title.like(like),
                    TestCase.content.like(like),
                    TestCase.image_url.like(like),
                )
            )

        where_clause = and_(*conditions)

        total_stmt = select(func.count()).select_from(TestCase).where(where_clause)
        total = (await self.db.execute(total_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = (
            select(TestCase)
            .where(where_clause)
            .order_by(TestCase.create_time.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = (await self.db.execute(stmt)).scalars().all()
        return total, list(items)

    async def get_by_id(self, test_case_id: int) -> Optional[TestCase]:
        """根据 ID 获取测试用例"""
        stmt = select(TestCase).where(
            TestCase.id == test_case_id,
            TestCase.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ids(self, test_case_ids: list[int]) -> list[TestCase]:
        """根据 ID 列表获取测试用例"""
        if not test_case_ids:
            return []
        stmt = select(TestCase).where(
            TestCase.id.in_(test_case_ids),
            TestCase.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        data: TestCaseCreate,
        created_by: Optional[str] = None,
    ) -> TestCase:
        """创建测试用例"""
        # 计算 MD5（用于去重）
        content_for_md5 = data.content or data.image_url or ""
        content_md5 = _compute_md5(content_for_md5) if content_for_md5 else None

        test_case = TestCase(
            test_set_code=data.test_set_code,
            title=data.title,
            content=data.content,
            image_url=data.image_url,
            meta=data.meta,
            tags=data.tags,
            content_md5=content_md5,
            enabled=data.enabled,
            created_by=created_by,
        )
        self.db.add(test_case)
        await self.db.commit()
        await self.db.refresh(test_case)
        return test_case

    async def update(
        self,
        test_case_id: int,
        data: TestCaseUpdate,
    ) -> Optional[TestCase]:
        """更新测试用例"""
        test_case = await self.get_by_id(test_case_id)
        if not test_case:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # 如果更新了 content 或 image_url，重新计算 md5
        if "content" in update_data or "image_url" in update_data:
            content_for_md5 = update_data.get("content") or update_data.get("image_url") or ""
            if content_for_md5:
                update_data["content_md5"] = _compute_md5(content_for_md5)

        for key, value in update_data.items():
            setattr(test_case, key, value)

        await self.db.commit()
        await self.db.refresh(test_case)
        return test_case

    async def delete(self, test_case_id: int) -> bool:
        """软删除测试用例"""
        stmt = (
            update(TestCase)
            .where(TestCase.id == test_case_id, TestCase.is_deleted == 0)
            .values(is_deleted=1)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def toggle_enabled(self, test_case_id: int) -> Optional[TestCase]:
        """切换启用状态"""
        test_case = await self.get_by_id(test_case_id)
        if not test_case:
            return None

        test_case.enabled = 0 if test_case.enabled == 1 else 1
        await self.db.commit()
        await self.db.refresh(test_case)
        return test_case

    async def batch_import(
        self,
        test_set_code: str,
        items: list[TestCaseImportItem],
        enabled: int = 1,
        created_by: Optional[str] = None,
    ) -> tuple[int, int]:
        """
        批量导入测试用例
        
        Returns:
            (success_count, skip_count) - 成功数量和跳过（重复）数量
        """
        # 获取现有的 content_md5 用于去重
        stmt = select(TestCase.content_md5).where(
            TestCase.test_set_code == test_set_code,
            TestCase.is_deleted == 0,
            TestCase.content_md5.isnot(None),
        )
        result = await self.db.execute(stmt)
        existing_md5s = set(r[0] for r in result.all() if r[0])

        success_count = 0
        skip_count = 0

        for item in items:
            # 计算 MD5
            content_for_md5 = item.content or item.image_url or ""
            if not content_for_md5:
                skip_count += 1
                continue

            content_md5 = _compute_md5(content_for_md5)

            # 跳过重复
            if content_md5 in existing_md5s:
                skip_count += 1
                continue

            test_case = TestCase(
                test_set_code=test_set_code,
                title=item.title,
                content=item.content,
                image_url=item.image_url,
                meta=item.meta,
                tags=item.tags,
                content_md5=content_md5,
                enabled=enabled,
                created_by=created_by,
            )
            self.db.add(test_case)
            existing_md5s.add(content_md5)
            success_count += 1

        await self.db.commit()
        return success_count, skip_count
