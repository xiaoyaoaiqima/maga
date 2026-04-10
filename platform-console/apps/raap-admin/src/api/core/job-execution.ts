/**
 * Job 执行追踪相关 API
 */
import { requestClient } from '#/api/request';

/**
 * Job 执行统计信息
 */
export interface JobExecutionStats {
  job_id: string;
  job_name?: string;
  status?: string;
  // 统计数据
  total_sub_jobs: number;
  running_sub_jobs: number;
  completed_sub_jobs: number;
  failed_sub_jobs: number;
  total_contents: number;
  valid_contents: number;
  invalid_contents: number;
  test_contents: number;
  // 目标与进度
  target_article_count?: number;
  progress_percentage?: number;
  // 时间信息
  first_sub_job_time?: string;
  last_sub_job_time?: string;
}

/**
 * SubJob 详情
 */
export interface SubJobDetail {
  id: number;
  job_id: string;
  sub_job_id: string;
  content_id: string;
  expert_list: string[];
  expert_complete_list?: string[];
  status: string;
  error_message?: string;
  create_time?: string;
  update_time?: string;
  // 关联的 content 信息
  content_title?: string;
  content_is_valid?: number;
  content_is_test?: number;
}

/**
 * 单个专家的评分详情
 */
export interface CriticScoreItem {
  /** 专家函数名 */
  expert_func: string;
  /** 专家类型：BAN/CRITIC */
  expert_type: string;
  /** 评分 0-100 */
  score: number;
  /** 是否通过 */
  passed: boolean;
  /** 评分理由 */
  reason?: string;
}

/**
 * Critic 评分汇总
 */
export interface ContentCriticSummary {
  /** Critic 专家数量 */
  total_critics: number;
  /** 通过数量 */
  passed_count: number;
  /** 不通过数量 */
  failed_count: number;
  /** 平均分 */
  avg_score: null | number;
  /** 最低分 */
  min_score: null | number;
  /** 是否有合规问题（BAN 类专家不通过） */
  has_ban_issue: boolean;
  /** 问题总数 */
  problem_count: number;
  /** 各专家评分详情 */
  scores: CriticScoreItem[];
}

/**
 * Content 详情
 */
export interface ContentDetail {
  id: number;
  job_id: string;
  sub_job_id: string;
  content_id: string;
  agent_code?: string;
  prompt?: string;
  /**
   * 兼容两种结构：
   * - 旧：string[]
   * - 新：Record<key, value>
   */
  context_list?: Record<string, unknown> | string[];
  title?: string;
  content?: string;
  is_valid: number;
  is_test_case: number;
  online_status?: 'OFFLINE' | 'ONLINE';
  is_locked: number;
  is_used: number;
  create_time?: string;
  update_time?: string;
  // SubJob 状态
  sub_job_status?: string;
  // Critic 评分汇总
  critic_summary?: ContentCriticSummary;
}

/**
 * Expert 业务结果详情
 */
export interface ExpertBusinessResultDetail {
  id: number;
  job_id: string;
  sub_job_id: string;
  content_id: string;
  expert_task_id?: number;
  expert_config_code: string;
  expert_config_name?: string;
  /** 专家函数名（CriticIllegal 等） */
  expert_func?: string;
  /** 专家类型：BAN/CRITIC */
  expert_type?: string;
  model_code?: string;
  business_type?: string;
  plugin_config_snapshot?: unknown[];
  prompt?: string;
  business_result?: Record<string, unknown>;
  status?: string;
  error_message?: string;
  create_time?: string;
}

/**
 * Job 执行详情
 */
export interface JobExecutionDetail {
  stats: JobExecutionStats;
  sub_jobs: SubJobDetail[];
  contents: ContentDetail[];
}

/**
 * Job 执行统计列表响应
 */
export interface JobExecutionStatsListResponse {
  total: number;
  items: JobExecutionStats[];
}

/**
 * 获取所有 Job 执行统计
 */
export async function getAllJobExecutionStatsApi(params?: {
  page?: number;
  page_size?: number;
}) {
  return requestClient.get<JobExecutionStatsListResponse>(
    '/v1/job-execution/stats',
    {
      params,
    },
  );
}

/**
 * 获取指定 Job 执行统计
 */
export async function getJobExecutionStatsApi(jobId: string) {
  return requestClient.get<JobExecutionStats>(
    `/v1/job-execution/${jobId}/stats`,
  );
}

/**
 * 获取指定 Job 执行详情
 */
export async function getJobExecutionDetailApi(
  jobId: string,
  params?: { include_test?: boolean },
) {
  return requestClient.get<JobExecutionDetail>(
    `/v1/job-execution/${jobId}/detail`,
    { params },
  );
}

/**
 * 获取指定 Job 的 SubJob 列表
 */
export async function getJobSubJobsApi(
  jobId: string,
  params?: {
    is_test_case?: number;
    is_valid?: number;
    limit?: number;
    skip?: number;
    status?: string;
  },
) {
  return requestClient.get<SubJobDetail[]>(
    `/v1/job-execution/${jobId}/sub-jobs`,
    {
      params,
    },
  );
}

/**
 * 获取指定 Job 的 Content 列表
 */
export async function getJobContentsApi(
  jobId: string,
  params?: {
    is_test_case?: number;
    is_valid?: number;
    limit?: number;
    skip?: number;
  },
) {
  return requestClient.get<ContentDetail[]>(
    `/v1/job-execution/${jobId}/contents`,
    {
      params,
    },
  );
}

/**
 * 获取指定 Job 的 Expert 业务结果列表
 */
export async function getJobBusinessResultsApi(
  jobId: string,
  params?: {
    content_id?: string;
    expert_config_code?: string;
    limit?: number;
    skip?: number;
  },
) {
  return requestClient.get<ExpertBusinessResultDetail[]>(
    `/v1/job-execution/${jobId}/business-results`,
    { params },
  );
}
