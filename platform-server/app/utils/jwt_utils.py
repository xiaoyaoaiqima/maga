"""
JWT Token utilities for authentication
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt, JWTError
from pydantic import BaseModel, ValidationError

from app.core.config import settings


class TokenPayload(BaseModel):
    """JWT Token payload"""
    user_id: str
    username: str
    name: Optional[str] = None
    exp: Optional[datetime] = None


class JWTUtils:
    """JWT Token utilities"""
    
    # 从配置读取，如果没有则使用默认值
    SECRET_KEY = getattr(settings, 'JWT_SECRET_KEY', 'raap-admin-secret-key-change-in-production')
    ALGORITHM = getattr(settings, 'JWT_ALGORITHM', 'HS256')
    ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, 'JWT_ACCESS_TOKEN_EXPIRE_MINUTES', 60 * 24 * 7)  # 7 days
    
    @classmethod
    def create_access_token(
        cls,
        user_id: str,
        username: str,
        name: Optional[str] = None,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        创建访问令牌
        
        Args:
            user_id: 用户ID
            username: 用户名
            name: 用户姓名
            expires_delta: 过期时间增量
        
        Returns:
            JWT token 字符串
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=cls.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {
            "user_id": user_id,
            "username": username,
            "name": name,
            "exp": expire
        }
        
        encoded_jwt = jwt.encode(to_encode, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
        return encoded_jwt
    
    @classmethod
    def decode_token(cls, token: str) -> Optional[TokenPayload]:
        """
        解码并验证 JWT token
        
        Args:
            token: JWT token 字符串
        
        Returns:
            TokenPayload 或 None（如果验证失败）
        """
        try:
            payload = jwt.decode(token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM])
            return TokenPayload(
                user_id=payload.get("user_id"),
                username=payload.get("username"),
                name=payload.get("name"),
                exp=datetime.fromtimestamp(payload.get("exp")) if payload.get("exp") else None
            )
        except (JWTError, ValidationError):
            return None
    
    @classmethod
    def verify_token(cls, token: str) -> bool:
        """
        验证 token 是否有效
        
        Args:
            token: JWT token 字符串
        
        Returns:
            是否有效
        """
        payload = cls.decode_token(token)
        if payload is None:
            return False
        
        # 检查是否过期
        if payload.exp and payload.exp < datetime.utcnow():
            return False
        
        return True
    
    @classmethod
    def get_token_expire_time(cls) -> int:
        """
        获取 token 过期时间（秒）
        
        Returns:
            过期时间（秒）
        """
        return cls.ACCESS_TOKEN_EXPIRE_MINUTES * 60


# 便捷函数
def create_token(user_id: str, username: str, name: Optional[str] = None) -> str:
    """创建访问令牌的便捷函数"""
    return JWTUtils.create_access_token(user_id, username, name)


def decode_token(token: str) -> Optional[TokenPayload]:
    """解码令牌的便捷函数"""
    return JWTUtils.decode_token(token)


def verify_token(token: str) -> bool:
    """验证令牌的便捷函数"""
    return JWTUtils.verify_token(token)

