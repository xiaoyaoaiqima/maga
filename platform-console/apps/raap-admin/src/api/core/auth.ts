import { requestClient } from '#/api/request';

export namespace AuthApi {
  /** 登录接口参数 */
  export interface LoginParams {
    password: string;
    username: string;
    /** Token 过期时间（分钟），不传则使用后端默认值 */
    token_expire_minutes?: number;
  }

  /** 登录接口返回值 */
  export interface LoginResult {
    id: string;
    username: string;
    name?: string;
    avatar?: string;
    token: string;
    access_token: string;
    expire_time: number;
  }

  /** API 响应包装 */
  export interface ApiResponse<T> {
    code: number;
    message: string;
    data: T;
  }
}

/**
 * 登录
 */
export async function loginApi(data: AuthApi.LoginParams) {
  // requestClient 的 defaultResponseInterceptor 已经提取了 data 字段
  // 所以 response 直接就是 LoginResult
  const response = await requestClient.post<AuthApi.LoginResult>(
    '/v1/auth/login',
    data,
  );
  // 返回 token 作为 accessToken
  return {
    accessToken: response.token,
    ...response,
  };
}

/**
 * 退出登录
 */
export async function logoutApi() {
  return requestClient.post('/v1/auth/logout');
}

/**
 * 获取用户权限码
 */
export async function getAccessCodesApi() {
  // requestClient 已经提取了 data 字段，直接返回
  return requestClient.get<string[]>('/v1/auth/perm-codes');
}

/**
 * 刷新 accessToken (当前实现不支持 refresh token，直接返回)
 */
export async function refreshTokenApi() {
  // 当前后端不支持 refresh token，返回空数据
  // 前端会在 token 过期时触发重新登录
  return { data: '', status: 200 };
}
