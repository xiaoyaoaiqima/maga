"""
TestSet service - 测试集 CRUD
"""
# pylint: disable=not-callable

import uuid
from typing import Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_set import TestSet
from app.models.test_case import TestCase
from app.schemas.expert_eval import (
    TestSetCreate,
    TestSetUpdate,
)


def _generate_code() -> str:
    """生成唯一编码"""
    return f"ts_{uuid.uuid4().hex[:12]}"


class TestSetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_test_sets(
        self,
        *,
        keyword: Optional[str] = None,
        type_filter: Optional[str] = None,
        enabled: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[dict]]:
        """
        获取测试集列表（带案例数量统计）
        
        Returns:
            (total, items) - 总数和测试集列表（含 case_count）
        """
        conditions = [TestSet.is_deleted == 0]

        if keyword:
            like = f"%{keyword}%"
            conditions.append(or_(TestSet.name.like(like), TestSet.code.like(like)))

        if type_filter:
            conditions.append(TestSet.type == type_filter)

        if enabled is not None:
            conditions.append(TestSet.enabled == (1 if enabled else 0))

        where_clause = and_(*conditions)

        # 获取总数
        total_stmt = select(func.count()).select_from(TestSet).where(where_clause)
        total = (await self.db.execute(total_stmt)).scalar() or 0

        # 获取列表
        offset = (page - 1) * page_size
        stmt = (
            select(TestSet)
            .where(where_clause)
            .order_by(TestSet.create_time.desc())
            .offset(offset)
            .limit(page_size)
        )
        test_sets = (await self.db.execute(stmt)).scalars().all()

        # 批量获取案例数量（通过 code 关联）
        if test_sets:
            test_set_codes = [ts.code for ts in test_sets]
            count_stmt = (
                select(TestCase.test_set_code, func.count())
                .where(
                    TestCase.test_set_code.in_(test_set_codes),
                    TestCase.is_deleted == 0,
                )
                .group_by(TestCase.test_set_code)
            )
            count_result = await self.db.execute(count_stmt)
            count_map = {r[0]: r[1] for r in count_result.all()}
        else:
            count_map = {}

        # 组装结果
        items = []
        for ts in test_sets:
            items.append({
                "id": ts.id,
                "code": ts.code,
                "name": ts.name,
                "type": ts.type,
                "description": ts.description,
                "enabled": ts.enabled,
                "case_count": count_map.get(ts.code, 0),
                "create_time": ts.create_time.isoformat() if ts.create_time else None,
                "update_time": ts.update_time.isoformat() if ts.update_time else None,
            })

        return total, items

    async def get_by_id(self, test_set_id: int) -> Optional[TestSet]:
        """根据 ID 获取测试集"""
        stmt = select(TestSet).where(
            TestSet.id == test_set_id,
            TestSet.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[TestSet]:
        """根据 code 获取测试集"""
        stmt = select(TestSet).where(
            TestSet.code == code,
            TestSet.is_deleted == 0,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_detail(self, test_set_id: int) -> Optional[dict]:
        """获取测试集详情（含案例数量）"""
        test_set = await self.get_by_id(test_set_id)
        if not test_set:
            return None

        return await self._build_detail(test_set)

    async def get_detail_by_code(self, code: str) -> Optional[dict]:
        """根据 code 获取测试集详情（含案例数量）"""
        test_set = await self.get_by_code(code)
        if not test_set:
            return None

        return await self._build_detail(test_set)

    async def _build_detail(self, test_set: TestSet) -> dict:
        """构建测试集详情"""
        # 获取案例数量（通过 code 关联）
        count_stmt = (
            select(func.count())
            .select_from(TestCase)
            .where(
                TestCase.test_set_code == test_set.code,
                TestCase.is_deleted == 0,
            )
        )
        case_count = (await self.db.execute(count_stmt)).scalar() or 0

        return {
            "id": test_set.id,
            "code": test_set.code,
            "name": test_set.name,
            "type": test_set.type,
            "description": test_set.description,
            "enabled": test_set.enabled,
            "case_count": case_count,
            "create_time": test_set.create_time.isoformat() if test_set.create_time else None,
            "update_time": test_set.update_time.isoformat() if test_set.update_time else None,
        }

    async def create(
        self,
        data: TestSetCreate,
        created_by: Optional[str] = None,
    ) -> TestSet:
        """创建测试集"""
        code = data.code if data.code else _generate_code()

        # 检查 code 是否已存在
        existing = await self.get_by_code(code)
        if existing:
            raise ValueError(f"测试集编码 '{code}' 已存在")

        test_set = TestSet(
            code=code,
            name=data.name,
            type=data.type,
            description=data.description,
            enabled=data.enabled,
            created_by=created_by,
        )
        self.db.add(test_set)
        await self.db.commit()
        await self.db.refresh(test_set)
        return test_set

    async def update(
        self,
        test_set_id: int,
        data: TestSetUpdate,
    ) -> Optional[TestSet]:
        """更新测试集"""
        test_set = await self.get_by_id(test_set_id)
        if not test_set:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            setattr(test_set, key, value)

        await self.db.commit()
        await self.db.refresh(test_set)
        return test_set

    async def delete(self, test_set_id: int) -> bool:
        """软删除测试集"""
        stmt = (
            update(TestSet)
            .where(TestSet.id == test_set_id, TestSet.is_deleted == 0)
            .values(is_deleted=1)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def toggle_enabled(self, test_set_id: int) -> Optional[TestSet]:
        """切换启用状态"""
        test_set = await self.get_by_id(test_set_id)
        if not test_set:
            return None

        test_set.enabled = 0 if test_set.enabled == 1 else 1
        await self.db.commit()
        await self.db.refresh(test_set)
        return test_set

    async def get_all_options(self) -> list[dict]:
        """获取所有测试集选项（用于下拉选择，含 case_count）"""
        stmt = (
            select(TestSet)
            .where(TestSet.is_deleted == 0, TestSet.enabled == 1)
            .order_by(TestSet.create_time.desc())
        )
        test_sets = (await self.db.execute(stmt)).scalars().all()

        if not test_sets:
            return []

        # 批量获取案例数量
        codes = [ts.code for ts in test_sets]
        count_stmt = (
            select(TestCase.test_set_code, func.count())
            .where(
                TestCase.test_set_code.in_(codes),
                TestCase.is_deleted == 0,
            )
            .group_by(TestCase.test_set_code)
        )
        count_result = await self.db.execute(count_stmt)
        count_map = {r[0]: r[1] for r in count_result.all()}

        return [
            {
                "id": ts.id,
                "code": ts.code,
                "name": ts.name,
                "type": ts.type,
                "case_count": count_map.get(ts.code, 0),
            }
            for ts in test_sets
        ]

