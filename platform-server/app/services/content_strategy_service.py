"""
内容策略服务

v2 重构：
- 简化组合模式为 cartesian / manual
- 新增 get_combinations 方法（获取策略的组合列表）
- 保留 generate_combinations 用于向后兼容
"""
from __future__ import annotations

import itertools
from typing import Any

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import (
    cache_get,
    cache_set,
    cache_delete_pattern,
    CACHE_TTL_DIMENSIONS,
    CACHE_TTL_NODE_BATCH,
)
from app.models.content_strategy import ContentStrategy
from app.models.graph import GraphNode


class ContentStrategyService:
    """内容策略服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _invalidate_strategy_combination_cache(self, strategy_id: int | None = None) -> None:
        """Invalidate cached strategy combinations and dependent merge results."""
        patterns = ["kc:strategy:merge:*"]
        if strategy_id is not None:
            patterns.append(f"kc:strategy:combinations:{strategy_id}:*")
        else:
            patterns.append("kc:strategy:combinations:*")

        for pattern in patterns:
            await cache_delete_pattern(pattern)

    def _build_combinations_cache_key(
        self,
        strategy_id: int,
        include_corpus: bool,
    ) -> str:
        return f"kc:strategy:combinations:{strategy_id}:{int(include_corpus)}"

    def _build_merge_cache_key(
        self,
        strategy_selections: list[dict[str, Any]],
        include_corpus: bool,
        target_count: int | None,
        sample_mode: str,
        primary_strategy_id: int | None,
    ) -> str:
        import hashlib
        import json

        normalized = {
            "strategy_selections": strategy_selections,
            "include_corpus": include_corpus,
            "target_count": target_count,
            "sample_mode": sample_mode,
            "primary_strategy_id": primary_strategy_id,
        }
        digest = hashlib.md5(
            json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return f"kc:strategy:merge:{digest}"

    # ==================== 辅助方法 ====================

    # ==================== CRUD ====================

    async def create_strategy(
        self,
        name: str,
        max_combinations: int = 200,
        description: str | None = None,
        node_pools: dict[str, dict[str, Any]] | None = None,
        defined_combinations: list[dict[str, Any]] | None = None,
        settings: dict[str, Any] | None = None,
        scope_context: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        tenant_code: str = "default",
        created_by: str | None = None,
    ) -> ContentStrategy:
        """创建内容策略"""
        # 检查名称是否重复（同一租户下）
        from sqlalchemy import select

        existing = await self.db.execute(
            select(ContentStrategy).where(
                ContentStrategy.name == name,
                ContentStrategy.tenant_code == tenant_code,
                ContentStrategy.is_deleted == 0,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"策略名称 '{name}' 已存在，请使用其他名称")

        strategy = ContentStrategy(
            name=name,
            description=description,
            node_pools=node_pools,
            defined_combinations=defined_combinations,
            max_combinations=max_combinations,
            settings=settings,
            scope_context=scope_context,
            tags=tags,
            tenant_code=tenant_code,
            created_by=created_by,
        )
        self.db.add(strategy)
        await self.db.commit()
        await self.db.refresh(strategy)
        await self._invalidate_strategy_combination_cache()

        logger.info(f"创建内容策略: id={strategy.id}, name={name}, scope_context={scope_context}")
        return strategy

    async def get_strategy(self, strategy_id: int) -> ContentStrategy | None:
        """获取内容策略"""
        strategy = await self.db.get(ContentStrategy, strategy_id)
        if strategy and strategy.is_deleted == 0:
            return strategy
        return None

    async def list_strategies(
        self,
        tenant_code: str | None = None,
        brand_code: str | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
        is_active: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ContentStrategy], int]:
        """获取内容策略列表"""
        conditions = [ContentStrategy.is_deleted == 0]
        
        if tenant_code:
            conditions.append(ContentStrategy.tenant_code == tenant_code)
        
        # 注：品牌筛选已简化，只使用 tenant_code 区分策略
        # brand_code 参数保留但不再用于筛选
        
        if name:
            conditions.append(ContentStrategy.name.like(f"%{name}%"))
        
        if tags:
            # JSON 包含筛选：tags 数组中包含所有传入的标签 ID
            # tags 字段存储的是 JSON 数组，如 ["176846269085900002"]
            # 使用 JSON_SEARCH 函数在数组中搜索字符串值（更可靠）
            for tag_id in tags:
                # JSON_SEARCH(json_doc, one_or_all, search_str, escape_char, path_list)
                # 在 JSON 文档中搜索字符串，返回匹配的路径
                # '$[*]' 表示搜索数组中的所有元素
                # 如果找到返回路径，否则返回 NULL
                conditions.append(
                    func.json_search(
                        ContentStrategy.tags,
                        'one',
                        tag_id,
                        None,
                        '$[*]'
                    ).isnot(None)
                )

        if is_active is not None:
            conditions.append(ContentStrategy.is_active == is_active)

        # 查询总数
        count_stmt = select(ContentStrategy).where(and_(*conditions))
        result = await self.db.execute(count_stmt)
        total = len(result.scalars().all())

        # 分页查询
        stmt = (
            select(ContentStrategy)
            .where(and_(*conditions))
            .order_by(ContentStrategy.create_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def update_strategy(
        self,
        strategy_id: int,
        name: str | None = None,
        description: str | None = None,
        node_pools: dict[str, dict[str, Any]] | None = None,
        defined_combinations: list[dict[str, Any]] | None = None,
        max_combinations: int | None = None,
        settings: dict[str, Any] | None = None,
        scope_context: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        is_active: int | None = None,
        updated_by: str | None = None,
    ) -> ContentStrategy | None:
        """更新内容策略"""
        logger.info(f"[update_strategy] 开始更新策略 id={strategy_id}")
        logger.info(f"[update_strategy] node_pools 参数: {node_pools}")
        logger.info(f"[update_strategy] defined_combinations 参数: {defined_combinations}")

        strategy = await self.get_strategy(strategy_id)
        if not strategy:
            logger.warning(f"[update_strategy] 策略不存在: id={strategy_id}")
            return None

        logger.info(f"[update_strategy] 更新前 strategy.node_pools: {strategy.node_pools}")

        if name is not None:
            strategy.name = name
        if description is not None:
            strategy.description = description
        if node_pools is not None:
            strategy.node_pools = node_pools
            logger.info(f"[update_strategy] 已设置 strategy.node_pools = {node_pools}")
        if defined_combinations is not None:
            strategy.defined_combinations = defined_combinations
            logger.info(f"[update_strategy] 已设置 strategy.defined_combinations = {defined_combinations}")
        if max_combinations is not None:
            strategy.max_combinations = max_combinations
        if settings is not None:
            strategy.settings = settings
        if scope_context is not None:
            strategy.scope_context = scope_context
            logger.info(f"[update_strategy] 已设置 strategy.scope_context = {scope_context}")
        if tags is not None:
            strategy.tags = tags
            logger.info(f"[update_strategy] 已设置 strategy.tags = {tags}")
        if is_active is not None:
            strategy.is_active = is_active
        if updated_by:
            strategy.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(strategy)
        await self._invalidate_strategy_combination_cache(strategy_id)

        logger.info(f"[update_strategy] 更新后 strategy.defined_combinations: {strategy.defined_combinations}")
        logger.info(f"更新内容策略: id={strategy_id}")
        return strategy

    async def delete_strategy(self, strategy_id: int) -> bool:
        """删除内容策略（软删除）"""
        strategy = await self.get_strategy(strategy_id)
        if not strategy:
            return False

        strategy.is_deleted = 1
        await self.db.commit()
        await self._invalidate_strategy_combination_cache(strategy_id)
        
        logger.info(f"删除内容策略: id={strategy_id}")
        return True

    async def copy_strategy(
        self,
        strategy_id: int,
        new_name: str | None = None,
        new_description: str | None = None,
        created_by: str | None = None,
    ) -> ContentStrategy:
        """
        复制内容策略
        
        Args:
            strategy_id: 源策略ID
            new_name: 新策略名称（默认添加"(副本)"后缀）
            new_description: 新策略描述
            created_by: 创建人
            
        Returns:
            新创建的策略
        """
        # 获取源策略
        source = await self.get_strategy(strategy_id)
        if not source:
            raise ValueError(f"源策略不存在: {strategy_id}")
        
        # 生成新名称
        if not new_name:
            new_name = f"{source.name}（副本）"
        
        # 复制策略
        new_strategy = ContentStrategy(
            name=new_name,
            description=new_description or source.description,
            node_pools=source.node_pools,
            defined_combinations=source.defined_combinations,
            max_combinations=source.max_combinations,
            settings=source.settings,
            scope_context=source.scope_context,
            tenant_code=source.tenant_code,
            is_active=1,  # 新策略默认启用
            is_deleted=0,
            created_by=created_by,
        )
        
        self.db.add(new_strategy)
        await self.db.commit()
        await self.db.refresh(new_strategy)
        await self._invalidate_strategy_combination_cache()
        
        logger.info(f"复制内容策略: source_id={strategy_id} -> new_id={new_strategy.id}, name={new_name}")
        return new_strategy

    # ==================== 组合获取（v2 新接口）====================

    async def get_combinations(
        self,
        strategy_id: int,
        include_corpus: bool = True,
    ) -> dict[str, Any]:
        """
        获取策略的组合列表（不再动态生成，直接返回定义好的组合）

        Args:
            strategy_id: 策略ID
            include_corpus: 是否包含语料

        Returns:
            {
                "strategy_id": "...",
                "strategy_name": "...",
                "combination_mode": "cartesian|manual",
                "total_count": 10,
                "combinations": [
                    {
                        "id": "combo_0",
                        "name": "创业妈妈 + 换季",
                        "nodes": {
                            "persona": {"id": "...", "name": "...", "corpus": [...]},
                            "scenario": {"id": "...", "name": "...", "corpus": [...]}
                        }
                    }
                ]
            }
        """
        strategy = await self.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"策略不存在: {strategy_id}")

        if strategy.is_active == 0:
            raise ValueError(f"策略已禁用: {strategy_id}")

        cache_key = self._build_combinations_cache_key(strategy_id, include_corpus)
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug(f"[get_combinations] 缓存命中: strategy_id={strategy_id}")
            return cached

        # 添加调试日志
        logger.info(f"[get_combinations] strategy_id={strategy_id}")
        logger.info(f"[get_combinations] node_pools={strategy.node_pools}")
        logger.info(f"[get_combinations] defined_combinations数量={len(strategy.defined_combinations or [])}")

        # 使用 defined_combinations（前端管理的笛卡尔积）
        combinations = await self._get_manual_combinations(
            strategy, include_corpus
        )

        logger.info(f"[get_combinations] 生成组合数量={len(combinations)}")

        result = {
            "strategy_id": str(strategy.id),
            "strategy_name": strategy.name,
            "combination_mode": "manual",
            "total_count": len(combinations),
            "combinations": combinations,
        }
        await cache_set(
            cache_key,
            result,
            ttl=settings.CONTENT_STRATEGY_COMBINATIONS_CACHE_TTL,
        )
        return result

    async def _get_manual_combinations(
        self,
        strategy: ContentStrategy,
        include_corpus: bool,
    ) -> list[dict[str, Any]]:
        """获取手动定义的组合
        
        支持多选模式：node_id 可以是逗号分隔的多个 ID，如 "node1,node2,node3"
        """
        defined = strategy.defined_combinations or []
        if not defined:
            return []

        # 收集所有需要查询的节点ID（支持逗号分隔的多节点）
        all_node_ids: set[str] = set()
        for combo in defined:
            nodes = combo.get("nodes", {})
            for node_id in nodes.values():
                if node_id:
                    # 支持逗号分隔的多节点 ID
                    for single_id in str(node_id).split(","):
                        single_id = single_id.strip()
                        if single_id:
                            all_node_ids.add(single_id)

        # 批量查询节点信息
        node_map = await self._batch_get_nodes(list(all_node_ids), include_corpus)

        # 组装结果
        result = []
        for combo in defined:
            combo_id = combo.get("id", f"combo_{len(result)}")
            combo_name = combo.get("name", "")
            nodes_config = combo.get("nodes", {})
            
            nodes_info = {}
            name_parts = []
            for dim_type, node_id in nodes_config.items():
                node_id_str = str(node_id) if node_id else ""
                
                # 检查是否是多选模式（逗号分隔的多节点）
                if "," in node_id_str:
                    # 多选模式：合并多个节点的信息
                    merged_node = self._merge_multi_nodes(node_id_str, node_map, dim_type)
                    if merged_node:
                        nodes_info[dim_type] = merged_node
                        name_parts.append(merged_node["name"])
                else:
                    # 单选模式：单个节点
                    node = node_map.get(node_id_str)
                    if node:
                        nodes_info[dim_type] = node
                        name_parts.append(node["name"])
            
            # 如果没有指定名称，自动生成
            if not combo_name:
                combo_name = " + ".join(name_parts)
            
            result.append({
                "id": combo_id,
                "name": combo_name,
                "nodes": nodes_info,
            })

        return result
    
    def _merge_multi_nodes(
        self,
        node_ids_str: str,
        node_map: dict[str, Any],
        dim_type: str,
    ) -> dict[str, Any] | None:
        """
        合并多选模式下的多个节点信息

        多选模式逻辑：
        1. 节点名称：用逗号连接（如 "全职妈妈, 职场女性"）
        2. 语料处理：每个节点取对应索引的语料，然后换行拼接
           - 组合1：节点1的第1条 + 节点2的第1条 + ...
           - 组合2：节点1的第2条 + 节点2的第2条 + ...
           - 以最短节点的语料数为准

        例如：
        - 节点1有3条语料，节点2有2条语料
        - 生成2条组合语料：
          * 组合1 = 节点1[0] + "\\n" + 节点2[0]
          * 组合2 = 节点1[1] + "\\n" + 节点2[1]
        """
        node_ids = [nid.strip() for nid in node_ids_str.split(",") if nid.strip()]
        if not node_ids:
            return None

        # 收集所有节点的语料
        node_corpus_list = []
        merged_names = []

        for nid in node_ids:
            node = node_map.get(nid)
            if node:
                merged_names.append(node.get("name", nid))
                # 收集每个节点的语料列表
                corpus = node.get("corpus", [])
                if isinstance(corpus, list):
                    # 格式化每条语料为文本
                    formatted_corpus = []
                    for item in corpus:
                        if isinstance(item, dict) and "fields" in item:
                            # 结构化语料：按字段格式化
                            parts = []
                            for field_def in self._get_corpus_fields(item):
                                value = item["fields"].get(field_def["key"])
                                if value:
                                    parts.append(f"{field_def['label']}: {value}")
                            formatted_corpus.append("\\n".join(parts) if parts else str(item))
                        elif isinstance(item, str):
                            formatted_corpus.append(item)
                        else:
                            formatted_corpus.append(str(item))
                    node_corpus_list.append(formatted_corpus)
                else:
                    node_corpus_list.append([])

        if not merged_names:
            return None

        # 生成组合语料：每个节点取对应索引的语料，用换行连接
        merged_corpus = []
        if node_corpus_list:
            # 以最短节点的语料数为准
            min_length = min(len(corpus) for corpus in node_corpus_list)
            # 如果所有节点都没有语料，至少生成一个空组合
            if min_length == 0:
                min_length = 1 if any(len(corpus) > 0 for corpus in node_corpus_list) else 0

            # 详细日志：记录每个节点的语料数量
            corpus_counts = [len(corpus) for corpus in node_corpus_list]
            from loguru import logger
            logger.info(f"[多选组合] 维度={dim_type}, 节点数={len(node_ids)}, node_ids={node_ids}")
            logger.info(f"[多选组合] 每个节点的语料数={corpus_counts}, min_length={min_length}")

            for i in range(min_length):
                corpus_parts = []
                for node_idx, node_corpus in enumerate(node_corpus_list):
                    if i < len(node_corpus):
                        corpus_parts.append(node_corpus[i])

                if corpus_parts:
                    # 用换行符连接不同节点的语料
                    combined = "\\n".join(corpus_parts)
                    merged_corpus.append(combined)
                    logger.info(f"组合{i+1}: 来源节点索引={i}, 组合语料数={len(corpus_parts)}, 预览={combined[:100] if len(combined) > 100 else combined}")

            logger.info(f"[多选组合] 最终: 总组合数={len(merged_corpus)}, 名称={merged_names}")

        return {
            "id": node_ids_str,  # 保留原始的逗号分隔 ID
            "name": ", ".join(merged_names),
            "label": dim_type,
            "corpus": merged_corpus if merged_corpus else None,
        }

    def _get_corpus_fields(self, corpus_item: dict) -> list[dict]:
        """获取语料项的字段定义（辅助方法）"""
        # 这里简化处理，实际应该从模板获取字段定义
        # 暂时返回所有字段
        fields = []
        for key, value in corpus_item.get("fields", {}).items():
            fields.append({"key": key, "label": key})
        return fields

    async def _get_cartesian_combinations(
        self,
        strategy: ContentStrategy,
        include_corpus: bool,
    ) -> list[dict[str, Any]]:
        """生成笛卡尔积组合"""
        # 获取节点池（优先使用 node_pools，否则从 dimensions 提取）
        node_pools = strategy.get_node_pools_from_dimensions()
        if not node_pools:
            return []

        # 批量查询所有节点（兼容多种格式）
        all_node_ids: set[str] = set()
        for pool_value in node_pools.values():
            # 兼容 string（单个ID）, list（ID列表）, dict（{node_ids: [...]}）
            if isinstance(pool_value, str):
                all_node_ids.add(pool_value)
            elif isinstance(pool_value, list):
                all_node_ids.update(pool_value)
            elif isinstance(pool_value, dict):
                node_ids = pool_value.get("node_ids", [])
                all_node_ids.update(node_ids)

        node_map = await self._batch_get_nodes(list(all_node_ids), include_corpus)

        # 为每个维度构建节点列表
        dim_types = list(node_pools.keys())
        node_lists: list[list[dict[str, Any]]] = []

        for dim_type in dim_types:
            dim_nodes = []
            pool_value = node_pools[dim_type]

            # 提取节点ID列表（兼容多种格式）
            node_id_list = []
            if isinstance(pool_value, str):
                node_id_list = [pool_value]
            elif isinstance(pool_value, list):
                node_id_list = pool_value
            elif isinstance(pool_value, dict):
                node_id_list = pool_value.get("node_ids", [])

            for node_id in node_id_list:
                node = node_map.get(str(node_id))
                if node:
                    dim_nodes.append(node)
            if dim_nodes:
                node_lists.append(dim_nodes)
            else:
                # 维度没有有效节点，返回空
                return []

        # 生成笛卡尔积
        all_combos = list(itertools.product(*node_lists))

        # 限制数量
        max_combos = strategy.max_combinations or 200
        all_combos = all_combos[:max_combos]

        # 组装结果
        result = []
        for idx, combo in enumerate(all_combos):
            nodes_info = {}
            name_parts = []
            for i, dim_type in enumerate(dim_types):
                nodes_info[dim_type] = combo[i]
                name_parts.append(combo[i]["name"])

            result.append({
                "id": f"combo_{idx}",
                "name": " + ".join(name_parts),
                "nodes": nodes_info,
            })

        return result

    async def _batch_get_nodes(
        self,
        node_ids: list[str],
        include_corpus: bool,
    ) -> dict[str, dict[str, Any]]:
        """
        批量获取节点信息（带 Redis 缓存）

        缓存策略：
        - 使用 md5(node_ids排序) 作为缓存键
        - include_corpus=True 时缓存时间较短（5分钟）
        - include_corpus=False 时缓存时间较长（10分钟）
        """
        if not node_ids:
            return {}

        # 确保所有 ID 都是有效的数字字符串
        valid_node_ids = []
        for nid in node_ids:
            try:
                int_id = int(nid)
                valid_node_ids.append(int_id)
            except (ValueError, TypeError):
                logger.warning(f"[_batch_get_nodes] 无效的节点ID格式: {nid}")

        if not valid_node_ids:
            logger.warning(f"[_batch_get_nodes] 没有有效的节点ID: {node_ids}")
            return {}

        # === 缓存检查 ===
        import hashlib
        node_ids_sorted = sorted(node_ids)
        node_ids_hash = hashlib.md5(",".join(node_ids_sorted).encode()).hexdigest()[:12]
        cache_key = f"kc:node:batch:{node_ids_hash}:{int(include_corpus)}"

        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug(f"[_batch_get_nodes] 缓存命中: {cache_key}, count={len(cached)}")
            return cached

        # === 数据库查询 ===
        stmt = select(GraphNode).where(
            and_(
                GraphNode.id.in_(valid_node_ids),
                GraphNode.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        nodes = list(result.scalars().all())

        node_map = {}
        for node in nodes:
            node_map[str(node.id)] = {
                "id": str(node.id),
                "name": node.name,
                "label": node.label,
                "description": node.description,
                "corpus": node.corpus if include_corpus else None,
            }

        # === 写入缓存 ===
        ttl = CACHE_TTL_NODE_BATCH if include_corpus else CACHE_TTL_NODE_BATCH * 2
        await cache_set(cache_key, node_map, ttl=ttl)
        logger.debug(f"[_batch_get_nodes] 缓存写入: {cache_key}, ttl={ttl}s, count={len(node_map)}")

        # 记录未找到的节点
        found_ids = set(node_map.keys())
        missing_ids = set(node_ids) - found_ids
        if missing_ids:
            # 如果大部分节点都找不到，升级为 WARNING
            if len(missing_ids) == len(node_ids):
                logger.warning(
                    f"[_batch_get_nodes] 所有节点都未找到！请检查策略中的节点ID是否正确。"
                    f" 查询的ID: {list(node_ids)[:5]}..."
                )
            else:
                logger.debug(
                    f"[_batch_get_nodes] 未找到 {len(missing_ids)} 个节点（可能已删除）: "
                    f"{list(missing_ids)[:5]}..."
                )

        return node_map

    def get_combinations_count(self, strategy: ContentStrategy) -> int:
        """计算策略的组合数量"""
        return len(strategy.defined_combinations or [])

    # ==================== 旧版接口（保留向后兼容）====================

    async def generate_combinations(
        self,
        strategy_id: int,
        count: int = 10,
        overrides: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """
        生成组合（旧版接口，保留向后兼容）
        
        内部调用 get_combinations 并截取指定数量
        """
        result = await self.get_combinations(strategy_id, include_corpus=True)
        
        # 截取指定数量
        combinations = result["combinations"][:count]
        
        return {
            "strategy_id": result["strategy_id"],
            "strategy_name": result["strategy_name"],
            "total_count": len(combinations),
            "combinations": combinations,  # 保留完整结构（包含 id, name, nodes）
        }

    # ==================== 多策略合并（strategy_v3）====================

    async def merge_strategy_combinations(
        self,
        strategy_selections: list[dict[str, Any]],
        include_corpus: bool = True,
        target_count: int | None = None,
        sample_mode: str = "first",
        primary_strategy_id: int | None = None,
    ) -> dict[str, Any]:
        """
        合并多个策略的组合（笛卡尔积）

        Args:
            strategy_selections: 策略选择列表
                [
                    {
                        "strategy_id": "1",
                        "selected_combo_ids": ["combo_0", "combo_1"]  # 可选，不传则使用全部组合
                    },
                    ...
                ]
            include_corpus: 是否包含语料

        Returns:
            {
                "merged_dimensions": ["人设", "场景", "卖点"],  # 合并后的维度列表
                "dimension_conflicts": [],  # 维度冲突列表
                "total_count": 6,
                "merged_combinations": [
                    {
                        "id": "merged_s1c0_s2c0",
                        "name": "卖点必带 + 过敏体质 + 季节天气",
                        "source_combos": [
                            {"strategy_id": "1", "combo_id": "combo_0"},
                            {"strategy_id": "2", "combo_id": "combo_0"}
                        ],
                        "merged_nodes": {
                            "卖点": {...},
                            "人设": {...},
                            "场景": {...}
                        }
                    },
                    ...
                ]
            }
        """
        if not strategy_selections:
            raise ValueError("至少需要选择一个策略")

        cache_key = self._build_merge_cache_key(
            strategy_selections=strategy_selections,
            include_corpus=include_corpus,
            target_count=target_count,
            sample_mode=sample_mode,
            primary_strategy_id=primary_strategy_id,
        )
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug("[merge_combinations] 缓存命中")
            return cached

        # 1. 获取每个策略的组合
        strategy_combos: list[dict[str, Any]] = []
        # dimension -> {strategy_id, strategy_name}
        all_dimensions: dict[str, dict[str, str]] = {}
        dimension_conflicts: list[dict[str, Any]] = []

        for selection in strategy_selections:
            strategy_id = selection.get("strategy_id")
            selected_combo_ids = selection.get("selected_combo_ids")

            if not strategy_id:
                continue

            # 获取策略的所有组合
            try:
                combo_result = await self.get_combinations(
                    strategy_id=int(strategy_id),
                    include_corpus=include_corpus,
                )
            except ValueError as e:
                logger.warning(f"[merge_combinations] 获取策略 {strategy_id} 组合失败: {e}")
                continue

            combinations = combo_result.get("combinations", [])
            if not combinations:
                continue

            # 如果指定了 selected_combo_ids，只保留选中的组合
            if selected_combo_ids:
                selected_ids_set = set(selected_combo_ids)
                combinations = [c for c in combinations if c.get("id") in selected_ids_set]

            if not combinations:
                continue

            strategy_name = combo_result.get("strategy_name", f"策略{strategy_id}")

            # 收集该策略的维度
            strategy_dims = set()
            for combo in combinations:
                for dim in combo.get("nodes", {}).keys():
                    strategy_dims.add(dim)

            # 检测维度冲突
            for dim in strategy_dims:
                if dim in all_dimensions:
                    # 维度冲突：记录双方策略名称
                    dimension_conflicts.append({
                        "dimension": dim,
                        "strategy_1_id": all_dimensions[dim]["id"],
                        "strategy_1_name": all_dimensions[dim]["name"],
                        "strategy_2_id": str(strategy_id),
                        "strategy_2_name": strategy_name,
                    })
                else:
                    all_dimensions[dim] = {"id": str(strategy_id), "name": strategy_name}

            strategy_combos.append({
                "strategy_id": str(strategy_id),
                "strategy_name": strategy_name,
                "dimensions": list(strategy_dims),
                "combinations": combinations,
            })

        if not strategy_combos:
            raise ValueError("未找到有效的策略组合")

        # 2. 如果有维度冲突，仅记录警告（允许覆盖）
        if dimension_conflicts:
            conflict_desc = ", ".join([
                f"「{c['dimension']}」被「{c['strategy_1_name']}」和「{c['strategy_2_name']}」同时使用"
                for c in dimension_conflicts
            ])
            logger.warning(f"策略合并存在维度冲突：{conflict_desc}。将按顺序覆盖（后优于前）。")
            # raise ValueError(f"策略合并失败：{conflict_desc}。合并模式要求各策略的维度不能重叠，请调整策略选择。")

        # 3. 生成笛卡尔积合并组合（支持两种采样模式）
        max_merged = target_count or 200
        
        logger.warning(
            f"[merge_combinations] 采样模式检查:\n"
            f"  sample_mode={sample_mode}\n"
            f"  primary_strategy_id={primary_strategy_id}\n"
            f"  进入primary_strategy分支={sample_mode == 'primary_strategy' and primary_strategy_id is not None}"
        )

        if sample_mode == "primary_strategy" and primary_strategy_id:
            # 主策略优先采样（主策略的每个组合都使用一次）
            logger.info(f"[merge_combinations] ✅ 使用主策略优先采样: {primary_strategy_id}")
            merged_combinations = self._sample_combinations_primary_strategy(
                strategy_combos,
                primary_strategy_id=primary_strategy_id,
                target_count=max_merged
            )
        elif sample_mode == "random":
            # 全随机采样
            logger.info("[merge_combinations] 🎲 使用全随机采样")
            merged_combinations = self._sample_combinations_random(
                strategy_combos,
                target_count=max_merged
            )
        else:
            # 前N个：笛卡尔积取前N个
            logger.info("[merge_combinations] 📋 使用前N个采样（笛卡尔积）")
            merged_combinations = self._generate_merged_cartesian(
                strategy_combos, 
                max_combinations=max_merged
            )

        result = {
            "merged_dimensions": list(all_dimensions.keys()),
            "dimension_conflicts": dimension_conflicts,
            "source_strategies": [
                {"strategy_id": s["strategy_id"], "strategy_name": s["strategy_name"]}
                for s in strategy_combos
            ],
            "total_count": len(merged_combinations),
            "merged_combinations": merged_combinations,
        }
        await cache_set(
            cache_key,
            result,
            ttl=settings.MERGED_STRATEGY_COMBINATIONS_CACHE_TTL,
        )
        return result

    def _generate_merged_cartesian(
        self,
        strategy_combos: list[dict[str, Any]],
        max_combinations: int = 200,
    ) -> list[dict[str, Any]]:
        """生成多策略组合的笛卡尔积（优化版：限制内存使用）"""
        import itertools

        if not strategy_combos:
            return []

        # 提取每个策略的组合列表
        combo_lists = [s["combinations"] for s in strategy_combos]
        strategy_ids = [s["strategy_id"] for s in strategy_combos]

        merged = []
        
        # 使用生成器而非列表，避免一次性生成所有组合
        cartesian_product = itertools.product(*combo_lists)
        
        for idx, product in enumerate(cartesian_product):
            # 达到限制后立即停止，不再生成更多组合
            if idx >= max_combinations:
                break

            # product 是一个 tuple，每个元素是一个策略的一个组合

            # 合并所有节点
            merged_nodes = {}
            name_parts = []
            source_combos = []

            for i, combo in enumerate(product):
                strategy_id = strategy_ids[i]
                combo_id = combo.get("id", f"combo_{i}")

                source_combos.append({
                    "strategy_id": strategy_id,
                    "combo_id": combo_id,
                })

                # 合并节点
                for dim, node_info in combo.get("nodes", {}).items():
                    merged_nodes[dim] = node_info
                    if isinstance(node_info, dict) and "name" in node_info:
                        name_parts.append(node_info["name"])

            # 生成合并组合 ID
            combo_id_parts = [f"s{s['strategy_id']}c{s['combo_id']}" for s in source_combos]
            merged_id = f"merged_{'_'.join(combo_id_parts)}"

            merged.append({
                "id": merged_id,
                "name": " + ".join(name_parts),
                "source_combos": source_combos,
                "merged_nodes": merged_nodes,
            })

        return merged

    def _sample_combinations_random(
        self,
        strategy_combos: list[dict[str, Any]],
        target_count: int = 100,
    ) -> list[dict[str, Any]]:
        """全随机采样：每个策略随机抽取一个组合（零笛卡尔积）

        完全不生成笛卡尔积，直接随机选择，允许重复

        Args:
            strategy_combos: 策略组合列表
            target_count: 目标数量

        Returns:
            采样的组合列表
        """
        import random

        if not strategy_combos:
            return []

        combo_lists = [s["combinations"] for s in strategy_combos]
        strategy_ids = [s["strategy_id"] for s in strategy_combos]

        result = []

        for _ in range(target_count):
            # 从每个策略随机选一个组合（允许重复）
            source_combos = []
            merged_nodes = {}
            name_parts = []

            for i, combo_list in enumerate(combo_lists):
                combo = random.choice(combo_list)
                source_combos.append({
                    "strategy_id": strategy_ids[i],
                    "combo_id": combo["id"],
                })

                # 合并节点
                for dim, node_info in combo.get("nodes", {}).items():
                    merged_nodes[dim] = node_info
                    if isinstance(node_info, dict) and "name" in node_info:
                        name_parts.append(node_info["name"])

            combo_id_parts = [f"s{s['strategy_id']}c{s['combo_id']}" for s in source_combos]
            merged_id = f"random_{'_'.join(combo_id_parts)}_{len(result)}"

            result.append({
                "id": merged_id,
                "name": " + ".join(name_parts),
                "source_combos": source_combos,
                "merged_nodes": merged_nodes,
            })

        return result

    def _sample_combinations_primary_strategy(
        self,
        strategy_combos: list[dict[str, Any]],
        primary_strategy_id: int,
        target_count: int = 100,
    ) -> list[dict[str, Any]]:
        """主策略优先采样（零笛卡尔积）

        主策略的每个组合都使用一次，其他策略完全随机抽取

        Args:
            strategy_combos: 策略组合列表
            primary_strategy_id: 主策略ID
            target_count: 目标数量

        Returns:
            采样的组合列表

        Example:
            策略1（痛点+场景组合，20 个，每个痛点4个）, 策略2（卖点，10 个）, 策略3（字数，3 个）
            primary_strategy_id = 1
            target_count = 20

            结果：
            - 策略1的20个组合，每个用1次（保持痛点+场景的组合关系）
            - 策略2、策略3：每次随机选1个
        """
        import random

        if not strategy_combos:
            return []

        # 1. 找到主策略和其他策略
        primary_strategy = None
        other_strategies = []

        for strategy in strategy_combos:
            sid = strategy.get("strategy_id")
            if isinstance(sid, str):
                sid = int(sid)

            if sid == primary_strategy_id:
                primary_strategy = strategy
            else:
                other_strategies.append(strategy)

        if not primary_strategy:
            raise ValueError(
                f"主策略ID '{primary_strategy_id}' 不在可用策略中。"
                f"可用策略: {[s.get('strategy_id') for s in strategy_combos]}"
            )

        primary_combos = primary_strategy["combinations"]
        actual_count = min(len(primary_combos), target_count)

        logger.info(
            f"[primary_strategy] 主策略ID={primary_strategy_id}, "
            f"组合数={len(primary_combos)}, "
            f"其他策略数={len(other_strategies)}, "
            f"目标总数={target_count}, 实际生成={actual_count}"
        )

        # 2. 如果没有其他策略，直接返回主策略组合
        if not other_strategies:
            result = []
            # 使用所有组合（保持顺序）
            combos_to_use = primary_combos[:actual_count]
            for combo in combos_to_use:
                result.append({
                    "id": combo["id"],
                    "name": combo.get("name", ""),
                    "primary_strategy_id": primary_strategy_id,
                    "source_combos": [{
                        "strategy_id": str(primary_strategy_id),
                        "combo_id": combo["id"],
                        "is_primary": True,
                    }],
                    "merged_nodes": combo.get("nodes", {}),
                })
            return result

        # 3. 提取其他策略的数据
        other_combo_lists = [s["combinations"] for s in other_strategies]
        other_strategy_ids = [s["strategy_id"] for s in other_strategies]

        # 4. 为主策略的每个组合生成配对（其他策略随机抽取）
        result = []

        for combo in primary_combos[:actual_count]:
            source_combos = [{
                "strategy_id": str(primary_strategy_id),
                "combo_id": combo["id"],
                "is_primary": True,
            }]

            merged_nodes = dict(combo.get("nodes", {}))
            name_parts = [combo.get("name", "")] if combo.get("name") else []

            for i, combo_list in enumerate(other_combo_lists):
                other_combo = random.choice(combo_list)
                source_combos.append({
                    "strategy_id": other_strategy_ids[i],
                    "combo_id": other_combo["id"],
                })

                for dim, node_info in other_combo.get("nodes", {}).items():
                    merged_nodes[dim] = node_info
                    if isinstance(node_info, dict) and "name" in node_info:
                        name_parts.append(node_info["name"])

            combo_id_parts = [f"s{s['strategy_id']}c{s['combo_id']}" for s in source_combos]
            merged_id = f"primary_s{primary_strategy_id}_{'_'.join(combo_id_parts[1:])}_{len(result)}"

            result.append({
                "id": merged_id,
                "name": " + ".join(name_parts),
                "primary_strategy_id": primary_strategy_id,
                "source_combos": source_combos,
                "merged_nodes": merged_nodes,
            })

        logger.info(
            f"[primary_strategy] 生成完成，总计={len(result)}, "
            f"主策略组合使用数={actual_count}"
        )

        return result

    # ==================== 其他 ====================

    async def get_available_dimensions(
        self,
        tenant_code: str = "default",
        include_global: bool = True,
    ) -> list[dict[str, Any]]:
        """
        获取可用的维度列表（从根节点 labels 中提取）
        
        动态从分类树根节点生成，不硬编码
        
        Args:
            tenant_code: 租户编码
            include_global: 是否包含全局维度
        
        Returns:
            维度列表，每个维度包含：
            - dimension_type: 维度类型（category_type）
            - dimension_name: 维度显示名（label）
            - node_id: 根节点 ID
            - node_count: 子节点数量
            - is_global: 是否为全局维度
        """
        from sqlalchemy import func as sqla_func
        
        from app.core.config import settings
        
        # === 缓存检查 ===
        cache_key = f"kc:dimensions:{tenant_code}:{include_global}"
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug(f"维度缓存命中: {cache_key}")
            return cached
        
        # 查询所有顶级节点，直接使用 label 字段作为 category_type
        stmt = (
            select(
                GraphNode.id,
                GraphNode.label,
                GraphNode.tenant_code,
                GraphNode.properties,
            )
            .where(
                and_(
                    GraphNode.is_deleted == 0,
                    GraphNode.is_active == 1,
                    sqla_func.json_extract(GraphNode.properties, "$.level") == 1,
                )
            )
        )
        result = await self.db.execute(stmt)
        rows = result.fetchall()

        dimensions = []
        seen = set()
        for node_id, label, node_tenant, properties in rows:
            # 直接使用 label 作为唯一标识
            dim_type = label
            if dim_type in seen:
                continue
            seen.add(dim_type)
            
            is_global = node_tenant == settings.GLOBAL_TENANT_CODE
            props = properties or {}
            
            dimensions.append({
                "dimension_type": dim_type,
                "dimension_name": label,
                "node_id": str(node_id),
                "icon": props.get("icon"),
                "is_global": is_global,
                "tenant_code": node_tenant,
                # 筛选属性
                "brands": props.get("brands", []),
                "tags": props.get("tags", []),
            })

        logger.info(f"获取可用维度: tenant_code={tenant_code}, include_global={include_global}, count={len(dimensions)}")
        
        # === 写入缓存 ===
        await cache_set(cache_key, dimensions, CACHE_TTL_DIMENSIONS)
        
        return dimensions

    async def get_dimension_nodes(
        self,
        dimension_type: str,
        tenant_code: str = "default",
        include_global: bool = True,
        brand_code: str | None = None,
        product_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        获取指定维度下的可选节点
        
        支持 Scope 过滤（Fallback 优先级：Product > Brand > Global）
        
        Args:
            dimension_type: 维度类型（category_type）
            tenant_code: 租户编码
            include_global: 是否包含全局节点
            brand_code: 品牌编码（用于 Scope 过滤）
            product_name: 产品名称（用于 Scope 过滤）
        
        Returns:
            节点列表
        """
        from sqlalchemy import func as sqla_func
        
        from app.core.config import settings
        from app.models.graph import GraphEdge
        
        # 先找到该维度的根节点，直接使用 label 字段
        root_stmt = (
            select(GraphNode.id)
            .where(
                and_(
                    GraphNode.is_deleted == 0,
                    GraphNode.is_active == 1,
                    sqla_func.json_extract(GraphNode.properties, "$.level") == 1,
                    GraphNode.label == dimension_type,  # 使用 label 字段
                )
            )
        )
        result = await self.db.execute(root_stmt)
        root_ids = [row[0] for row in result.fetchall()]
        
        if not root_ids:
            return []
        
        # 获取这些根节点的直接子节点
        edge_stmt = select(GraphEdge.target_node_id).where(
            and_(
                GraphEdge.source_node_id.in_(root_ids),
                GraphEdge.relation_type == "INCLUDES",
                GraphEdge.is_deleted == 0,
                GraphEdge.is_active == 1,
            )
        )
        result = await self.db.execute(edge_stmt)
        child_ids = [row[0] for row in result.fetchall()]
        
        if not child_ids:
            return []
        
        # 获取子节点详情
        nodes_stmt = select(GraphNode).where(
            and_(
                GraphNode.id.in_(child_ids),
                GraphNode.is_deleted == 0,
                GraphNode.is_active == 1,
            )
        )
        result = await self.db.execute(nodes_stmt)
        nodes = list(result.scalars().all())
        
        # 构建结果（包含 Scope 信息）
        result_nodes = []
        for node in nodes:
            props = node.properties or {}
            scope = props.get("scope", {})
            
            # Scope 过滤逻辑
            if brand_code or product_name:
                scope_level = scope.get("level", "global")
                scope_brand_codes = scope.get("brand_codes", [])
                scope_product_names = scope.get("product_names", [])
                
                # 产品级：必须匹配产品
                if scope_level == "product":
                    if product_name and product_name not in scope_product_names:
                        continue
                    if brand_code and brand_code not in scope_brand_codes:
                        continue
                # 品牌级：必须匹配品牌
                elif scope_level == "brand":
                    if brand_code and brand_code not in scope_brand_codes:
                        continue
                # 全局级：无需过滤
            
            is_global = node.tenant_code == settings.GLOBAL_TENANT_CODE
            
            result_nodes.append({
                "id": str(node.id),
                "name": node.name,
                "label": node.label,
                "description": node.description,
                "scope": scope,
                "is_global": is_global,
                "tenant_code": node.tenant_code,
            })
        
        logger.info(f"获取维度节点: dimension={dimension_type}, count={len(result_nodes)}")
        return result_nodes
