# API 设计文档

## 7.1 API 设计

### 7.1.1 获取插件变量映射配置

```typescript
GET /api/v1/plugins/{plugin_id}/variable-mappings

Response:
{
  "plugin_id": 123,
  "plugin_code": "writer_plugin",
  "strategy_id": 1,
  "strategy_name": "双11皇家美素佳儿策略",
  "strategy_labels": ["人设", "场景", "卖点"],  // 策略中可用的 label
  "variable_mappings": [
    {
      "variable_name": "写者",
      "label": "人设",
      "attribute_filters": {
        "brands": ["皇家美素佳儿"]
      }
    },
    {
      "variable_name": "场景",
      "label": "场景",
      "attribute_filters": null
    }
  ]
}
```

### 7.1.2 更新变量映射

```typescript
PUT /api/v1/plugins/{plugin_id}/variable-mappings

Request:
{
  "strategy_id": 1,
  "variable_mappings": [
    {
      "variable_name": "写者",
      "label": "人设",
      "attribute_filters": {
        "brands": ["皇家美素佳儿"]
      }
    },
    {
      "variable_name": "场景",
      "label": "场景",
      "attribute_filters": null
    },
    {
      "variable_name": "卖点",
      "label": "卖点",
      "attribute_filters": null
    }
  ]
}

Response:
{
  "success": true,
  "message": "变量映射配置已保存"
}
```

### 7.1.3 获取策略的节点池详情

```typescript
GET /api/v1/content-strategies/{strategy_id}/node-pools

Response:
{
  "strategy_id": 1,
  "strategy_name": "双11皇家美素佳儿策略",
  "node_pools": {
    "人设": [
      {
        "id": "3001004101",
        "name": "精致妈妈",
        "properties": {
          "brands": ["皇家美素佳儿"],
          "tag_groups": ["双11大促"]
        }
      },
      {
        "id": "3001004102",
        "name": "创业妈妈",
        "properties": {
          "brands": ["皇家美素佳儿"],
          "tag_groups": ["双11大促"]
        }
      }
    ],
    "场景": [...],
    "卖点": [...]
  }
}
```

### 7.1.4 内联创建策略（高级模式）

```typescript
POST /api/v1/content-strategies/inline

Request:
{
  "name": "双11皇家美素佳儿策略",
  "scope_context": {
    "level": "product",
    "brand_code": "2000001",
    "brand_name": "皇家美素佳儿",
    "product_name": "旺玥"
  },
  "node_pools": {
    "人设": ["3001004101", "3001004102", "3001004103"],
    "场景": ["3001004201", "3001004202", "3001004203"],
    "卖点": ["3001004301", "3001004302", "3001004303"]
  },
  "combination_mode": "cartesian",
  "max_combinations": 100
}

Response:
{
  "strategy_id": 1,
  "message": "策略创建成功"
}
```

## 7.2 服务层实现

### 7.2.1 PluginService

```python
class PluginService:
    """
    插件服务
    """

    async def update_variable_mappings(
        self,
        plugin_id: int,
        strategy_id: int,
        variable_mappings: List[VariableMapping]
    ) -> Plugin:
        """
        更新插件的变量映射配置
        """

        # 1. 获取插件
        plugin = await self.repository.get_by_id(plugin_id)
        if not plugin:
            raise PluginNotFoundError(plugin_id)

        # 2. 验证策略是否存在
        strategy = await ContentStrategyService.get_by_id(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)

        # 3. 验证变量映射配置
        await self._validate_variable_mappings(
            variable_mappings,
            strategy,
            plugin
        )

        # 4. 更新插件
        plugin.strategy_id = strategy_id
        plugin.variable_mappings = variable_mappings

        await self.repository.update(plugin)

        # 5. 清除相关缓存
        await self.cache.clear_pattern(f"snapshot:*:{plugin.plugin_code}")

        return plugin

    async def _validate_variable_mappings(
        self,
        variable_mappings: List[VariableMapping],
        strategy: ContentStrategy,
        plugin: Plugin
    ):
        """
        验证变量映射配置
        """

        # 1. 检查变量是否都在模板中使用
        template_vars = self._extract_variables_from_template(plugin.context_template)
        mapping_vars = [m["variable_name"] for m in variable_mappings]

        missing_vars = set(template_vars) - set(mapping_vars)
        if missing_vars:
            raise InvalidVariableMappingError(
                f"模板中的变量未映射: {missing_vars}"
            )

        # 2. 检查每个映射的 label 是否在策略的 node_pools 中
        strategy_labels = set(strategy.node_pools.keys())

        for mapping in variable_mappings:
            label = mapping.get("label")
            if label not in strategy_labels:
                raise InvalidVariableMappingError(
                    f"策略中没有 label '{label}'，可用: {strategy_labels}"
                )

        # 3. 检查属性筛选是否有效
        for mapping in variable_mappings:
            filters = mapping.get("attribute_filters")
            if filters:
                await self._validate_attribute_filters(filters, strategy)

    async def _validate_attribute_filters(
        self,
        filters: dict,
        strategy: ContentStrategy
    ):
        """
        验证属性筛选配置
        """
        # 检查品牌标签是否存在
        if "brands" in filters:
            for brand_name in filters["brands"]:
                # 查询 node_property_meta 表
                brand = await NodePropertyMeta.filter(
                    item_type="brand",
                    name=brand_name,
                    is_deleted=0
                ).first()
                if not brand:
                    raise InvalidFilterError(f"品牌标签不存在: {brand_name}")

        # 检查活动标签是否存在
        if "tag_groups" in filters:
            for tag_name in filters["tag_groups"]:
                tag = await NodePropertyMeta.filter(
                    item_type="tag_group",
                    name=tag_name,
                    is_deleted=0
                ).first()
                if not tag:
                    raise InvalidFilterError(f"活动标签不存在: {tag_name}")
```

### 7.2.2 SnapshotService (修正版)

```python
class SnapshotService:
    """
    快照服务（支持属性筛选）
    """

    async def generate_snapshot_from_strategy(
        self,
        plugin: Plugin,
        strategy: ContentStrategy
    ) -> dict:
        """
        根据插件配置的 variable_mappings 从策略生成快照
        """
        snapshot = {}

        # 1. 获取策略的节点池
        node_pools = strategy.node_pools  # {"人设": [node_ids], "场景": [node_ids]}

        # 2. 遍历插件的变量映射配置
        for var_mapping in plugin.variable_mappings:
            variable_name = var_mapping["variable_name"]  # "写者"
            label = var_mapping["label"]                   # "人设"
            filters = var_mapping.get("attribute_filters")  # {"brands": ["皇家美素佳儿"]}

            # 3. 从策略的节点池获取节点ID列表
            node_ids = node_pools.get(label)
            if not node_ids:
                raise ValueError(f"策略中没有 {label} 的节点")

            # 4. 查询节点详情
            nodes = await GraphNode.filter(
                id__in=node_ids,
                is_active=1,
                is_deleted=0
            )

            # 5. 应用属性筛选
            if filters:
                nodes = self._apply_attribute_filters(nodes, filters)

            if not nodes:
                raise ValueError(f"没有节点满足筛选条件: {filters}")

            # 6. 随机选择一个节点
            selected_node = random.choice(nodes)

            # 7. 随机选择一条语料
            corpus_list = selected_node.corpus or []
            if not corpus_list:
                raise ValueError(f"节点 {selected_node.name} 没有语料")

            corpus = random.choice(corpus_list)

            # 8. 构建快照条目
            snapshot[variable_name] = {
                "source": "strategy",
                "strategy_id": strategy.id,
                "label": label,
                "node_id": selected_node.id,
                "node_name": selected_node.name,
                "corpus_id": corpus_list.index(corpus),
                "corpus_text": corpus["text"],
                "filters_applied": filters  # 记录应用的筛选条件
            }

        return snapshot

    def _apply_attribute_filters(
        self,
        nodes: List[GraphNode],
        filters: dict
    ) -> List[GraphNode]:
        """
        应用属性筛选
        """
        filtered = nodes

        # 品牌标签筛选
        if "brands" in filters:
            brands = filters["brands"]
            filtered = [
                node for node in filtered
                if self._node_has_brands(node, brands)
            ]

        # 活动标签筛选
        if "tag_groups" in filters:
            tag_groups = filters["tag_groups"]
            filtered = [
                node for node in filtered
                if self._node_has_tag_groups(node, tag_groups)
            ]

        return filtered

    def _node_has_brands(self, node: GraphNode, brands: List[str]) -> bool:
        """
        检查节点是否包含指定的品牌标签
        """
        if not node.properties:
            return False

        node_brands = node.properties.get("brands", [])
        return any(brand in node_brands for brand in brands)

    def _node_has_tag_groups(self, node: GraphNode, tag_groups: List[str]) -> bool:
        """
        检查节点是否包含指定的活动标签
        """
        if not node.properties:
            return False

        node_tags = node.properties.get("tag_groups", [])
        return any(tag in node_tags for tag in tag_groups)
```
