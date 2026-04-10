/**
 * 测试集 API
 */
import { requestClient } from '#/api/request';

// ==================== 类型定义 ====================

export namespace TestSetApi {
  /** 测试集类型 */
  export type TestSetType = 'image' | 'text';

  /** 测试集项 */
  export interface TestSetItem {
    id: number;
    code: string;
    name: string;
    type: TestSetType;
    description?: null | string;
    enabled: number;
    case_count: number;
    create_time?: string;
    update_time?: string;
  }

  /** 测试集列表响应 */
  export interface TestSetListResponse {
    items: TestSetItem[];
    total: number;
    page: number;
    page_size: number;
  }

  /** 测试集选项（下拉用） */
  export interface TestSetOption {
    id: number;
    code: string;
    name: string;
    type: TestSetType;
  }

  /** 创建测试集请求 */
  export interface CreateRequest {
    code?: string;
    name: string;
    type: TestSetType;
    description?: string;
    enabled?: number;
  }

  /** 更新测试集请求 */
  export interface UpdateRequest {
    name?: string;
    description?: string;
    enabled?: number;
  }

  /** 列表查询参数 */
  export interface ListParams {
    keyword?: string;
    type?: TestSetType;
    enabled?: boolean;
    page?: number;
    page_size?: number;
  }
}

// ==================== API 函数 ====================

/**
 * 获取测试集列表
 */
export async function listTestSetsApi(params?: TestSetApi.ListParams) {
  return requestClient.get<TestSetApi.TestSetListResponse>('/v1/test-sets', {
    params,
  });
}

/**
 * 获取测试集选项（下拉用）
 */
export async function listTestSetOptionsApi() {
  return requestClient.get<TestSetApi.TestSetOption[]>('/v1/test-sets/options');
}

/**
 * 获取单个测试集详情（按 ID）
 */
export async function getTestSetApi(id: number) {
  return requestClient.get<TestSetApi.TestSetItem>(`/v1/test-sets/${id}`);
}

/**
 * 获取单个测试集详情（按 code）
 */
export async function getTestSetByCodeApi(code: string) {
  return requestClient.get<TestSetApi.TestSetItem>(
    `/v1/test-sets/code/${code}`,
  );
}

/**
 * 创建测试集
 */
export async function createTestSetApi(data: TestSetApi.CreateRequest) {
  return requestClient.post<TestSetApi.TestSetItem>('/v1/test-sets', data);
}

/**
 * 更新测试集
 */
export async function updateTestSetApi(
  id: number,
  data: TestSetApi.UpdateRequest,
) {
  return requestClient.put<TestSetApi.TestSetItem>(`/v1/test-sets/${id}`, data);
}

/**
 * 删除测试集
 */
export async function deleteTestSetApi(id: number) {
  return requestClient.delete<{ deleted: boolean }>(`/v1/test-sets/${id}`);
}

/**
 * 切换启用状态
 */
export async function toggleTestSetEnabledApi(id: number) {
  return requestClient.put<TestSetApi.TestSetItem>(
    `/v1/test-sets/${id}/toggle`,
  );
}
