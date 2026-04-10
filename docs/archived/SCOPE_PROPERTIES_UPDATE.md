# 代码与文档同步更新说明

> **更新时间**: 2025-01-07
> **目的**: 修正方案文档中关于 properties 和 scope 的描述，与实际代码保持一致

---

## 一、代码实际情况

### 1.1 GraphNode 表（nodes 表）

**文件**: `raap-service-keyword-corpus/app/models/graph.py`

```python
class GraphNode(Base):
    # 核心属性
    label: Mapped[str] = mapped_column(String(50), ...)
    name: Mapped[str] = mapped_column(String(255), ...)
    description: Mapped[str | None] = mapped_column(String(500), ...)
    corpus: Mapped[list | None] = mapped_column(JSON, ...)
    ai_instruction: Mapped[dict | None] = mapped_column(JSON, ...)
    properties: Mapped[dict | None] = mapped_column(JSON, ...)  # ⭐

    # Scope 是独立字段
    scope_key: Mapped[str] = mapped_column(String(255), ...)  # ⭐
```

**关键点**：
- ✅ `properties` 是一个 JSON 字段，存储扩展属性
- ✅ `scope_key` 是**独立的字段**，**不在 properties 里面**
- ✅ `properties` 的典型内容：`{"sort_order": 1, "tags": ["小红书"]}`

### 1.2 ContentStrategy 表（content_strategies 表）

**文件**: `raap-service-keyword-corpus/app/models/content_strategy.py`

```python
class ContentStrategy(Base):
    # 节点池
    node_pools: Mapped[dict | None] = mapped_column(JSON, ...)

    # 组合列表
    defined_combinations: Mapped[list | None] = mapped_column(JSON, ...)

    # Scope 上下文（独立字段）
    scope_context: Mapped[dict | None] = mapped_column(JSON, ...)  # ⭐
```

**scope_context 的内容结构**：
```python
{
    "level": "product",         # global / brand / product
    "brand_code": "2000001",
    "brand_name": "皇家美素佳儿",
    "product_name": "旺玥",
    "activity_name": "双11大促",  # 可选
    "fallback_enabled": true    # 是否启用回退机制
}
```

---

## 二、文档更新情况

### 2.1 已更新的文档

| 文档 | 状态 | 说明 |
|------|------|------|
| **KEYWORD_CORPUS_REFACTOR_PLAN_V2.md** | ✅ 已更新 | 新增的 V2.0 方案，已确保 scope_context 与代码一致 |
| **KEYWORD_CORPUS_REFACTOR_PLAN.md** | ✅ 无需更新 | 原始完整方案，描述正确（scope_key 是独立字段） |
| **KEYWORD_CORPUS_REFACTOR_PLAN_SUMMARY.md** | ✅ 无需更新 | 总结文档，未涉及 properties 内部结构 |
| **KEYWORD_CORPUS_REFACTOR_PLAN_API_ONLY.md** | ✅ 无需更新 | API 文档，scope_context 描述正确 |

### 2.2 更新内容

**KEYWORD_CORPUS_REFACTOR_PLAN_V2.md** 的修正：

1. **ContentStrategy 的 scope_context 字段**（第133-140行）：
```python
# ✅ 修正后：明确说明 scope_context 是独立字段
"scope_context": {
    "level": "product",        # global / brand / product
    "brand_code": "2000001",
    "brand_name": "皇家美素佳儿",
    "product_name": "旺玥",
    "activity_name": "双11大促"   # 可选：活动名称
},
```

2. **数据库迁移脚本的注释**（第399-407行）：
```sql
-- ✅ 修正后：与 ContentStrategy 表保持一致
{
    "level": "product",         -- global / brand / product
    "brand_code": "2000001",
    "brand_name": "皇家美素佳儿",
    "product_name": "旺玥",
    "activity_name": "双11大促", -- 可选
    "fallback_enabled": true    -- 是否启用回退机制
}
```

---

## 三、核心设计原则总结

### 3.1 GraphNode 的字段设计

```python
GraphNode = {
    # 主分类
    "label": "人设",              # 语义标签（主分类）

    # 扩展属性（⚠️ 不包含 scope）
    "properties": {
        "sort_order": 1,
        "tags": ["小红书"]
    },

    # Scope 独立字段（⭐ 不在 properties 里面）
    "scope_key": "global:"       # 格式: {level}:{product_names或brand_codes}
}
```

### 3.2 ContentStrategy 的字段设计

```python
ContentStrategy = {
    # 节点池
    "node_pools": {...},

    # Scope 上下文（独立字段）
    "scope_context": {           # ⭐ 独立字段
        "level": "product",
        "brand_code": "2000001",
        "brand_name": "皇家美素佳儿",
        "product_name": "旺玥",
        "activity_name": "双11大促",
        "fallback_enabled": true
    }
}
```

---

## 四、关键结论

1. ✅ **properties 中不包含 scope**：无论是 GraphNode 还是其他模型，scope 都是独立字段
2. ✅ **GraphNode 使用 scope_key**：格式为 `{level}:{product_names或brand_codes}`
3. ✅ **ContentStrategy 使用 scope_context**：更结构化的 JSON 对象
4. ✅ **所有文档已同步**：确保方案文档与实际代码结构一致

---

## 五、实施注意事项

### 5.1 前端开发

- 节点的 scope 信息从 `scope_key` 字段读取，**不是**从 `properties.scope`
- 策略的 scope 信息从 `scope_context` 字段读取

### 5.2 后端开发

- 创建/更新节点时，`scope_key` 和 `properties` 是**独立设置**的
- 创建/更新策略时，`scope_context` 是**独立字段**，不要放在其他字段里面

### 5.3 数据库查询

```python
# ✅ 正确：直接查询 scope_key 字段
nodes = await GraphNode.filter(scope_key="product:旺玥")

# ❌ 错误：不要查询 properties.scope
nodes = await GraphNode.filter(properties__scope="product:旺玥")
```

---

**文档维护**：本文档作为代码与文档同步的参考，确保后续更新时保持一致性。
