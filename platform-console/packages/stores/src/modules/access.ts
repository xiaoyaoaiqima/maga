import type { RouteRecordRaw } from 'vue-router';

import type { MenuRecordRaw } from '@vben-core/typings';

import { acceptHMRUpdate, defineStore } from 'pinia';

type AccessToken = null | string;

/** 默认 token 过期时间（分钟） */
const DEFAULT_TOKEN_EXPIRY_MINUTES = 480; // 8小时

/** localStorage key for token expiry minutes (独立存储，不受 store reset 影响) */
const TOKEN_EXPIRY_STORAGE_KEY = 'vben-token-expiry-minutes';

/**
 * 从 localStorage 获取 token 过期时间配置
 */
function getStoredTokenExpiryMinutes(): number {
  try {
    const stored = localStorage.getItem(TOKEN_EXPIRY_STORAGE_KEY);
    if (stored) {
      const value = Number.parseInt(stored, 10);
      if (!Number.isNaN(value) && value >= 5 && value <= 43_200) {
        return value;
      }
    }
  } catch {
    // ignore
  }
  return DEFAULT_TOKEN_EXPIRY_MINUTES;
}

/**
 * 保存 token 过期时间配置到 localStorage
 */
function saveTokenExpiryMinutes(minutes: number): void {
  try {
    localStorage.setItem(TOKEN_EXPIRY_STORAGE_KEY, String(minutes));
  } catch {
    // ignore
  }
}

interface AccessState {
  /**
   * 权限码
   */
  accessCodes: string[];
  /**
   * 可访问的菜单列表
   */
  accessMenus: MenuRecordRaw[];
  /**
   * 可访问的路由列表
   */
  accessRoutes: RouteRecordRaw[];
  /**
   * 登录 accessToken
   */
  accessToken: AccessToken;
  /**
   * 是否已经检查过权限
   */
  isAccessChecked: boolean;
  /**
   * 是否锁屏状态
   */
  isLockScreen: boolean;
  /**
   * 锁屏密码
   */
  lockScreenPassword?: string;
  /**
   * 登录是否过期
   */
  loginExpired: boolean;
  /**
   * 登录 accessToken
   */
  refreshToken: AccessToken;
  /**
   * Token 过期时间戳（毫秒）
   */
  tokenExpiresAt: null | number;
  /**
   * Token 过期时间配置（分钟）
   */
  tokenExpiryMinutes: number;
}

/**
 * @zh_CN 访问权限相关
 */
export const useAccessStore = defineStore('core-access', {
  actions: {
    getMenuByPath(path: string) {
      function findMenu(
        menus: MenuRecordRaw[],
        path: string,
      ): MenuRecordRaw | undefined {
        for (const menu of menus) {
          if (menu.path === path) {
            return menu;
          }
          if (menu.children) {
            const matched = findMenu(menu.children, path);
            if (matched) {
              return matched;
            }
          }
        }
      }
      return findMenu(this.accessMenus, path);
    },
    lockScreen(password: string) {
      this.isLockScreen = true;
      this.lockScreenPassword = password;
    },
    setAccessCodes(codes: string[]) {
      this.accessCodes = codes;
    },
    setAccessMenus(menus: MenuRecordRaw[]) {
      this.accessMenus = menus;
    },
    setAccessRoutes(routes: RouteRecordRaw[]) {
      this.accessRoutes = routes;
    },
    setAccessToken(token: AccessToken) {
      this.accessToken = token;
    },
    setIsAccessChecked(isAccessChecked: boolean) {
      this.isAccessChecked = isAccessChecked;
    },
    setLoginExpired(loginExpired: boolean) {
      this.loginExpired = loginExpired;
    },
    setRefreshToken(token: AccessToken) {
      this.refreshToken = token;
    },
    /**
     * 设置 token 过期时间戳
     * @param expiresAt 过期时间戳（毫秒），null 表示清除
     */
    setTokenExpiresAt(expiresAt: null | number) {
      this.tokenExpiresAt = expiresAt;
    },
    /**
     * 设置 token 过期时间配置（分钟）
     * @param minutes 过期时间（分钟）
     */
    setTokenExpiryMinutes(minutes: number) {
      this.tokenExpiryMinutes = minutes;
      // 同时保存到 localStorage，防止 store reset 时丢失
      saveTokenExpiryMinutes(minutes);
    },
    /**
     * 检查 token 是否已过期
     * @returns true 表示已过期
     */
    isTokenExpired(): boolean {
      if (!this.accessToken || !this.tokenExpiresAt) {
        return false;
      }
      return Date.now() >= this.tokenExpiresAt;
    },
    /**
     * 获取 token 剩余有效时间（毫秒）
     * @returns 剩余时间毫秒数，如果已过期返回 0
     */
    getTokenRemainingTime(): number {
      if (!this.tokenExpiresAt) {
        return 0;
      }
      const remaining = this.tokenExpiresAt - Date.now();
      return Math.max(remaining, 0);
    },
    /**
     * 根据配置的过期时间更新 token 过期时间戳
     * 在登录成功后调用
     */
    updateTokenExpiresAt() {
      const expiresAt = Date.now() + this.tokenExpiryMinutes * 60 * 1000;
      this.tokenExpiresAt = expiresAt;
    },
    unlockScreen() {
      this.isLockScreen = false;
      this.lockScreenPassword = undefined;
    },
  },
  persist: {
    // 持久化
    pick: [
      'accessToken',
      'refreshToken',
      'accessCodes',
      'accessMenus', // 持久化菜单数据，避免刷新后侧边栏为空
      // 注意：不持久化 isAccessChecked，让路由守卫每次刷新时重新检查并注册路由
      'isLockScreen',
      'lockScreenPassword',
      'tokenExpiresAt',
      'tokenExpiryMinutes',
    ],
  },
  state: (): AccessState => ({
    accessCodes: [],
    accessMenus: [],
    accessRoutes: [],
    accessToken: null,
    isAccessChecked: false,
    isLockScreen: false,
    lockScreenPassword: undefined,
    loginExpired: false,
    refreshToken: null,
    tokenExpiresAt: null,
    // 从 localStorage 读取，即使 store reset 也不会丢失用户设置
    tokenExpiryMinutes: getStoredTokenExpiryMinutes(),
  }),
});

// 解决热更新问题
const hot = import.meta.hot;
if (hot) {
  hot.accept(acceptHMRUpdate(useAccessStore, hot));
}
