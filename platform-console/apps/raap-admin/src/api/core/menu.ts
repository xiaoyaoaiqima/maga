import type { RouteRecordStringComponent } from '@vben/types';

import { requestClient } from '#/api/request';

export namespace MenuApi {
  /** 菜单项 */
  export interface MenuItem {
    id: string;
    parent_id: string;
    menu_name: string;
    menu_type: string;
    path?: string;
    component?: string;
    icon?: string;
    perm_code?: string;
    sort_order: number;
    visible: number;
    children?: MenuItem[];
  }

  /** API 响应包装 */
  export interface ApiResponse<T> {
    code: number;
    message: string;
    data: T;
  }
}

function collect_menu_paths(menus: MenuApi.MenuItem[]): Map<string, number> {
  const path_count = new Map<string, number>();

  const walk = (items: MenuApi.MenuItem[]) => {
    for (const item of items) {
      const path = item.path?.trim();
      if (path) {
        path_count.set(path, (path_count.get(path) ?? 0) + 1);
      }
      if (item.children?.length) {
        walk(item.children);
      }
    }
  };

  walk(menus);
  return path_count;
}

type transform_context = {
  /** route.name 的基础名计数器，用于生成稳定的 __n 后缀 */
  baseNameCounter: Map<string, number>;
  /** 已使用的 route.name，保证全局唯一 */
  usedNames: Set<string>;
};

function get_route_base_name(menu: MenuApi.MenuItem): string {
  // 后端一般保证 id 存在；兜底使用 path/menu_name，避免 name 为空
  return menu.id || menu.path || menu.menu_name || 'menu';
}

function make_unique_route_name(
  baseName: string,
  ancestorNames: Set<string>,
  ctx: transform_context,
): string {
  if (!ancestorNames.has(baseName) && !ctx.usedNames.has(baseName)) {
    ctx.usedNames.add(baseName);
    return baseName;
  }

  let n = (ctx.baseNameCounter.get(baseName) ?? 0) + 1;
  while (true) {
    const candidate = `${baseName}__${n}`;
    if (!ancestorNames.has(candidate) && !ctx.usedNames.has(candidate)) {
      ctx.baseNameCounter.set(baseName, n);
      ctx.usedNames.add(candidate);
      return candidate;
    }
    n++;
  }
}

/**
 * 转换菜单数据为路由格式
 *
 * 注意：
 * - 对于目录类型（menu_type = 'M'）的菜单，不设置 component，框架会自动处理
 * - 空字符串 '' 会触发组件查找逻辑，导致找不到匹配组件而显示 404
 */
function transformMenuToRoute(
  menu: MenuApi.MenuItem,
  ancestorNames: Set<string>,
  ctx: transform_context,
): RouteRecordStringComponent {
  const baseName = get_route_base_name(menu);
  const routeName = make_unique_route_name(baseName, ancestorNames, ctx);
  const nextAncestors = new Set(ancestorNames);
  nextAncestors.add(routeName);

  const route: RouteRecordStringComponent = {
    name: routeName,
    path: menu.path || '',
    component: '', // 临时占位，下面会根据实际情况处理
    meta: {
      title: menu.menu_name,
      icon: menu.icon,
      order: menu.sort_order,
      hideInMenu: menu.visible === 0,
      fullPathKey: false, // 使用 path 而不是 fullPath 作为 tab key，避免查询参数不同导致重复创建 tab
    },
  };

  // 重要：只有当 menu.component 有实际值时才设置 component
  // 如果为空/null/undefined，删除 component 属性让框架自动处理
  if (menu.component) {
    if (
      ['BasicLayout', 'IFrame', 'IFrameView', 'LAYOUT'].includes(menu.component)
    ) {
      route.component = menu.component;
    } else {
      // 路径标准化：确保匹配 import.meta.glob('../views/**/*.vue') 的 key
      // 1. 去除开头的 /
      let comp = menu.component.startsWith('/')
        ? menu.component.slice(1)
        : menu.component;
      // 2. 去除结尾的 .vue (如果后端传了)
      if (comp.endsWith('.vue')) {
        comp = comp.slice(0, -4);
      }
      // 3. 拼接标准前缀和后缀
      route.component = `../views/${comp}.vue`;
    }
  } else {
    // 删除空的 component 属性，避免空字符串触发组件查找逻辑
    delete (route as { component?: string }).component;
  }

  if (menu.children && menu.children.length > 0) {
    route.children = menu.children.map((child) =>
      transformMenuToRoute(child, nextAncestors, ctx),
    );

    // 目录默认落到第一个子菜单（避免目录 path 没有页面导致点击后 404）
    if (menu.menu_type === 'M') {
      const first_child_path = menu.children.find((c) => !!c.path)?.path;
      if (first_child_path && first_child_path !== route.path) {
        route.redirect = first_child_path;
      }
    }
  }

  return route;
}

/**
 * 获取用户所有菜单
 *
 * 注意：requestClient 配置了两层拦截器：
 * 1. responseReturn: 'data' - 返回 axios response 的 data（即后端返回的 JSON body）
 * 2. defaultResponseInterceptor({ dataField: 'data' }) - 从 JSON body 中提取 data 字段
 *
 * 所以最终返回的直接就是 MenuItem[]，不是 { code, message, data }
 */
export async function getAllMenusApi() {
  // 直接获取菜单数组（拦截器已经提取了 data 字段）
  const menus = await requestClient.get<MenuApi.MenuItem[]>('/v1/auth/menus');

  // 确保 menus 是数组
  const menuArray = Array.isArray(menus) ? menus : [];

  // 防御：检测重复 path（重复会导致路由冲突/覆盖）
  const path_count = collect_menu_paths(menuArray);
  const duplicated_paths = [...path_count.entries()]
    .filter(([, count]) => count > 1)
    .map(([path]) => path);
  if (duplicated_paths.length > 0) {
    console.error('[菜单配置错误] 检测到重复路由 path：', duplicated_paths);
  }

  // 转换菜单数据为路由格式
  const ctx: transform_context = {
    usedNames: new Set<string>(),
    baseNameCounter: new Map<string, number>(),
  };

  return menuArray.map((menu) => transformMenuToRoute(menu, new Set(), ctx));
}
