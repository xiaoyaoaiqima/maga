-- 添加分类管理菜单
-- 需要确保 keyword_corpus 父菜单存在

-- 1. 查找 keyword_corpus 父菜单 ID
SELECT id, menu_name, path FROM sys_menu WHERE path = '/keyword_corpus' AND is_deleted = 0;

-- 2. 插入分类管理菜单
INSERT INTO sys_menu (
    id,
    parent_id,
    menu_name,
    menu_type,
    path,
    component,
    icon,
    perm_code,
    sort_order,
    visible,
    status,
    is_deleted,
    created_at,
    updated_at
) VALUES (
    UUID(),                                          -- 自动生成 UUID
    (SELECT id FROM (SELECT id FROM sys_menu WHERE path = '/keyword_corpus' AND is_deleted = 0 LIMIT 1) t),  -- 父菜单ID
    '分类管理',                                       -- 菜单名称
    'C',                                             -- 菜单类型（C=菜单）
    '/keyword_corpus/category',                       -- 路由路径
    'keyword_corpus/category/index',                  -- 组件路径
    'FolderOpenOutlined',                            -- 图标
    'keyword_corpus:category',                       -- 权限标识
    1,                                               -- 排序
    1,                                               -- 可见
    1,                                               -- 启用
    0,                                               -- 未删除
    NOW(),
    NOW()
);

-- 3. 将新菜单分配给 admin 角色
INSERT INTO sys_role_menu (role_id, menu_id, created_at)
SELECT 
    'role-admin',
    id,
    NOW()
FROM sys_menu 
WHERE path = '/keyword_corpus/category' AND is_deleted = 0;

-- 验证
SELECT * FROM sys_menu WHERE path LIKE '/keyword_corpus%' AND is_deleted = 0;
SELECT * FROM sys_role_menu WHERE menu_id IN (
    SELECT id FROM sys_menu WHERE path = '/keyword_corpus/category'
);

