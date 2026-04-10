# 关键词语料系统重构方案 V2.0 - 策略类型抽象

> **版本**: v2.0
> **更新时间**: 2025-01-07
> **核心优化**: 插件绑定抽象策略类型，而非具体策略实例

---

## 一、问题与优化目标

### 1.1 当前设计的问题

```python
# ❌ 当前设计：插件直接绑定具体策略实例
Plugin = {
    "plugin_code": "writer_plugin",
    "strategy_id": 1,  # 双11策略 = 1，春节策略 = 2
    # 换活动时需要手动切换 strategy_id
}

# 问题：
# 1. 换活动需要切换策略ID（手动操作）
# 2. 不同活动创建了多个"人设×场景×卖点"的策略实例
# 3. 策略实例数量会随着活动增加而爆炸式增长
# 4. 无法表达"这个插件需要人设、场景、卖点三个维度"的抽象需求
```

### 1.2 优化目标

```python
# ✅ 优化后：插件绑定抽象策略类型
Plugin = {
    "plugin_code": "writer_plugin",
    "strategy_type_id": 1,  # 策略类型：人设×场景×卖点
}

# 策略类型定义（抽象）
ContentStrategyType = {
    "id": 1,
    "name": "人设×场景×卖点",
    "dimension_labels": ["人设", "场景", "卖点"],  # ⭐ 只关注有哪些 label
    # 不关注具体是哪些关键词，也不关注顺序
}

# 具体策略（多个实例）
ContentStrategy = {
    "id": 1,
    "strategy_type_id": 1,  # 属于"人设×场景×卖点"类型
    "name": "双11皇家美素佳儿策略",
    "node_pools": {
        "人设": [...],  # 双11精选的人设
        "场景": [...],  # 双11精选的场景
        "卖点": [...]   # 双11精选的卖点
    }
}

ContentStrategy = {
    "id": 2,
    "strategy_type_id": 1,  # 同样属于"人设×场景×卖点"类型
    "name": "春节皇家美素佳儿策略",
    "node_pools": {
        "人设": [...],  # 春节精选的人设
        "场景": [...],  # 春节精选的场景
        "卖点": [...]   # 春节精选的卖点
    }
}

# 优势：
# 1. 插件绑定策略类型，表达"我需要人设、场景、卖点"的抽象需求
# 2. 运行时根据 scope（活动/产品）自动选择对应的具体策略
# 3. 策略类型数量固定（由 label 组合决定）
# 4. 策略实例可以按需创建（每次活动一个）
```

---

## 二、核心概念定义

### 2.1 ContentStrategyType（策略类型 - 抽象）

> **新增表**: `content_strategy_types`
> **职责**: 定义策略的抽象类型（包含哪些 label）

```python
ContentStrategyType = {
    "id": 1,
    "name": "人设×场景×卖点",
    "code": "persona_scenario_selling_point",
    "description": "包含人设、场景、卖点三个维度的策略",

    # ⭐ 核心字段：包含哪些 label（维度）
    "dimension_labels": ["人设", "场景", "卖点"],

    # 不包含具体的关键词，也不关注顺序
    # 只表达"这个类型的策略需要人设、场景、卖点三个维度"

    "tenant_code": "default",
    "is_active": 1,
    "is_deleted": 0
}

# ⭐ 核心设计原则：
# 1. dimension_labels 是一个集合（set），不是列表（list）
# 2. 顺序不重要：["人设", "场景", "卖点"] = ["场景", "卖点", "人设"]
# 3. 只关心"有哪些 label"，不关心"具体是哪些关键词"
# 4. 一个策略类型可以有无数个策略实例
```

### 2.2 ContentStrategy（策略实例 - 具体）

> **现有表**: `content_strategies`
> **变更**: 新增 `strategy_type_id` 字段

```python
ContentStrategy = {
    "id": 1,
    "strategy_type_id": 1,  # ⭐ 新增字段：属于哪个策略类型

    "name": "双11皇家美素佳儿策略",
    "description": "双11活动专用的内容策略",

    # ⭐ 节点池：key 是 label，value 是已筛选的节点ID
    "node_pools": {
        "人设": ["3001004101", "3001004102", "3001004103"],  # 双11精选
        "场景": ["3001004201", "3001004202", "3001004203"],
        "卖点": ["3001004301", "3001004302", "3001004303"]
    },

    # 组合模式
    "combination_mode": "cartesian",
    "defined_combinations": [...],

    # Scope 上下文（策略实例的 scope_context 字段）
    "scope_context": {
        "level": "product",        # global / brand / product
        "brand_code": "2000001",
        "brand_name": "皇家美素佳儿",
        "product_name": "旺玥",
        "activity_name": "双11大促"   # 可选：活动名称
    },

    "tenant_code": "default",
    "is_active": 1,
    "is_deleted": 0
}

# ⭐ 核心设计原则：
# 1. 一个策略类型可以有多个策略实例
# 2. 每个策略实例绑定到不同的 scope（活动/产品）
# 3. node_pools 的 key 必须与 strategy_type.dimension_labels 匹配
# 4. 换活动时创建新的策略实例，但 strategy_type_id 不变
```

### 2.3 Plugin（插件 - 绑定策略类型）

> **现有表**: `plugin` (在 orchestrator 服务)
> **变更**: `strategy_id` → `strategy_type_id`

```python
Plugin = {
    "plugin_code": "writer_plugin",
    "plugin_name": "小红书种草文生成",
    "context_template": "你是{{写者}}，正在经历{{场景}}的场景，请写一篇关于{{卖点}}的种草文",

    # ⭐ 变更：绑定策略类型（而非策略实例）
    "strategy_type_id": 1,  # 人设×场景×卖点

    # 变量映射配置（保持不变）
    "variable_mappings": [
        {"variable_name": "写者", "label": "人设"},
        {"variable_name": "场景", "label": "场景"},
        {"variable_name": "卖点", "label": "卖点"}
    ]
}

# ⭐ 核心设计原则：
# 1. 插件绑定策略类型，表达"我需要人设、场景、卖点"
# 2. 不绑定具体策略实例，避免换活动时手动切换
# 3. 运行时根据 scope（活动/产品）自动选择对应的策略实例
# 4. variable_mappings 保持不变（仍绑定 label）
```

---

## 三、运行时策略选择机制

### 3.1 策略选择流程

```python
class StrategyResolver:
    """
    策略解析器：根据 scope 自动选择对应的策略实例
    """

    async def resolve_strategy(
        self,
        strategy_type_id: int,
        scope_context: dict
    ) -> ContentStrategy:
        """
        根据策略类型和 scope 上下文，解析出具体的策略实例

        Args:
            strategy_type_id: 策略类型ID
            scope_context: Scope 上下文
                {
                    "level": "product",  # global / brand / product
                    "brand_code": "2000001",
                    "brand_name": "皇家美素佳儿",
                    "product_name": "旺玥",
                    "activity_name": "双11大促"  # 可选
                }

        Returns:
            ContentStrategy: 匹配的策略实例
        """

        # 1. 查询该策略类型的所有策略实例
        strategies = await ContentStrategy.filter(
            strategy_type_id=strategy_type_id,
            is_active=1,
            is_deleted=0
        )

        # 2. 按 scope 优先级匹配
        # 优先级：product > brand > global
        matched_strategy = self._match_by_scope(strategies, scope_context)

        if not matched_strategy:
            raise StrategyNotFoundError(
                f"未找到匹配的策略: strategy_type_id={strategy_type_id}, "
                f"scope={scope_context}"
            )

        return matched_strategy

    def _match_by_scope(
        self,
        strategies: List[ContentStrategy],
        scope_context: dict
    ) -> Optional[ContentStrategy]:
        """
        按 scope 优先级匹配策略

        匹配规则：
        1. 优先匹配 level=product 且 product_name 匹配
        2. 其次匹配 level=brand 且 brand_code 匹配
        3. 最后匹配 level=global
        4. 如果有 activity_name，优先匹配包含该活动的策略
        """

        level = scope_context.get("level", "global")
        product_name = scope_context.get("product_name")
        brand_code = scope_context.get("brand_code")
        activity_name = scope_context.get("activity_name")

        # 1. Product 级别匹配
        if level == "product" and product_name:
            for strategy in strategies:
                if strategy.scope_context.get("level") == "product":
                    if strategy.scope_context.get("product_name") == product_name:
                        # 如果有活动名称，优先匹配活动
                        if activity_name:
                            if strategy.scope_context.get("activity_name") == activity_name:
                                return strategy
                        elif not strategy.scope_context.get("activity_name"):
                            # 没有活动名称时，选择没有活动绑定的策略
                            return strategy

        # 2. Brand 级别匹配
        if brand_code:
            for strategy in strategies:
                if strategy.scope_context.get("level") == "brand":
                    if strategy.scope_context.get("brand_code") == brand_code:
                        if activity_name:
                            if strategy.scope_context.get("activity_name") == activity_name:
                                return strategy
                        elif not strategy.scope_context.get("activity_name"):
                            return strategy

        # 3. Global 级别匹配
        for strategy in strategies:
            if strategy.scope_context.get("level") == "global":
                return strategy

        return None
```

### 3.2 快照生成流程（更新）

```python
async def generate_snapshot_from_strategy_type(
    plugin: Plugin,
    scope_context: dict
) -> dict:
    """
    根据插件绑定的策略类型和 scope 上下文生成快照

    Args:
        plugin: 插件配置
        scope_context: Scope 上下文（从 SubJob 或 Task 传入）

    流程：
    1. 获取插件绑定的策略类型
    2. 根据 scope 自动选择匹配的策略实例
    3. 从策略实例生成快照
    """

    # 1. 获取策略类型
    strategy_type = await ContentStrategyType.get_by_id(plugin.strategy_type_id)
    if not strategy_type:
        raise ValueError(f"策略类型不存在: {plugin.strategy_type_id}")

    # 2. 根据 scope 解析出具体的策略实例
    resolver = StrategyResolver()
    strategy = await resolver.resolve_strategy(
        strategy_type_id=strategy_type.id,
        scope_context=scope_context
    )

    logger.info(
        f"策略解析成功: plugin={plugin.plugin_code}, "
        f"strategy_type={strategy_type.name}, "
        f"strategy={strategy.name}, "
        f"scope={scope_context}"
    )

    # 3. 从策略实例生成快照（逻辑与之前相同）
    snapshot = await _generate_snapshot_from_strategy(plugin, strategy)

    return snapshot
```

---

## 四、数据库设计

### 4.1 新增表：content_strategy_types

```sql
CREATE TABLE content_strategy_types (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '策略类型ID',
    tenant_code VARCHAR(50) NOT NULL DEFAULT 'default' COMMENT '租户编码',

    -- 基础信息
    name VARCHAR(100) NOT NULL COMMENT '策略类型名称（如：人设×场景×卖点）',
    code VARCHAR(100) UNIQUE NOT NULL COMMENT '策略类型编码（如：persona_scenario_selling_point）',
    description VARCHAR(500) COMMENT '策略类型描述',

    -- ⭐ 核心字段：包含哪些 label（维度）
    dimension_labels JSON NOT NULL COMMENT '维度标签列表（JSON数组），如：["人设", "场景", "卖点"]',

    -- 元数据
    metadata JSON COMMENT '元数据（如：创建时间、使用统计等）',

    -- 状态
    is_active INT DEFAULT 1 COMMENT '是否启用',
    is_deleted INT DEFAULT 0 COMMENT '是否删除',

    -- 审计字段
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    created_by VARCHAR(50) COMMENT '创建人',

    -- 索引
    INDEX idx_tenant (tenant_code),
    INDEX idx_tenant_active (tenant_code, is_active, is_deleted),
    INDEX idx_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='内容策略类型表（抽象）';
```

**数据示例**：

```sql
-- 策略类型示例
INSERT INTO content_strategy_types (name, code, dimension_labels, description) VALUES
('人设×场景', 'persona_scenario', '["人设", "场景"]', '包含人设和场景两个维度'),
('人设×场景×卖点', 'persona_scenario_selling_point', '["人设", "场景", "卖点"]', '包含人设、场景、卖点三个维度'),
('人设×场景×卖点×字数', 'persona_scenario_selling_point_length', '["人设", "场景", "卖点", "字数"]', '包含人设、场景、卖点、字数四个维度');
```

### 4.2 修改表：content_strategies

```sql
-- 为 content_strategies 表添加字段
ALTER TABLE content_strategies
ADD COLUMN strategy_type_id BIGINT NOT NULL COMMENT '策略类型ID（关联 content_strategy_types.id）',
ADD COLUMN scope_context JSON COMMENT 'Scope 上下文（用于策略匹配）',
ADD INDEX idx_strategy_type (strategy_type_id),
ADD INDEX idx_tenant_scope (tenant_code, strategy_type_id, is_active, is_deleted);
```

**更新示例**：

```sql
-- 更新现有策略，添加 strategy_type_id
UPDATE content_strategies SET strategy_type_id = 1 WHERE name LIKE '%双11%';

-- scope_context 字段内容示例（与 ContentStrategy 表保持一致）
{
    "level": "product",         -- global / brand / product
    "brand_code": "2000001",
    "brand_name": "皇家美素佳儿",
    "product_name": "旺玥",
    "activity_name": "双11大促", -- 可选
    "fallback_enabled": true    -- 是否启用回退机制
}
```

### 4.3 修改表：plugin（orchestrator 服务）

```sql
-- 为 plugin 表修改字段
ALTER TABLE plugin
CHANGE COLUMN strategy_id strategy_type_id BIGINT COMMENT '策略类型ID（关联 content_strategy_types.id）';

-- ⚠️ 注意：这里需要数据迁移，将旧的 strategy_id 映射到 strategy_type_id
```

---

## 五、前端交互设计

### 5.1 插件配置页面

```
┌─────────────────────────────────────────────────────────────┐
│ 插件配置: writer_plugin                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 基本信息                                                     │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 插件编码: writer_plugin                                 │ │
│ │ 插件名称: 小红书种草文生成                               │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ 提示词模板                                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 你是{{写者}}，正在经历{{场景}}的场景，                  │ │
│ │ 请写一篇关于{{卖点}}的种草文。                           │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ⭐ 策略类型配置（新增）                                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                                                         │ │
│ │ 选择策略类型                                             │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │ [人设×场景×卖点 ▼]                                │   │ │
│ │ │   - 包含维度: 人设、场景、卖点                     │   │ │
│ │ │   - 可用策略: 3个（双11、春节、618）               │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ │                                                         │ │
│ │ 说明: 插件绑定策略类型后，系统会根据活动/产品自动选择   │ │
│ │       对应的具体策略实例，无需手动切换。                 │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ⭐ 变量映射配置（保持不变）                                  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 提取到3个变量: 写者, 场景, 卖点                           │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │ 变量: 写者 → label: 人设                           │   │ │
│ │ │ 变量: 场景 → label: 场景                           │   │ │
│ │ │ 变量: 卖点 → label: 卖点                           │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────┐  ┌──────────────┐                            │
│ │  取消       │  │  保存配置     │                            │
│ └─────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 策略类型管理页面（新增）

```
┌─────────────────────────────────────────────────────────────┐
│ 策略类型管理                                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 策略类型列表                                                 │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                                                         │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │ 策略类型: 人设×场景×卖点                           │   │ │
│ │ │ 编码: persona_scenario_selling_point              │   │ │
│ │ │ 维度: 人设、场景、卖点                             │   │ │
│ │ │ 策略实例数: 3个（双11、春节、618）                │   │ │
│ │ │ 使用插件数: 5个                                    │   │ │
│ │ │ [查看实例] [编辑] [删除]                           │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ │                                                         │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │ 策略类型: 人设×场景                               │   │ │
│ │ │ 编码: persona_scenario                            │   │ │
│ │ │ 维度: 人设、场景                                  │   │ │
│ │ │ 策略实例数: 2个（春季、夏季）                     │   │ │
│ │ │ 使用插件数: 3个                                    │   │ │
│ │ │ [查看实例] [编辑] [删除]                           │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ │                                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────┐                                            │
│ │  创建策略类型 │                                            │
│ └─────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 策略实例管理页面（更新）

```
┌─────────────────────────────────────────────────────────────┐
│ 策略实例管理 - 策略类型: 人设×场景×卖点                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 策略实例列表                                                 │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                                                         │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │ 策略: 双11皇家美素佳儿策略                         │   │ │
│ │ │ Scope: 旺玥产品 + 双11大促                        │   │ │
│ │ │ 节点池: 人设(3) + 场景(3) + 卖点(3)               │   │ │
│ │ │ 状态: ✅ 启用                                      │   │ │
│ │ │ [编辑] [复制] [禁用] [删除]                        │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ │                                                         │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │ 策略: 春节皇家美素佳儿策略                         │   │ │
│ │ │ Scope: 旺玥产品 + 春节活动                        │   │ │
│ │ │ 节点池: 人设(5) + 场景(4) + 卖点(4)               │   │ │
│ │ │ 状态: ✅ 启用                                      │   │ │
│ │ │ [编辑] [复制] [禁用] [删除]                        │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ │                                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────┐  ┌──────────────┐                            │
│ │  创建策略实例 │  │  从模板创建   │                            │
│ └─────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、API 设计

### 6.1 策略类型管理 API

```typescript
// 1. 获取所有策略类型
GET /api/v1/strategy-types

Response:
{
    "code": 200,
    "data": {
        "items": [
            {
                "id": 1,
                "name": "人设×场景×卖点",
                "code": "persona_scenario_selling_point",
                "dimension_labels": ["人设", "场景", "卖点"],
                "description": "包含人设、场景、卖点三个维度",
                "strategy_count": 3,  // 该类型下的策略实例数
                "plugin_count": 5     // 使用该类型的插件数
            }
        ],
        "total": 3
    }
}

// 2. 创建策略类型
POST /api/v1/strategy-types

Request:
{
    "name": "人设×场景",
    "code": "persona_scenario",
    "dimension_labels": ["人设", "场景"],
    "description": "包含人设和场景两个维度"
}

// 3. 更新策略类型
PUT /api/v1/strategy-types/{id}

// 4. 删除策略类型
DELETE /api/v1/strategy-types/{id}

// 5. 获取策略类型的所有实例
GET /api/v1/strategy-types/{id}/strategies

Response:
{
    "code": 200,
    "data": {
        "strategy_type": {
            "id": 1,
            "name": "人设×场景×卖点"
        },
        "strategies": [
            {
                "id": 1,
                "name": "双11皇家美素佳儿策略",
                "scope_context": {...},
                "node_pools": {...}
            }
        ]
    }
}
```

### 6.2 策略实例管理 API（更新）

```typescript
// 1. 创建策略实例（指定策略类型）
POST /api/v1/content-strategies

Request:
{
    "strategy_type_id": 1,  // ⭐ 新增字段
    "name": "双11皇家美素佳儿策略",
    "node_pools": {
        "人设": [...],
        "场景": [...],
        "卖点": [...]
    },
    "scope_context": {
        "level": "product",
        "brand_code": "2000001",
        "product_name": "旺玥",
        "activity_name": "双11大促"
    }
}

// 2. 根据策略类型和 scope 查询策略
GET /api/v1/content-strategies/resolve?
    strategy_type_id=1&
    level=product&
    brand_code=2000001&
    product_name=旺玥&
    activity_name=双11大促

Response:
{
    "code": 200,
    "data": {
        "id": 1,
        "name": "双11皇家美素佳儿策略",
        "strategy_type_id": 1,
        "scope_context": {...},
        "node_pools": {...}
    }
}
```

### 6.3 插件配置 API（更新）

```typescript
// 更新插件配置（绑定策略类型）
PUT /api/v1/plugins/{plugin_id}/variable-mappings

Request:
{
    "strategy_type_id": 1,  // ⭐ 绑定策略类型（而非策略实例）
    "variable_mappings": [
        {"variable_name": "写者", "label": "人设"},
        {"variable_name": "场景", "label": "场景"},
        {"variable_name": "卖点", "label": "卖点"}
    ]
}

Response:
{
    "code": 200,
    "data": {
        "plugin_id": 123,
        "strategy_type_id": 1,
        "strategy_type_name": "人设×场景×卖点",
        "available_strategies": [
            {
                "id": 1,
                "name": "双11皇家美素佳儿策略",
                "scope_context": {...}
            }
        ],
        "variable_mappings": [...]
    }
}
```

---

## 七、数据迁移方案

### 7.1 迁移步骤

```python
# migration_script.py

async def migrate_to_strategy_type():
    """
    将现有的策略体系迁移到策略类型模式
    """

    # 1. 分析现有策略，推断策略类型
    strategies = await ContentStrategy.filter(is_deleted=0)

    strategy_type_map = {}

    for strategy in strategies:
        # 提取 node_pools 的所有 label（key）
        labels = sorted(set(strategy.node_pools.keys()))
        labels_key = json.dumps(labels, sort_keys=True)

        # 生成策略类型编码
        type_code = "_".join([label_to_code(l) for l in labels])

        if labels_key not in strategy_type_map:
            # 创建策略类型
            strategy_type = await ContentStrategyType.create(
                name=f"{'×'.join(labels)}",
                code=type_code,
                dimension_labels=labels,
                description=f"包含{'、'.join(labels)}维度"
            )
            strategy_type_map[labels_key] = strategy_type.id

        # 更新策略的 strategy_type_id
        strategy.strategy_type_id = strategy_type_map[labels_key]

        # 推断 scope_context（如果还没有）
        if not strategy.scope_context:
            strategy.scope_context = infer_scope_from_strategy(strategy)

        await strategy.update()

    # 2. 更新插件配置
    plugins = await Plugin.filter(strategy_id__isnull=False)

    for plugin in plugins:
        # 获取插件绑定的策略
        strategy = await ContentStrategy.get_by_id(plugin.strategy_id)

        # 更新插件绑定到策略类型
        plugin.strategy_type_id = strategy.strategy_type_id

        await plugin.update()

    logger.info("迁移完成")

def label_to_code(label: str) -> str:
    """
    将 label 转换为编码

    例如：
    - "人设" → "persona"
    - "场景" → "scenario"
    - "卖点" → "selling_point"
    """
    mapping = {
        "人设": "persona",
        "场景": "scenario",
        "卖点": "selling_point",
        "字数": "length"
    }
    return mapping.get(label, label.lower())
```

---

## 八、优势总结

| 优势 | 说明 |
|------|------|
| **概念清晰** | 插件绑定策略类型（抽象），策略实例绑定具体内容 |
| **自动切换** | 换活动时自动选择对应的策略实例，无需手动操作 |
| **数量可控** | 策略类型数量固定（由 label 组合决定），不会爆炸增长 |
| **复用性强** | 一个策略类型可以有无数个策略实例 |
| **管理方便** | 策略按类型分组管理，清晰易懂 |

---

## 九、实施计划

| 阶段 | 内容 | 服务 | 优先级 |
|------|------|------|--------|
| **Phase 1** | 数据库变更（新增 content_strategy_types 表） | keyword-corpus | P0 |
| **Phase 2** | 数据库变更（content_strategies 添加 strategy_type_id） | keyword-corpus | P0 |
| **Phase 3** | 数据库变更（plugin.strategy_id → strategy_type_id） | orchestrator | P0 |
| **Phase 4** | 数据迁移脚本 | orchestrator | P0 |
| **Phase 5** | 策略解析器实现 | orchestrator | P0 |
| **Phase 6** | API 开发（策略类型管理） | keyword-corpus | P1 |
| **Phase 7** | 前端：策略类型管理页面 | admin-frontend | P1 |
| **Phase 8** | 前端：插件配置页面更新 | admin-frontend | P1 |
| **Phase 9** | 测试与验证 | all | P1 |

---

## 十、总结

本次优化将"插件直接绑定策略实例"改为"插件绑定策略类型"，实现了：

1. ✅ **抽象与具体分离**：策略类型定义抽象需求，策略实例提供具体内容
2. ✅ **自动化策略选择**：运行时根据 scope 自动选择匹配的策略实例
3. ✅ **避免数量爆炸**：策略类型数量固定，策略实例可按需创建
4. ✅ **简化配置流程**：换活动时无需手动切换策略

这个方案与现有的"内容策略"概念完美契合，提升了系统的灵活性和可维护性。
