-- 修复关键词菜单 is_deleted 标志
-- 问题：子菜单的 is_deleted=1，导致后端过滤掉该菜单

-- 修复子菜单的 is_deleted 标志
UPDATE sys_menu 
SET is_deleted = 0
WHERE id = '820734bf-474b-4fc9-98b4-1228d8f3f74e';

-- 验证修复结果
SELECT 
  id,
  menu_name,
  parent_id,
  path,
  component,
  visible,
  status,
  is_deleted
FROM sys_menu 
WHERE id = '820734bf-474b-4fc9-98b4-1228d8f3f74e';

-- 预期结果：is_deleted 应该为 0
