import type { UserInfo } from '@vben/types';

import { preferences } from '@vben/preferences';

import { requestClient } from '#/api/request';

export namespace UserApi {
  /** 用户信息响应 */
  export interface UserInfoResponse {
    id: string;
    username: string;
    name?: string;
    email?: string;
    phone?: string;
    avatar?: string;
    dept_id?: string;
    status: number;
    roles: string[];
    permissions: string[];
  }

  /** API 响应包装 */
  export interface ApiResponse<T> {
    code: number;
    message: string;
    data: T;
  }
}

/**
 * 获取用户信息
 */
export async function getUserInfoApi() {
  // requestClient 的 defaultResponseInterceptor 已经提取了 data 字段
  const response =
    await requestClient.get<UserApi.UserInfoResponse>('/v1/auth/userinfo');

  // 转换为 UserInfo 格式
  const userInfo: UserInfo = {
    userId: response.id,
    username: response.username,
    realName: response.name || response.username,
    avatar: response.avatar || '',
    email: response.email || '',
    phone: response.phone || '',
    roles: response.roles || [],
    token: '',
    // 其他可能需要的字段
    desc: '',
    homePath: preferences.app.defaultHomePath,
  };

  return userInfo;
}

/**
 * 更新个人信息
 */
export async function updateUserProfileApi(data: {
  avatar?: string;
  email?: string;
  name?: string;
  phone?: string;
}) {
  return requestClient.put('/v1/auth/profile', data);
}

/**
 * 修改密码
 */
export async function updateUserPasswordApi(data: any) {
  return requestClient.put('/v1/auth/password', data);
}
