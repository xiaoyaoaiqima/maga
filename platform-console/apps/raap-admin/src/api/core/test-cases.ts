/**
 * 测试用例 API
 */
import { requestClient } from '#/api/request';

// ==================== 类型定义 ====================

export namespace TestCaseApi {
  /** 测试用例项 */
  export interface TestCaseItem {
    id: number;
    test_set_code: string;
    title?: null | string;
    content?: null | string;
    image_url?: null | string;
    enabled: number;
    create_time?: string;
    update_time?: string;
  }

  /** 测试用例列表响应 */
  export interface TestCaseListResponse {
    items: TestCaseItem[];
    total: number;
    page: number;
    page_size: number;
  }

  /** 创建测试用例请求 */
  export interface CreateRequest {
    test_set_code: string;
    title?: string;
    content?: string;
    image_url?: string;
    enabled?: number;
  }

  /** 更新测试用例请求 */
  export interface UpdateRequest {
    title?: string;
    content?: string;
    image_url?: string;
    enabled?: number;
  }

  /** 批量导入项 */
  export interface ImportItem {
    title?: string;
    content?: string;
    image_url?: string;
  }

  /** 批量导入请求 */
  export interface ImportRequest {
    test_set_code: string;
    items: ImportItem[];
    enabled?: number;
  }

  /** 批量导入响应 */
  export interface ImportResponse {
    success_count: number;
    skip_count: number;
    total: number;
  }

  /** 列表查询参数 */
  export interface ListParams {
    test_set_code: string;
    keyword?: string;
    enabled?: boolean;
    page?: number;
    page_size?: number;
  }
}

// ==================== API 函数 ====================

/**
 * 获取测试用例列表
 */
export async function listTestCasesApi(params: TestCaseApi.ListParams) {
  return requestClient.get<TestCaseApi.TestCaseListResponse>('/v1/test-cases', {
    params,
  });
}

/**
 * 获取单个测试用例
 */
export async function getTestCaseApi(id: number) {
  return requestClient.get<TestCaseApi.TestCaseItem>(`/v1/test-cases/${id}`);
}

/**
 * 创建测试用例
 */
export async function createTestCaseApi(data: TestCaseApi.CreateRequest) {
  return requestClient.post<TestCaseApi.TestCaseItem>('/v1/test-cases', data);
}

/**
 * 更新测试用例
 */
export async function updateTestCaseApi(
  id: number,
  data: TestCaseApi.UpdateRequest,
) {
  return requestClient.put<TestCaseApi.TestCaseItem>(
    `/v1/test-cases/${id}`,
    data,
  );
}

/**
 * 删除测试用例
 */
export async function deleteTestCaseApi(id: number) {
  return requestClient.delete<{ deleted: boolean }>(`/v1/test-cases/${id}`);
}

/**
 * 切换启用状态
 */
export async function toggleTestCaseEnabledApi(id: number) {
  return requestClient.put<TestCaseApi.TestCaseItem>(
    `/v1/test-cases/${id}/toggle`,
  );
}

/**
 * 批量导入测试用例
 */
export async function importTestCasesApi(data: TestCaseApi.ImportRequest) {
  return requestClient.post<TestCaseApi.ImportResponse>(
    '/v1/test-cases/import',
    data,
  );
}
