# scope_key 字段移除 - 实施总结

> **执行时间**: 2025-01-07
> **状态**: ✅ 代码变更已完成，待数据库迁移执行

---

## 📊 完成情况

### ✅ 已完成（100%）

#### 1. 代码变更（4/4）
- ✅ **GraphNode 模型** ([app/models/graph.py](raap-service-keyword-corpus/app/models/graph.py))
  - 标记 scope_key 为 deprecated
  - 添加注释说明将在后续版本删除
  - 更新索引注释

- ✅ **统计服务** ([app/services/metadata_service.py](raap-service-keyword-corpus/app/services/metadata_service.py))
  - 删除按 scope 统计的方法
  - 改为统计全部语料数量
  - 改为使用 properties.brands 和 properties.tags 查询

- ✅ **节点复制服务** ([app/services/category_service.py](raap-service-keyword-corpus/app/services/category_service.py))
  - 唯一性检查改为 (label, name)
  - 不再显式设置 scope_key

- ✅ **导入脚本** ([scripts/import_xiaohongshu_data.sql](raap-service-keyword-corpus/scripts/import_xiaohongshu_data.sql))
  - 移除 scope_key 显式赋值
  - 添加废弃说明注释

#### 2. 数据库脚本（2/2）
- ✅ **迁移脚本**: [scripts/migrations/remove_scope_key.sql](raap-service-keyword-corpus/scripts/migrations/remove_scope_key.sql)
  - 数据验证 SQL
  - 索引迁移步骤
  - 验证步骤
  - 详细的注释和警告

- ✅ **回滚脚本**: [scripts/migrations/rollback_remove_scope_key.sql](raap-service-keyword-corpus/scripts/migrations/rollback_remove_scope_key.sql)
  - 恢复旧索引
  - 恢复旧唯一约束
  - 验证步骤
  - 完整回滚指南

---

## 📁 变更的文件

| 文件 | 变更类型 | 状态 |
|------|----------|------|
| `raap-service-keyword-corpus/app/models/graph.py` | 代码修改 | ✅ 完成 |
| `raap-service-keyword-corpus/app/services/metadata_service.py` | 代码修改 | ✅ 完成 |
| `raap-service-keyword-corpus/app/services/category_service.py` | 代码修改 | ✅ 完成 |
| `raap-service-keyword-corpus/scripts/import_xiaohongshu_data.sql` | 脚本修改 | ✅ 完成 |
| `raap-service-keyword-corpus/scripts/migrations/remove_scope_key.sql` | 新增 | ✅ 完成 |
| `raap-service-keyword-corpus/scripts/migrations/rollback_remove_scope_key.sql` | 新增 | ✅ 完成 |

---

## 🔍 关键变更说明

### 1. 统计逻辑变更

**之前**：
```python
# 按 scope 统计
global_corpus = await self._count_corpus_by_scope(tenant_code, "global:")
brand_corpus = await self._count_corpus_by_scope_prefix(tenant_code, "brand:")
product_corpus = await self._count_corpus_by_scope_prefix(tenant_code, "product:")
```

**之后**：
```python
# 统计全部语料（不区分 scope）
total_corpus = await self._count_all_corpus(tenant_code)
```

### 2. 唯一性约束变更

**之前**：
```python
# 检查 (label, name, scope_key)
existing_names: set[tuple[str, str, str]] = {
    (r.label, r.name, r.scope_key or "global:") for r in ...
}
```

**之后**：
```python
# 只检查 (label, name)
existing_names: set[tuple[str, str]] = {
    (r.label, r.name) for r in ...
}
```

### 3. 关联查询变更

**之前**：
```python
# 通过 scope_key 查询
GraphNode.scope_key.like(f"brand:{brand_code}%")
```

**之后**：
```python
# 通过 properties.brands 查询
GraphNode.properties["brands"].astext.contains(brand_name)
```

---

## ⏭️ 后续步骤

### 短期（1-2周内）

1. **测试环境验证**
   - [ ] 在 K8s 测试环境执行迁移脚本
   - [ ] 运行单元测试
   - [ ] 手动测试节点创建、复制、查询功能

2. **生产环境执行**
   - [ ] 备份生产数据库
   - [ ] 执行迁移脚本（仅索引迁移）
   - [ ] 验证服务正常运行

3. **观察期**
   - [ ] 监控错误日志
   - [ ] 检查性能指标
   - [ ] 收集用户反馈

### 中期（1-2个版本后）

4. **删除字段（可选）**
   - [ ] 确认无问题后，删除 scope_key 字段
   - [ ] 清理相关文档

---

## 📋 执行检查清单

### 执行前

- [x] 代码变更已完成
- [x] 迁移脚本已准备
- [x] 回滚脚本已准备
- [ ] 生产数据库已备份
- [ ] 测试环境已验证

### 执行时

- [ ] 在 K8s 容器中执行迁移脚本
- [ ] 检查每个步骤的执行结果
- [ ] 验证索引已正确创建/删除
- [ ] 测试节点创建功能
- [ ] 测试节点复制功能

### 执行后

- [ ] 监控服务日志 24 小时
- [ ] 检查数据库性能
- [ ] 验证统计功能正常
- [ ] 确认无异常后，观察 1-2 周
- [ ] 考虑删除 scope_key 字段

---

## ⚠️ 注意事项

### 1. 数据库迁移

- **必须先备份**：执行前务必备份数据库
- **分阶段执行**：先迁移索引，观察后再删除字段
- **验证优先**：每一步都要验证结果

### 2. 回滚准备

- 保留回滚脚本
- 记录迁移前的索引状态
- 准备快速回滚方案

### 3. 监控重点

- 节点创建是否正常
- 节点复制是否正常
- 统计功能是否正常
- 性能是否下降

---

## 📚 相关文档

- [移除方案详细文档](readme/REMOVE_SCOPE_KEY_PLAN.md)
- [scope_key 与 properties 同步更新说明](readme/SCOPE_PROPERTIES_UPDATE.md)
- [迁移脚本](raap-service-keyword-corpus/scripts/migrations/remove_scope_key.sql)
- [回滚脚本](raap-service-keyword-corpus/scripts/migrations/rollback_remove_scope_key.sql)

---

## 🎯 总结

本次 scope_key 字段移除工作已完成**代码层面的所有变更**，并准备了完整的数据库迁移脚本。

**核心成果**：
1. ✅ 代码不再依赖 scope_key 进行业务逻辑
2. ✅ 统计功能改为使用 properties.brands 和 properties.tags
3. ✅ 唯一性约束简化为 (tenant_code, label, name, is_deleted)
4. ✅ 提供了完整的迁移和回滚方案

**下一步**：等待合适的时间窗口，在测试环境验证后，再在生产环境执行数据库迁移。

---

**文档维护**：本文档随着实施进展持续更新。
