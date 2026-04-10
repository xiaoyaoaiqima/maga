"""
BAN 词表管理 Schemas
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema, PageInfo, TimestampSchema


ListType = Literal["WHITELIST", "BLACKLIST"]


class BanTermItem(TimestampSchema):
    id: int
    tenant_code: str
    term: str
    list_type: ListType
    category: str
    enabled: bool
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None


class BanTermCreate(BaseSchema):
    tenant_code: str = Field(default="default", min_length=1, max_length=64)
    term: str = Field(..., min_length=1, max_length=255)
    list_type: ListType
    category: str = Field(default="global", min_length=1, max_length=64)
    enabled: bool = True


class BanTermUpdate(BaseSchema):
    tenant_code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    term: Optional[str] = Field(default=None, min_length=1, max_length=255)
    list_type: Optional[ListType] = None
    category: Optional[str] = Field(default=None, min_length=1, max_length=64)
    enabled: Optional[bool] = None


class BanTermListQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    tenant_code: Optional[str] = None
    keyword: Optional[str] = None
    list_type: Optional[ListType] = None
    category: Optional[str] = None
    enabled: Optional[bool] = None


class BanTermMetaResponse(BaseSchema):
    active_version: int
    whitelist_count: int
    blacklist_count: int


class BanTermListResponse(BaseSchema):
    items: list[BanTermItem]
    page_info: PageInfo


class BanTermOptionsResponse(BaseSchema):
    """筛选选项（从数据库动态获取）"""
    tenant_codes: list[str]
    categories: list[str]
    list_types: list[str]

