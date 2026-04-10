/**
 * Dashboard API - 仪表盘统计数据
 */
import { requestClient } from '#/api/request';

export namespace DashboardApi {
  /** 系统状态 */
  export interface SystemStatus {
    orchestrator: boolean;
    database: boolean;
    redis: boolean;
  }

  /** 统计数据 (旧版) */
  export interface Stats {
    total_plugins: number;
    total_expert_configs: number;
    total_jobs: number;
    deployed_jobs: number;
    running_jobs: number;
    today_executions: number;
    success_rate: number;
  }

  /** 最近执行记录 */
  export interface RecentExecution {
    id: string;
    job_name: string;
    job_id?: string;
    expert_config_code: string;
    status: 'failed' | 'running' | 'success';
    created_at: string;
    execution_time_ms?: number;
    error?: string;
  }

  /** Dashboard 完整响应 (旧版) */
  export interface DashboardResponse {
    stats: Stats;
    system_status: SystemStatus;
    recent_executions: RecentExecution[];
  }

  /** 概览统计 (Redash 指标) */
  export interface OverviewStats {
    total_jobs: number;
    total_contents: number;
    total_cost: number;
    adopt_rate: null | number;
  }

  /** 日趋势数据 */
  export interface DailyTrendItem {
    date: string;
    content_count: number;
    daily_cost: number;
    avg_latency_ms: null | number;
  }

  /** Dashboard 概览响应 (新版) */
  export interface DashboardOverviewResponse {
    filters: Record<string, any>;
    overview: OverviewStats;
    trend: DailyTrendItem[];
    last_updated_at?: string; // ✅ v1.5.3: 数据最后更新时间
  }

  /** 通用指标查询请求 */
  export interface MetricQueryRequest {
    metric_key: string;
    start_date: string;
    end_date: string;
    tenant_id?: number | number[];
    activity_id?: number | number[];
    agent_code?: string | string[];
  }

  /** 通用指标查询响应 */
  export interface MetricQueryResponse<T = any> {
    metric_key: string;
    metric_name: string;
    columns: string[];
    data: T[];
    rows_count: number;
    last_updated_at?: string; // ✅ v1.5.3: 数据最后更新时间（ISO 8601 格式）
  }

  /** 分页指标查询请求 */
  export interface MetricPaginatedQueryRequest {
    metric_key: string;
    start_date: string;
    end_date: string;
    tenant_id?: number | number[];
    activity_id?: number | number[];
    agent_code?: string | string[];
    page: number;
    page_size: number;
  }

  /** 分页指标查询响应 */
  export interface MetricPaginatedQueryResponse<T = any> {
    metric_key: string;
    metric_name: string;
    columns: string[];
    data: T[];
    pagination: {
      page: number;
      page_size: number;
      total: number;
      total_pages: number;
    };
  }

  /** 批量指标查询请求 */
  export interface MetricBatchQueryRequest {
    metric_keys: string[];
    start_date: string;
    end_date: string;
    tenant_id?: number | number[];
    activity_id?: number | number[];
    agent_code?: string | string[];
  }

  /** 批量指标查询响应 */
  export interface MetricBatchQueryResponse {
    filters: Record<string, any>;
    cached: boolean;
    results: Record<
      string,
      {
        data: any[];
        metric_key: string;
        metric_name: string;
        rows_count: number;
      }
    >;
    errors?: Record<string, string>;
    success_count: number;
    error_count: number;
  }

  /** Agent 成本分布数据 */
  export interface AgentCostItem {
    agent_code: string;
    agent_name: null | string;
    currency: string;
    total_cost: number;
    job_count: number;
    content_count: number;
  }

  /** Job 成本明细数据 */
  export interface JobCostItem {
    job_id: string;
    job_name: string;
    agent_code: string;
    agent_name: null | string;
    currency: string;
    total_cost: number;
    content_count: number;
    start_time: string;
    end_time: string;
  }

  /** 总成本汇总数据 */
  export interface TotalCostItem {
    currency: string;
    total_cost: number;
    agent_count: number;
    job_count: number;
    content_count: number;
  }

  /** 内容转化漏斗数据 */
  export interface ContentFunnelData {
    total_count: number;
    valid_count: number;
    online_count: number;
    used_count: number;
  }

  /** 漏斗阶段数据 */
  export interface FunnelStage {
    id: string;
    label: string;
    count: number;
    percentage: number;
    icon?: string;
    color: string;
    description?: string;
  }
}

/**
 * 获取仪表盘统计数据 (系统状态、最近执行)
 */
export async function getDashboardStatsApi(): Promise<DashboardApi.DashboardResponse> {
  return requestClient.get<DashboardApi.DashboardResponse>(
    '/v1/dashboard/stats',
  );
}

/**
 * 获取 Dashboard 概览数据 (业务指标、趋势)
 */
export async function getDashboardOverviewApi(params: {
  activity_id?: number | number[];
  agent_code?: string | string[];
  end_date: string;
  start_date: string;
  tenant_id?: number | number[];
}): Promise<DashboardApi.DashboardOverviewResponse> {
  // 转换单值为数组
  let tenantIds: number[] = [];
  if (Array.isArray(params.tenant_id)) {
    tenantIds = params.tenant_id;
  } else if (params.tenant_id) {
    tenantIds = [params.tenant_id];
  }

  let activityIds: number[] = [];
  if (Array.isArray(params.activity_id)) {
    activityIds = params.activity_id;
  } else if (params.activity_id) {
    activityIds = [params.activity_id];
  }

  let agentCodes: string[] = [];
  if (Array.isArray(params.agent_code)) {
    agentCodes = params.agent_code;
  } else if (params.agent_code) {
    agentCodes = [params.agent_code];
  }

  // 手动构建 Query String 以适配 FastAPI 的数组格式 (?key=1&key=2)
  // 避免 axios 默认的 key[]=value 格式导致后端无法识别
  const query = new URLSearchParams();
  query.append('start_date', params.start_date);
  query.append('end_date', params.end_date);

  tenantIds.forEach((id) => query.append('tenant_id', String(id)));
  activityIds.forEach((id) => query.append('activity_id', String(id)));
  agentCodes.forEach((code) => query.append('agent_code', code));

  // 注意：直接将 query string 拼接到 url 上
  const queryString = query.toString();
  const url = `/v1/data-query/metrics/dashboard?${queryString}`;

  return requestClient.get<DashboardApi.DashboardOverviewResponse>(url);
}

/**
 * 直接查询指标数据
 */
export async function queryMetricApi<T = any>(
  data: DashboardApi.MetricQueryRequest,
): Promise<DashboardApi.MetricQueryResponse<T>> {
  return requestClient.post<DashboardApi.MetricQueryResponse<T>>(
    '/v1/data-query/metrics/query',
    data,
  );
}

/**
 * 分页查询指标数据
 */
export async function queryMetricPaginatedApi<T = any>(
  data: DashboardApi.MetricPaginatedQueryRequest,
): Promise<DashboardApi.MetricPaginatedQueryResponse<T>> {
  return requestClient.post<DashboardApi.MetricPaginatedQueryResponse<T>>(
    '/v1/data-query/metrics/query-paginated',
    data,
  );
}

/**
 * 查询内容转化漏斗数据
 */
export async function queryContentFunnelApi(params: {
  activity_id?: number | number[];
  agent_code?: string | string[];
  end_date: string;
  start_date: string;
  tenant_id?: number | number[];
}): Promise<DashboardApi.MetricQueryResponse<DashboardApi.ContentFunnelData>> {
  return requestClient.post<
    DashboardApi.MetricQueryResponse<DashboardApi.ContentFunnelData>
  >('/v1/data-query/metrics/query', {
    metric_key: 'content_funnel',
    start_date: params.start_date,
    end_date: params.end_date,
    tenant_id: params.tenant_id,
    activity_id: params.activity_id,
    agent_code: params.agent_code,
  });
}

/**
 * 批量查询 Dashboard 指标（优化版）
 *
 * 性能优化：
 * - 1 个请求替代 16+ 个独立请求
 * - 支持缓存（默认 30 秒）
 * - 并行查询所有指标
 *
 * @example
 * ```ts
 * const data = await queryDashboardSummaryApi({
 *   metric_keys: ['cost_total_by_currency', 'generation_agent_stats', ...],
 *   start_date: '2024-01-01',
 *   end_date: '2024-12-31',
 *   tenant_id: [1],
 * });
 * ```
 */
export async function queryDashboardSummaryApi(
  data: DashboardApi.MetricBatchQueryRequest,
  options?: {
    cache_ttl?: number;
    use_cache?: boolean;
  },
): Promise<DashboardApi.MetricBatchQueryResponse> {
  const params = new URLSearchParams();
  if (options?.use_cache !== undefined) {
    params.append('use_cache', String(options.use_cache));
  }
  if (options?.cache_ttl !== undefined) {
    params.append('cache_ttl', String(options.cache_ttl));
  }

  const queryString = params.toString();
  const url = queryString
    ? `/v1/data-query/metrics/dashboard-summary?${queryString}`
    : '/v1/data-query/metrics/dashboard-summary';

  return requestClient.post<DashboardApi.MetricBatchQueryResponse>(url, data);
}
