"""
JobVariant service - Variant 方案库（列表/创建/编辑/禁用）
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.job_variant import JobVariant
from app.schemas.job_variant import JobVariantCreate, JobVariantUpdate


class JobVariantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, variant_id: str) -> Optional[JobVariant]:
        stmt = select(JobVariant).where(
            and_(JobVariant.variant_id == variant_id, JobVariant.is_deleted == 0)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        tenant_id: Optional[int] = None,
        agent_code: Optional[str] = None,
        enabled: Optional[bool] = None,
        keyword: Optional[str] = None,
        limit: int = 200,
        skip: int = 0,
    ) -> list[JobVariant]:
        conditions: list[Any] = [JobVariant.is_deleted == 0]
        if tenant_id is not None:
            # 既返回“租户内”Variant，也返回“全局共享（tenant_id=NULL）”Variant
            conditions.append(or_(JobVariant.tenant_id == tenant_id, JobVariant.tenant_id.is_(None)))
        if agent_code:
            conditions.append(JobVariant.agent_code == agent_code)
        if enabled is not None:
            conditions.append(JobVariant.enabled == enabled)
        if keyword:
            kw = f"%{keyword.strip()}%"
            conditions.append(or_(JobVariant.variant_name.like(kw), JobVariant.remark.like(kw)))

        stmt = (
            select(JobVariant)
            .where(and_(*conditions))
            .order_by(desc(JobVariant.update_time), desc(JobVariant.id))
            .offset(skip)
            .limit(min(max(limit, 1), 500))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: JobVariantCreate) -> JobVariant:
        if not data.variant_name.strip():
            raise ValueError("variant_name 不能为空")
        if data.expert_param_config is None:
            raise ValueError("expert_param_config 不能为空")

        variant_id = f"variant-{uuid.uuid4().hex[:16]}"
        variant = JobVariant(
            variant_id=variant_id,
            tenant_id=data.tenant_id,
            agent_code=data.agent_code,
            variant_name=data.variant_name.strip(),
            tags=data.tags or [],
            expert_config_code_list=data.expert_config_code_list or [],
            expert_param_config=data.expert_param_config,
            enabled=data.enabled,
            remark=data.remark,
            created_by=data.created_by,
            updated_by=data.created_by,
        )
        self.db.add(variant)
        await self.db.commit()
        await self.db.refresh(variant)
        return variant

    async def update(self, variant_id: str, data: JobVariantUpdate) -> JobVariant:
        variant = await self.get(variant_id)
        if not variant:
            raise ValueError("Variant 不存在")

        if data.tenant_id is not None:
            variant.tenant_id = data.tenant_id
        if data.agent_code is not None:
            variant.agent_code = data.agent_code
        if data.variant_name is not None:
            name = data.variant_name.strip()
            if not name:
                raise ValueError("variant_name 不能为空")
            variant.variant_name = name
        if data.tags is not None:
            variant.tags = data.tags or []
            flag_modified(variant, "tags")
        if data.expert_config_code_list is not None:
            variant.expert_config_code_list = data.expert_config_code_list or []
            flag_modified(variant, "expert_config_code_list")
        if data.expert_param_config is not None:
            variant.expert_param_config = data.expert_param_config
            flag_modified(variant, "expert_param_config")
        if data.enabled is not None:
            variant.enabled = data.enabled
        if data.remark is not None:
            variant.remark = data.remark

        variant.updated_by = data.updated_by
        await self.db.commit()
        await self.db.refresh(variant)
        return variant

    async def disable(self, variant_id: str, *, updated_by: Optional[str] = None) -> JobVariant:
        variant = await self.get(variant_id)
        if not variant:
            raise ValueError("Variant 不存在")
        variant.enabled = False
        variant.updated_by = updated_by
        await self.db.commit()
        await self.db.refresh(variant)
        return variant

    async def delete(self, variant_id: str, *, updated_by: Optional[str] = None) -> bool:
        variant = await self.get(variant_id)
        if not variant:
            return False
        variant.is_deleted = 1
        variant.updated_by = updated_by
        await self.db.commit()
        return True