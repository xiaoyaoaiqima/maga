import type { Router } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';
import { resetAllStores, useAccessStore, useUserStore } from '@vben/stores';
import { resetStaticRoutes, startProgress, stopProgress } from '@vben/utils';

import { message } from 'ant-design-vue';

import {
  accessRoutes,
  coreRouteNames,
  routes as staticRoutes,
} from '#/router/routes';
import { useAuthStore } from '#/store';

import { generateAccess } from './access';

function safe_decode_uri_component(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function is_cancelled_request(error: any): boolean {
  const code = error?.code as string | undefined;
  const name = error?.name as string | undefined;
  const msg = String(error?.message ?? '');
  // Axios v1 cancellation (also covers AbortController-based cancellations surfaced by axios)
  return (
    code === 'ERR_CANCELED' ||
    name === 'CanceledError' ||
    msg.toLowerCase().includes('canceled') ||
    msg.toLowerCase().includes('cancelled')
  );
}

function is_backend_unreachable(error: any): boolean {
  // Never treat cancellations as “backend unreachable”
  if (is_cancelled_request(error)) return false;

  const status = error?.response?.status as number | undefined;
  // Gateway/backends truly failing
  if (typeof status === 'number' && status >= 500) return true;

  const code = error?.code as string | undefined;
  // Network/connectivity errors (axios / browser / node)
  if (
    code &&
    [
      'ECONNABORTED',
      'ECONNREFUSED',
      'EHOSTUNREACH',
      'ENETUNREACH',
      'ENOTFOUND',
      'ERR_NETWORK',
      'ETIMEDOUT',
    ].includes(code)
  ) {
    return true;
  }

  const msg = String(error?.message ?? '');
  if (
    /Network Error/i.test(msg) ||
    /Failed to fetch/i.test(msg) ||
    /timeout/i.test(msg)
  ) {
    return true;
  }

  // Only consider “no response” as unreachable for axios-like errors,
  // not for plain JS runtime errors (e.g. duplicate routes).
  const isAxiosLike = Boolean(
    error?.isAxiosError || error?.name === 'AxiosError' || error?.config,
  );
  if (isAxiosLike && error?.request && !error?.response) return true;

  return false;
}

function has_route_authority(
  authority: string[] | undefined,
  roles: string[] | undefined,
): boolean {
  if (!authority?.length) return true;
  return (roles || []).some((role) => authority.includes(role));
}

/**
 * 通用守卫配置
 * @param router
 */
function setupCommonGuard(router: Router) {
  // 记录已经加载的页面
  const loadedPaths = new Set<string>();

  router.beforeEach((to) => {
    to.meta.loaded = loadedPaths.has(to.path);

    // 页面加载进度条
    if (!to.meta.loaded && preferences.transition.progress) {
      startProgress();
    }
    return true;
  });

  router.afterEach((to) => {
    // 记录页面是否加载,如果已经加载，后续的页面切换动画等效果不在重复执行

    loadedPaths.add(to.path);

    // 关闭页面加载进度条
    if (preferences.transition.progress) {
      stopProgress();
    }
  });
}

/**
 * 权限访问守卫配置
 * @param router
 */
function setupAccessGuard(router: Router) {
  router.beforeEach(async (to, from) => {
    const accessStore = useAccessStore();
    const userStore = useUserStore();
    const authStore = useAuthStore();

    // 基本路由，这些路由不需要进入权限拦截
    if (coreRouteNames.includes(to.name as string)) {
      if (to.path === LOGIN_PATH && accessStore.accessToken) {
        const redirect = to.query?.redirect as string | undefined;
        if (redirect) {
          return safe_decode_uri_component(redirect);
        }
        return userStore.userInfo?.homePath || preferences.app.defaultHomePath;
      }
      // 已登录但未生成权限时，让流程继续以加载菜单/路由
      if (accessStore.accessToken && !accessStore.isAccessChecked) {
        // fall through
      } else {
        return true;
      }
    }

    // accessToken 检查
    if (!accessStore.accessToken) {
      // 明确声明忽略权限访问权限，则可以访问
      if (to.meta.ignoreAccess) {
        return true;
      }

      // 没有访问权限，跳转登录页面
      if (to.fullPath !== LOGIN_PATH) {
        return {
          path: LOGIN_PATH,
          // 如不需要，直接删除 query
          query:
            to.fullPath === preferences.app.defaultHomePath
              ? {}
              : { redirect: encodeURIComponent(to.fullPath) },
          // 携带当前跳转的页面，登录后重新跳转该页面
          replace: true,
        };
      }
      return to;
    }

    // 路由层二次校验，避免通过直接输入 URL 绕过侧栏菜单的 admin 可见性限制。
    if (
      accessStore.isAccessChecked &&
      !has_route_authority(to.meta.authority, userStore.userInfo?.roles)
    ) {
      message.warning('当前账号无权访问该页面');
      return {
        path: preferences.app.defaultHomePath,
        replace: true,
      };
    }

    // 是否已经生成过动态路由。MAGA 菜单由前端路由生成，若持久化状态里菜单为空，
    // 必须重新生成，否则侧栏会渲染成空白。
    if (accessStore.isAccessChecked && accessStore.accessMenus.length > 0) {
      return true;
    }
    if (accessStore.isAccessChecked && accessStore.accessMenus.length === 0) {
      accessStore.setIsAccessChecked(false);
    }

    // 生成路由表
    // 当前登录用户拥有的角色标识列表
    try {
      const [userInfo] = await Promise.all([
        userStore.userInfo || authStore.fetchUserInfo(),
        authStore.fetchSystemInfo(),
      ]);
      const userRoles = userInfo.roles ?? [];

      if (!has_route_authority(to.meta.authority, userRoles)) {
        message.warning('当前账号无权访问该页面');
        return {
          path: preferences.app.defaultHomePath,
          replace: true,
        };
      }

      // 生成菜单和路由
      const { accessibleMenus, accessibleRoutes } = await generateAccess({
        roles: userRoles,
        router,
        // 则会在菜单中显示，但是访问会被重定向到403
        routes: accessRoutes,
      });

      // 保存菜单信息和路由信息
      accessStore.setAccessMenus(accessibleMenus);
      accessStore.setAccessRoutes(accessibleRoutes);
      accessStore.setIsAccessChecked(true);
      const fromRedirect = from.query.redirect as string | undefined;
      const redirectPath = fromRedirect
        ? safe_decode_uri_component(fromRedirect)
        : ((to.path === preferences.app.defaultHomePath
            ? userInfo.homePath || preferences.app.defaultHomePath
            : to.fullPath) as string);

      return {
        ...router.resolve(redirectPath),
        replace: true,
      };
    } catch (error: any) {
      console.error('[菜单加载失败]', error);
      accessStore.setIsAccessChecked(false);

      // Navigation changes during logout/login can cancel in-flight requests.
      // In that case, do NOT toast “backend unreachable” or reset auth state.
      if (is_cancelled_request(error)) {
        return true;
      }

      if (is_backend_unreachable(error)) {
        message.error(
          '后端不可达：请确认 MAGA Platform Server 已启动，并且 5100 端口可访问',
        );
      } else if (error instanceof URIError) {
        message.error(
          '路由重定向参数解析失败：请清空地址栏 redirect 参数后重试',
        );
      } else {
        message.warning('加载菜单失败，请重新登录或稍后重试');
      }

      // 清理 token，避免死循环重试
      // 同时重置路由，避免登出/重登后重复动态路由导致的异常
      resetStaticRoutes(router, staticRoutes);
      resetAllStores();
      return {
        path: LOGIN_PATH,
        replace: true,
      };
    }
  });
}

/**
 * 项目守卫配置
 * @param router
 */
function createRouterGuard(router: Router) {
  /** 通用 */
  setupCommonGuard(router);
  /** 权限访问 */
  setupAccessGuard(router);
}

export { createRouterGuard };
