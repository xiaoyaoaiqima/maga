"""
User endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.schemas.base import ResponseData
from app.schemas.user import UserCreate, UserResponse
from app.services.user_service import UserService

router = APIRouter()


@router.post("", response_model=ResponseData[UserResponse])
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[UserResponse]:
    """Create new user"""
    service = UserService(db)
    
    # Check if user exists
    existing_user = await service.get_by_username(user_in.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    existing_email = await service.get_by_email(user_in.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user
    user = await service.create(user_in)
    
    return ResponseData(
        code=200,
        message="创建成功",
        data=UserResponse.model_validate(user)
    )


@router.get("/{user_id}", response_model=ResponseData[UserResponse])
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[UserResponse]:
    """Get user by ID"""
    service = UserService(db)
    user = await service.get(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return ResponseData(
        data=UserResponse.model_validate(user)
    )


@router.get("", response_model=ResponseData[list[UserResponse]])
async def list_users(
    skip: int = 0,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[UserResponse]]:
    """List all users"""
    service = UserService(db)
    users = await service.list(skip=skip, limit=limit)

    return ResponseData(
        data=[UserResponse.model_validate(user) for user in users]
    )

