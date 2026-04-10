/**
 * 该文件可自行根据业务逻辑进行调整
 */
import type { RequestClientOptions } from '@vben/request';

import { useAppConfig } from '@vben/hooks';
import { preferences } from '@vben/preferences';
import {
  authenticateResponseInterceptor,
  defaultResponseInterceptor,
  errorMessageResponseInterceptor,
  RequestClient,
} from '@vben/request';
import { resetAllStores, useAccessStore } from '@vben/stores';

import { message } from 'ant-design-vue';

import { logger } from '#/utils/logger';

import { refreshTokenApi } from './core';

const { apiURL } = useAppConfig(import.meta.env, import.meta.env.PROD);

function is_cancelled_request(error: any): boolean {
  const code = error?.code as string | undefined;
  const name = error?.name as string | undefined;
  const msg = String(error?.message ?? '');
  return (
    code === 'ERR_CANCELED' ||
    name === 'CanceledError' ||
    msg.toLowerCase().includes('canceled') ||
    msg.toLowerCase().includes('cancelled')
  );
}

function is_backend_unreachable_error(error: any): boolean {
  if (is_cancelled_request(error)) return false;

  const status = error?.response?.status as number | undefined;
  if (typeof status === 'number' && status >= 500) return true;

  const code = error?.code as string | undefined;
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

  const isAxiosLike = Boolean(
    error?.isAxiosError || error?.name === 'AxiosError' || error?.config,
  );
  if (isAxiosLike && error?.request && !error?.response) return true;

  return false;
}

function createRequestClient(baseURL: string, options?: RequestClientOptions) {
  const client = new RequestClient({
    ...options,
    baseURL,
  });

  /**
   * 重新认证逻辑
   * 注意：
   * 1. 如果当前已在登录页，说明可能是登录请求失败或旧请求的 401 响应，不需要跳转
   *    由 auth store 处理错误提示
   * 2. 不能调用 authStore.logout()，因为 logout 会调用 logoutApi，
   *    如果 logoutApi 也返回 401，会再次触发 doReAuthenticate，导致无限循环
   * 3. 在登录页时不要清除 token，因为可能是新登录成功后的竞态条件：
   *    旧请求的 401 可能会覆盖刚设置的新 token
   */
  async function doReAuthenticate() {
    const accessStore = useAccessStore();
    const currentPath = window.location.href;

    // 如果已经在登录页，说明是登录请求失败或旧请求返回 401
    // 重要：不要设置 accessToken 为 null！因为可能用户刚刚登录成功设置了新 token
    // 让 auth store 的 catch 块来处理错误消息
    if (currentPath.includes('/auth/login') || currentPath.includes('/login')) {
      logger.debug(
        '[doReAuthenticate] 在登录页收到 401，忽略（可能是旧请求的响应）',
      );
      return;
    }

    logger.warn('Access token or refresh token is invalid or expired.');
    accessStore.setAccessToken(null);

    if (
      preferences.app.loginExpiredMode === 'modal' &&
      accessStore.isAccessChecked
    ) {
      accessStore.setLoginExpired(true);
    } else {
      // 直接重置状态，不调用 logout API，避免无限循环
      resetAllStores();
      accessStore.setLoginExpired(false);
      // 跳转到登录页
      const isHash = import.meta.env.VITE_ROUTER_HISTORY === 'hash';
      window.location.href = isHash ? '/#/auth/login' : '/auth/login';
    }
  }

  /**
   * 刷新token逻辑
   */
  async function doRefreshToken() {
    const accessStore = useAccessStore();
    const resp = await refreshTokenApi();
    const newToken = resp.data;
    accessStore.setAccessToken(newToken);
    return newToken;
  }

  function formatToken(token: null | string) {
    return token ? `Bearer ${token}` : null;
  }

  // 请求头处理
  client.addRequestInterceptor({
    fulfilled: async (config) => {
      const accessStore = useAccessStore();

      config.headers.Authorization = formatToken(accessStore.accessToken);
      config.headers['Accept-Language'] = preferences.app.locale;
      return config;
    },
  });

  // 处理返回的响应数据格式
  client.addResponseInterceptor(
    defaultResponseInterceptor({
      codeField: 'code',
      dataField: 'data',
      successCode: 200, // 后端成功码是 200
    }),
  );

  // token过期的处理
  client.addResponseInterceptor(
    authenticateResponseInterceptor({
      client,
      doReAuthenticate,
      doRefreshToken,
      enableRefreshToken: preferences.app.enableRefreshToken,
      formatToken,
    }),
  );

  // 通用的错误处理,如果没有进入上面的错误处理逻辑，就会进入这里
  client.addResponseInterceptor(
    errorMessageResponseInterceptor((msg: string, error) => {
      // 统一错误体：后端已返回 { code, message, data, detail }，优先使用 detail
      const responseData = error?.response?.data ?? {};
      let errorMessage =
        responseData?.detail ??
        responseData?.error ??
        responseData?.message ??
        '';

      // 适配 FastAPI 的 422 错误详情（可能为数组或对象）
      if (typeof errorMessage === 'object' && errorMessage !== null) {
        try {
          errorMessage = JSON.stringify(errorMessage);
        } catch {
          errorMessage = '未知错误详情';
        }
      }

      const url = error?.config?.url as string | undefined;

      // 明确提示"本地未转发/后端不可达"，避免用户看到黑盒 404
      if (
        is_backend_unreachable_error(error) &&
        (url?.includes('/v1/auth/menus') || url?.includes('/v1/auth/userinfo'))
      ) {
        message.error(
          '后端不可达：请确认 MAGA Platform Server 已启动，并且 5100 端口可访问',
        );
        return;
      }

      // 特殊错误处理：策略合并冲突交给业务组件处理（显示更详细的 Modal）
      if (
        errorMessage &&
        (errorMessage.includes('合并模式要求') ||
          errorMessage.includes('不能重叠') ||
          errorMessage.includes('overlap'))
      ) {
        return;
      }

      // 业务校验错误（如名称冲突）使用 warning 提示，更友好
      if (errorMessage && errorMessage.includes('已存在')) {
        message.warning(errorMessage);
        return;
      }

      // 语料模板缺失错误：改为 warning 提示（UI 已有友好提示，不需要 error）
      if (
        errorMessage &&
        errorMessage.includes('未找到分类类型') &&
        errorMessage.includes('的模板') &&
        url?.includes('/corpus-templates/by-category/')
      ) {
        message.warning(errorMessage);
        return;
      }

      // 401：已在 authenticateResponseInterceptor 中执行 doReAuthenticate（跳转登录或登录过期弹窗），
      // 不再用后端 detail 弹 error，避免「报错」形式的重复提示；非登录页时可给一句友好提示
      const status = error?.response?.status;
      if (status === 401) {
        const onLoginPage =
          typeof window !== 'undefined' &&
          (window.location.href.includes('/auth/login') ||
            window.location.href.includes('/login'));
        if (!onLoginPage) {
          message.info('登录已过期，请重新登录');
        }
        return;
      }

      // 如果没有错误信息，则会根据状态码进行提示
      message.error(errorMessage || msg);
    }),
  );

  return client;
}

export const requestClient = createRequestClient(apiURL, {
  responseReturn: 'data',
});

export const baseRequestClient = new RequestClient({ baseURL: apiURL });
