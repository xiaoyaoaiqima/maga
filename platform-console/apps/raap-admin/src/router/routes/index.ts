import type { RouteRecordRaw } from 'vue-router';

import { traverseTreeValues } from '@vben/utils';

import { coreRoutes, fallbackNotFoundRoute } from './core';
import { frontendTabRoutes } from './frontend-tabs';

const externalRoutes: RouteRecordRaw[] = [];

/** 路由列表，由基本路由、外部路由和404兜底路由组成
 *  无需走权限验证（会一直显示在菜单中） */
const routes: RouteRecordRaw[] = [
  ...coreRoutes,
  ...externalRoutes,
  fallbackNotFoundRoute,
];

/** 有权限校验的路由列表，包含动态路由和静态路由 */
const accessRoutes = frontendTabRoutes;

const accessRouteNames = new Set(
  traverseTreeValues(accessRoutes, (route) => route.name),
);

/** 基本路由列表，这些路由不需要进入权限拦截 */
const coreRouteNames = traverseTreeValues(coreRoutes, (route) => route.name)
  // 前端菜单页虽然也存在于 coreRoutes 供首屏匹配，但必须进入 generateAccess，
  // 否则 accessMenus 不会生成，侧边栏会变成空菜单。
  .filter((name) => !accessRouteNames.has(name));

export { accessRoutes, coreRouteNames, routes };
