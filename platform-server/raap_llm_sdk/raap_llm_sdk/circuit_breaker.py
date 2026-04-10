"""
熔断器实现

支持：
- 本地内存存储（单实例）
- Redis 存储（多实例共享）
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from .models import CircuitBreakerState

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    熔断器（支持 Redis 多实例共享状态）
    
    状态机：
    - CLOSED: 正常状态，允许调用
    - OPEN: 熔断状态，拒绝调用
    - HALF_OPEN: 半开状态，允许探测调用
    """
    
    REDIS_KEY_PREFIX = "llm:circuit_breaker:"
    REDIS_TTL = 3600  # 状态过期时间（秒）
    
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 1,
        redis_client = None,
    ):
        """
        初始化熔断器
        
        Args:
            failure_threshold: 触发熔断的连续失败次数
            recovery_timeout: 熔断恢复时间（秒）
            half_open_max_calls: 半开状态最大探测次数
            redis_client: Redis 客户端（可选，用于多实例共享）
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._redis = redis_client
        self._local_states: Dict[str, Dict[str, Any]] = {}
    
    def _get_default_state(self) -> Dict[str, Any]:
        """获取默认状态"""
        return {
            "state": "closed",
            "failure_count": 0,
            "success_count": 0,
            "open_until": None,
            "last_failure_reason": None,
            "last_failure_time": None,
        }
    
    def _get_state(self, provider_code: str) -> Dict[str, Any]:
        """获取熔断状态"""
        if self._redis:
            # Redis 实现（多实例共享）
            key = f"{self.REDIS_KEY_PREFIX}{provider_code}"
            data = self._redis.get(key)
            if data:
                state = json.loads(data)
                # 解析时间字符串
                if state.get("open_until"):
                    state["open_until"] = datetime.fromisoformat(state["open_until"])
                if state.get("last_failure_time"):
                    state["last_failure_time"] = datetime.fromisoformat(state["last_failure_time"])
                return state
            return self._get_default_state()
        else:
            # 本地内存（单实例）
            return self._local_states.get(provider_code, self._get_default_state())
    
    def _set_state(self, provider_code: str, state: str, **kwargs):
        """设置熔断状态"""
        state_data = {
            "state": state,
            "failure_count": kwargs.get("failure_count", 0),
            "success_count": kwargs.get("success_count", 0),
            "open_until": kwargs.get("open_until"),
            "last_failure_reason": kwargs.get("last_failure_reason"),
            "last_failure_time": kwargs.get("last_failure_time"),
        }
        
        if self._redis:
            # Redis 实现
            key = f"{self.REDIS_KEY_PREFIX}{provider_code}"
            # 序列化时间对象
            data = state_data.copy()
            if data["open_until"]:
                data["open_until"] = data["open_until"].isoformat()
            if data["last_failure_time"]:
                data["last_failure_time"] = data["last_failure_time"].isoformat()
            self._redis.setex(key, self.REDIS_TTL, json.dumps(data))
        else:
            # 本地内存
            self._local_states[provider_code] = state_data
    
    def is_open(self, provider_code: str) -> bool:
        """
        检查是否熔断中
        
        Args:
            provider_code: 端点编码
        
        Returns:
            True 表示熔断中，应跳过该端点
        """
        state = self._get_state(provider_code)
        
        if state["state"] == "open":
            open_until = state.get("open_until")
            if open_until and datetime.now() > open_until:
                # 进入半开状态
                self._set_state(
                    provider_code, "half_open",
                    failure_count=state["failure_count"],
                )
                return False
            return True
        
        return False
    
    def record_success(self, provider_code: str):
        """
        记录成功
        
        Args:
            provider_code: 端点编码
        """
        state = self._get_state(provider_code)
        
        if state["state"] == "half_open":
            # 半开状态成功，恢复正常
            self._set_state(provider_code, "closed", failure_count=0, success_count=1)
            logger.info(f"端点 {provider_code} 从半开状态恢复正常")
        elif state["state"] == "closed":
            # 正常状态，重置失败计数
            self._set_state(
                provider_code, "closed",
                failure_count=0,
                success_count=state.get("success_count", 0) + 1,
            )
    
    def record_failure(self, provider_code: str, reason: str):
        """
        记录失败
        
        Args:
            provider_code: 端点编码
            reason: 失败原因
        """
        state = self._get_state(provider_code)
        new_count = state.get("failure_count", 0) + 1
        
        if state["state"] == "half_open":
            # 半开状态失败，重新熔断
            self._set_state(
                provider_code, "open",
                failure_count=new_count,
                open_until=datetime.now() + timedelta(seconds=self._recovery_timeout),
                last_failure_reason=reason,
                last_failure_time=datetime.now(),
            )
            logger.warning(f"端点 {provider_code} 半开状态失败，重新熔断")
        elif new_count >= self._failure_threshold:
            # 达到阈值，触发熔断
            self._set_state(
                provider_code, "open",
                failure_count=new_count,
                open_until=datetime.now() + timedelta(seconds=self._recovery_timeout),
                last_failure_reason=reason,
                last_failure_time=datetime.now(),
            )
            logger.warning(f"端点 {provider_code} 触发熔断，原因: {reason}")
        else:
            # 记录失败次数
            self._set_state(
                provider_code, "closed",
                failure_count=new_count,
                last_failure_reason=reason,
                last_failure_time=datetime.now(),
            )
    
    def get_status(self, provider_code: str) -> CircuitBreakerState:
        """
        获取熔断状态
        
        Args:
            provider_code: 端点编码
        
        Returns:
            CircuitBreakerState 对象
        """
        state = self._get_state(provider_code)
        return CircuitBreakerState(
            provider_code=provider_code,
            state=state["state"],
            failure_count=state.get("failure_count", 0),
            success_count=state.get("success_count", 0),
            last_failure_time=state.get("last_failure_time"),
            last_failure_reason=state.get("last_failure_reason"),
            open_until=state.get("open_until"),
        )
    
    def reset(self, provider_code: str):
        """
        重置熔断状态（手动恢复）
        
        Args:
            provider_code: 端点编码
        """
        self._set_state(provider_code, "closed", failure_count=0, success_count=0)
        logger.info(f"端点 {provider_code} 熔断状态已重置")
    
    def force_open(self, provider_code: str, reason: str = "Manual intervention"):
        """
        强制熔断（手动禁用）
        
        Args:
            provider_code: 端点编码
            reason: 熔断原因
        """
        self._set_state(
            provider_code, "open",
            failure_count=0,
            open_until=datetime.now() + timedelta(days=365),  # 长期熔断
            last_failure_reason=reason,
            last_failure_time=datetime.now(),
        )
        logger.warning(f"端点 {provider_code} 被强制熔断: {reason}")

