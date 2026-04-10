-- 关键词菜单问题诊断 SQL
-- 执行此 SQL 检查所有可能的问题

-- ============================================
-- 1. 检查子菜单基本信息
-- ============================================
SELECT 
  '子菜单基本信息' AS check_type,
  id,
  menu_name,
  parent_id,
  menu_type,
  path,
  component,
  visible,
  status,
  is_deleted,
  sort_order
FROM sys_menu 
WHERE id = '820734bf-474b-4fc9-98b4-1228d8f3f74e';

-- ============================================
-- 2. 检查父菜单是否存在
-- ============================================
SELECT 
  '父菜单信息' AS check_type,
  id,
  menu_name,
  parent_id,
  menu_type,
  path,
  visible,
  status,
  is_deleted
FROM sys_menu 
WHERE id = '440ae105-7424-4962-b4a7-7056cfad33d1';

-- ============================================
-- 3. 检查角色菜单关联
-- ============================================
SELECT 
  '角色菜单关联' AS check_type,
  rm.id AS relation_id,
  rm.role_id,
  rm.menu_id,
  r.role_code,
  r.role_name,
  m.menu_name
FROM sys_role_menu rm
JOIN sys_role r ON rm.role_id = r.id
JOIN sys_menu m ON rm.menu_id = m.id
WHERE rm.role_id = 'role-admin' 
  AND rm.menu_id = '820734bf-474b-4fc9-98b4-1228d8f3f74e';

-- ============================================
-- 4. 检查 role-admin 角色的所有菜单
-- ============================================
SELECT 
  'role-admin 的所有菜单' AS check_type,
  m.id,
  m.menu_name,
  m.parent_id,
  m.path,
  m.component,
  m.visible,
  m.status,
  m.is_deleted
FROM sys_role_menu rm
JOIN sys_menu m ON rm.menu_id = m.id
WHERE rm.role_id = 'role-admin'
  AND m.is_deleted = 0
  AND m.status = 1
ORDER BY m.sort_order;

-- ============================================
-- 5. 检查关键词相关的所有菜单
-- ============================================
SELECT 
  '关键词相关菜单' AS check_type,
  m.id,
  m.menu_name,
  m.parent_id,
  m.path,
  m.component,
  m.visible,
  m.status,
  m.is_deleted,
  CASE 
    WHEN rm.menu_id IS NOT NULL THEN '已分配'
    ELSE '未分配'
  END AS assigned_to_role_admin
FROM sys_menu m
LEFT JOIN sys_role_menu rm ON m.id = rm.menu_id AND rm.role_id = 'role-admin'
WHERE m.id IN (
  '440ae105-7424-4962-b4a7-7056cfad33d1',  -- 父菜单
  '820734bf-474b-4fc9-98b4-1228d8f3f74e'   -- 子菜单
)
ORDER BY m.parent_id, m.sort_order;

-- ============================================
-- 6. 一键修复（如果发现问题）
-- ============================================
-- 取消下面的注释来执行修复

/*
-- 修复 1: 确保子菜单状态正常
UPDATE sys_menu 
SET 
  visible = 1,
  status = 1,
  is_deleted = 0,
  parent_id = '440ae105-7424-4962-b4a7-7056cfad33d1',
  path = '/keyword_corpus/list',
  component = 'keyword_corpus/list/index',
  menu_name = '关键词管理',
  menu_type = 'C',
  sort_order = 1
WHERE id = '820734bf-474b-4fc9-98b4-1228d8f3f74e';

-- 修复 2: 确保角色菜单关联存在
INSERT INTO sys_role_menu (id, role_id, menu_id, created_at)
SELECT 
  CONCAT('fix-', UUID()) AS id,
  'role-admin' AS role_id,
  '820734bf-474b-4fc9-98b4-1228d8f3f74e' AS menu_id,
  NOW() AS created_at
WHERE NOT EXISTS (
  SELECT 1 FROM sys_role_menu 
  WHERE role_id = 'role-admin' 
    AND menu_id = '820734bf-474b-4fc9-98b4-1228d8f3f74e'
);

-- 修复 3: 确保父菜单状态正常
UPDATE sys_menu 
SET 
  visible = 1,
  status = 1,
  is_deleted = 0
WHERE id = '440ae105-7424-4962-b4a7-7056cfad33d1';
*/

