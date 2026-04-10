"""
User schemas
"""
from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema, TimestampSchema


class UserBase(BaseSchema):
    """User base schema"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    """User create schema"""
    password: str = Field(..., min_length=6, max_length=50)


class UserUpdate(BaseSchema):
    """User update schema"""
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=6, max_length=50)
    is_active: bool | None = None


class UserInDB(UserBase, TimestampSchema):
    """User in database schema"""
    id: int
    is_active: bool
    is_superuser: bool


class UserResponse(UserInDB):
    """User response schema"""
    pass

