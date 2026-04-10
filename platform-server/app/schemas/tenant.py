"""
Tenant schemas - 租户相关 Pydantic 模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from app.schemas.base import TimestampSchema


# ============== 基础 Schema ==============

class TenantBase(BaseModel):
    """租户基础信息"""
    tenant_code: str = Field(..., min_length=1, max_length=64, description="租户编码")
    tenant_name: str = Field(..., min_length=1, max_length=255, description="租户名称")
    contact_name: Optional[str] = Field(None, max_length=64, description="联系人姓名")
    contact_phone: Optional[str] = Field(None, max_length=32, description="联系电话")
    contact_email: Optional[str] = Field(None, max_length=128, description="联系邮箱")
    quota_config: Optional[Dict[str, Any]] = Field(None, description="配额配置")
    status: str = Field(default="ACTIVE", description="状态：ACTIVE/SUSPENDED/EXPIRED")
    expire_time: Optional[datetime] = Field(None, description="服务到期时间")
    remark: Optional[str] = Field(None, description="备注")


class TenantCreate(TenantBase):
    """创建租户"""
    pass


class TenantUpdate(BaseModel):
    """更新租户"""
    tenant_name: Optional[str] = Field(None, min_length=1, max_length=255, description="租户名称")
    contact_name: Optional[str] = Field(None, max_length=64, description="联系人姓名")
    contact_phone: Optional[str] = Field(None, max_length=32, description="联系电话")
    contact_email: Optional[str] = Field(None, max_length=128, description="联系邮箱")
    quota_config: Optional[Dict[str, Any]] = Field(None, description="配额配置")
    status: Optional[str] = Field(None, description="状态：ACTIVE/SUSPENDED/EXPIRED")
    expire_time: Optional[datetime] = Field(None, description="服务到期时间")
    remark: Optional[str] = Field(None, description="备注")


class TenantResponse(TenantBase, TimestampSchema):
    """租户响应"""
    id: int = Field(..., description="租户ID")
    access_key: Optional[str] = Field(None, description="Access Key")
    secret_key: Optional[str] = Field(None, description="Secret Key")
    enabled: int = Field(..., description="是否启用")
    created_by: Optional[str] = Field(None, description="创建人")
    updated_by: Optional[str] = Field(None, description="更新人")
    
    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    """租户列表响应"""
    total: int = Field(..., description="总数")
    items: List[TenantResponse] = Field(..., description="租户列表")


# ============== 查询参数 ==============

class TenantFilters(BaseModel):
    """租户查询过滤"""
    tenant_code: Optional[str] = Field(None, description="租户编码（模糊匹配）")
    tenant_name: Optional[str] = Field(None, description="租户名称（模糊匹配）")
    status: Optional[str] = Field(None, description="状态")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量")


# ============== 简单租户列表（下拉框用）==============

class TenantSimpleItem(BaseModel):
    """简单租户项"""
    id: int = Field(..., description="租户ID")
    tenant_code: str = Field(..., description="租户编码")
    tenant_name: str = Field(..., description="租户名称")
    
    class Config:
        from_attributes = True
