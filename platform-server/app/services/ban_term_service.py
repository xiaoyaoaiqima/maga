"""
BAN 词表管理服务
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.ban_term import BanTerm, BanTermMeta
from app.models.sys_user import SysUser
from app.schemas.ban_term import BanTermCreate, BanTermListQuery, BanTermUpdate


def _normalize_term(term: str) -> str:
    return term.strip()


async def list_terms(*, session: AsyncSession, query: BanTermListQuery) -> tuple[list[dict], int]:
    conditions = [BanTerm.is_deleted == 0]
    if query.tenant_code:
        conditions.append(BanTerm.tenant_code == query.tenant_code.strip())
    if query.keyword:
        conditions.append(BanTerm.term.like(f"%{query.keyword.strip()}%"))
    if query.list_type:
        conditions.append(BanTerm.list_type == query.list_type)
    if query.category:
        conditions.append(BanTerm.category == query.category.strip())
    if query.enabled is not None:
        conditions.append(BanTerm.enabled.is_(query.enabled))

    # LEFT JOIN sys_user 获取创建者和修改者的用户名
    creator = SysUser.__table__.alias("creator")
    updater = SysUser.__table__.alias("updater")

    stmt = (
        select(
            BanTerm.id,
            BanTerm.tenant_code,
            BanTerm.term,
            BanTerm.list_type,
            BanTerm.category,
            BanTerm.enabled,
            creator.c.username.label("created_by_name"),
            updater.c.username.label("updated_by_name"),
            BanTerm.create_time,
            BanTerm.update_time,
        )
        .join(creator, creator.c.id == BanTerm.created_by, isouter=True)
        .join(updater, updater.c.id == BanTerm.updated_by, isouter=True)
        .where(and_(*conditions))
        .order_by(BanTerm.update_time.desc(), BanTerm.id.desc())
    )
    count_stmt = select(func.count()).select_from(BanTerm).where(and_(*conditions))

    total = int((await session.execute(count_stmt)).scalar() or 0)
    page = max(int(query.page), 1)
    page_size = min(max(int(query.page_size), 1), 200)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    items = [row._asdict() for row in result.fetchall()]
    return items, total


async def create_term(*, session: AsyncSession, payload: BanTermCreate, operator: str = "system") -> BanTerm:
    term = _normalize_term(payload.term)
    if not term:
        raise ValueError("term 不能为空")

    tenant_code = payload.tenant_code.strip() if payload.tenant_code else "default"

    dup_stmt = select(func.count()).select_from(BanTerm).where(
        and_(
            BanTerm.is_deleted == 0,
            BanTerm.tenant_code == tenant_code,
            BanTerm.term == term,
            BanTerm.list_type == payload.list_type,
            BanTerm.category == payload.category,
        )
    )
    dup = int((await session.execute(dup_stmt)).scalar() or 0)
    if dup:
        raise ValueError("该词条已存在")

    obj = BanTerm(
        tenant_code=tenant_code,
        term=term,
        list_type=payload.list_type,
        category=payload.category,
        enabled=payload.enabled,
        created_by=operator,
        updated_by=operator,
    )
    session.add(obj)
    await session.flush()
    await session.refresh(obj)
    return obj


async def update_term(
    *,
    session: AsyncSession,
    term_id: int,
    payload: BanTermUpdate,
    operator: str = "system",
) -> Optional[BanTerm]:
    obj = await session.get(BanTerm, term_id)
    if obj is None or obj.is_deleted != 0:
        return None

    target_tenant_code = payload.tenant_code.strip() if payload.tenant_code is not None else obj.tenant_code
    target_term = _normalize_term(payload.term) if payload.term is not None else obj.term
    target_list_type = payload.list_type if payload.list_type is not None else obj.list_type
    target_category = payload.category.strip() if payload.category is not None else obj.category

    # 若修改了唯一键，做去重校验
    unique_key = (target_tenant_code, target_term, target_list_type, target_category)
    old_unique_key = (obj.tenant_code, obj.term, obj.list_type, obj.category)
    if unique_key != old_unique_key:
        dup_stmt = select(func.count()).select_from(BanTerm).where(
            and_(
                BanTerm.is_deleted == 0,
                BanTerm.id != obj.id,
                BanTerm.tenant_code == target_tenant_code,
                BanTerm.term == target_term,
                BanTerm.list_type == target_list_type,
                BanTerm.category == target_category,
            )
        )
        dup = int((await session.execute(dup_stmt)).scalar() or 0)
        if dup:
            raise ValueError("该词条已存在")

    if payload.tenant_code is not None:
        obj.tenant_code = target_tenant_code
    if payload.term is not None:
        obj.term = target_term
    if payload.list_type is not None:
        obj.list_type = payload.list_type
    if payload.category is not None:
        obj.category = target_category
    if payload.enabled is not None:
        obj.enabled = payload.enabled
    obj.updated_by = operator

    await session.flush()
    await session.refresh(obj)
    return obj


async def delete_term(*, session: AsyncSession, term_id: int, operator: str = "system") -> bool:
    obj = await session.get(BanTerm, term_id)
    if obj is None or obj.is_deleted != 0:
        return False
    obj.is_deleted = 1
    obj.updated_by = operator
    await session.flush()
    return True


async def get_meta(*, session: AsyncSession) -> tuple[int, int, int]:
    meta = await session.get(BanTermMeta, 1)
    if meta is None:
        meta = BanTermMeta(id=1, active_version=1, created_by="system", updated_by="system")
        session.add(meta)
        await session.flush()

    whitelist_count_stmt = select(func.count()).select_from(BanTerm).where(
        and_(
            BanTerm.is_deleted == 0,
            BanTerm.enabled.is_(True),
            BanTerm.list_type == "WHITELIST",
        )
    )
    blacklist_count_stmt = select(func.count()).select_from(BanTerm).where(
        and_(
            BanTerm.is_deleted == 0,
            BanTerm.enabled.is_(True),
            BanTerm.list_type == "BLACKLIST",
        )
    )
    whitelist_count = int((await session.execute(whitelist_count_stmt)).scalar() or 0)
    blacklist_count = int((await session.execute(blacklist_count_stmt)).scalar() or 0)
    return int(meta.active_version or 0), whitelist_count, blacklist_count


async def publish(*, session: AsyncSession, operator: str = "system") -> int:
    meta = await session.get(BanTermMeta, 1)
    if meta is None:
        meta = BanTermMeta(id=1, active_version=1, created_by=operator, updated_by=operator)
        session.add(meta)
        await session.flush()

    # 使用 SQL 层原子自增，避免并发发布丢失
    await session.execute(
        update(BanTermMeta)
        .where(BanTermMeta.id == 1)
        .values(active_version=BanTermMeta.active_version + 1, updated_by=operator)
    )
    await session.flush()
    await session.refresh(meta)
    return int(meta.active_version or 0)


async def list_tenant_codes(*, session: AsyncSession) -> list[str]:
    """
    获取所有不重复的租户编码（未删除的词条）
    """
    stmt = (
        select(BanTerm.tenant_code)
        .where(and_(BanTerm.is_deleted == 0))
        .distinct()
        .order_by(BanTerm.tenant_code)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.fetchall() if row[0]]


async def list_categories(*, session: AsyncSession) -> list[str]:
    """
    获取所有不重复的分类（未删除的词条）
    """
    stmt = (
        select(BanTerm.category)
        .where(and_(BanTerm.is_deleted == 0))
        .distinct()
        .order_by(BanTerm.category)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.fetchall() if row[0]]


async def list_list_types(*, session: AsyncSession) -> list[str]:
    """
    获取所有不重复的名单类型（未删除的词条）
    """
    stmt = (
        select(BanTerm.list_type)
        .where(and_(BanTerm.is_deleted == 0))
        .distinct()
        .order_by(BanTerm.list_type)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.fetchall() if row[0]]


async def get_options(*, session: AsyncSession) -> dict:
    """
    获取筛选选项（租户、分类、名单类型）
    """
    tenant_codes = await list_tenant_codes(session=session)
    categories = await list_categories(session=session)
    list_types = await list_list_types(session=session)
    return {
        "tenant_codes": tenant_codes,
        "categories": categories,
        "list_types": list_types,
    }

