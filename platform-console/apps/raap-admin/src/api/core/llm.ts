import { requestClient } from '#/api/request';

export namespace LLMApi {
  /** Provider 类型 */
  export type ProviderType =
    | 'anthropic'
    | 'azure_openai'
    | 'custom'
    | 'openai_compatible';

  /** 熔断状态 */
  export type CircuitState = 'closed' | 'half_open' | 'open';

  /** LLM Provider 配置 */
  export interface ProviderConfig {
    id: number;
    provider_code: string;
    provider_name: string;
    provider_type: ProviderType;
    base_url: string;
    api_key_masked: string;
    default_model?: string;
    available_models?: string[];
    default_params?: Record<string, any>;
    rate_limit?: number;
    timeout: number;
    priority: number;
    enabled: boolean;
    description?: string;
    create_time: string;
    update_time: string;
  }

  /** 创建 Provider 参数 */
  export interface ProviderCreate {
    provider_code: string;
    provider_name: string;
    provider_type: ProviderType;
    base_url: string;
    api_key: string;
    default_model?: string;
    available_models?: string[];
    default_params?: Record<string, any>;
    rate_limit?: number;
    timeout?: number;
    priority?: number;
    enabled?: boolean;
    description?: string;
  }

  /** 更新 Provider 参数 */
  export interface ProviderUpdate {
    provider_name?: string;
    provider_type?: ProviderType;
    base_url?: string;
    api_key?: string;
    default_model?: string;
    available_models?: string[];
    default_params?: Record<string, any>;
    rate_limit?: number;
    timeout?: number;
    priority?: number;
    enabled?: boolean;
    description?: string;
  }

  /** Provider 列表响应 */
  export interface ProviderListResponse {
    items: ProviderConfig[];
    total: number;
  }

  /** 模型路由 */
  export interface ModelRoute {
    id: number;
    model_code: string;
    model_name: string;
    provider_code: string;
    provider_model: string;
    priority: number;
    enabled: boolean;
    max_context_length?: number;
    features?: Record<string, boolean>;
    cost_per_1k_input?: string;
    cost_per_1k_output?: string;
    currency: string;
    timeout_seconds?: number;
    description?: string;
    create_time: string;
    update_time: string;
  }

  /** 创建模型路由参数 */
  export interface ModelRouteCreate {
    model_code: string;
    model_name: string;
    provider_code: string;
    provider_model: string;
    priority?: number;
    enabled?: boolean;
    max_context_length?: number;
    features?: Record<string, boolean>;
    cost_per_1k_input?: number;
    cost_per_1k_output?: number;
    currency?: string;
    timeout_seconds?: number;
    description?: string;
  }

  /** 更新模型路由参数 */
  export interface ModelRouteUpdate {
    model_name?: string;
    provider_model?: string;
    priority?: number;
    enabled?: boolean;
    max_context_length?: number;
    features?: Record<string, boolean>;
    cost_per_1k_input?: number;
    cost_per_1k_output?: number;
    currency?: string;
    timeout_seconds?: number;
    description?: string;
  }

  /** 模型路由列表响应 */
  export interface ModelRouteListResponse {
    items: ModelRoute[];
    total: number;
  }

  /** 可用模型（聚合） */
  export interface AvailableModel {
    model_code: string;
    model_name: string;
    providers: string[];
    max_context_length?: number;
    features?: Record<string, boolean>;
    cost_per_1k_input?: number;
    cost_per_1k_output?: number;
    currency: string;
  }

  /** 熔断状态 */
  export interface CircuitBreaker {
    id: number;
    provider_code: string;
    state: CircuitState;
    failure_count: number;
    success_count: number;
    last_failure_time?: string;
    last_success_time?: string;
    opened_at?: string;
    half_open_at?: string;
    create_time: string;
    update_time: string;
  }

  /** 连接测试响应 */
  export interface ConnectionTestResponse {
    success: boolean;
    latency_ms?: number;
    error_message?: string;
    model_tested?: string;
  }

  /** 远程模型信息 */
  export interface RemoteModelInfo {
    model_id: string;
    model_name: string;
    description?: string;
    model_type: string;
    features: string[];
    input_modalities: string[];
    max_output?: number;
    context_length?: number;
    cost_per_1k_input?: number;
    cost_per_1k_output?: number;
    currency: string;
  }

  /** 远程模型列表响应 */
  export interface RemoteModelListResponse {
    items: RemoteModelInfo[];
    total: number;
    provider_code: string;
  }

  /** 同步模型请求 */
  export interface SyncModelsRequest {
    model_ids?: string[];
    overwrite?: boolean;
  }

  /** 同步模型响应 */
  export interface SyncModelsResponse {
    synced_count: number;
    skipped_count: number;
    failed_count: number;
    details: Array<{
      model_id: string;
      reason?: string;
      status: 'created' | 'failed' | 'skipped' | 'updated';
    }>;
  }

  /** Provider 统计 */
  export interface ProviderStats {
    provider_code: string;
    total_calls: number;
    total_tokens: number;
    total_cost: number;
    currency: string;
    avg_latency_ms: number;
    success_rate: number;
  }

  /** 模型统计 */
  export interface ModelStats {
    model_code: string;
    total_calls: number;
    total_tokens: number;
    total_cost: number;
    currency: string;
    avg_latency_ms: number;
  }

  /** 日趋势统计 */
  export interface DailyStats {
    date: string;
    total_calls: number;
    total_tokens: number;
    total_cost: number;
    currency: string;
  }
}

// ==================== Provider API ====================

/**
 * 获取 Provider 列表
 */
export async function getProviderListApi(params?: {
  enabled?: boolean;
  limit?: number;
  provider_type?: string;
  skip?: number;
}) {
  return requestClient.get<LLMApi.ProviderListResponse>('/v1/llm-providers', {
    params,
  });
}

/**
 * 获取 Provider 详情
 */
export async function getProviderApi(code: string) {
  return requestClient.get<LLMApi.ProviderConfig>(`/v1/llm-providers/${code}`);
}

/**
 * 创建 Provider
 */
export async function createProviderApi(data: LLMApi.ProviderCreate) {
  return requestClient.post<LLMApi.ProviderConfig>('/v1/llm-providers', data);
}

/**
 * 更新 Provider
 */
export async function updateProviderApi(
  code: string,
  data: LLMApi.ProviderUpdate,
) {
  return requestClient.put<LLMApi.ProviderConfig>(
    `/v1/llm-providers/${code}`,
    data,
  );
}

/**
 * 删除 Provider
 */
export async function deleteProviderApi(code: string) {
  return requestClient.delete(`/v1/llm-providers/${code}`);
}

/**
 * 启用 Provider
 */
export async function enableProviderApi(code: string) {
  return requestClient.post(`/v1/llm-providers/${code}/enable`);
}

/**
 * 禁用 Provider
 */
export async function disableProviderApi(code: string) {
  return requestClient.post(`/v1/llm-providers/${code}/disable`);
}

/**
 * 测试 Provider 连接
 */
export async function testProviderApi(code: string, model?: string) {
  return requestClient.post<LLMApi.ConnectionTestResponse>(
    `/v1/llm-providers/${code}/test`,
    { model },
  );
}

/**
 * 获取 Provider 的远程可用模型列表
 */
export async function getRemoteModelsApi(code: string, modelType?: string) {
  return requestClient.get<LLMApi.RemoteModelListResponse>(
    `/v1/llm-providers/${code}/remote-models`,
    { params: { model_type: modelType } },
  );
}

/**
 * 获取远程模型列表（用于新增 Provider 时测试）
 */
export async function fetchRemoteModelsApi(data: {
  api_key: string;
  base_url: string;
  model_type?: string;
  provider_type?: string;
}) {
  return requestClient.post<LLMApi.RemoteModelListResponse>(
    '/v1/llm-providers/fetch-remote-models',
    data,
    {
      timeout: 35_000, // 35 秒超时（后端默认 30 秒，多 5 秒缓冲）
    },
  );
}

/**
 * 同步远程模型到本地路由表
 */
export async function syncModelsApi(
  code: string,
  data?: LLMApi.SyncModelsRequest,
) {
  return requestClient.post<LLMApi.SyncModelsResponse>(
    `/v1/llm-providers/${code}/sync-models`,
    data ?? {},
  );
}

/**
 * 从 Provider 已配置的可用模型生成本地模型路由
 */
export async function syncConfiguredModelsApi(
  code: string,
  data?: LLMApi.SyncModelsRequest,
) {
  return requestClient.post<LLMApi.SyncModelsResponse>(
    `/v1/llm-providers/${code}/sync-configured-models`,
    data ?? {},
  );
}

// ==================== Model Route API ====================

/**
 * 获取模型路由列表
 */
export async function getRouteListApi(params?: {
  enabled?: boolean;
  limit?: number;
  model_code?: string;
  provider_code?: string;
  skip?: number;
}) {
  return requestClient.get<LLMApi.ModelRouteListResponse>(
    '/v1/llm-providers/routes',
    { params },
  );
}

/**
 * 创建模型路由
 */
export async function createRouteApi(data: LLMApi.ModelRouteCreate) {
  return requestClient.post<LLMApi.ModelRoute>(
    '/v1/llm-providers/routes',
    data,
  );
}

/**
 * 更新模型路由
 */
export async function updateRouteApi(
  id: number,
  data: LLMApi.ModelRouteUpdate,
) {
  return requestClient.put<LLMApi.ModelRoute>(
    `/v1/llm-providers/routes/${id}`,
    data,
  );
}

/**
 * 删除模型路由
 */
export async function deleteRouteApi(id: number) {
  return requestClient.delete(`/v1/llm-providers/routes/${id}`);
}

/**
 * 获取可用模型列表（聚合）
 */
export async function getAvailableModelsApi() {
  return requestClient.get<{ items: LLMApi.AvailableModel[] }>(
    '/v1/llm-providers/models',
  );
}

// ==================== Circuit Breaker API ====================

/**
 * 获取熔断状态列表
 */
export async function getCircuitBreakersApi() {
  return requestClient.get<{ items: LLMApi.CircuitBreaker[] }>(
    '/v1/llm-providers/circuit-breakers',
  );
}

/**
 * 重置熔断器
 */
export async function resetCircuitBreakerApi(code: string) {
  return requestClient.post(`/v1/llm-providers/circuit-breakers/${code}/reset`);
}

/**
 * 强制打开熔断器
 */
export async function forceOpenCircuitBreakerApi(code: string) {
  return requestClient.post(
    `/v1/llm-providers/circuit-breakers/${code}/force-open`,
  );
}

// ==================== Stats API ====================

/**
 * 获取 Provider 统计
 */
export async function getProviderStatsApi(params?: {
  end_date?: string;
  start_date?: string;
}) {
  return requestClient.get<LLMApi.ProviderStats[]>(
    '/v1/llm-providers/stats/provider',
    { params },
  );
}

/**
 * 获取模型统计
 */
export async function getModelStatsApi(params?: {
  end_date?: string;
  start_date?: string;
}) {
  return requestClient.get<LLMApi.ModelStats[]>(
    '/v1/llm-providers/stats/model',
    { params },
  );
}

/**
 * 获取日趋势统计
 */
export async function getDailyStatsApi(params?: {
  end_date?: string;
  model_code?: string;
  provider_code?: string;
  start_date?: string;
}) {
  return requestClient.get<LLMApi.DailyStats[]>(
    '/v1/llm-providers/stats/daily',
    { params },
  );
}
