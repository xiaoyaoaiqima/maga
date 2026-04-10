# scope_key 移除 - 前端测试指南

> **创建时间**: 2025-01-07
> **目的**: 指导前端测试 scope_key 移除后的功能是否正常

---

## 一、测试环境

### 1.1 前端地址
- **本地开发**: http://localhost:3101
- **登录凭据**:
  - 用户名: `buka`
  - 密码: `buka123`

### 1.2 后端服务
- **APISIX Gateway**: http://localhost:30080 (已通过 port-forward 暴露)
- **Orchestrator**: K8s Pod 运行中
- **keyword-corpus**: K8s Pod 运行中

---

## 二、测试重点功能

### 2.1 元数据统计（验证 scope_key 移除后的统计逻辑）

**路径**: 关键词语料 → 元数据管理 → 统计信息

**验证点**:
1. ✅ 统计 API 调用成功（不返回 500 错误）
2. ✅ 显示正确的语料数量
3. ✅ 品牌语料数量为 0（已废弃字段）
4. ✅ 产品语料数量为 0（已废弃字段）
5. ✅ 全局语料数量正确

**API 端点**: `GET /api/v1/keyword-corpus/metadata/stats?tenant_code=default`

**预期响应**:
```json
{
  "code": 200,
  "data": {
    "brand_count": 1,
    "product_count": 2,
    "tag_group_count": 5,
    "tag_count": 10,
    "global_corpus_count": 150,  // 实际语料总数
    "brand_corpus_count": 0,       // ⚠️ 已废弃，返回 0
    "product_corpus_count": 0      // ⚠️ 已废弃，返回 0
  }
}
```

### 2.2 节点复制功能（验证唯一性约束变更）

**路径**: 关键词语料 → 分类树管理 → 选择节点 → 复制

**验证点**:
1. ✅ 复制节点成功
2. ✅ 名称冲突检测正确（只检查 label + name）
3. ✅ 复制的节点 scope_key 为 "global:"（默认值）
4. ✅ 多次复制同一个节点，名称自动加后缀（_副本, _副本2, ...）

**测试步骤**:
1. 选择一个节点（如"人设"分类下的某个节点）
2. 点击"复制"按钮
3. 检查复制后的节点名称是否正确
4. 重复复制，验证名称冲突处理

### 2.3 节点创建功能（验证不显式设置 scope_key）

**路径**: 关键词语料 → 分类树管理 → 新增节点

**验证点**:
1. ✅ 创建节点成功
2. ✅ 新节点自动使用 scope_key 默认值 "global:"
3. ✅ 相同 label + name 的节点会被唯一约束阻止

**测试步骤**:
1. 在某个分类下新增节点
2. 设置名称和属性
3. 保存后查看节点详情
4. 尝试创建同名节点（应该失败）

---

## 三、测试用例

### 用例 1: 元数据统计显示

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 登录系统 | 登录成功 |
| 2 | 进入"关键词语料"→"元数据管理" | 显示元数据列表 |
| 3 | 查看统计信息卡片 | 显示统计数据 |
| 4 | 检查"全局语料"数量 | 数量 > 0 |
| 5 | 检查"品牌语料"数量 | 数量 = 0 |
| 6 | 检查"产品语料"数量 | 数量 = 0 |

### 用例 2: 节点复制名称冲突

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 选择节点 A（名称："测试节点"） | 选中成功 |
| 2 | 点击"复制"按钮 | 复制成功 |
| 3 | 检查新节点名称 | "测试节点_副本" |
| 4 | 再次复制节点 A | 复制成功 |
| 5 | 检查新节点名称 | "测试节点_副本2" |

### 用例 3: 相同名称节点创建失败

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 进入"分类树管理" | 显示分类树 |
| 2 | 选择某个分类 | 选中成功 |
| 3 | 点击"新增节点" | 打开新增对话框 |
| 4 | 输入名称"测试节点"（已存在） | - |
| 5 | 点击"确定" | 提示"节点名称已存在" |

---

## 四、问题排查

### 4.1 统计 API 返回 500 错误

**可能原因**:
- 代码修改后 Pod 未重新加载
- properties 字段查询语法错误

**排查方法**:
```bash
# 查看 keyword-corpus 服务日志
kubectl logs -n raap-dev deployment/raap-service-keyword-corpus --tail=100 | grep ERROR

# 检查是否使用了新的查询语法
kubectl logs -n raap-dev deployment/raap-service-keyword-corpus --tail=100 | grep "properties\["
```

**解决方法**:
- 如果使用了 devMode，代码会自动重载
- 如果未使用 devMode，需要重启 Pod：
  ```bash
  kubectl rollout restart deployment/raap-service-keyword-corpus -n raap-dev
  ```

### 4.2 节点创建失败

**可能原因**:
- 唯一约束冲突
- 数据库连接问题

**排查方法**:
```bash
# 检查数据库中是否已存在同名节点
kubectl exec -it -n raap-dev <mysql-pod> -- mysql -u<user> -p<password> -e "
SELECT label, name, COUNT(*) FROM nodes
WHERE tenant_code='default' AND is_deleted=0
GROUP BY label, name HAVING COUNT(*) > 1;"
```

### 4.3 前端无法连接后端

**可能原因**:
- APISIX port-forward 未运行
- Token 过期

**排查方法**:
```bash
# 1. 检查 APISIX port-forward
ps aux | grep "port-forward" | grep "30080"

# 2. 测试 APISIX 连接
curl http://localhost:30080/api/v1/health

# 3. 重新登录获取新 token
curl -X POST 'http://localhost:30080/api/v1/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"username":"buka","password":"buka123"}'
```

---

## 五、测试检查清单

### 功能测试
- [ ] 登录成功
- [ ] 元数据统计显示正常
- [ ] 全局语料数量正确
- [ ] 品牌语料数量为 0（已废弃）
- [ ] 产品语料数量为 0（已废弃）
- [ ] 节点复制功能正常
- [ ] 节点复制名称冲突处理正确
- [ ] 节点创建功能正常
- [ ] 相同名称节点创建被阻止

### 性能测试
- [ ] 统计 API 响应时间 < 1s
- [ ] 节点复制响应时间 < 2s
- [ ] 节点创建响应时间 < 1s

### 兼容性测试
- [ ] 已有节点可正常查询
- [ ] 已有节点可正常编辑
- [ ] 已有节点可正常删除
- [ ] 前端页面无报错

---

## 六、测试结果记录

### 测试日期: ___________

### 测试人员: ___________

### 测试结果:

| 功能 | 通过/失败 | 备注 |
|------|-----------|------|
| 元数据统计 | ⏳ | - |
| 节点复制 | ⏳ | - |
| 节点创建 | ⏳ | - |
| 名称冲突处理 | ⏳ | - |

### 发现的问题:

1. ___________

2. ___________

### 改进建议:

1. ___________

2. ___________

---

## 七、快速测试命令

### 使用 curl 测试（需要 token）

```bash
# 1. 登录获取 token
TOKEN=$(curl -s -X POST 'http://localhost:30080/api/v1/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"username":"buka","password":"buka123"}' \
  | jq -r '.data.token')

# 2. 测试元数据统计 API
curl -s "http://localhost:30080/api/v1/keyword-corpus/metadata/stats?tenant_code=default" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 3. 测试分类树 API
curl -s "http://localhost:30080/api/v1/keyword-corpus/categories/tree?tenant_code=default" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 4. 测试节点查询 API
curl -s "http://localhost:30080/api/v1/keyword-corpus/nodes?tenant_code=default&label=人设&page=1&page_size=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

**文档维护**: 随着测试进展持续更新
