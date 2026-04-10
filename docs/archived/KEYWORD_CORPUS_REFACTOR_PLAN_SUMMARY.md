# 关键词语料系统重构方案 - 最终设计方案总结

## 核心设计决策

### 方案C: label = 维度（最简洁方案）

**核心原则**：
1. **nodes.label** 就是维度（人设、场景、卖点等）
2. **ContentStrategy.node_pools** 的 key 就是 label，在创建策略时已按属性筛选好节点
3. **Plugin.variable_mappings** 只配置到 label，不需要 attribute_filters
4. **职责分离**：策略负责筛选，插件只负责映射

---

## 数据结构

### ContentStrategy（策略）

```python
ContentStrategy = {
    "id": 1,
    "name": "双11皇家美素佳儿策略",

    # ⭐ 节点池：key 是 label（维度），value 是已筛选的节点ID
    "node_pools": {
        "人设": ["3001004101", "3001004102", "3001004103"],  # 双11活动的人设节点
        "场景": ["3001004201", "3001004202", "3001004203"],  # 全部场景节点
        "卖点": ["3001004301", "3001004302", "3001004303"]   # 旺玥产品的卖点节点
    },

    "combination_mode": "cartesian",  # 笛卡尔积 / 手动定义
    "defined_combinations": [...],     # 手动定义的组合（可选）
    "scope_context": {...}             # Scope 上下文（可选）
}
```

**关键点**：
- `node_pools` 的 key 就是 label（"人设"、"场景"、"卖点"）
- 在创建策略时，已经按品牌、活动等属性筛选好节点
- 例如："人设"维度的节点已筛选出"双11大促"活动下的人设

---

### Plugin（插件）

```python
Plugin = {
    "plugin_code": "writer_plugin",
    "plugin_name": "小红书种草文生成",
    "context_template": "你是{{写者}}，正在经历{{场景}}的场景，请写一篇关于{{卖点}}的种草文",

    # ⭐ 新增字段1：绑定的内容策略ID（可替换）
    "strategy_id": 1,  # 双11策略 = 1，春节策略 = 2，换活动时切换这个值

    # ⭐ 新增字段2：变量映射配置（只绑定 label）
    "variable_mappings": [
        {
            "variable_name": "写者",
            "label": "人设"  # ⭐ 使用策略中 node_pools["人设"] 的节点
        },
        {
            "variable_name": "场景",
            "label": "场景"  # ⭐ 使用策略中 node_pools["场景"] 的节点
        },
        {
            "variable_name": "卖点",
            "label": "卖点"  # ⭐ 使用策略中 node_pools["卖点"] 的节点
        }
    ]
}
```

**关键点**：
- `variable_mappings` 只配置 `variable_name` → `label` 的映射
- **不需要** `attribute_filters`（由策略在创建时定义）
- 换活动时，只需切换 `strategy_id`，`variable_mappings` 保持不变

---

## 核心设计原则

### 1. 插件配置只绑定 label（维度）

```python
# ✅ 正确：只绑定 label
"variable_mappings": [
    {"variable_name": "写者", "label": "人设"}
]

# ❌ 错误：不要在插件中配置属性筛选
"variable_mappings": [
    {
        "variable_name": "写者",
        "label": "人设",
        "attribute_filters": {"brands": ["皇家美素佳儿"]}  # ← 不要这样
    }
]
```

### 2. 换活动/产品时，只需要切换 strategy_id

```python
# 双11活动
Plugin = {
    "strategy_id": 1,  # 双11策略
    "variable_mappings": [
        {"variable_name": "写者", "label": "人设"}
    ]
}

# 春节活动：只改 strategy_id
Plugin = {
    "strategy_id": 2,  # 春节策略
    "variable_mappings": [
        {"variable_name": "写者", "label": "人设"}  # 不变
    ]
}
```

### 3. 职责分离

| 层级 | 职责 | 示例 |
|------|------|------|
| **策略层** | 定义 node_pools 时按属性筛选节点 | "双11人设"：筛选 brands=皇家美素佳儿 + tag_groups=双11大促 |
| **插件层** | 只负责变量到 label 的映射 | "写者" → "人设" |
| **数据层** | 关键词库按 label 和属性标签组织 | nodes.label + nodes.properties.tags |

---

## 前端配置界面

### 快速模式：选用已有策略

```
┌─────────────────────────────────────────────────────────────┐
│ 插件配置: writer_plugin                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 选择内容策略                                                 │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [双11皇家美素佳儿策略 ▼]                                 │ │
│ │   - 人设: 3个节点                                        │ │
│ │   - 场景: 3个节点                                        │ │
│ │   - 卖点: 3个节点                                        │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ⭐ 变量映射配置（手动配置）                                  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 提取到3个变量: 写者, 场景, 卖点                           │ │
│ │                                                         │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │ 变量: 写者                                         │   │ │
│ │ │ ├─ 使用策略中的维度: [人设 ▼]  ← 下拉显示策略中所有label│   │ │
│ │ │ └─ 预览: 将从策略的"人设"节点池中随机选择           │   │ │
│ │ │    (3个节点: 精致妈妈, 创业妈妈, 职场精英)         │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 高级模式：内联配置新策略

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 选择关键词池                                             │
├─────────────────────────────────────────────────────────────┤
│ Label筛选（必选）                                           │
│ ☑ 人设 (15个可用)  ☑ 场景 (8个可用)  ☑ 卖点 (12个可用)    │
│                                                             │
│ 属性筛选（可选）                                             │
│ 品牌: [皇家美素佳儿 ▼]                                      │
│ 活动: [双11大促 ▼]                                          │
│                                                             │
│ [应用筛选]                                                  │
│                                                             │
│ 筛选结果                                                    │
│ - 人设: 3个节点（精致妈妈, 创业妈妈, 职场精英）             │
│ - 场景: 3个节点（居家带娃, 职场分享, 亲子出游）             │
│ - 卖点: 3个节点（温和无刺激, 性价比高, OPO结构脂）          │
└─────────────────────────────────────────────────────────────┘
```

---

## 运行时快照生成

```python
async def generate_snapshot_from_strategy(
    plugin: Plugin,
    strategy: ContentStrategy
) -> dict:
    """
    根据插件配置的 variable_mappings 从策略生成快照
    """
    snapshot = {}

    # 1. 获取策略的节点池（策略创建时已按属性筛选）
    node_pools = strategy.node_pools  # {"人设": [node_ids], "场景": [node_ids]}

    # 2. 遍历插件的变量映射配置
    for var_mapping in plugin.variable_mappings:
        variable_name = var_mapping["variable_name"]  # "写者"
        label = var_mapping["label"]                   # "人设"

        # 3. 从策略的节点池获取节点ID列表
        node_ids = node_pools.get(label)
        if not node_ids:
            raise ValueError(f"策略中没有 {label} 的节点")

        # 4. 查询节点详情（策略已筛选，无需再次筛选）
        nodes = await GraphNode.filter(id__in=node_ids, is_active=1)

        # 5. 随机选择一个节点和语料
        selected_node = random.choice(nodes)
        corpus = random.choice(selected_node.corpus)

        # 6. 构建快照条目
        snapshot[variable_name] = {
            "source": "strategy",
            "strategy_id": strategy.id,
            "label": label,
            "node_id": selected_node.id,
            "node_name": selected_node.name,
            "corpus_text": corpus["text"]
        }

    return snapshot
```

**关键点**：
- 策略的 `node_pools` 已经按属性筛选好节点
- 运行时不需要再次应用 `attribute_filters`
- 直接从 `node_pools[label]` 获取节点ID列表

---

## 完整示例

### 创建策略

```python
# 1. 创建双11活动策略
ContentStrategy.create(
    name="双11皇家美素佳儿策略",
    node_pools={
        # 已按属性筛选：双11活动 + 皇家美素佳儿品牌的人设
        "人设": ["node_1", "node_2", "node_3"],

        # 全部场景（不筛选）
        "场景": ["node_4", "node_5", "node_6"],

        # 旺玥产品的卖点
        "卖点": ["node_7", "node_8", "node_9"]
    }
)
```

### 配置插件

```python
# 2. 配置插件（只绑定 label）
Plugin.update(
    plugin_code="writer_plugin",
    strategy_id=1,  # 绑定到双11策略
    variable_mappings=[
        {"variable_name": "写者", "label": "人设"},
        {"variable_name": "场景", "label": "场景"},
        {"variable_name": "卖点", "label": "卖点"}
    ]
)
```

### 换活动

```python
# 3. 春节活动：只切换 strategy_id
Plugin.update(
    plugin_code="writer_plugin",
    strategy_id=2,  # 切换到春节策略
    # variable_mappings 不变！
)
```

---

## 优势总结

| 优势 | 说明 |
|------|------|
| **概念清晰** | label 就是维度，无需额外抽象层 |
| **配置简单** | 插件只需配置 `variable_name` → `label` |
| **职责分离** | 策略负责筛选，插件负责映射 |
| **易于切换** | 换活动只需切换 `strategy_id` |
| **性能优化** | 策略创建时已筛选，运行时无需重复计算 |

---

## 文档位置

- **完整方案**: [KEYWORD_CORPUS_REFACTOR_PLAN.md](./KEYWORD_CORPUS_REFACTOR_PLAN.md)
- **API 设计**: [KEYWORD_CORPUS_REFACTOR_PLAN_API_ONLY.md](./KEYWORD_CORPUS_REFACTOR_PLAN_API_ONLY.md)
- **策略页面参考**: [raap-admin-frontend/apps/raap-admin/src/views/keyword_corpus/strategy/index.vue](../raap-admin-frontend/apps/raap-admin/src/views/keyword_corpus/strategy/index.vue)
