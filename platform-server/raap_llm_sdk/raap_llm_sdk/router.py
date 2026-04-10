"""
模型路由器

负责：
- 根据 model_code 查找可用路由
- 按优先级排序
- 过滤熔断的端点
- 支持路由策略（优先级、轮询、加权）
"""
import logging
from typing import List, Optional, Callable
from enum import Enum

from .models import ModelRoute, ProviderConfig
from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """路由策略"""
    PRIORITY = "priority"       # 按优先级（默认）
    ROUND_ROBIN = "round_robin" # 轮询
    WEIGHTED = "weighted"       # 加权随机


class ModelRouter:
    """
    模型路由器
    
    根据 model_code 选择最佳的 Provider 和 Model 组合
    
    使用示例：
    ```python
    router = ModelRouter(
        circuit_breaker=circuit_breaker,
        strategy=RoutingStrategy.PRIORITY
    )
    
    # 获取可用路由（按优先级，排除熔断的）
    routes = router.get_available_routes(all_routes)
    
    for route in routes:
        if router.can_use_route(route):
            # 使用该路由
            break
    ```
    """
    
    def __init__(
        self,
        circuit_breaker: CircuitBreaker = None,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
    ):
        """
        初始化路由器
        
        Args:
            circuit_breaker: 熔断器实例（用于检查端点状态）
            strategy: 路由策略
        """
        self._circuit_breaker = circuit_breaker
        self._strategy = strategy
        self._round_robin_index: dict = {}  # 轮询索引
    
    def get_available_routes(
        self,
        routes: List[ModelRoute],
        filter_circuit_broken: bool = True,
    ) -> List[ModelRoute]:
        """
        获取可用路由列表
        
        Args:
            routes: 所有路由配置
            filter_circuit_broken: 是否过滤熔断的端点
        
        Returns:
            按策略排序后的可用路由列表
        """
        if not routes:
            return []
        
        # 过滤已禁用的路由
        available = [r for r in routes if r.enabled]
        
        # 过滤熔断的端点
        if filter_circuit_broken and self._circuit_breaker:
            available = [
                r for r in available
                if not self._circuit_breaker.is_open(r.provider_code)
            ]
        
        # 按策略排序
        if self._strategy == RoutingStrategy.PRIORITY:
            available = self._sort_by_priority(available)
        elif self._strategy == RoutingStrategy.ROUND_ROBIN:
            available = self._sort_round_robin(available, routes[0].model_code if routes else "default")
        elif self._strategy == RoutingStrategy.WEIGHTED:
            available = self._sort_weighted(available)
        
        return available
    
    def _sort_by_priority(self, routes: List[ModelRoute]) -> List[ModelRoute]:
        """按优先级降序排序"""
        return sorted(routes, key=lambda r: r.priority, reverse=True)
    
    def _sort_round_robin(self, routes: List[ModelRoute], model_code: str) -> List[ModelRoute]:
        """
        轮询排序
        
        每次调用会返回从不同位置开始的路由列表
        """
        if not routes:
            return []
        
        # 获取当前索引
        current_index = self._round_robin_index.get(model_code, 0)
        
        # 更新索引
        self._round_robin_index[model_code] = (current_index + 1) % len(routes)
        
        # 先按优先级排序，再从当前索引开始轮询
        sorted_routes = sorted(routes, key=lambda r: r.priority, reverse=True)
        return sorted_routes[current_index:] + sorted_routes[:current_index]
    
    def _sort_weighted(self, routes: List[ModelRoute]) -> List[ModelRoute]:
        """
        加权排序
        
        优先级作为权重，随机选择（暂时简化为按优先级）
        """
        # TODO: 实现真正的加权随机
        return self._sort_by_priority(routes)
    
    def can_use_route(self, route: ModelRoute) -> bool:
        """
        检查路由是否可用
        
        Args:
            route: 路由配置
        
        Returns:
            True 表示可用
        """
        if not route.enabled:
            return False
        
        if self._circuit_breaker and self._circuit_breaker.is_open(route.provider_code):
            return False
        
        return True
    
    def select_route(
        self,
        routes: List[ModelRoute],
        exclude_providers: List[str] = None,
    ) -> Optional[ModelRoute]:
        """
        选择一个可用路由
        
        Args:
            routes: 所有路由配置
            exclude_providers: 要排除的 Provider 列表
        
        Returns:
            选中的路由，无可用时返回 None
        """
        available = self.get_available_routes(routes)
        
        if exclude_providers:
            available = [r for r in available if r.provider_code not in exclude_providers]
        
        return available[0] if available else None
    
    def get_failover_route(
        self,
        routes: List[ModelRoute],
        failed_provider: str,
        previous_attempts: List[str] = None,
    ) -> Optional[ModelRoute]:
        """
        获取 failover 路由
        
        Args:
            routes: 所有路由配置
            failed_provider: 刚失败的 Provider
            previous_attempts: 之前尝试过的 Provider 列表
        
        Returns:
            下一个可用的路由
        """
        exclude = set(previous_attempts or [])
        exclude.add(failed_provider)
        
        available = self.get_available_routes(routes)
        
        for route in available:
            if route.provider_code not in exclude:
                return route
        
        return None
    
    def get_route_stats(self, routes: List[ModelRoute]) -> dict:
        """
        获取路由统计信息
        
        Args:
            routes: 所有路由配置
        
        Returns:
            统计信息字典
        """
        total = len(routes)
        enabled = len([r for r in routes if r.enabled])
        circuit_broken = 0
        
        if self._circuit_breaker:
            circuit_broken = len([
                r for r in routes
                if r.enabled and self._circuit_breaker.is_open(r.provider_code)
            ])
        
        available = enabled - circuit_broken
        
        return {
            "total": total,
            "enabled": enabled,
            "circuit_broken": circuit_broken,
            "available": available,
        }


