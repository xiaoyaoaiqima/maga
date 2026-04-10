# 修复关键词页面菜单缺失问题

## 问题描述

前端看不到"关键词管理"子菜单，后端返回的菜单数据中只有父菜单"关键词和语料系统"，没有子菜单。

## 问题分析

从后端返回的数据看：
- ✅ 父菜单存在：`440ae105-7424-4962-b4a7-7056cfad33d1`（关键词和语料系统）
- ❌ 子菜单缺失：`820734bf-474b-4fc9-98b4-1228d8f3f74e`（关键词管理）

**可能原因**：
1. 子菜单没有被分配给当前用户角色
2. 子菜单在数据库中被删除或状态异常
3. 子菜单的 `visible` 或 `status` 被设置为 0

## 解决方案

### 方案 1：检查并分配子菜单给角色（推荐）

#### 步骤 1：检查子菜单是否存在

```bash
# 查询子菜单
curl -X GET "http://localhost:30080/api/v1/system/menus/820734bf-474b-4fc9-98b4-1228d8f3f74e" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### 步骤 2：检查角色菜单关联

```bash
# 查询 role-admin 角色的所有菜单
curl -X GET "http://localhost:30080/api/v1/system/roles/role-admin/menus" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### 步骤 3：如果子菜单不在角色中，添加它

```bash
# 获取当前角色的菜单列表（先查询）
# 然后添加子菜单 ID 到 menu_ids 数组
curl -X PUT "http://localhost:30080/api/v1/system/roles/role-admin/menus" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "menu_ids": [
      "已有菜单ID1",
      "已有菜单ID2",
      "820734bf-474b-4fc9-98b4-1228d8f3f74e"  # 添加子菜单ID
    ]
  }'
```

### 方案 2：重新创建子菜单（如果子菜单不存在）

如果子菜单不存在，需要重新创建：

```bash
# 创建子菜单
curl -X POST "http://localhost:30080/api/v1/system/menus" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "menu_name": "关键词管理",
    "menu_type": "C",
    "parent_id": "440ae105-7424-4962-b4a7-7056cfad33d1",
    "path": "/keyword_corpus/list",
    "component": "keyword_corpus/list/index",
    "icon": "lucide:list-minus",
    "perm_code": "keyword_corpus:list",
    "sort_order": 1,
    "visible": 1,
    "status": 1
  }'
```

**注意**：创建后需要将新菜单 ID 添加到角色权限中。

### 方案 3：直接使用 SQL 修复（如果 API 不可用）

如果 API 不可用，可以直接在数据库中修复：

```sql
-- 1. 检查子菜单是否存在
SELECT * FROM sys_menu WHERE id = '820734bf-474b-4fc9-98b4-1228d8f3f74e';

-- 2. 检查角色菜单关联
SELECT * FROM sys_role_menu 
WHERE role_id = 'role-admin' 
  AND menu_id = '820734bf-474b-4fc9-98b4-1228d8f3f74e';

-- 3. 如果关联不存在，添加它
INSERT INTO sys_role_menu (id, role_id, menu_id, created_at)
VALUES (
  UUID(),
  'role-admin',
  '820734bf-474b-4fc9-98b4-1228d8f3f74e',
  NOW()
);

-- 4. 确保子菜单状态正常
UPDATE sys_menu 
SET visible = 1, status = 1, is_deleted = 0
WHERE id = '820734bf-474b-4fc9-98b4-1228d8f3f74e';
```

## 验证步骤

修复后，验证菜单是否正常显示：

1. **刷新前端页面**，检查菜单是否出现
2. **检查后端 API 返回**：
   ```bash
   curl -X GET "http://localhost:30080/api/v1/auth/menus" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```
   应该能看到子菜单在父菜单的 `children` 数组中

3. **直接访问页面**：
   ```
   http://localhost:3100/keyword_corpus/list
   ```

## 预期结果

修复后，后端应该返回类似这样的数据结构：

```json
{
  "menu_name": "关键词和语料系统",
  "menu_type": "M",
  "path": "/keyword_corpus",
  "children": [
    {
      "menu_name": "关键词管理",
      "menu_type": "C",
      "path": "/keyword_corpus/list",
      "component": "keyword_corpus/list/index",
      "icon": "lucide:list-minus",
      "perm_code": "keyword_corpus:list"
    }
  ]
}
```

## 常见问题

### Q: 为什么父菜单显示，但子菜单不显示？

A: 因为菜单权限是独立的。即使父菜单有权限，子菜单也需要单独分配权限。

### Q: 如何批量检查所有菜单的权限分配？

A: 可以查询角色菜单关联表：
```sql
SELECT rm.role_id, rm.menu_id, m.menu_name, m.parent_id
FROM sys_role_menu rm
JOIN sys_menu m ON rm.menu_id = m.id
WHERE rm.role_id = 'role-admin'
ORDER BY m.sort_order;
```

---

*文档创建时间：2025-12-11*

