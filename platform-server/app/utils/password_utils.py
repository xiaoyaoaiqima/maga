"""
Password utilities for authentication
"""
from passlib.context import CryptContext


# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class PasswordUtils:
    """Password utilities"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        对密码进行哈希加密
        
        Args:
            password: 明文密码
        
        Returns:
            加密后的密码哈希
        """
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        验证密码
        
        Args:
            plain_password: 明文密码
            hashed_password: 加密后的密码哈希
        
        Returns:
            密码是否匹配
        """
        return pwd_context.verify(plain_password, hashed_password)


# 便捷函数
def hash_password(password: str) -> str:
    """加密密码的便捷函数"""
    return PasswordUtils.hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码的便捷函数"""
    return PasswordUtils.verify_password(plain_password, hashed_password)

