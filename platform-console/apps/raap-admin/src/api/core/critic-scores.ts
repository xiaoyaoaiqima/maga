/**
 * Critic Scores 分析 API
 */
import { requestClient } from '#/api/request';

export namespace CriticScoreApi {
  export type SourceType = 'debug' | 'eval_run' | 'job';

  export interface RecordItem {
    id: number;
    job_id: string;
    sub_job_id: string;
    content_id: string;
    source_type?: SourceType;
    dataset_code?: null | string;
    run_id?: null | number;
    test_case_id?: null | number;
    expert_config_code: string;
    expert_func: string;
    model_code?: null | string;
    provider_code?: null | string;
    score: number;
    passed: boolean;
    reason?: null | string;
    highlights?: null | string;
    problem_tags?: null | string[];
    problem_snippets?: null | string[];
    duration_ms?: null | number;
    trace_id?: null | string;
    version: number;
    create_time?: null | string;
  }

  export interface Summary {
    total_count: number;
    passed_count: number;
    pass_rate: number;
    avg_score: number;
    min_score: number;
    max_score: number;
    avg_duration_ms: number;
  }

  export interface TrendItem {
    date: string;
    total_count: number;
    passed_count: number;
    pass_rate: number;
    avg_score: number;
  }

  export interface DistributionItem {
    range: string;
    min: number;
    max: number;
    count: number;
  }

  export interface ModelComparisonItem {
    model_code: string;
    total_count: number;
    passed_count: number;
    pass_rate: number;
    avg_score: number;
    avg_duration_ms: number;
  }

  export interface DatasetItem {
    dataset_code: string;
    total: number;
  }

  export interface ProblemContextTopItem {
    key: string;
    count: number;
  }

  export interface ReasonWordCloudItem {
    word: string;
    count: number;
  }

  export interface DimensionHeatmapResponse {
    dimensions: string[];
    score_ranges: string[];
    data: number[][]; // [[dim_idx, range_idx, count], ...]
  }

  export interface ScatterDataItem {
    dimension: string;
    score: number;
    content_id: string;
  }
}

/** 专家类型 */
export type ExpertType = 'BAN' | 'CRITIC';

/** 通用筛选参数（job 场景专属字段） */
export interface CriticScoreFilterParams {
  activity_id?: number;
  dataset_code?: string;
  end_date?: string;
  expert_func?: string;
  /** 专家类型：BAN（合规封禁）/ CRITIC（质量评分） */
  expert_type?: ExpertType;
  job_id?: string;
  model_code?: string;
  source_type?: CriticScoreApi.SourceType;
  start_date?: string;
  tenant_id?: number;
}

export async function getCriticSummaryApi(params?: CriticScoreFilterParams) {
  return requestClient.get<CriticScoreApi.Summary>(
    '/v1/critic-scores/stats/summary',
    {
      params,
    },
  );
}

export async function getCriticTrendApi(
  params: CriticScoreFilterParams & { end_date: string; start_date: string },
) {
  return requestClient.get<CriticScoreApi.TrendItem[]>(
    '/v1/critic-scores/stats/trend',
    {
      params,
    },
  );
}

export async function getCriticDistributionApi(
  params?: CriticScoreFilterParams & { bucket_size?: number },
) {
  return requestClient.get<CriticScoreApi.DistributionItem[]>(
    '/v1/critic-scores/stats/score-distribution',
    { params },
  );
}

export async function getCriticModelComparisonApi(
  params?: CriticScoreFilterParams,
) {
  return requestClient.get<CriticScoreApi.ModelComparisonItem[]>(
    '/v1/critic-scores/stats/model-comparison',
    { params },
  );
}

export async function listCriticDatasetsApi(params?: {
  source_type?: CriticScoreApi.SourceType;
}) {
  return requestClient.get<CriticScoreApi.DatasetItem[]>(
    '/v1/critic-scores/datasets',
    {
      params,
    },
  );
}

export async function getCriticProblemContextTopApi(
  params?: CriticScoreFilterParams & { top_n?: number },
) {
  return requestClient.get<CriticScoreApi.ProblemContextTopItem[]>(
    '/v1/critic-scores/stats/problem-contexts/top',
    { params },
  );
}

export async function getCriticReasonWordCloudApi(
  params?: CriticScoreFilterParams & {
    min_len?: number;
    sample_limit?: number;
    top_n?: number;
  },
) {
  return requestClient.get<CriticScoreApi.ReasonWordCloudItem[]>(
    '/v1/critic-scores/stats/reasons/wordcloud',
    { params },
  );
}

export async function getCriticDimensionHeatmapApi(
  params?: Omit<CriticScoreFilterParams, 'expert_func'> & {
    bucket_size?: number;
  },
) {
  return requestClient.get<CriticScoreApi.DimensionHeatmapResponse>(
    '/v1/critic-scores/stats/dimension-heatmap',
    { params },
  );
}

export async function getCriticScatterDataApi(
  params?: Omit<CriticScoreFilterParams, 'expert_func'> & { limit?: number },
) {
  return requestClient.get<CriticScoreApi.ScatterDataItem[]>(
    '/v1/critic-scores/stats/scatter-data',
    { params },
  );
}

/** Expert Config 下拉选项 */
export interface ExpertConfigOptionItem {
  /** Expert 配置编码 */
  expert_config_code: string;
  /** Expert 配置名称 */
  expert_config_name: string;
  /** Expert 类型：CRITIC / BAN */
  expert_type: ExpertType;
  /** Expert 函数名 */
  expert_func: string;
}

/**
 * 获取 CRITIC/BAN 类型的 expert_config 列表（用于下拉选项）
 * @param params - 查询参数
 * @param params.expert_type - 专家类型：CRITIC / BAN，不传则返回全部
 * @param params.tenant_code - 租户编码
 */
export async function listExpertConfigOptionsApi(params?: {
  expert_type?: ExpertType;
  tenant_code?: string;
}) {
  return requestClient.get<ExpertConfigOptionItem[]>(
    '/v1/critic-scores/expert-configs',
    { params },
  );
}
