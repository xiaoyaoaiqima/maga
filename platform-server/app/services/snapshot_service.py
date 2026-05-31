"""
快照服务 - 生成插件的变量快照

核心功能：
1. 根据插件配置的 variable_mappings 和 strategy_id 生成快照
2. 支持新旧两种模式（strategy 模式 / context_name 模式）
3. SubJob 级缓存保证同一插件只生成一次快照
"""

import random
from typing import Any, Dict, List, Optional

from app.core.logger import get_logger
from app.models.plugin import Plugin

logger = get_logger()


def _extract_node_ids_from_pool(pool_value: Any) -> List[str]:
    """
    从 node_pools 的值中提取节点ID列表
    
    支持两种格式:
    - 旧格式: ["node_id1", "node_id2"]  (list)
    - 新格式 v3: {"node_ids": ["node_id1", "node_id2"], "select_mode": "random"}  (dict)
    
    Returns:
        节点ID列表
    """
    if pool_value is None:
        return []
    
    # 新格式 v3: dict with node_ids
    if isinstance(pool_value, dict):
        node_ids = pool_value.get("node_ids", [])
        return [str(nid) for nid in node_ids] if node_ids else []
    
    # 旧格式: list of node IDs
    if isinstance(pool_value, list):
        return [str(nid) for nid in pool_value]
    
    return []


async def _fetch_strategy_detail(
    strategy_id: int,
    tenant_code: str = "default"
) -> Optional[Dict[str, Any]]:
    """旧关键词策略源已下线。"""
    logger.warning(f"旧关键词策略源已下线，忽略 strategy_id={strategy_id}, tenant_code={tenant_code}")
    return None


async def _fetch_nodes_batch(
    node_ids: List[str],
    tenant_code: str = "default"
) -> Dict[str, Dict[str, Any]]:
    """旧关键词节点源已下线。"""
    if node_ids:
        logger.warning(f"旧关键词节点源已下线，忽略 node_ids={node_ids[:3]}, tenant_code={tenant_code}")
    return {}


class SnapshotBuilder:
    """
    快照构建器
    
    根据插件配置的 variable_mappings 和 strategy_id 生成快照
    """
    
    def __init__(self, tenant_code: str = "default"):
        self.tenant_code = tenant_code
        self._strategy_cache: Dict[int, Dict[str, Any]] = {}
        self._node_cache: Dict[str, Dict[str, Any]] = {}
    
    async def build_snapshot(self, plugin: Plugin) -> Dict[str, Any]:
        """
        构建插件快照
        
        Args:
            plugin: 插件实例
        
        Returns:
            快照字典，格式: {"变量名": {"source": "strategy", "node_id": "xxx", ...}}
        """
        # 检查是否配置了新模式（strategy_id + variable_mappings）
        if not plugin.strategy_id or not plugin.variable_mappings:
            logger.debug(f"插件 {plugin.plugin_code} 未配置策略绑定，跳过快照生成")
            return {}
        
        return await self._generate_strategy_snapshot(plugin)
    
    async def _generate_strategy_snapshot(self, plugin: Plugin) -> Dict[str, Any]:
        """
        基于策略生成快照（新模式）
        
        流程：
        1. 获取策略详情（包含 node_pools）
        2. 遍历 variable_mappings，从对应 label 的节点池中随机选择节点
        3. 为每个节点随机选择一条语料
        4. 构建快照
        """
        strategy_id = plugin.strategy_id
        
        # 1. 获取策略详情
        strategy = await self._get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"策略不存在: strategy_id={strategy_id}")
        
        node_pools = strategy.get("node_pools") or {}
        if not node_pools:
            # 尝试从旧版 dimensions 字段获取
            dimensions = strategy.get("dimensions") or []
            for dim in dimensions:
                dim_type = dim.get("dimension_type")
                node_ids = dim.get("node_ids", [])
                if dim_type and node_ids:
                    node_pools[dim_type] = node_ids
        
        if not node_pools:
            raise ValueError(f"策略 {strategy_id} 没有配置节点池")
        
        # 2. 收集所有需要查询的节点ID
        all_node_ids = set()
        for mapping in plugin.variable_mappings:
            label = mapping.get("label")
            if label and label in node_pools:
                all_node_ids.update(_extract_node_ids_from_pool(node_pools[label]))
        
        # 3. 批量获取节点详情
        nodes_data = await self._get_nodes_batch(list(all_node_ids))
        
        # 4. 为每个变量生成快照
        snapshot = {}
        for mapping in plugin.variable_mappings:
            variable_name = mapping.get("variable_name")
            label = mapping.get("label")
            
            if not variable_name or not label:
                continue
            
            # 从节点池获取该 label 的节点ID列表
            pool_node_ids = _extract_node_ids_from_pool(node_pools.get(label))
            if not pool_node_ids:
                logger.warning(f"策略 {strategy_id} 的节点池中没有 {label} 的节点")
                continue
            
            # 过滤出有效的节点（存在且有语料）
            valid_nodes = []
            for nid in pool_node_ids:
                node_data = nodes_data.get(str(nid))
                if node_data and node_data.get("corpus"):
                    valid_nodes.append((str(nid), node_data))
            
            if not valid_nodes:
                logger.warning(f"没有可用的节点满足条件: label={label}, strategy_id={strategy_id}")
                continue
            
            # 随机选择一个节点
            selected_node_id, selected_node = random.choice(valid_nodes)
            
            # 随机选择一条语料
            corpus_list = selected_node.get("corpus", [])
            if not corpus_list:
                continue
            
            selected_corpus = random.choice(corpus_list)
            corpus_text = self._extract_corpus_text(selected_corpus)
            corpus_id = corpus_list.index(selected_corpus)
            
            # 构建快照条目
            snapshot[variable_name] = {
                "source": "strategy",
                "strategy_id": strategy_id,
                "label": label,
                "node_id": selected_node_id,
                "node_name": selected_node.get("name", ""),
                "corpus_id": corpus_id,
                "corpus_text": corpus_text,
            }
            
            logger.debug(
                f"变量 {variable_name} 快照: label={label}, "
                f"node={selected_node.get('name')}, corpus_len={len(corpus_text)}"
            )
        
        return snapshot
    
    async def _get_strategy(self, strategy_id: int) -> Optional[Dict[str, Any]]:
        """获取策略详情（带缓存）"""
        if strategy_id in self._strategy_cache:
            return self._strategy_cache[strategy_id]
        
        strategy = await _fetch_strategy_detail(strategy_id, self.tenant_code)
        if strategy:
            self._strategy_cache[strategy_id] = strategy
        return strategy
    
    async def _get_nodes_batch(self, node_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取节点详情（带缓存）"""
        # 找出未缓存的节点
        uncached_ids = [nid for nid in node_ids if nid not in self._node_cache]
        
        # 批量获取未缓存的节点
        if uncached_ids:
            new_nodes = await _fetch_nodes_batch(uncached_ids, self.tenant_code)
            self._node_cache.update(new_nodes)
        
        # 返回所有请求的节点
        return {nid: self._node_cache.get(nid, {}) for nid in node_ids}
    
    def _extract_corpus_text(self, corpus_item: Any) -> str:
        """从语料项中提取文本"""
        if isinstance(corpus_item, str):
            return corpus_item
        if isinstance(corpus_item, dict):
            # 新格式：{"text": "内容", "weight": 1.0}
            if "text" in corpus_item:
                return corpus_item["text"]
            # 结构化格式：{"structure": {...}}
            if "structure" in corpus_item:
                structure = corpus_item["structure"]
                if isinstance(structure, dict):
                    # 拼接所有字段值
                    parts = []
                    for key, value in structure.items():
                        if value:
                            parts.append(f"{key}: {value}")
                    return "\n".join(parts)
            # 兜底：返回 JSON 字符串
            import json
            return json.dumps(corpus_item, ensure_ascii=False)
        return str(corpus_item)


class PluginSnapshotManager:
    """
    插件快照管理器
    
    职责：
    1. 在 SubJob 创建时，为所有需要的 Plugin 生成快照
    2. 保证同一 SubJob 中，同一 Plugin 只生成一次快照
    3. 缓存快照，供后续 Expert 使用
    """
    
    def __init__(self, tenant_code: str = "default"):
        self.tenant_code = tenant_code
        self.builder = SnapshotBuilder(tenant_code)
    
    async def create_snapshots_for_plugins(
        self,
        plugins: List[Plugin],
    ) -> Dict[str, Dict[str, Any]]:
        """
        为多个插件创建快照
        
        Args:
            plugins: 插件列表
        
        Returns:
            plugin_snapshots: {plugin_code: snapshot}
        """
        plugin_snapshots = {}
        
        for plugin in plugins:
            try:
                snapshot = await self.builder.build_snapshot(plugin)
                if snapshot:
                    plugin_snapshots[plugin.plugin_code] = snapshot
                    logger.info(f"生成快照成功: {plugin.plugin_code} -> {list(snapshot.keys())}")
            except Exception as e:
                logger.error(f"生成快照失败: {plugin.plugin_code} - {e}")
                # 根据业务需求，可以选择抛出异常或跳过
        
        return plugin_snapshots
    
    async def get_or_create_snapshot(
        self,
        plugin: Plugin,
        existing_snapshots: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        获取或创建插件快照
        
        优先从 existing_snapshots 获取，不存在则新建
        
        Args:
            plugin: 插件实例
            existing_snapshots: 已有的快照缓存（如 SubJob.plugin_snapshots）
        
        Returns:
            插件快照
        """
        # 优先从已有快照获取
        if existing_snapshots and plugin.plugin_code in existing_snapshots:
            logger.debug(f"命中快照缓存: {plugin.plugin_code}")
            return existing_snapshots[plugin.plugin_code]
        
        # 新建快照
        snapshot = await self.builder.build_snapshot(plugin)
        return snapshot
