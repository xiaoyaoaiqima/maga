import type { Recordable, UserInfo } from '@vben/types';

import { ref } from 'vue';
import { useRouter } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';
import { resetAllStores, useAccessStore, useUserStore } from '@vben/stores';
import { resetStaticRoutes } from '@vben/utils';

import { notification } from 'ant-design-vue';
import { defineStore } from 'pinia';

import {
  getAccessCodesApi,
  getSystemInfoApi,
  getUserInfoApi,
  loginApi,
  logoutApi,
} from '#/api';
import { $t } from '#/locales';
import { routes as staticRoutes } from '#/router/routes';

/**
 * 带重试的异步函数执行（用于登录后首次 API 调用）
 */
async function withRetry<T>(
  fn: () => Promise<T>,
  retries: number = 2,
  delay: number = 300,
): Promise<T> {
  let lastError: unknown;
  for (let i = 0; i <= retries; i++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (i < retries) {
        console.warn(
          `[auth.ts] 请求失败，${delay}ms 后重试 (${i + 1}/${retries})...`,
        );
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
  }
  throw lastError;
}

export const useAuthStore = defineStore('auth', () => {
  const accessStore = useAccessStore();
  const userStore = useUserStore();
  const router = useRouter();

  const loginLoading = ref(false);
  const appEnv = ref<string>('production');

  /**
   * 异步处理登录操作
   * Asynchronously handle the login process
   * @param params 登录表单数据
   */
  async function authLogin(
    params: Recordable<any>,
    onSuccess?: () => Promise<void> | void,
  ) {
    // 异步处理用户登录操作并获取 accessToken
    let userInfo: null | UserInfo = null;
    try {
      loginLoading.value = true;

      // 在登录前确保清除旧的状态，避免旧的 401 响应干扰新的登录流程
      accessStore.setAccessToken(null);
      accessStore.setIsAccessChecked(false);
      userStore.setUserInfo(null);

      // 短暂延迟确保状态已清除
      await new Promise((resolve) => setTimeout(resolve, 50));

      // 获取用户配置的 token 过期时间，传递给后端
      const tokenExpireMinutes = accessStore.tokenExpiryMinutes;
      const { accessToken } = await loginApi({
        ...params,
        token_expire_minutes: tokenExpireMinutes,
      } as any);

      // 如果成功获取到 accessToken
      if (accessToken) {
        accessStore.setAccessToken(accessToken);
        // 设置 token 过期时间（基于用户配置的过期分钟数）
        accessStore.updateTokenExpiresAt();

        // 短暂延迟，确保 token 已被设置到请求头并同步
        await new Promise((resolve) => setTimeout(resolve, 100));

        // 获取用户信息并存储到 accessStore 中（带重试机制，避免首次请求失败）
        const [fetchUserInfoResult, accessCodes, systemInfo] = await withRetry(
          () =>
            Promise.all([
              fetchUserInfo(),
              getAccessCodesApi(),
              getSystemInfoApi(),
            ]),
          3, // 最多重试 3 次
          500, // 每次重试间隔 500ms
        );

        userInfo = fetchUserInfoResult;

        userStore.setUserInfo(userInfo);
        accessStore.setAccessCodes(accessCodes);
        if (systemInfo?.app_env) {
          appEnv.value = systemInfo.app_env;
        }

        if (accessStore.loginExpired) {
          accessStore.setLoginExpired(false);
        } else {
          onSuccess
            ? await onSuccess?.()
            : await router.push(
                userInfo.homePath || preferences.app.defaultHomePath,
              );
        }

        if (userInfo?.realName) {
          notification.success({
            description: `${$t('authentication.loginSuccessDesc')}:${userInfo?.realName}`,
            duration: 3,
            message: $t('authentication.loginSuccess'),
          });
        }
      }
    } catch (error: unknown) {
      // 处理登录失败
      console.error('Login failed:', error);
      // 从错误响应中提取错误信息
      const err = error as {
        message?: string;
        response?: { data?: { detail?: string; message?: string } };
      };
      const errorMessage =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message ||
        '登录失败，请检查用户名和密码';

      // 使用 notification 显示错误（更可靠）
      notification.error({
        message: '登录失败',
        description: errorMessage,
        duration: 4,
      });
    } finally {
      loginLoading.value = false;
    }

    return {
      userInfo,
    };
  }

  async function logout(redirect: boolean = true) {
    try {
      await logoutApi();
    } catch {
      // 不做任何处理
    }
    // 重置路由，避免退出后重登时重复动态路由导致异常
    resetStaticRoutes(router, staticRoutes);
    resetAllStores();
    accessStore.setLoginExpired(false);

    // 回登录页带上当前路由地址
    await router.replace({
      path: LOGIN_PATH,
      query: redirect
        ? {
            redirect: encodeURIComponent(router.currentRoute.value.fullPath),
          }
        : {},
    });
  }

  async function fetchUserInfo() {
    let userInfo: null | UserInfo = null;
    userInfo = await getUserInfoApi();
    userStore.setUserInfo(userInfo);
    return userInfo;
  }

  async function fetchSystemInfo() {
    try {
      const systemInfo = await getSystemInfoApi();
      if (systemInfo?.app_env) {
        appEnv.value = systemInfo.app_env;
      }
    } catch (error) {
      console.error('Failed to fetch system info:', error);
    }
  }

  function $reset() {
    loginLoading.value = false;
  }

  return {
    $reset,
    appEnv,
    authLogin,
    fetchUserInfo,
    fetchSystemInfo,
    loginLoading,
    logout,
  };
});
