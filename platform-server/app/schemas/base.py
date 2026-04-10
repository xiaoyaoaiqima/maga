"""
Base schemas
"""
from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, field_serializer


class BaseSchema(BaseModel):
    """Base schema configuration"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        protected_namespaces=(),
    )


class TimestampSchema(BaseSchema):
    """Schema with timestamp fields"""
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    @field_serializer("create_time", "update_time")
    def serialize_dt(self, dt: Optional[datetime], _info):
        if dt is None:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")


class ResponseBase(BaseSchema):
    """Base response schema"""
    code: int = 200
    message: str = "Success"


T = TypeVar("T")


class ResponseData(ResponseBase, Generic[T]):
    """Response with data"""
    data: Optional[T] = None


class PageInfo(BaseSchema):
    """Pagination info"""
    page: int
    page_size: int
    total: int
    total_pages: int


class PageResponse(ResponseBase, Generic[T]):
    """Paginated response"""
    data: list[T]
    page_info: PageInfo


class ResponseModel(BaseSchema):
    """通用响应模型"""
    code: int = 200
    message: str = "success"
    data: Optional[dict | list] = None

