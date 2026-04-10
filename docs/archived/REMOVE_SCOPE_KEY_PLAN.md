# 移除 scope_key 字段方案

> **创建时间**: 2025-01-07
> **更新时间**: 2025-01-07
> **状态**: ✅ 代码变更已完成，待数据库迁移
> **目的**: 清理废弃的 scope_key 字段，简化数据模型

---

## 一、实施进度

### 1.1 已完成项 ✅

- [x] **代码变更完成**（2025-01-07）
  - [x] GraphNode 模型标记 scope_key 为 deprecated
  - [x] metadata_service.py 统计逻辑改为不区分 scope
  - [x] category_service.py 节点复制逻辑移除 scope_key 依赖
  - [x] 导入脚本移除 scope_key 显式赋值

- [x] **数据库脚本创建**（2025-01-07）
  - [x] 迁移脚本：`scripts/migrations/remove_scope_key.sql`
  - [x] 回滚脚本：`scripts/migrations/rollback_remove_scope_key.sql`

### 1.2 待执行项 ⏳

- [ ] **数据库迁移执行**
  - [ ] 在测试环境验证
  - [ ] 在生产环境执行（观察期 1-2 周）
  - [ ] 删除 scope_key 字段（可选，需再次确认）

- [ ] **文档更新**
  - [ ] 更新 API 文档
  - [ ] 更新数据库设计文档

---

## 二、分析结论

**后端使用**：
- ✅ **唯一约束**：`uk_tenant_label_name_scope(tenant_code, label, name, scope_key, is_deleted)`
- ⚠️ **统计功能**：`metadata_service.py` 中按 scope 统计语料数量（低频功能）
- ⚠️ **节点复制**：`category_service.py` 中检查名称冲突（可改用其他方式）

**前端使用**：
- ❌ **完全未使用**

**关键发现**：
- 根据 commit 记录，scope API 已被删除
- `scope_key` 实际上**不再承担业务隔离功能**
- 当前所有节点的 `scope_key` 都是 `"global:"`
- **可以安全移除**

### 1.2 移除理由

1. ✅ **功能已废弃**：scope API 已删除，业务逻辑不再使用
2. ✅ **数据一致性**：所有节点 scope_key 都是 `"global:"，无实际区分作用
3. ✅ **简化模型**：减少字段数量，降低维护成本
4. ✅ **性能提升**：减少索引数量，提升写入性能

---

## 三、已实施的代码变更

### 3.1 GraphNode 模型（app/models/graph.py）

**变更内容**：
- ✅ 标记 scope_key 字段为 deprecated
- ✅ 添加注释说明将在后续版本删除
- ✅ 更新索引注释，标记为待删除

```python
# ⚠️ scope_key 字段已废弃，将在后续版本删除
# 当前保留仅用于唯一约束兼容性
scope_key: Mapped[str] = mapped_column(
    String(255),
    nullable=False,
    default="global:",
    comment="[已废弃] Scope 唯一键，将在后续版本删除"
)

__table_args__ = (
    # ...
    # ⚠️ 以下索引/约束将在后续版本删除
    Index("idx_scope_key", "scope_key"),
    # 唯一约束：当前保留 scope_key 以兼容现有数据
    Index("uk_tenant_label_name_scope", "tenant_code", "label", "name", "scope_key", "is_deleted", unique=True),
)
```

### 3.2 统计服务（app/services/metadata_service.py）

**变更内容**：
- ✅ 删除 `_count_corpus_by_scope` 方法
- ✅ 删除 `_count_corpus_by_scope_prefix` 方法
- ✅ 新增 `_count_all_corpus` 方法（统计全部语料）
- ✅ 修改 `_count_related_corpus` 方法（改为使用 properties.brands 和 properties.tags）

```python
# ⚠️ scope_key 已废弃，改为统计全部语料数量
total_corpus = await self._count_all_corpus(tenant_code)

return MetadataStatsResponse(
    # ...
    global_corpus_count=total_corpus,  # 全部语料
    brand_corpus_count=0,  # ⚠️ 已废弃，返回 0
    product_corpus_count=0,  # ⚠️ 已废弃，返回 0
)

async def _count_all_corpus(self, tenant_code: str) -> int:
    """统计全部语料数量（不区分 scope）"""
    # ... 实现 ...

async def _count_related_corpus(self, item: NodePropertyMeta) -> int:
    """
    ⚠️ scope_key 已废弃，改为通过 properties.brands 和 properties.tags 统计
    """
    # ... 使用 properties.brands 和 properties.tags 查询 ...
```

### 3.3 节点复制服务（app/services/category_service.py）

**变更内容**：
- ✅ 唯一性检查改为 `(label, name)`，不再包含 scope_key
- ✅ 创建新节点时不再显式设置 scope_key（使用字段默认值）

```python
# ⚠️ scope_key 已废弃，改为只检查 (label, name)
existing_names_stmt = select(GraphNode.label, GraphNode.name).where(...)
existing_names: set[tuple[str, str]] = {
    (r.label, r.name) for r in existing_result.fetchall()
}

# 如果名称冲突（相同 label + name），添加数字后缀
while (old_node.label, new_name) in existing_names:
    # ... 处理冲突 ...

# 创建新节点（scope_key 使用默认值 "global:"）
new_node = GraphNode(
    # ...
    # scope_key 使用字段默认值 "global:"
)
```

### 3.4 导入脚本（scripts/import_xiaohongshu_data.sql）

**变更内容**：
- ✅ Part 0 主分类节点插入时移除 scope_key 字段
- ✅ 添加注释说明 scope_key 已废弃

```sql
-- ⚠️ scope_key 字段已废弃，此处保留仅为兼容性（后续版本将删除）
INSERT INTO nodes (id, tenant_code, label, name, description, is_active, is_deleted, created_at, updated_at)
VALUES
(3001004001, 'default', '平台黑话', '平台黑话', '各平台流行的原生表达方式', 1, 0, NOW(), NOW()),
(3001005001, 'default', '内容结构', '内容结构', '内容创作的结构化方法', 1, 0, NOW(), NOW())
```

---

## 四、移除方案（待执行）

### 2.1 数据库变更

#### Step 1: 删除索引（先删索引，避免冲突）

```sql
-- 1. 删除普通索引
DROP INDEX idx_scope_key ON nodes;

-- 2. 删除唯一约束（需要重建新的唯一约束）
ALTER TABLE nodes DROP INDEX uk_tenant_label_name_scope;
```

#### Step 2: 创建新的唯一约束（不包含 scope_key）

```sql
-- 新的唯一约束：(tenant_code, label, name, is_deleted)
-- 允许不同租户有相同名称的节点
-- 同一租户下，相同 label 和 name 的节点只能有一个
ALTER TABLE nodes
ADD UNIQUE INDEX uk_tenant_label_name (tenant_code, label, name, is_deleted);
```

#### Step 3: 删除字段（可选，建议先保留字段观察）

```sql
-- ⚠️ 警告：删除字段前建议先观察一段时间
-- 可以先设置为 deprecated，后续版本再删除
ALTER TABLE nodes DROP COLUMN scope_key;
```

**推荐做法**：
1. 先保留字段，不再写入新值
2. 观察 1-2 个版本，确认无问题
3. 再删除字段

### 2.2 代码变更

#### 2.2.1 移除 GraphNode.scope_key 字段

**文件**: `raap-service-keyword-corpus/app/models/graph.py`

```python
class GraphNode(Base):
    # ... 其他字段 ...

    # ❌ 删除这一行
    # scope_key: Mapped[str] = mapped_column(String(255), nullable=False, default="global:", ...)

    __table_args__ = (
        Index("idx_tenant", "tenant_code"),
        Index("idx_label", "label"),
        Index("idx_tenant_label", "tenant_code", "label"),
        Index("idx_status", "is_active"),
        Index("idx_name", "name"),
        # ❌ 删除这一行
        # Index("idx_scope_key", "scope_key"),
        # ✅ 新的唯一约束
        Index("uk_tenant_label_name", "tenant_code", "label", "name", "is_deleted", unique=True),
    )
```

#### 2.2.2 修改统计功能

**文件**: `raap-service-keyword-corpus/app/services/metadata_service.py`

```python
# ❌ 删除这些方法
# async def _count_corpus_by_scope(self, tenant_code: str, scope_key: str) -> int:
# async def _count_corpus_by_scope_prefix(self, tenant_code: str, prefix: str) -> int:

# ✅ 改为统计全部语料数量
async def get_statistics(self, tenant_code: str) -> dict:
    # ... 其他统计 ...

    # 统计语料数量（不区分 scope）
    corpus_count = await self._count_all_corpus(tenant_code)

    return {
        # ...
        "corpus_count": corpus_count,
    }

async def _count_all_corpus(self, tenant_code: str) -> int:
    """统计全部语料数量"""
    stmt = select(func.count()).select_from(GraphNode).where(
        and_(
            GraphNode.tenant_code == tenant_code,
            GraphNode.is_deleted == 0,
            GraphNode.is_active == 1,
            GraphNode.corpus.isnot(None),
            GraphNode.corpus != json.dumps([]),
        )
    )
    result = await self.db.execute(stmt)
    return result.scalar() or 0
```

#### 2.2.3 修改节点复制逻辑

**文件**: `raap-service-keyword-corpus/app/services/category_service.py`

```python
async def batch_copy_structured(...):
    # ❌ 删除 scope_key 相关逻辑
    # existing_names_stmt = select(GraphNode.label, GraphNode.name, GraphNode.scope_key).where(...)
    # existing_names: set[tuple[str, str, str]] = {
    #     (r.label, r.name, r.scope_key or "global:") for r in ...
    # }

    # ✅ 改为只检查 (label, name)
    existing_names_stmt = select(GraphNode.label, GraphNode.name).where(
        and_(
            GraphNode.tenant_code == tenant_code,
            GraphNode.is_deleted == 0,
        )
    )
    existing_result = await self.db.execute(existing_names_stmt)
    existing_names: set[tuple[str, str]] = {
        (r.label, r.name) for r in existing_result.fetchall()
    }

    # ... 复制逻辑 ...

    # ❌ 删除 scope_key 相关
    # scope_key = "global:"
    # while (old_node.label, new_name, scope_key) in existing_names:
    #     ...

    # ✅ 改为只检查 (label, name)
    while (old_node.label, new_name) in existing_names:
        # ...

    existing_names.add((old_node.label, new_name))

    # 创建新节点时
    new_node = GraphNode(
        # ...
        # ❌ 删除这一行
        # scope_key=scope_key,
    )
```

#### 2.2.4 修改导入脚本

**文件**: `raap-service-keyword-corpus/scripts/import_xiaohongshu_data.py`

```python
# ❌ 删除这一行
# scope_key="global:",

new_node = GraphNode(
    tenant_code=tenant_code,
    label=label,
    name=name,
    description=description,
    properties=properties,
    corpus=corpus_list,
    # scope_key 已删除
    is_active=1,
    is_deleted=0,
)
```

---

## 三、迁移脚本

### 3.1 数据库迁移脚本

**文件**: `raap-service-keyword-corpus/scripts/migrations/remove_scope_key.sql`

```sql
-- ============================================
-- 移除 scope_key 字段迁移脚本
-- 版本: v1.0
-- 创建时间: 2025-01-07
-- ============================================

-- ⚠️ 执行前请备份数据库！

-- Step 1: 检查当前数据分布
SELECT
    scope_key,
    COUNT(*) as count
FROM nodes
WHERE is_deleted = 0
GROUP BY scope_key;

-- 预期结果：所有记录的 scope_key 都是 "global:"

-- Step 2: 删除旧索引
DROP INDEX idx_scope_key ON nodes;

-- Step 3: 删除旧唯一约束
ALTER TABLE nodes DROP INDEX uk_tenant_label_name_scope;

-- Step 4: 创建新的唯一约束（不包含 scope_key）
ALTER TABLE nodes
ADD UNIQUE INDEX uk_tenant_label_name (tenant_code, label, name, is_deleted);

-- Step 5: 验证约束是否生效
-- 尝试插入重复数据（应该失败）
-- INSERT INTO nodes (tenant_code, label, name, is_deleted) VALUES ('default', '人设', '测试', 0);

-- Step 6: （可选）删除字段
-- ⚠️ 建议先观察一段时间，确认无问题后再执行
-- ALTER TABLE nodes DROP COLUMN scope_key;
```

### 3.2 回滚脚本

**文件**: `raap-service-keyword-corpus/scripts/migrations/rollback_remove_scope_key.sql`

```sql
-- ============================================
-- 回滚脚本：恢复 scope_key 字段
-- ⚠️ 仅在移除字段前有效！
-- ============================================

-- Step 1: 删除新的唯一约束
ALTER TABLE nodes DROP INDEX uk_tenant_label_name;

-- Step 2: 恢复旧索引
CREATE INDEX idx_scope_key ON nodes (scope_key);

-- Step 3: 恢复旧唯一约束
ALTER TABLE nodes
ADD UNIQUE INDEX uk_tenant_label_name_scope (tenant_code, label, name, scope_key, is_deleted);

-- Step 4: 恢复字段（如果已删除）
-- ALTER TABLE nodes ADD COLUMN scope_key VARCHAR(255) NOT NULL DEFAULT 'global:' COMMENT 'Scope 唯一键';
```

---

## 四、实施计划

### 4.1 阶段划分

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| **Phase 1** | 代码变更（删除 scope_key 使用） | P0 |
| **Phase 2** | 数据库迁移脚本开发 | P0 |
| **Phase 3** | 测试环境验证 | P0 |
| **Phase 4** | 生产环境执行（分两步） | P1 |
| **Phase 5** | 观察期（1-2周） | P1 |
| **Phase 6** | 删除字段（可选） | P2 |

### 4.2 详细步骤

#### Phase 1: 代码变更
- [ ] 修改 `GraphNode` 模型（保留字段，标记为 deprecated）
- [ ] 修改 `metadata_service.py` 统计逻辑
- [ ] 修改 `category_service.py` 节点复制逻辑
- [ ] 修改导入脚本
- [ ] 单元测试

#### Phase 2: 数据库迁移
- [ ] 编写迁移脚本
- [ ] 编写回滚脚本
- [ ] 在测试环境执行

#### Phase 3: 测试验证
- [ ] 运行单元测试
- [ ] 运行集成测试
- [ ] 手动测试节点创建、复制、查询

#### Phase 4: 生产环境（分两步）
- [ ] Step 1: 执行索引迁移（保留字段）
- [ ] Step 2: 观察 1-2 周，确认无问题

#### Phase 5: 清理工作
- [ ] 删除字段（可选）
- [ ] 更新 API 文档
- [ ] 更新数据库设计文档

---

## 五、风险评估

### 5.1 风险识别

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| **唯一约束冲突** | 高 | 低 | 执行前检查数据，如有冲突先清理 |
| **统计功能失效** | 低 | 低 | 已修改统计逻辑，改为统计全部 |
| **性能下降** | 低 | 低 | 减少索引反而提升性能 |
| **回滚困难** | 中 | 低 | 保留回滚脚本，分阶段执行 |

### 5.2 数据验证

执行前运行以下 SQL 验证：

```sql
-- 1. 检查是否有重复数据（相同 tenant_code + label + name）
SELECT tenant_code, label, name, COUNT(*) as count
FROM nodes
WHERE is_deleted = 0
GROUP BY tenant_code, label, name
HAVING COUNT(*) > 1;

-- 预期结果：空（无重复）

-- 2. 检查 scope_key 分布
SELECT scope_key, COUNT(*) as count
FROM nodes
WHERE is_deleted = 0
GROUP BY scope_key;

-- 预期结果：只有 "global:" 这一种值

-- 3. 检查是否有 NULL 值
SELECT COUNT(*) FROM nodes WHERE scope_key IS NULL;

-- 预期结果：0
```

---

## 六、总结

### 6.1 移除优势

1. ✅ **简化模型**：减少无意义字段
2. ✅ **提升性能**：减少索引数量
3. ✅ **降低维护成本**：减少代码复杂度
4. ✅ **数据一致性**：避免字段冗余

### 6.2 注意事项

1. ⚠️ **分阶段执行**：先改代码，再迁移数据库，最后删除字段
2. ⚠️ **充分测试**：在测试环境完整验证
3. ⚠️ **准备回滚**：保留回滚脚本
4. ⚠️ **数据备份**：执行前必须备份数据库

### 6.3 后续优化

移除 `scope_key` 后，可以考虑：
1. 重新评估其他字段的使用情况
2. 清理 `properties` 字段中的冗余数据
3. 优化其他索引

---

**文档维护**：本文档随着实施进展持续更新。
