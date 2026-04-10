import { requestClient } from '#/api/request';

export namespace TraceApi {
  /** 追踪状态 */
  export type TraceStatus =
    | 'failed'
    | 'pending'
    | 'running'
    | 'success'
    | 'timeout';

  /** 追踪阶段 */
  export type TraceStage =
    | 'ag_ban'
    | 'ag_critic'
    | 'debug'
    | 'expert_call'
    | 'ge_generation'
    | 'llm_call'
    | 'plugin_render'
    | 'prompt_render'
    // RLHF 阶段
    | 'rlhf_adopt'
    | 'rlhf_edit'
    | 'rlhf_like'
    | 'rlhf_score'
    | 'rlhf_tag';

  /** 追踪记录 */
  export interface TraceSpan {
    id: number;
    job_id: string;
    sub_job_id: string;
    content_id?: string;
    trace_id: string;
    span_id: string;
    parent_span_id?: string;
    stage: TraceStage;
    expert_config_code?: string;
    expert_type?: string;
    service_app: string;
    service_method: string;
    status: TraceStatus;
    error_type?: string;
    error_message?: string;
    start_time: string;
    end_time?: string;
    duration_ms?: number;
    queue_time_ms?: number;
    model_time_ms?: number;
    render_time_ms?: number;
    model_code?: string;
    model_provider?: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    experiment_id?: string;
    experiment_group?: string;
    experiment_variant?: string;
    experiment_source?: string;
    result_summary?: Record<string, any>;
    plugin_config_snapshot?: Record<string, any>;
    rendered_prompt?: string;
    caller_service?: string;
    caller_user_id?: string;
    client_ip?: string;
    source_log_id?: string;
    source_log_table?: string;
    // 成本信息
    input_cost?: number;
    output_cost?: number;
    total_cost?: number;
    currency?: string;
    // RLHF 扩展字段
    rlhf_feedback_id?: number;
    reviewer_id?: string;
    reviewer_name?: string;
    created_at: string;
  }

  /** 追踪列表查询参数 */
  export interface TraceListQuery {
    page?: number;
    page_size?: number;
    job_id?: string;
    sub_job_id?: string;
    content_id?: string;
    trace_id?: string;
    stage?: string;
    status?: string;
    expert_config_code?: string;
    experiment_id?: string;
    start_date?: string;
    end_date?: string;
  }

  /** 追踪列表响应 */
  export interface TraceListResponse {
    total: number;
    page: number;
    page_size: number;
    items: TraceSpan[];
  }

  /** 追踪详情响应 */
  export interface TraceDetailResponse {
    trace: TraceSpan;
    spans: TraceSpan[];
  }

  /** 追踪统计查询参数 */
  export interface TraceStatsQuery {
    start_date: string;
    end_date: string;
    stage?: string;
    expert_config_code?: string;
    experiment_id?: string;
    group_by?: 'date' | 'experiment' | 'expert' | 'stage';
  }

  /** 追踪统计响应 */
  export interface TraceStatsResponse {
    summary: {
      avg_duration_ms: number;
      failed_count: number;
      success_count: number;
      success_rate: number;
      timeout_count: number;
      total_count: number;
      total_input_tokens: number;
      total_output_tokens: number;
    };
    groups: Array<{
      avg_duration_ms: number;
      failed_count: number;
      group_key: string;
      success_count: number;
      total_count: number;
      total_tokens: number;
    }>;
  }

  /** A/B 实验 */
  export interface ABExperiment {
    id: number;
    experiment_id: string;
    experiment_name: string;
    description?: string;
    target_type: string;
    target_code?: string;
    groups: Array<{
      group: string;
      variant: string;
      weight: number;
    }>;
    traffic_ratio: number;
    status: 'completed' | 'draft' | 'paused' | 'running';
    start_time?: string;
    end_time?: string;
    created_by?: string;
    created_at: string;
    updated_at: string;
  }

  /** 创建 A/B 实验参数 */
  export interface ABExperimentCreate {
    experiment_name: string;
    description?: string;
    target_type: string;
    target_code?: string;
    groups: Array<{
      group: string;
      variant: string;
      weight: number;
    }>;
    traffic_ratio?: number;
  }

  /** 更新 A/B 实验参数 */
  export interface ABExperimentUpdate {
    experiment_name?: string;
    description?: string;
    groups?: Array<{
      group: string;
      variant: string;
      weight: number;
    }>;
    traffic_ratio?: number;
  }

  /** A/B 实验列表响应 */
  export interface ABExperimentListResponse {
    total: number;
    items: ABExperiment[];
  }

  /** Expert 执行结果摘要 */
  export interface ExpertResultSummary {
    id: number;
    expert_config_code: string;
    expert_config_name?: string;
    expert_func?: string;
    expert_type?: string;
    model_code?: string;
    business_type?: string;
    plugin_config_snapshot?: Array<Record<string, any>>;
    prompt?: string;
    business_result?: Record<string, any>;
    status?: string;
    error_message?: string;
    create_time?: string;
  }

  /** 生成背景信息 */
  export interface GenerationContextResponse {
    content_id: string;
    job_id: string;
    background: {
      activity_id?: number;
      agent_code?: string;
      brand_id?: number;
      campaign_id?: number;
      extra_context?: Record<string, any>;
      job_description?: string;
      job_name: string;
      platform_code?: string;
      tenant_id?: number;
    };
    generation?: {
      currency?: string;
      duration_ms: number;
      expert_config_code?: string;
      input_tokens: number;
      model_code?: string;
      output_tokens: number;
      rendered_prompt?: string;
      result_summary?: Record<string, any>;
      total_cost: number;
      total_tokens: number;
    };
    spans: TraceSpan[];
    expert_results: ExpertResultSummary[];
  }
}

/**
 * 获取追踪列表
 */
export async function getTraceListApi(params?: TraceApi.TraceListQuery) {
  return requestClient.get<TraceApi.TraceListResponse>('/v1/traces', {
    params,
  });
}

/**
 * 获取追踪详情
 */
export async function getTraceDetailApi(traceId: string) {
  return requestClient.get<TraceApi.TraceDetailResponse>(
    `/v1/traces/${traceId}`,
  );
}

/**
 * 根据 ID 获取追踪记录
 */
export async function getTraceByIdApi(id: number) {
  return requestClient.get<TraceApi.TraceSpan>(`/v1/traces/by-id/${id}`);
}

/**
 * 获取追踪统计
 */
export async function getTraceStatsApi(params: TraceApi.TraceStatsQuery) {
  return requestClient.get<TraceApi.TraceStatsResponse>('/v1/traces/stats', {
    params,
  });
}

/**
 * 获取 A/B 实验列表
 */
export async function getExperimentListApi(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  target_type?: string;
}) {
  return requestClient.get<TraceApi.ABExperimentListResponse>(
    '/v1/traces/experiments',
    { params },
  );
}

/**
 * 创建 A/B 实验
 */
export async function createExperimentApi(data: TraceApi.ABExperimentCreate) {
  return requestClient.post<TraceApi.ABExperiment>(
    '/v1/traces/experiments',
    data,
  );
}

/**
 * 获取 A/B 实验详情
 */
export async function getExperimentApi(experimentId: string) {
  return requestClient.get<TraceApi.ABExperiment>(
    `/v1/traces/experiments/${experimentId}`,
  );
}

/**
 * 更新 A/B 实验
 */
export async function updateExperimentApi(
  experimentId: string,
  data: TraceApi.ABExperimentUpdate,
) {
  return requestClient.put<TraceApi.ABExperiment>(
    `/v1/traces/experiments/${experimentId}`,
    data,
  );
}

/**
 * 启动 A/B 实验
 */
export async function startExperimentApi(experimentId: string) {
  return requestClient.post<TraceApi.ABExperiment>(
    `/v1/traces/experiments/${experimentId}/start`,
  );
}

/**
 * 停止 A/B 实验
 */
export async function stopExperimentApi(experimentId: string) {
  return requestClient.post<TraceApi.ABExperiment>(
    `/v1/traces/experiments/${experimentId}/stop`,
  );
}

/**
 * 获取文章生成的背景信息（溯源）
 */
export async function getGenerationContextApi(contentId: string) {
  return requestClient.get<TraceApi.GenerationContextResponse>(
    `/v1/traces/generation-context/${contentId}`,
  );
}
