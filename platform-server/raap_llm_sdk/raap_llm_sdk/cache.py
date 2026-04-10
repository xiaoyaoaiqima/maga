"""
本地缓存实现

支持 TTL 过期和主动失效
"""
import time
from typing import Optional, Any, Dict
from dataclasses import dataclass, field


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    expire_at: float  # 过期时间戳


class LocalCache:
    """
    本地内存缓存
    
    特性：
    - TTL 过期
    - 主动删除
    - 线程安全（单线程 asyncio 环境）
    """
    
    def __init__(self, default_ttl: int = 300):
        """
        初始化缓存
        
        Args:
            default_ttl: 默认 TTL（秒），默认 5 分钟
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
        
        Returns:
            缓存值，如果不存在或已过期返回 None
        """
        entry = self._cache.get(key)
        if entry is None:
            return None
        
        # 检查是否过期
        if time.time() > entry.expire_at:
            del self._cache[key]
            return None
        
        return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 使用默认值
        """
        ttl = ttl if ttl is not None else self._default_ttl
        expire_at = time.time() + ttl
        self._cache[key] = CacheEntry(value=value, expire_at=expire_at)
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
        
        Returns:
            是否删除成功
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    def clear(self):
        """清空所有缓存"""
        self._cache.clear()
    
    def cleanup_expired(self):
        """清理过期条目"""
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry.expire_at
        ]
        for key in expired_keys:
            del self._cache[key]
    
    def __contains__(self, key: str) -> bool:
        """检查键是否存在（且未过期）"""
        return self.get(key) is not None
    
    def __len__(self) -> int:
        """返回缓存条目数量（包含过期的）"""
        return len(self._cache)

