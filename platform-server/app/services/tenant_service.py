"""
Tenant service - 租户服务
"""
import secrets
from typing import Optional, List, Tuple

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.tenant import Tenant
from app.schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantFilters,
    TenantSimpleItem,
)
class TenantService:
    """租户服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_tenant(self, data: TenantCreate, created_by: Optional[str] = None) -> TenantResponse:
        """
        创建租户
        """
        # 检查租户编码是否已存在
        stmt = select(Tenant).where(
            and_(
                Tenant.tenant_code == data.tenant_code,
                Tenant.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError(f"租户编码 '{data.tenant_code}' 已存在")
        
        # 自动生成 AK/SK
        access_key = f"ak_{secrets.token_hex(8)}"
        secret_key = secrets.token_urlsafe(32)
        
        # 创建租户
        tenant = Tenant(
            tenant_code=data.tenant_code,
            tenant_name=data.tenant_name,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            contact_email=data.contact_email,
            quota_config=data.quota_config,
            access_key=access_key,
            secret_key=secret_key,
            status=data.status,
            expire_time=data.expire_time,
            remark=data.remark,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(tenant)
        
        await self.db.commit()
        await self.db.refresh(tenant)
        
        logger.info(f"创建租户成功: {tenant.tenant_code}")
        return TenantResponse.model_validate(tenant)
    
    async def get_tenant(self, tenant_id: int) -> Optional[TenantResponse]:
        """获取租户详情"""
        stmt = select(Tenant).where(
            and_(
                Tenant.id == tenant_id,
                Tenant.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            return None
        
        return TenantResponse.model_validate(tenant)
    
    async def get_tenant_by_code(self, tenant_code: str) -> Optional[TenantResponse]:
        """根据编码获取租户"""
        stmt = select(Tenant).where(
            and_(
                Tenant.tenant_code == tenant_code,
                Tenant.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            return None
        
        return TenantResponse.model_validate(tenant)
    
    async def list_tenants(self, filters: TenantFilters) -> Tuple[int, List[TenantResponse]]:
        """获取租户列表"""
        query = select(Tenant).where(Tenant.is_deleted == 0)
        
        if filters.tenant_code:
            query = query.where(Tenant.tenant_code.ilike(f"%{filters.tenant_code}%"))
        if filters.tenant_name:
            query = query.where(Tenant.tenant_name.ilike(f"%{filters.tenant_name}%"))
        if filters.status:
            query = query.where(Tenant.status == filters.status)
            
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()
        
        # Get items with pagination
        query = query.order_by(Tenant.create_time.desc())
        query = query.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
        
        result = await self.db.execute(query)
        items = result.scalars().all()
        
        return total, [TenantResponse.model_validate(item) for item in items]

    async def list_simple(self) -> List[TenantSimpleItem]:
        """
        获取简单租户列表（用于下拉框）
        
        Returns:
            简单租户列表
        """
        stmt = (
            select(Tenant)
            .where(
                and_(
                    Tenant.is_deleted == 0,
                    Tenant.status == "ACTIVE"
                )
            )
            .order_by(Tenant.tenant_name)
        )
        result = await self.db.execute(stmt)
        tenants = result.scalars().all()
        
        return [TenantSimpleItem.model_validate(t) for t in tenants]

    async def update_tenant(self, tenant_id: int, data: TenantUpdate, updated_by: Optional[str] = None) -> Optional[TenantResponse]:
        """更新租户"""
        stmt = select(Tenant).where(
            and_(
                Tenant.id == tenant_id,
                Tenant.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            return None
            
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tenant, field, value)
            
        tenant.updated_by = updated_by
        
        await self.db.commit()
        await self.db.refresh(tenant)
        return TenantResponse.model_validate(tenant)

    async def delete_tenant(self, tenant_id: int, updated_by: Optional[str] = None) -> bool:
        """删除租户（软删除）"""
        stmt = select(Tenant).where(
            and_(
                Tenant.id == tenant_id,
                Tenant.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            return False
            
        tenant.is_deleted = 1
        tenant.updated_by = updated_by
        
        await self.db.commit()
        return True
